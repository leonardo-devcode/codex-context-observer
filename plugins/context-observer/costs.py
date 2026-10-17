"""Model-token estimates from reported per-response usage; no credentials or network."""
import json
from decimal import Decimal
from pathlib import Path

PRICES = json.loads((Path(__file__).parent/'pricing.json').read_text())
TIERS = ('standard', 'fast', 'flex', 'ultrafast', 'auto', 'inferred')
CHATGPT_PLANS = {'free','go','plus','pro','prolite','team','business','enterprise','edu'}

def auth_mode(value):
    if not isinstance(value,str):return None
    return {'apikey':'api','apiKey':'api','chatgpt':'subscription','chatgptAuthTokens':'subscription',
            }.get(value)
FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens')

def valid_count(value):
    return type(value) is int and value >= 0

def normalized_tier(value):
    return {'default':'standard', 'priority':'fast'}.get(value, value)

def charge(model, provider, usage, tier):
    if provider != 'openai': return None, 'Provedor sem tarifa cadastrada'
    card = PRICES['models'].get(model, {})
    rates = card.get(tier)
    if not rates: return None, 'Modelo ou modalidade sem tarifa cadastrada'
    if not all(valid_count(usage.get(k)) for k in ('input_tokens','cached_input_tokens','output_tokens')):
        return None, 'Contadores de tokens incompletos'
    long = usage['input_tokens'] > PRICES['longContextAbove'] and any(
        x is not None for t in card.values() for x in t['long'])
    rates = rates['long' if long else 'short']
    if rates[0] is None or rates[3] is None: return None, 'Tarifa de contexto longo indisponível'
    write = usage.get('cache_write_input_tokens')
    if write is None and rates[2] is None: write = 0
    if not valid_count(write): return None, 'Contagem de gravação de cache indisponível'
    inp, cached, output = (usage[k] for k in ('input_tokens','cached_input_tokens','output_tokens'))
    if cached + write > inp: return None, 'Contadores de entrada inconsistentes'
    if (cached and rates[1] is None) or (write and rates[2] is None):
        return None, 'Tarifa de cache indisponível'
    counts = (inp-cached-write, cached, write, output)
    parts = [Decimal(n)*Decimal(str(rate or 0))/Decimal(1000000) for n,rate in zip(counts,rates)]
    return parts, None

class UsageLedger:
    def __init__(self, thread_id):
        self.thread_id=thread_id
        self.provider=None
        self.turns={}
        self.active_turn=None
        self.turn_plans={}
        self.records={}
        self.unidentified=0
        self.reported_total=0

    def consume(self, kind, p):
        if kind=='session_meta': self.provider=p.get('model_provider')
        elif kind=='turn_context' and p.get('turn_id'):
            self.active_turn=p['turn_id']
            self.turns[p['turn_id']]={k:p.get(k) for k in ('model','service_tier','model_provider','auth_mode')}
        elif kind=='event_msg' and p.get('type')=='task_started':
            self.active_turn=p.get('turn_id')
        elif kind=='token_usage_record':
            if p.get('thread_id')!=self.thread_id: return
            total=(p.get('thread_token_usage') or {}).get('total_tokens')
            if valid_count(total): self.reported_total=max(self.reported_total,total)
            response=p.get('response_id')
            if not isinstance(response,str) or not response:
                self.unidentified+=1
                return
            # Same response updated or replayed replaces its previous counters.
            self.records[response]={k:p.get(k) for k in ('turn_id','model','model_provider','service_tier','usage','auth_mode')}
        elif kind=='event_msg' and p.get('type')=='token_count':
            plan=(p.get('rate_limits') or {}).get('plan_type')
            if self.active_turn and plan in CHATGPT_PLANS:
                self.turn_plans.setdefault(self.active_turn,set()).add(plan)
            total=((p.get('info') or {}).get('total_token_usage') or {}).get('total_tokens')
            if valid_count(total): self.reported_total=max(self.reported_total,total)

    def snapshot(self):
        groups={}
        for record in self.records.values():
            context=self.turns.get(record['turn_id'],{})
            model=record.get('model') or context.get('model') or 'Modelo não identificado'
            provider=record.get('model_provider') or context.get('model_provider') or self.provider
            key=(model,provider)
            if key not in groups:
                groups[key]={'model':model,'provider':provider,'calls':0,'tokens':dict.fromkeys(FIELDS,0),
                    'missingCounters':set(),'inferredModelCalls':0,'assumedTierCalls':0,
                    'billingCounts':{'api':0,'subscription':0,'unknown':0,'conflict':0},'plans':set(),
                    'rateCard':PRICES['models'].get(model,{}),
                    'estimates':{t:{'parts':[Decimal(0)]*4,'pricedCalls':0,'reasons':set(),'tiers':set()} for t in TIERS}}
            group=groups[key];group['calls']+=1
            if not record.get('model'):group['inferredModelCalls']+=1
            usage=record.get('usage') or {}
            for field in FIELDS:
                if valid_count(usage.get(field)):group['tokens'][field]+=usage[field]
                else:group['missingCounters'].add(field)
            explicit=auth_mode(record.get('auth_mode') or context.get('auth_mode'))
            plans=self.turn_plans.get(record['turn_id'],set())
            # Conflicting explicit API auth and ChatGPT plan evidence stays unknown.
            mode='conflict' if explicit=='api' and plans else explicit or ('subscription' if plans else 'unknown')
            group['billingCounts'][mode]+=1
            group['plans'].update(plans)
            actual_tier=normalized_tier(record.get('service_tier') or context.get('service_tier'))
            if not actual_tier:group['assumedTierCalls']+=1
            for tier in TIERS:
                estimate=group['estimates'][tier]
                if tier=='auto' and mode!='api': continue
                if tier=='inferred' and mode not in ('api','unknown'): continue
                selected=actual_tier or ('standard' if tier in ('auto','inferred') else tier)
                estimate['tiers'].add(selected)
                parts,reason=charge(model,provider,usage,selected)
                if reason:estimate['reasons'].add(reason)
                else:
                    estimate['pricedCalls']+=1
                    estimate['parts']=[a+b for a,b in zip(estimate['parts'],parts)]
        rows=[]
        for group in groups.values():
            for estimate in group['estimates'].values():
                estimate['usd']=float(sum(estimate['parts'])) if estimate['pricedCalls'] else None
                estimate['parts']=[float(x) for x in estimate['parts']]
                estimate['reasons']=sorted(estimate['reasons'])
                estimate['tiers']=sorted(estimate['tiers'])
            group['plans']=sorted(group['plans'])
            group['missingCounters']=sorted(group['missingCounters'])
            rows.append(group)
        rows.sort(key=lambda r:(-(r['tokens']['input_tokens']+r['tokens']['output_tokens']),r['model']))
        covered=sum(r['tokens']['input_tokens']+r['tokens']['output_tokens'] for r in rows)
        billing={mode:sum(r['billingCounts'][mode] for r in rows) for mode in ('api','subscription','unknown','conflict')}
        return {'billingCounts':billing,'plans':sorted({p for row in rows for p in row['plans']}),'rows':rows,'calls':len(self.records),'unidentifiedRecords':self.unidentified,
            'uncoveredTokens':max(0,self.reported_total-covered),'reportedTokens':self.reported_total,
            'currency':PRICES['currency'],'pricesVerifiedAt':PRICES['verifiedAt'],'priceSource':PRICES['source'],
            'scope':'recorded-responses-only'}
