import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugins/context-observer'))
from costs import UsageLedger, charge
from decimal import Decimal
A='conversation-A'
class CostsTests(unittest.TestCase):
    def ledger(self):
        x=UsageLedger(A);x.consume('session_meta',{'model_provider':'openai'})
        x.consume('turn_context',{'turn_id':'turn-A','model':'gpt-6-astra'})
        return x
    def record(self,x,id='response-A',model=None,inp=1000,cached=400,write=100,out=200,turn='turn-A',**extra):
        r={'thread_id':A,'response_id':id,'turn_id':turn,'usage':{'input_tokens':inp,'cached_input_tokens':cached,'cache_write_input_tokens':write,'output_tokens':out,'reasoning_output_tokens':100},**extra}
        if model:r['model']=model
        x.consume('token_usage_record',r)
        return r
    def test_rates_no_double_count_of_cache_or_reasoning(self):
        x=self.ledger();self.record(x)
        row=x.snapshot()['rows'][0];e=row['estimates']['standard']
        self.assertEqual(e['parts'],[.005,.0004,.00125,.01]);self.assertAlmostEqual(e['usd'],.01665)
    def test_duplicates_and_revised_response(self):
        x=self.ledger();r=self.record(x);x.consume('token_usage_record',r)
        self.assertEqual(x.snapshot()['calls'],1)
        self.record(x,out=300)
        self.assertEqual(x.snapshot()['rows'][0]['tokens']['output_tokens'],300)
    def test_models_mapped_by_turn_even_if_arriving_late(self):
        x=self.ledger();self.record(x,id='1');self.record(x,id='2',turn='turn-B')
        x.consume('turn_context',{'turn_id':'turn-B','model':'gpt-6-luna'})
        self.assertEqual({r['model']:r['calls'] for r in x.snapshot()['rows']},{'gpt-6-astra':1,'gpt-6-luna':1})
        self.record(x,id='3',model='gpt-6.1-sol');self.assertEqual(len(x.snapshot()['rows']),3)
    def test_unknown_model_and_provider_remain_unpriced(self):
        x=self.ledger();self.record(x,model='unknown');self.record(x,id='2',model_provider='azure')
        for r in x.snapshot()['rows']:self.assertIsNone(r['estimates']['standard']['usd'])
    def test_actual_tier_overrides_assumed(self):
        x=self.ledger();self.record(x,service_tier='priority')
        row=x.snapshot()['rows'][0]
        self.assertAlmostEqual(row['estimates']['standard']['usd'],.0333)
        self.assertEqual(row['estimates']['flex']['usd'],row['estimates']['standard']['usd'])
        self.assertEqual(row['assumedTierCalls'],0)
    def test_long_context_is_per_call_not_conversation_total(self):
        x=self.ledger();self.record(x,inp=272000,cached=0,write=0,out=0);self.record(x,id='2',inp=272001,cached=0,write=0,out=0)
        self.assertAlmostEqual(x.snapshot()['rows'][0]['estimates']['standard']['usd'],2.72+5.44002)
    def test_missing_cache_write_invalid_usage_and_unsupported_tier(self):
        usage={'input_tokens':1000,'cached_input_tokens':400,'output_tokens':200}
        self.assertIsNone(charge('gpt-6-astra','openai',usage,'standard')[0])
        self.assertIsNotNone(charge('gpt-5.3-codex','openai',usage,'standard')[0])
        usage['cache_write_input_tokens']=700
        self.assertIsNone(charge('gpt-6-astra','openai',usage,'standard')[0])
        self.assertIsNone(charge('gpt-6-astra','openai',usage,'mystery')[0])
    def test_coverage_and_compaction_do_not_reset_cost(self):
        x=self.ledger();self.record(x)
        x.consume('compacted',{})
        x.consume('event_msg',{'type':'token_count','info':{'total_token_usage':{'total_tokens':2000}}})
        self.assertEqual(x.snapshot()['uncoveredTokens'],800)
        self.assertEqual(x.snapshot()['calls'],1)
    def test_other_thread_and_missing_response_id_not_charged(self):
        x=self.ledger();self.record(x,thread_id='other');self.record(x,id=None)
        self.assertEqual(x.snapshot()['calls'],0);self.assertEqual(x.snapshot()['unidentifiedRecords'],1)
    def test_repeated_token_count_does_not_add_cost(self):
        x=self.ledger();self.record(x)
        for _ in range(3):x.consume('event_msg',{'type':'token_count','info':{'total_token_usage':{'total_tokens':1200}}})
        self.assertEqual(x.snapshot()['calls'],1);self.assertEqual(x.snapshot()['uncoveredTokens'],0)
if __name__=='__main__':unittest.main()
