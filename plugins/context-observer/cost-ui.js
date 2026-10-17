const el=id=>document.getElementById(id);
const number=new Intl.NumberFormat('pt-BR');
const dollars=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'USD',minimumFractionDigits:4,maximumFractionDigits:4});
const money=value=>Number.isFinite(value)?(value>0 && value<0.0001?'< US$ 0,0001':dollars.format(value)):'—';
const names={standard:'Standard',fast:'Fast',flex:'Flex',ultrafast:'Ultrafast'};
let signature='',thread=null;
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
export function costView(data){
  const b=data.billingCounts||{},api=b.api||0,subscription=b.subscription||0,unknown=b.unknown||0;
  if(api)return {key:'auto',eligible:api,status:subscription?'API + ChatGPT registrados':'API registrada',source:'Forma de cobrança identificada nos registros. O subtotal considera somente as respostas identificadas como API.'};
  if(unknown && data.currentAuth?.mode==='api')return {key:'inferred',eligible:unknown,status:'Estimativa · login API atual',source:'O login atual do Codex CLI usa API. Ele serve como referência para respostas sem forma de cobrança registrada; não confirma a conta usada pelo aplicativo nem a cobrança histórica. Respostas identificadas como ChatGPT são excluídas.'};
  if(subscription)return {key:null,eligible:0,status:'ChatGPT identificado',source:'Os registros indicam uso de ChatGPT. Esses tokens não são apresentados como gasto de API. Respostas sem identificação permanecem sem custo estimado.'};
  if(data.currentAuth?.mode==='subscription')return {key:null,eligible:0,status:'ChatGPT · login atual',source:'O login atual do Codex CLI usa ChatGPT. O histórico não confirma a forma de cobrança destas respostas.'};
  return {key:null,eligible:0,status:'Cobrança não identificada',source:'Não há informação suficiente nos registros ou no login local para estimar a cobrança automaticamente.'};
}
export function costSummary(data,key,eligible=data.calls){
  let usd=0,priced=0;
  for(const row of data.rows||[]){const e=row.estimates[key];if(Number.isFinite(e?.usd))usd+=e.usd;priced+=e?.pricedCalls||0;}
  return {usd:priced?usd:null,priced,partial:priced!==eligible || data.uncoveredTokens>0 || data.unidentifiedRecords>0};
}
export function renderCosts(data,threadId){
  if(thread!==threadId){thread=threadId;signature='';}
  if(!data){el('costTotal').textContent='—';el('costTotalLabel').textContent='Coletor sem dados de custo. Reabra o Codex após atualizar o plugin.';return;}
  const view=costView(data),api=Boolean(view.key),total=costSummary(data,view.key,view.eligible),b=data.billingCounts||{};
  el('costStatus').textContent=view.status;
  el('costDetection').textContent=view.source;
  const assumed=(data.rows||[]).reduce((n,r)=>n+r.assumedTierCalls,0);
  el('costTierNote').textContent=api && assumed?'Standard é a tarifa de referência quando a modalidade não foi registrada. Modalidades registradas têm prioridade.':'';
  el('costTotal').textContent=api?money(total.usd):'—';
  el('costTotalLabel').textContent=api?(total.partial?'Subtotal estimado dos registros calculáveis':'Custo estimado dos tokens identificados'):b.subscription?'Uso de ChatGPT não é convertido em cobrança de API':'Consumo por modelo disponível; custo sem identificação suficiente';
  const counts=[`${number.format(b.api||0)} API`,`${number.format(b.subscription||0)} ChatGPT`,`${number.format(b.unknown||0)} sem identificação`];
  if(b.conflict)counts.push(`${number.format(b.conflict)} com evidências conflitantes (excluídas)`);
  el('costCoverage').textContent=(api?`${number.format(total.priced)} de ${number.format(view.eligible)} respostas elegíveis calculadas. `:'')+counts.join(' · ')+(data.uncoveredTokens?` · ${number.format(data.uncoveredTokens)} tokens acumulados sem detalhamento`:'')+(data.unidentifiedRecords?` · ${number.format(data.unidentifiedRecords)} registros sem ID`:'')+'.';
  el('costMethod').textContent=`Tarifas públicas consultadas em ${(data.pricesVerifiedAt||'').split('-').reverse().join('/')}, aplicadas ao histórico. Contexto longo é calculado por chamada acima de 272 mil tokens de entrada. Cache e raciocínio não são somados novamente. Não inclui impostos, descontos, acréscimos regionais, ferramentas cobradas à parte nem subagentes em outros registros. Não é uma fatura.`;
  el('costAssumptions').textContent='A detecção usa a autenticação registrada ou o plano ChatGPT associado ao turno. O login atual do CLI é consultado localmente, no máximo uma vez por minuto, como referência quando o histórico não informa a cobrança. Credenciais não são retornadas ao painel. O modelo vem da resposta ou do turno correspondente. Somente o provedor OpenAI recebe as tarifas cadastradas.';
  el('costSource').href=data.priceSource;
  const sig=JSON.stringify([data.rows,view.key]);if(sig===signature)return;signature=sig;
  const opened=new Set([...el('costModels').children].filter(x=>x.open).map(x=>x.dataset.key));
  const rows=[...data.rows].sort((a,b)=>api?(b.estimates[view.key]?.usd??-1)-(a.estimates[view.key]?.usd??-1):0);
  el('costModels').replaceChildren(...rows.map(row=>{
    const details=node('details',undefined,'cost-model');details.dataset.key=JSON.stringify([row.model,row.provider]);details.open=opened.has(details.dataset.key);
    const estimate=row.estimates[view.key],summary=node('summary');
    summary.append(node('span',row.model),node('strong',api?(estimate?.usd==null?'Sem estimativa':money(estimate.usd)):`${number.format(row.calls)} respostas`));details.append(summary);
    details.append(node('p',`${number.format(row.calls)} respostas · provedor: ${row.provider||'não registrado'}. ${row.inferredModelCalls?`${number.format(row.inferredModelCalls)} atribuídas ao modelo do turno.`:''}`,'note'));
    const counts=row.billingCounts||{};
    details.append(node('p',`${number.format(counts.api||0)} API · ${number.format(counts.subscription||0)} ChatGPT · ${number.format(counts.unknown||0)} sem identificação${counts.conflict?` · ${number.format(counts.conflict)} conflitantes`:''}.`,'note'));
    const fields=[['input_tokens','Entrada total'],['cached_input_tokens','↳ Leitura de cache'],['cache_write_input_tokens','↳ Gravação de cache'],['output_tokens','Saída (inclui raciocínio)']];
    for(const [field,label] of fields){const line=node('div',undefined,'row');line.append(node('span',label),node('span',number.format(row.tokens[field])+(row.missingCounters.includes(field)?' · parcial':'')));details.append(line);}
    if(api && estimate){
      const labels=['Entrada sem cache','Leitura de cache','Gravação de cache','Saída'];
      details.append(node('p',`${number.format(estimate.pricedCalls)} respostas com custo calculado neste modelo.`,'note'));
      if(estimate.pricedCalls)details.append(node('p',labels.map((x,i)=>`${x}: ${money(estimate.parts[i])}`).join(' · '),'note'));
      if(estimate.reasons.length)details.append(node('p',estimate.reasons.join(' · '),'note'));
      for(const used of estimate.tiers){const card=row.rateCard[used];if(!card)continue;
        const describe=values=>values.map((v,i)=>`${labels[i]} ${v===null?'sem tarifa':money(v)}`).join(' · ');
        details.append(node('p',`${names[used]||used} · USD por 1 milhão de tokens: ${describe(card.short)}.`,'note'));
        if(card.long.some(x=>x!==null))details.append(node('p',`Acima de 272 mil tokens de entrada: ${describe(card.long)}.`,'note'));
      }
    }
    return details;
  }));
  if(!rows.length)el('costModels').append(node('p','Sem registros detalhados de uso por resposta. Os contadores gerais não permitem atribuir um custo confiável por modelo.','note'));
}
