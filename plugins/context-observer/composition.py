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
            ('messages','Mensagens · texto','Textos de usuário e assistente registrados na sessão. Exclui imagens, áudio e overhead do protocolo.'),
            ('tool_io','Chamadas e resultados de ferramentas','Texto dos argumentos e resultados registrados. Não são os schemas das ferramentas. Inclui conteúdo de arquivos que tenha sido retornado por ferramentas.'),
            ('base','Instruções-base registradas','Contagem do campo base_instructions.text. Pode não representar todo o system prompt efetivo.'),
            ('developer','Instruções developer registradas','Texto de mensagens developer persistidas. Pode se sobrepor a catálogos e outras instruções mostradas separadamente.'),
            ('skills','Catálogo de skills','Texto do catálogo da sessão: nomes, descrições e referências. Não equivale ao conteúdo completo das skills lidas.'),
            ('mcp','Catálogo MCP · resumos','Nomes e descrições dos namespaces MCP no estado da sessão. Não inclui schemas ativos nem instruções completas dos servidores.'),
            ('agents','Referências AGENTS.md','Somente o texto do campo agents_md, que pode conter apenas uma referência a outro arquivo. Não mede todos os arquivos de memória.'),
        ]
        rows=[]
        for key,label,note in definitions:
            value = self.counts.get(key)
            status = 'estimate' if value is not None else 'unavailable'
            if self.compacted and key in ('messages','tool_io','developer'):
                note += ' Após compactação: conta apenas o histórico preservado legível e os registros seguintes.' if self.replacement_available else ' Conta somente novos registros após a compactação; o histórico preservado não está disponível.'
            reason = None
            if status == 'unavailable':
                reason = 'Tokenizer local indisponível.' if ENCODING is None else 'Sem registro legível desta categoria após a compactação.' if self.compacted else 'Sem registro legível desta categoria.'
            rows.append({'id':key,'label':label,'tokens':value if status=='estimate' else None,
                         'status':status,'note':note,'records':self.records.get(key,0),'unavailableReason':reason})
        return {'tokenizer':'o200k_base' if ENCODING else None, 'exact':False,
                'scope':'Texto observado no registro local; não é uma decomposição exata do contexto ativo.',
                'canSum':False,'multimodalBlocksExcluded':self.multimodal,
                'compactionInvalidated':self.compacted and not self.replacement_available,
                'compactionSeen':self.compacted,'replacementHistoryAvailable':self.replacement_available,
                'encryptedBlocksExcluded':self.encrypted,
                'rows':rows}
