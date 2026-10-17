import sys,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugins/context-observer'))
from account_status import AccountStatus
import test_costs
class BillingTests(unittest.TestCase):
    ledger=test_costs.CostsTests.ledger
    record=test_costs.CostsTests.record
    def test_plan_scoped_to_turn(self):
        x=self.ledger();self.record(x)
        x.consume('event_msg',{'type':'token_count','rate_limits':{'plan_type':'prolite'}})
        x.consume('event_msg',{'type':'task_started','turn_id':'turn-B'})
        self.record(x,id='2',turn='turn-B',model='gpt-6-astra')
        s=x.snapshot();self.assertEqual(s['billingCounts'],{'api':0,'subscription':1,'unknown':1,'conflict':0})
        self.assertEqual(s['rows'][0]['estimates']['inferred']['pricedCalls'],1)
        self.assertIsNone(s['rows'][0]['estimates']['auto']['usd'])
    def test_recorded_api_and_priority(self):
        x=self.ledger();self.record(x,auth_mode='apikey',service_tier='priority')
        s=x.snapshot();self.assertEqual(s['billingCounts']['api'],1)
        self.assertAlmostEqual(s['rows'][0]['estimates']['auto']['usd'],.0333)
    def test_mixed_history_and_conflict(self):
        x=self.ledger();self.record(x,id='1',auth_mode='chatgpt')
        self.record(x,id='2',auth_mode='apiKey');self.record(x,id='3')
        s=x.snapshot();self.assertEqual(s['rows'][0]['estimates']['auto']['pricedCalls'],1)
        self.assertEqual(s['rows'][0]['estimates']['inferred']['pricedCalls'],2)
        x.consume('event_msg',{'type':'token_count','rate_limits':{'plan_type':'plus'}})
        s=x.snapshot();self.assertEqual(s['billingCounts']['conflict'],1)
        self.assertIsNone(s['rows'][0]['estimates']['inferred']['usd'])
    def test_unknown_auth_does_not_imply_subscription(self):
        x=self.ledger();self.record(x,auth_mode='agentIdentity')
        self.assertEqual(x.snapshot()['billingCounts']['unknown'],1)
class AccountTests(unittest.TestCase):
    @patch('account_status.shutil.which',return_value='/local/codex')
    @patch('account_status.subprocess.run')
    def test_api_output_is_not_exposed_and_cached(self,run,which):
        run.return_value=subprocess.CompletedProcess([],0,'','Logged in using an API key - sk-sensitive-example')
        a=AccountStatus('/tmp/other-account');s=a.read();self.assertEqual(s['mode'],'api')
        self.assertNotIn('sensitive',str(s));self.assertEqual(a.read(),s);run.assert_called_once()
        self.assertEqual(run.call_args.kwargs['env']['CODEX_HOME'],'/tmp/other-account')
    @patch('account_status.shutil.which',return_value='/local/codex')
    @patch('account_status.subprocess.run')
    def test_failures_and_other_account(self,run,which):
        for result,expected in [(subprocess.CompletedProcess([],0,'Logged in using ChatGPT',''),'subscription'),(subprocess.CompletedProcess([],1,'Logged in using an API key',''),'unknown'),(subprocess.CompletedProcess([],0,'unexpected format',''),'unknown')]:
            run.return_value=result;self.assertEqual(AccountStatus('/tmp').read()['mode'],expected)
        run.side_effect=subprocess.TimeoutExpired('codex',4)
        self.assertEqual(AccountStatus('/tmp').read()['mode'],'unknown')
if __name__=='__main__':unittest.main()
