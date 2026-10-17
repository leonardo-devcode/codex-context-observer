import {renderCosts} from './cost-ui.js';
import {sortRows, relativeAge, versionState} from './ui-state.mjs';
const $ = id => document.getElementById(id);
const fmt = new Intl.NumberFormat('en-US');
const n = x => Number.isFinite(x) ? fmt.format(x) : '—';
const compact = x => Number.isFinite(x) ? new Intl.NumberFormat('en-US', {notation:'compact',maximumFractionDigits:1}).format(x) : '—';
const set = (id, value) => { $(id).textContent = value; };
let latest = null, busy = false, selectedCatalog = 'mcp';
let compositionSignature = '';
let lastSuccess=null, connectionError=null, requestSequence=0;
const uiVersion=window.contextPanelVersion || 'preview';

function renderHealth() {
  const age=lastSuccess===null?Infinity:Date.now()-lastSuccess;
  set('freshness',lastSuccess===null?'Waiting for the first update':`Updated ${relativeAge(lastSuccess)} · last call ${relativeAge(latest?.measuredAt)}`);
  set('version',`Panel v${uiVersion}`);
  const versions=versionState(uiVersion,latest?.plugin);
  set('versionNote',versions.pending ? `v${latest.plugin.installedVersion} installed. Restart Codex to load the update.` : versions.mismatch ? `Collector v${latest.plugin.runningVersion}. Reopen the panel to update the interface.` : '');
  $('versionNote').hidden=!versions.pending && !versions.mismatch;
  if(connectionError) {set('connection','● Disconnected'); $('connection').className='pill warning';}
  else if(document.hidden) {set('connection','● Paused · panel hidden'); $('connection').className='pill';}
  else if(lastSuccess && age>8000) {set('connection','● Outdated data'); $('connection').className='pill warning';}
  else if(lastSuccess) {set('connection',latest.state==='running'?'● Live · active turn':'● Live · idle'); $('connection').className='pill live';}
}

function renderCompactions(data) {
  const entries=data.compactionHistory||[];
  set('compactionCount',`${n(data.compactionsObserved||0)} recorded`);
  const signature=JSON.stringify(entries);
  if($('compactionList').dataset.signature===signature) return;
  $('compactionList').dataset.signature=signature;
  const time=value=>value?new Date(value).toLocaleString('en-US'):'time not recorded';
  $('compactionList').replaceChildren(...entries.slice().reverse().map(item=>{
    const row=node('details',undefined,'compaction-item');
    const change=item.differenceTokens;
    const status=!item.after?'Waiting for the next measurement':!Number.isFinite(change)?'Incomplete comparison':change>=0?`${n(change)} fewer tokens`:`${n(-change)} more tokens`;
    const summary=node('summary');summary.append(node('span',`#${item.number} · ${time(item.at)}`),node('strong',status));
    row.append(summary,node('p',`Input before: ${n(item.before?.input)} tokens · ${time(item.before?.at)}`),node('p',`Input after: ${n(item.after?.input)} tokens · ${time(item.after?.at)}`));
    row.append(node('p',item.readableHistoryAvailable?'Estimates partially rebuilt; encrypted content excluded.':'Preserved history unavailable; estimates cover subsequent records only.'));
    if(item.after && item.before?.window!==item.after.window) row.append(node('p','The reported window also changed between these calls.'));
    return row;
  }));
  if(!entries.length) $('compactionList').append(node('p','No compactions recorded in this conversation.','note'));
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
  return name.includes('__') ? name.split('__')[0] : 'Environment tools';
}
function catalogData() {
  if (!latest) return [];
  if (selectedCatalog === 'mcp') return (latest.mcpCatalog || []).map(x=>({...x,group:'MCP namespaces'}));
  if (selectedCatalog === 'skills') return (latest.skillsCatalog || []).map(x=>({...x,group:x.name.includes(':') ? x.name.split(':')[0] : 'Standalone skills'}));
  return (latest.catalogSnapshot.tools || []).map(x=>({...x,group:toolGroup(x.name)}));
}
function renderCatalog() {
  const all = catalogData();
  const query = $('catalogSearch').value.trim().toLocaleLowerCase();
  const group = $('catalogFilter').value;
  const filtered = all.filter(x => (!group || x.group===group) && [x.name,x.description,x.path,x.group].filter(Boolean).join(' ').toLocaleLowerCase().includes(query));
  set('catalogMeta', `${n(filtered.length)} of ${n(all.length)} items · click a name for details`);
  const items = filtered.map(item => {
    const detail = node('details',undefined,'catalog-item');
    const summary = node('summary',item.name);
    detail.append(summary,node('div',item.group,'item-group'),node('p',item.description || 'No description provided by the catalog.'));
    if (item.path) detail.append(node('p',item.path,'item-path'));
    if (selectedCatalog === 'mcp') {
      const tools = (latest.catalogSnapshot.tools || []).filter(t=>t.name.startsWith(item.name+'_'));
      detail.append(node('p',`${tools.length} matching tools in the available snapshot. The namespace list and tool catalog have different scopes.`));
      if (tools.length) {
        const button = node('button','View tools for this MCP');
        button.addEventListener('click',()=>openCatalog('tools',item.name+'_'));
        detail.append(button);
      }
    }
    return detail;
  });
  $('catalogList').replaceChildren(...(items.length ? items : [node('p','No items match your search.','empty')]));
}
function openCatalog(kind, query='') {
  if (!latest) return;
  selectedCatalog = kind;
  const labels = {mcp:['MCP namespaces','Servers and integrations recorded in this session state.'],skills:['Available skills','Names, descriptions and paths from the session catalog.'],tools:['Available tools','The host does not provide a complete per-conversation tool catalog through this integration.']};
  set('catalogTitle',labels[kind][0]); set('catalogDescription',labels[kind][1]);
  document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===kind)));
  $('catalogSearch').value=query;
  const options=[node('option','All groups')]; options[0].value='';
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
    ? 'This conversation was compacted. Estimates were recalculated from readable preserved history and subsequent records; the encrypted summary is excluded.'
    : 'This conversation was compacted. Estimates cover new records only; preserved history is unavailable.' : '';
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
    row.querySelector('.token-count').textContent=estimated ? '≈ '+n(item.tokens) : 'Unavailable';
    const percent=estimated && Number.isFinite(contextWindow) && contextWindow>0 ? item.tokens/contextWindow*100 : null;
    row.querySelector('.context-share').textContent=percent===null ? '' : percent>0 && percent<0.01 ? '< 0.01% of window' : '≈ '+percent.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})+'% of window';
    row.querySelector('p').textContent=item.note;
    row.querySelector('.method-note').textContent=item.status==='estimate' ? `${n(item.records)} records · tokenizer ${data.tokenizer}. Model-specific tokenization may differ.` : item.unavailableReason || 'No measurement is available for this category.';
    $('categories').append(row);
  }
  if(focused?.isConnected && document.activeElement!==focused && $('categories').contains(focused)) focused.focus({preventScroll:true});
  set('compositionNote',`Percentages use the full reported window (${n(contextWindow)} tokens), not just the used portion. Estimates use ${data.tokenizer || 'an unavailable tokenizer'}. Do not add the rows: categories may overlap. Excludes complete schemas, overhead, ${data.multimodalBlocksExcluded} multimodal blocks and ${data.encryptedBlocksExcluded || 0} encrypted blocks.`);
}
async function refresh(force=false) {
  if (busy && !force) return; busy=true;
  const sequence=++requestSequence;
  try {
    const d=await window.readContextSnapshot();
    if(sequence!==requestSequence) return;
    if (!d.verified) throw new Error('Conversation identity could not be verified.');
    if(latest && latest.threadId!==d.threadId) throw new Error('The update returned a different conversation. Reopen the panel in the intended conversation.');
    latest=d;
    lastSuccess=Date.now(); connectionError=null;
    $('error').style.display='none'; set('threadName',d.name);
    set('threadIdentity',d.threadId);
    set('bindingState','Fixed to this conversation · data updates automatically.');
    set('percent',d.inputWindowPercentEstimate==null?'—':d.inputWindowPercentEstimate.toLocaleString('en-US',{maximumFractionDigits:1}));
    const pct=Math.max(0,Math.min(100,d.inputWindowPercentEstimate??0));
    $('fill').style.width=pct+'%'; $('meter').setAttribute('aria-valuenow',pct);
    set('ratio',compact(d.last?.input_tokens)+' / '+compact(d.window)+' tokens'); set('remaining','≈ '+compact(d.remainingInputWindowEstimate)+' remaining');
    for (const [id,key] of [['input','input_tokens'],['cached','cached_input_tokens'],['output','output_tokens'],['reasoning','reasoning_output_tokens'],['lastTotal','total_tokens']]) set(id,n(d.last?.[key]));
    set('namespaces',n(d.namespaces.length)); set('skills',n(d.skillsCount)); set('toolCount',n(d.catalogSnapshot.total));
    set('model',d.model??'Unavailable'); set('accumulated',n(d.accumulated?.total_tokens));
    set('measuredAt',d.measuredAt?new Date(d.measuredAt).toLocaleString('en-US',{timeZoneName:'short'}):'No measurement');
    set('events',n(d.diagnostics.tokenEventsObserved)); set('verified','Conversation verified'); set('threadId',d.threadId); set('source',d.source.path);
    set('diagnostics',d.diagnostics.invalidLines+' invalid lines; '+d.diagnostics.pendingBytes+' bytes waiting for a line ending. This integration does not provide a complete tool catalog.');
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
        const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`First measurement after compaction #${s.compactionNumber}`;circle.append(title);markers.push(circle);
      }
    });
    $('compactionMarkers').replaceChildren(...markers);
    set('footer','Read-only · local processing · updates every 2 s while visible');
    renderHealth();
  } catch (err) {
    if(sequence!==requestSequence || err.superseded) return;
    connectionError=err.message;
    set('error',err.message+' The last displayed values may be outdated.'); $('error').style.display='block';
    renderHealth();
  } finally { if(sequence===requestSequence) busy=false; }
}

$('refresh').addEventListener('click',()=>refresh());
window.addEventListener('context-ready',()=>refresh(true));
document.addEventListener('visibilitychange',()=>{if(!document.hidden) refresh(); renderHealth();});
renderHealth();
setInterval(renderHealth,1000);
setInterval(()=>{if(window.readContextSnapshot && !document.hidden) refresh();},2000);
