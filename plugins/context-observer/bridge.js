import {App} from '@modelcontextprotocol/ext-apps';
const VERSION='__PLUGIN_VERSION__';
const app = new App({name:'context-observer',version:VERSION});
window.contextPanelVersion=VERSION;
let binding=null, initial=null, bindingError=null, fixedThread=null;
function accept(result) {
  const meta=result._meta||{};
  if(binding) return; // An existing panel keeps its first successful opening.
  if(meta.binding && meta.snapshot?.threadId) { binding=meta.binding; initial=meta.snapshot; fixedThread=meta.snapshot.threadId; bindingError=null; }
  if(meta.bindingError) bindingError=meta.bindingError;
  window.dispatchEvent(new Event('context-ready'));
}
async function call(name,args) {
  let timer;
  try {
    const result=await Promise.race([
      app.callServerTool({name,arguments:args}),
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Codex did not respond within 12 seconds. Try refreshing again.')),12000);})
    ]);
    if(result.isError) throw new Error(result.content?.find(x=>x.type==='text')?.text||'Local collection failed.');
    return result;
  } finally {clearTimeout(timer);}
}
app.ontoolresult=accept;
window.readContextSnapshot = async () => {
  if(bindingError) throw new Error(bindingError);
  if(!binding) throw new Error('Waiting for Codex to bind this panel to the conversation.');
  if(initial) {const value=initial; initial=null; return value;}
  const result=await call('read_context_panel',{binding});
  if(!result._meta?.snapshot) throw new Error('The host did not return panel data.');
  if(result._meta.snapshot.threadId!==fixedThread) throw new Error('The update returned a different conversation. The panel kept the original conversation data.');
  return result._meta.snapshot;
};
app.connect().catch(error=>{
  bindingError='This panel must be opened as an MCP App in Codex: '+error.message;
  window.dispatchEvent(new Event('context-ready'));
});
