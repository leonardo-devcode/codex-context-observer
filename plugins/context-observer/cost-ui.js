const el=id=>document.getElementById(id);
const number=new Intl.NumberFormat('en-US');
const dollars=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:4,maximumFractionDigits:4});
const money=value=>Number.isFinite(value)?(value>0 && value<0.0001?'< $0.0001':dollars.format(value)):'—';
const names={standard:'Standard',fast:'Fast',flex:'Flex',ultrafast:'Ultrafast'};
let signature='',thread=null;
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
export function costView(data){
  const b=data.billingCounts||{},api=b.api||0,subscription=b.subscription||0,unknown=b.unknown||0;
  if(api)return {key:'auto',eligible:api,status:subscription?'API + ChatGPT recorded':'API recorded',source:'Billing method identified in the records. The subtotal includes only responses identified as API usage.'};
  if(unknown && data.currentAuth?.mode==='api')return {key:'inferred',eligible:unknown,status:'Estimate · current API login',source:'The current Codex CLI login uses an API key. It is a reference for responses without a recorded billing method; it does not confirm the account used by the app or historical billing. Responses identified as ChatGPT usage are excluded.'};
  if(subscription)return {key:null,eligible:0,status:'ChatGPT identified',source:'The records indicate ChatGPT usage. These tokens are not shown as API spending. Unidentified responses remain without a cost estimate.'};
  if(data.currentAuth?.mode==='subscription')return {key:null,eligible:0,status:'ChatGPT · current login',source:'The current Codex CLI login uses ChatGPT. The history does not confirm how these responses were billed.'};
  return {key:null,eligible:0,status:'Billing not identified',source:'The records and local login do not provide enough information to estimate billing automatically.'};
}
export function costSummary(data,key,eligible=data.calls){
  let usd=0,priced=0;
  for(const row of data.rows||[]){const e=row.estimates[key];if(Number.isFinite(e?.usd))usd+=e.usd;priced+=e?.pricedCalls||0;}
  return {usd:priced?usd:null,priced,partial:priced!==eligible || data.uncoveredTokens>0 || data.unidentifiedRecords>0};
}
export function renderCosts(data,threadId){
  if(thread!==threadId){thread=threadId;signature='';}
  if(!data){el('costTotal').textContent='—';el('costTotalLabel').textContent='The collector has no cost data. Restart Codex after updating the plugin.';return;}
  const view=costView(data),api=Boolean(view.key),total=costSummary(data,view.key,view.eligible),b=data.billingCounts||{};
  el('costStatus').textContent=view.status;
  el('costDetection').textContent=view.source;
  const assumed=(data.rows||[]).reduce((n,r)=>n+r.assumedTierCalls,0);
  el('costTierNote').textContent=api && assumed?'Standard pricing is the reference when no service tier was recorded. Recorded service tiers take priority.':'';
  el('costTotal').textContent=api?money(total.usd):'—';
  el('costTotalLabel').textContent=api?(total.partial?'Estimated subtotal of priceable records':'Estimated cost of identified tokens'):b.subscription?'ChatGPT usage is not converted into API charges':'Usage by model is available; billing evidence is insufficient';
  const counts=[`${number.format(b.api||0)} API`,`${number.format(b.subscription||0)} ChatGPT`,`${number.format(b.unknown||0)} unidentified`];
  if(b.conflict)counts.push(`${number.format(b.conflict)} with conflicting evidence (excluded)`);
  el('costCoverage').textContent=(api?`${number.format(total.priced)} of ${number.format(view.eligible)} eligible responses priced. `:'')+counts.join(' · ')+(data.uncoveredTokens?` · ${number.format(data.uncoveredTokens)} cumulative tokens without detailed records`:'')+(data.unidentifiedRecords?` · ${number.format(data.unidentifiedRecords)} records without an ID`:'')+'.';
  el('costMethod').textContent=`Public rates checked on ${data.pricesVerifiedAt||'an unknown date'}, applied to the history. Long-context pricing applies per call above 272K input tokens. Cache and reasoning are not added again. Excludes taxes, discounts, regional surcharges, separately billed tools and subagents in other records. This is not an invoice.`;
  el('costAssumptions').textContent='Detection uses recorded authentication or the ChatGPT plan associated with the turn. The current CLI login is checked locally, at most once per minute, as a reference when billing is missing from the history. Credentials are never returned to the panel. The model comes from the response or its turn. Listed rates apply only to the OpenAI provider.';
  el('costSource').href=data.priceSource;
  const sig=JSON.stringify([data.rows,view.key]);if(sig===signature)return;signature=sig;
  const opened=new Set([...el('costModels').children].filter(x=>x.open).map(x=>x.dataset.key));
  const rows=[...data.rows].sort((a,b)=>api?(b.estimates[view.key]?.usd??-1)-(a.estimates[view.key]?.usd??-1):0);
  el('costModels').replaceChildren(...rows.map(row=>{
    const details=node('details',undefined,'cost-model');details.dataset.key=JSON.stringify([row.model,row.provider]);details.open=opened.has(details.dataset.key);
    const estimate=row.estimates[view.key],summary=node('summary');
    summary.append(node('span',row.model),node('strong',api?(estimate?.usd==null?'No estimate':money(estimate.usd)):`${number.format(row.calls)} responses`));details.append(summary);
    details.append(node('p',`${number.format(row.calls)} responses · provider: ${row.provider||'not recorded'}. ${row.inferredModelCalls?`${number.format(row.inferredModelCalls)} attributed to the model recorded for the turn.`:''}`,'note'));
    const counts=row.billingCounts||{};
    details.append(node('p',`${number.format(counts.api||0)} API · ${number.format(counts.subscription||0)} ChatGPT · ${number.format(counts.unknown||0)} unidentified${counts.conflict?` · ${number.format(counts.conflict)} conflicting`:''}.`,'note'));
    const fields=[['input_tokens','Total input'],['cached_input_tokens','↳ Cache reads'],['cache_write_input_tokens','↳ Cache writes'],['output_tokens','Output (includes reasoning)']];
    for(const [field,label] of fields){const line=node('div',undefined,'row');line.append(node('span',label),node('span',number.format(row.tokens[field])+(row.missingCounters.includes(field)?' · partial':'')));details.append(line);}
    if(api && estimate){
      const labels=['Uncached input','Cache reads','Cache writes','Output'];
      details.append(node('p',`${number.format(estimate.pricedCalls)} responses priced for this model.`,'note'));
      if(estimate.pricedCalls)details.append(node('p',labels.map((x,i)=>`${x}: ${money(estimate.parts[i])}`).join(' · '),'note'));
      if(estimate.reasons.length)details.append(node('p',estimate.reasons.join(' · '),'note'));
      for(const used of estimate.tiers){const card=row.rateCard[used];if(!card)continue;
        const describe=values=>values.map((v,i)=>`${labels[i]} ${v===null?'no rate':money(v)}`).join(' · ');
        details.append(node('p',`${names[used]||used} · USD per 1 million tokens: ${describe(card.short)}.`,'note'));
        if(card.long.some(x=>x!==null))details.append(node('p',`Above 272K input tokens: ${describe(card.long)}.`,'note'));
      }
    }
    return details;
  }));
  if(!rows.length)el('costModels').append(node('p','No detailed per-response usage records. Aggregate counters cannot provide a reliable cost by model.','note'));
}
