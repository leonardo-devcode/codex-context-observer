"""Partial local text token counts. Never returns prompt or transcript text."""
import os
from pathlib import Path

os.environ.setdefault('TIKTOKEN_CACHE_DIR', str(Path(__file__).resolve().parent / 'tokenizer-cache'))
try:
    import tiktoken
    ENCODING = tiktoken.get_encoding('o200k_base')
except (ImportError, OSError, ValueError):
    ENCODING = None

def text_tokens(text):
    if ENCODING is None:
        return None
    return len(ENCODING.encode(text, disallowed_special=()))

def visible_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(filter(None, (visible_text(v) for v in value)))
    if isinstance(value, dict):
        # Never tokenize base64 images, encrypted reasoning or arbitrary metadata.
        if isinstance(value.get('text'), str):
            return value['text']
        if 'content' in value:
            return visible_text(value['content'])
    return ''

class Composition:
    def __init__(self):
        self.counts = {}
        self.records = {}
        self.multimodal = 0
        self.compacted = False
        self.replacement_available = False
        self.encrypted = 0

    def set(self, key, text):
        self.counts[key] = text_tokens(text)
        self.records[key] = 1

    def add(self, key, text):
        count = text_tokens(text)
        self.counts[key] = (self.counts.get(key) or 0) + count if count is not None else None
        self.records[key] = self.records.get(key, 0) + 1

    def consume(self, kind, p):
        if kind == 'session_meta':
            self.set('base', p.get('base_instructions', {}).get('text', ''))
        elif kind == 'world_state':
            state = p.get('state', {})
            if 'host_skills' in state:
                self.set('skills', state['host_skills'].get('body', ''))
            if isinstance(state.get('tools'), dict):
                self.set('mcp', '\n'.join(k + ': ' + v for k, v in state['tools'].items() if isinstance(v,str)))
            if 'agents_md' in state:
                self.set('agents', state['agents_md'].get('text', ''))
        elif kind == 'response_item':
            item = p.get('type')
            if item == 'compaction' and p.get('encrypted_content'):
                self.encrypted += 1
            if item == 'message':
                role = p.get('role')
                key = 'messages' if role in ('user', 'assistant') else 'developer' if role == 'developer' else None
                if key:
                    self.add(key, visible_text(p.get('content')))
                for block in p.get('content', []):
                    if isinstance(block,dict) and block.get('type') in ('input_image', 'image', 'input_audio'):
                        self.multimodal += 1
            elif item in ('function_call','custom_tool_call'):
                self.add('tool_io', visible_text(p.get('arguments', p.get('input',''))))
            elif item in ('function_call_output','custom_tool_call_output'):
                self.add('tool_io', visible_text(p.get('output','')))

    def rebuild_after_compaction(self, payload):
        # Discard old history. Only count readable replacement items and later
        # records; never decode or estimate encrypted compaction content.
        self.counts = {}
        self.records = {}
        self.multimodal = 0
        self.encrypted = 0
        self.compacted = True
        history = payload.get('replacement_history')
        self.replacement_available = isinstance(history, list)
        if self.replacement_available:
            for item in history:
                if isinstance(item, dict):
                    self.consume('response_item', item)

    def invalidate_compaction(self):
        self.rebuild_after_compaction({})

    def snapshot(self):
        definitions = [
            ('messages','Messages · text','User and assistant text recorded in the session. Excludes images, audio and protocol overhead.'),
            ('tool_io','Tool calls and results','Recorded argument and result text, not tool schemas. Includes file content returned by tools.'),
            ('base','Recorded base instructions','Count of the base_instructions.text field. May not represent the entire effective system prompt.'),
            ('developer','Recorded developer instructions','Persisted developer message text. May overlap with catalogs and other instructions shown separately.'),
            ('skills','Skills catalog','Session catalog text: names, descriptions and references. Does not include the full content of skills read.'),
            ('mcp','MCP catalog · summaries','MCP namespace names and descriptions from the session state. Excludes active schemas and full server instructions.'),
            ('agents','AGENTS.md references','Only the agents_md field text, which may just reference another file. Does not measure all memory files.'),
        ]
        rows=[]
        for key,label,note in definitions:
            value = self.counts.get(key)
            status = 'estimate' if value is not None else 'unavailable'
            if self.compacted and key in ('messages','tool_io','developer'):
                note += ' After compaction: counts only readable preserved history and subsequent records.' if self.replacement_available else ' Counts only new records after compaction; preserved history is unavailable.'
            reason = None
            if status == 'unavailable':
                reason = 'Local tokenizer unavailable.' if ENCODING is None else 'No readable records for this category after compaction.' if self.compacted else 'No readable records for this category.'
            rows.append({'id':key,'label':label,'tokens':value if status=='estimate' else None,
                         'status':status,'note':note,'records':self.records.get(key,0),'unavailableReason':reason})
        return {'tokenizer':'o200k_base' if ENCODING else None, 'exact':False,
                'scope':'Text observed in the local record; not an exact breakdown of the active context.',
                'canSum':False,'multimodalBlocksExcluded':self.multimodal,
                'compactionInvalidated':self.compacted and not self.replacement_available,
                'compactionSeen':self.compacted,'replacementHistoryAvailable':self.replacement_available,
                'encryptedBlocksExcluded':self.encrypted,
                'rows':rows}
