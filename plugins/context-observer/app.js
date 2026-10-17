import {renderCosts} from './cost-ui.js';
import {sortRows, relativeAge, versionState} from './ui-state.mjs';
const $ = id => document.getElementById(id);
const fmt = new Intl.NumberFormat('pt-BR');
const n = x => Number.isFinite(x) ? fmt.format(x) : '—';
const compact = x => Number.isFinite(x) ? new Intl.NumberFormat('pt-BR', {notation:'compact',maximumFractionDigits:1}).format(x) : '—';
const set = (id, value) => { $(id).textContent = value; };
let latest = null, busy = false, selectedCatalog = 'mcp';
let compositionSignature = '';
let lastSuccess=null, connectionError=null, requestSequence=0;
const uiVersion=window.contextPanelVersion || 'prévia';

function renderHealth() {
  const age=lastSuccess===null?Infinity:Date.now()-lastSuccess;
  set('freshness',lastSuccess===null?'Aguardando a primeira consulta':`Consulta ${relativeAge(lastSuccess)} · última chamada ${relativeAge(latest?.measuredAt)}`);
  set('version',`Painel v${uiVersion}`);
  const versions=versionState(uiVersion,latest?.plugin);
  set('versionNote',versions.pending ? `v${latest.plugin.installedVersion} instalada. Reabra o Codex para carregar a atualização.` : versions.mismatch ? `Coletor v${latest.plugin.runningVersion}. Reabra o painel para atualizar a interface.` : '');
  $('versionNote').hidden=!versions.pending && !versions.mismatch;
  if(connectionError) {set('connection','● Conexão interrompida'); $('connection').className='pill warning';}
  else if(document.hidden) {set('connection','● Pausado · painel oculto'); $('connection').className='pill';}
  else if(lastSuccess && age>8000) {set('connection','● Dados desatualizados'); $('connection').className='pill warning';}
  else if(lastSuccess) {set('connection',latest.state==='running'?'● Ao vivo · turno ativo':'● Ao vivo · em espera'); $('connection').className='pill live';}
}

function renderCompactions(data) {
  const entries=data.compactionHistory||[];
  set('compactionCount',`${n(data.compactionsObserved||0)} registrada(s)`);
  const signature=JSON.stringify(entries);
  if($('compactionList').dataset.signature===signature) return;
  $('compactionList').dataset.signature=signature;
  const time=value=>value?new Date(value).toLocaleString('pt-BR'):'horário não registrado';
  $('compactionList').replaceChildren(...entries.slice().reverse().map(item=>{
    const row=node('details',undefined,'compaction-item');
    const change=item.differenceTokens;
    const status=!item.after?'Aguardando medição posterior':!Number.isFinite(change)?'Comparação incompleta':change>=0?`${n(change)} tokens a menos`:`${n(-change)} tokens a mais`;
    const summary=node('summary');summary.append(node('span',`#${item.number} · ${time(item.at)}`),node('strong',status));
    row.append(summary,node('p',`Entrada antes: ${n(item.before?.input)} tokens · ${time(item.before?.at)}`),node('p',`Entrada depois: ${n(item.after?.input)} tokens · ${time(item.after?.at)}`));
    row.append(node('p',item.readableHistoryAvailable?'Estimativas reconstruídas parcialmente; conteúdo criptografado excluído.':'Histórico preservado não disponível; estimativas limitadas aos registros seguintes.'));
    if(item.after && item.before?.window!==item.after.window) row.append(node('p','A janela reportada também mudou entre estas chamadas.'));
    return row;
  }));
  if(!entries.length) $('compactionList').append(node('p','Nenhuma compactação registrada nesta conversa.','note'));
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function toolGroup(name) {
  const namespace = [...(latest?.namespaces || [])].sort((a,b)=>b.length-a.length).find(x => name.startsWith(x+'_'));
  if (namespace) return namespace.replace(/^mcp__/, '');
  if (name.startsWith('mcp__')) return name.split('__')[1];
  return name.includes('__') ? name.split('__')[0] : 'Ferramentas do ambiente';
}
function catalogData() {
  if (!latest) return [];
  if (selectedCatalog === 'mcp') return (latest.mcpCatalog || []).map(x=>({...x,group:'Namespaces MCP'}));
  if (selectedCatalog === 'skills') return (latest.skillsCatalog || []).map(x=>({...x,group:x.name.includes(':') ? x.name.split(':')[0] : 'Skills individuais'}));
  return (latest.catalogSnapshot.tools || []).map(x=>({...x,group:toolGroup(x.name)}));
}
function renderCatalog() {
  const all = catalogData();
  const query = $('catalogSearch').value.trim().toLocaleLowerCase();
  const group = $('catalogFilter').value;
  const filtered = all.filter(x => (!group || x.group===group) && [x.name,x.description,x.path,x.group].filter(Boolean).join(' ').toLocaleLowerCase().includes(query));
  set('catalogMeta', `${n(filtered.length)} de ${n(all.length)} itens · clique em um nome para ver os detalhes`);
  const items = filtered.map(item => {
    const detail = node('details',undefined,'catalog-item');
    const summary = node('summary',item.name);
    detail.append(summary,node('div',item.group,'item-group'),node('p',item.description || 'Descrição não fornecida pelo catálogo.'));
    if (item.path) detail.append(node('p',item.path,'item-path'));
    if (selectedCatalog === 'mcp') {
      const tools = (latest.catalogSnapshot.tools || []).filter(t=>t.name.startsWith(item.name+'_'));
      detail.append(node('p',`${tools.length} ferramentas correspondentes no snapshot consultável. A lista de namespaces e o catálogo de ferramentas têm escopos diferentes.`));
      if (tools.length) {
        const button = node('button','Ver ferramentas deste MCP');
        button.addEventListener('click',()=>openCatalog('tools',item.name+'_'));
        detail.append(button);
      }
    }
    return detail;
  });
  $('catalogList').replaceChildren(...(items.length ? items : [node('p','Nenhum item corresponde à busca.','empty')]));
}
function openCatalog(kind, query='') {
  if (!latest) return;
  selectedCatalog = kind;
  const labels = {mcp:['Namespaces MCP','Servidores e integrações registrados no estado desta sessão.'],skills:['Skills disponíveis','Nomes, descrições e caminhos do catálogo da sessão.'],tools:['Ferramentas consultáveis','O host não fornece o catálogo completo de ferramentas por conversa nesta integração.']};
  set('catalogTitle',labels[kind][0]); set('catalogDescription',labels[kind][1]);
  document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===kind)));
  $('catalogSearch').value=query;
  const options=[node('option','Todos os grupos')]; options[0].value='';
  for (const group of [...new Set(catalogData().map(x=>x.group))].sort()) {
    const option=node('option',group); option.value=group; options.push(option);
  }
  $('catalogFilter').replaceChildren(...options);
  renderCatalog();
  if (!$('catalogDialog').open) $('catalogDialog').showModal();
  $('catalogSearch').focus();
}
document.querySelectorAll('[data-catalog]').forEach(b=>b.addEventListener('click',()=>openCatalog(b.dataset.catalog)));
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>openCatalog(b.dataset.tab)));
$('catalogSearch').addEventListener('input',renderCatalog);
$('catalogFilter').addEventListener('change',renderCatalog);
$('closeCatalog').addEventListener('click',()=>$('catalogDialog').close());

function renderComposition(data, contextWindow) {
  if (!data) return;
  const signature=JSON.stringify([data,contextWindow]);
  if (signature===compositionSignature) return;
  compositionSignature=signature;
  let statusNote=$('compositionStatus');
  if (!statusNote) {
    statusNote=node('p','','note'); statusNote.id='compositionStatus';
    $('categories').before(statusNote);
  }
  statusNote.textContent=data.compactionSeen ? data.replacementHistoryAvailable
    ? 'A conversa foi compactada. Estimativas recalculadas sobre o histórico preservado legível e os registros seguintes; o resumo criptografado não está incluído.'
    : 'A conversa foi compactada. Estimativas limitadas aos novos registros; o histórico preservado não está disponível.' : '';
  statusNote.hidden=!data.compactionSeen;
  const rows=sortRows(data.rows);
  const valid=new Set(rows.map(x=>x.id));
  for(const child of [...$('categories').children]) if(!valid.has(child.dataset.id)) child.remove();
  const focused=document.activeElement;
  for (const item of rows) {
    let row=[...$('categories').children].find(x=>x.dataset.id===item.id);
    if (!row) {
      row=node('details',undefined,'composition-row'); row.dataset.id=item.id;
      const summary=node('summary');
      const value=node('span','','value');
      value.append(node('span','','token-count'),node('small','','context-share'));
      summary.append(node('span',item.label),value);
      row.append(summary,node('p',item.note),node('p','','method-note'));
      $('categories').append(row);
    }
    const estimated=item.status==='estimate' && Number.isFinite(item.tokens);
    row.querySelector('.token-count').textContent=estimated ? '≈ '+n(item.tokens) : 'Indisponível';
    const percent=estimated && Number.isFinite(contextWindow) && contextWindow>0 ? item.tokens/contextWindow*100 : null;
    row.querySelector('.context-share').textContent=percent===null ? '' : percent>0 && percent<0.01 ? '< 0,01% da janela' : '≈ '+percent.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})+'% da janela';
    row.querySelector('p').textContent=item.note;
    row.querySelector('.method-note').textContent=item.status==='estimate' ? `${n(item.records)} registro(s) · tokenizer ${data.tokenizer}. A tokenização específica do modelo pode ser diferente.` : item.unavailableReason || 'Não há medição disponível para esta categoria.';
    $('categories').append(row);
  }
  if(focused?.isConnected && document.activeElement!==focused && $('categories').contains(focused)) focused.focus({preventScroll:true});
  set('compositionNote',`Percentuais sobre a janela total reportada (${n(contextWindow)} tokens), não apenas sobre a parte usada. Estimativas com ${data.tokenizer || 'tokenizer indisponível'}. Não some as linhas: pode haver sobreposição. Exclui schemas completos, overhead, ${data.multimodalBlocksExcluded} bloco(s) multimodal(is) e ${data.encryptedBlocksExcluded || 0} bloco(s) criptografado(s).`);
}
async function refresh(force=false) {
  if (busy && !force) return; busy=true;
  const sequence=++requestSequence;
  try {
    const d=await window.readContextSnapshot();
    if(sequence!==requestSequence) return;
    if (!d.verified) throw new Error('Identidade da conversa não validada.');
    if(latest && latest.threadId!==d.threadId) throw new Error('A atualização trouxe outra conversa. Reabra o painel na conversa desejada.');
    latest=d;
    lastSuccess=Date.now(); connectionError=null;
    $('error').style.display='none'; set('threadName',d.name);
    set('threadIdentity',d.threadId);
    set('bindingState','Fixo nesta conversa · dados atualizados automaticamente.');
    set('percent',d.inputWindowPercentEstimate==null?'—':d.inputWindowPercentEstimate.toLocaleString('pt-BR',{maximumFractionDigits:1}));
    const pct=Math.max(0,Math.min(100,d.inputWindowPercentEstimate??0));
    $('fill').style.width=pct+'%'; $('meter').setAttribute('aria-valuenow',pct);
    set('ratio',compact(d.last?.input_tokens)+' / '+compact(d.window)+' tokens'); set('remaining','≈ '+compact(d.remainingInputWindowEstimate)+' livres');
    for (const [id,key] of [['input','input_tokens'],['cached','cached_input_tokens'],['output','output_tokens'],['reasoning','reasoning_output_tokens'],['lastTotal','total_tokens']]) set(id,n(d.last?.[key]));
    set('namespaces',n(d.namespaces.length)); set('skills',n(d.skillsCount)); set('toolCount',n(d.catalogSnapshot.total));
    set('model',d.model??'Indisponível'); set('accumulated',n(d.accumulated?.total_tokens));
    set('measuredAt',d.measuredAt?new Date(d.measuredAt).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'})+' BRT':'Sem medição');
    set('events',n(d.diagnostics.tokenEventsObserved)); set('verified','Conversa confirmada'); set('threadId',d.threadId); set('source',d.source.path);
    set('diagnostics',d.diagnostics.invalidLines+' linhas inválidas; '+d.diagnostics.pendingBytes+' bytes aguardando término de linha. Catálogo completo de ferramentas não fornecido por esta integração.');
    const samples=d.samples.filter(s=>Number.isFinite(s.input));
    $('sparkline').setAttribute('points',samples.map((s,i)=>`${samples.length>1?i/(samples.length-1)*360:0},${55-Math.max(0,Math.min(1,s.input/(d.window||1)))*52}`).join(' '));
    renderComposition(d.composition,d.window);
    renderCompactions(d);
    renderCosts(d.costs,d.threadId);
    const markers=[];
    samples.forEach((s,i)=>{
      if(i>0 && s.compactionNumber>samples[i-1].compactionNumber) {
        const circle=document.createElementNS('http://www.w3.org/2000/svg','circle');
        circle.setAttribute('cx',String(i/(samples.length-1)*360));circle.setAttribute('cy',String(55-Math.max(0,Math.min(1,s.input/(d.window||1)))*52));circle.setAttribute('r','3.5');circle.setAttribute('fill','#c48e3c');
        const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`Primeira medição após compactação #${s.compactionNumber}`;circle.append(title);markers.push(circle);
      }
    });
    $('compactionMarkers').replaceChildren(...markers);
    set('footer','Somente leitura · processamento local · atualização a cada 2 s com o painel visível');
    renderHealth();
  } catch (err) {
    if(sequence!==requestSequence || err.superseded) return;
    connectionError=err.message;
    set('error',err.message+' Os últimos valores exibidos podem estar desatualizados.'); $('error').style.display='block';
    renderHealth();
  } finally { if(sequence===requestSequence) busy=false; }
}

$('refresh').addEventListener('click',()=>refresh());
window.addEventListener('context-ready',()=>refresh(true));
document.addEventListener('visibilitychange',()=>{if(!document.hidden) refresh(); renderHealth();});
renderHealth();
setInterval(renderHealth,1000);
setInterval(()=>{if(window.readContextSnapshot && !document.hidden) refresh();},2000);
