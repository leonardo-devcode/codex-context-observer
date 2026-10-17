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
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('O Codex não respondeu em 12 segundos. Tente atualizar novamente.')),12000);})
    ]);
    if(result.isError) throw new Error(result.content?.find(x=>x.type==='text')?.text||'Falha na coleta local.');
    return result;
  } finally {clearTimeout(timer);}
}
app.ontoolresult=accept;
window.readContextSnapshot = async () => {
  if(bindingError) throw new Error(bindingError);
  if(!binding) throw new Error('Aguardando o Codex vincular este painel à conversa.');
  if(initial) {const value=initial; initial=null; return value;}
  const result=await call('read_context_panel',{binding});
  if(!result._meta?.snapshot) throw new Error('O host não entregou os dados do painel.');
  if(result._meta.snapshot.threadId!==fixedThread) throw new Error('A atualização trouxe outra conversa. O painel manteve os dados da conversa original.');
  return result._meta.snapshot;
};
app.connect().catch(error=>{
  bindingError='O painel precisa ser aberto como MCP App no Codex: '+error.message;
  window.dispatchEvent(new Event('context-ready'));
});
