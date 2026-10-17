#!/usr/bin/env python3
"""Read-only local MCP server. Session text never leaves the collector."""
import json
import os
import re
import secrets
import sys
import time
from collections import OrderedDict
from pathlib import Path
from server import resolve
from account_status import AccountStatus

ROOT = Path(__file__).resolve().parent
VERSION = json.loads((ROOT/'.codex-plugin/plugin.json').read_text())['version']
URI = f'ui://context-observer/panel-{VERSION}.html'
MIME = 'text/html;profile=mcp-app'
UUID = re.compile(r'^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$')

def host_thread(meta):
    """Same metadata keys recognized by the bundled Codex app tools.

    These are observed host details, not a stable public focus API.
    Do not use CODEX_THREAD_ID inherited by a shared MCP process.
    """
    meta = meta if isinstance(meta, dict) else {}
    values = [meta.get(k) for k in ('openai/threadId','openai/thread_id','codexThreadId','codex_thread_id','threadId','thread_id')]
    turn = meta.get('x-codex-turn-metadata', {})
    if isinstance(turn, str):
        try: turn = json.loads(turn)
        except ValueError: turn = {}
    if isinstance(turn, dict): values.append(turn.get('thread_id'))
    if isinstance(meta.get('thread'), dict): values.append(meta['thread'].get('id'))
    for value in values:
        if isinstance(value, str) and UUID.fullmatch(value): return value.lower()
    return None

class Monitor:
    def __init__(self, codex_home=None):
        self.home = codex_home or Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))
        self.account_status = AccountStatus(self.home)
        self.collectors = OrderedDict()
        self.bindings = OrderedDict()
        self.last_identity_refresh = {}

    def snapshot(self, thread_id):
        if thread_id not in self.collectors:
            self.collectors[thread_id] = resolve(thread_id, self.home)
        self.collectors.move_to_end(thread_id)
        while len(self.collectors)>8: self.collectors.popitem(last=False)
        if time.monotonic() - self.last_identity_refresh.get(thread_id, 0) > 10:
            fresh = resolve(thread_id, self.home)
            self.collectors[thread_id].name = fresh.name
            self.last_identity_refresh[thread_id] = time.monotonic()
        data = self.collectors[thread_id].snapshot()
        installed_version = VERSION
        install_root = os.environ.get('CONTEXT_OBSERVER_INSTALL_ROOT')
        if install_root:
            try:
                installed_version = json.loads((Path(install_root)/'current.json').read_text())['version']
            except (OSError, ValueError, KeyError):
                pass
        data['costs']['currentAuth'] = self.account_status.read()
        data['plugin'] = {'runningVersion':VERSION,'installedVersion':installed_version,
                          'updatePending':installed_version != VERSION}
        return data

    def call(self, name, args, meta):
        if name not in ('open_context_panel','read_context_panel'):
            raise ValueError('Unknown tool.')
        thread_id = host_thread(meta)
        source = 'host' if thread_id else 'bound'
        binding = args.get('binding')
        if name == 'open_context_panel':
            if not thread_id:
                candidate = args.get('thread_id')
                if isinstance(candidate,str) and UUID.fullmatch(candidate): thread_id = candidate.lower()
            if not thread_id:
                return {'content':[{'type':'text','text':'Codex did not provide a conversation ID when opening this panel. Ask the agent to use open_context_panel with the ID of this conversation.'}],'isError':True,'_meta':{'bindingError':'Codex did not provide a conversation ID. Ask in this conversation: open the context panel.'}}
            # Validate identity before allocating a binding.
            data = self.snapshot(thread_id)
            binding = secrets.token_urlsafe(32)
            self.bindings[binding] = thread_id
            while len(self.bindings)>64: self.bindings.popitem(last=False)
        else:
            if not isinstance(binding,str) or binding not in self.bindings:
                raise ValueError('Binding expired. Close this panel and open a new one in the intended conversation.')
            # The opening fixes identity. Later host metadata must never retarget this panel.
            thread_id = self.bindings[binding]
            source = 'opening'
            data = self.snapshot(thread_id)
        data['bindingSource'] = source
        data['binding'] = {'source':source,'mode':'fixed','focusTracking':'opening-only'}
        return {'content':[{'type':'text','text':'Local context panel opened.'}] if name=='open_context_panel' else [],
                '_meta':{'snapshot':data,'binding':binding},
                'structuredContent':{'threadId':thread_id,'verified':data['verified'],'version':VERSION}}

def tools_list():
    annotations={'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False}
    return {'tools':[
        {'name':'open_context_panel','title':'Conversation context','description':'Opens the local context metrics panel for this conversation. The host identifies the chat automatically when it provides metadata. If needed, pass only the exact current conversation ID, never the most recent chat.',
         'inputSchema':{'type':'object','properties':{'thread_id':{'type':'string','description':'Exact current conversation ID, used only if the host does not provide it.'}},'additionalProperties':False},
         'annotations':annotations,'_meta':{'ui':{'resourceUri':URI},'openai/outputTemplate':URI,'openai/ui':{'entrypoints':[{'type':'thread'}]}}},
        {'name':'read_context_panel','title':'Refresh context','description':'Updates data for the conversation bound when the panel opened, without running the model.',
         'inputSchema':{'type':'object','properties':{'binding':{'type':'string'}},'required':['binding'],'additionalProperties':False},
         'annotations':annotations,'_meta':{'ui':{'visibility':['app']},'openai/visibility':'private'}}]}

def dispatch(method, params, monitor):
    if method == 'initialize':
        return {'protocolVersion':params.get('protocolVersion','2025-06-18'),'capabilities':{'tools':{},'resources':{}},'serverInfo':{'name':'context-observer','version':VERSION}}
    if method == 'ping': return {}
    if method == 'tools/list': return tools_list()
    if method == 'resources/list': return {'resources':[{'uri':URI,'name':'Conversation context','mimeType':MIME}]}
    if method == 'resources/templates/list': return {'resourceTemplates':[]}
    if method == 'resources/read':
        if params.get('uri') != URI: raise ValueError('Unknown resource.')
        return {'contents':[{'uri':URI,'mimeType':MIME,'text':(ROOT/'panel.html').read_text(),
                '_meta':{'ui':{'csp':{'connectDomains':[],'resourceDomains':[]}},'openai/ui':{'preferredDisplayMode':'inline','availableDisplayModes':['inline','fullscreen']}}}]}
    if method == 'tools/call':
        try: return monitor.call(params.get('name'),params.get('arguments') or {},params.get('_meta'))
        except (ValueError,OSError) as err:
            # No traceback, transcript or private instructions in tool responses.
            return {'content':[{'type':'text','text':str(err) if isinstance(err,ValueError) else 'Could not read the local session.'}],'isError':True}
    raise ValueError('Unsupported MCP method.')

def main():
    monitor = Monitor()
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if not isinstance(request,dict): raise ValueError('Invalid request.')
            if 'id' not in request: continue
            result = dispatch(request.get('method'),request.get('params') or {},monitor)
            reply = {'jsonrpc':'2.0','id':request['id'],'result':result}
        except Exception:
            reply = {'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,'error':{'code':-32603,'message':'Could not process the local request.'}}
        print(json.dumps(reply,ensure_ascii=False),flush=True)

if __name__ == '__main__': main()
