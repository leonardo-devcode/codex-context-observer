import json,os,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PLUGIN=ROOT/'plugins/context-observer'
A='11111111-1111-1111-1111-111111111111'
class PackageTests(unittest.TestCase):
    def test_stdio_with_synthetic_local_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);sessions=home/'sessions';sessions.mkdir()
            rollout=sessions/'synthetic.jsonl'
            events=[{'type':'session_meta','payload':{'id':A,'model_provider':'openai'}},
                    {'type':'turn_context','payload':{'turn_id':'turn-A','model':'gpt-6-astra'}},
                    {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'PRIVATE-FIXTURE-MESSAGE'}]}}]
            rollout.write_text(''.join(json.dumps(x)+'\n' for x in events))
            with sqlite3.connect(home/'state_5.sqlite') as db:
                db.execute('CREATE TABLE threads (id TEXT, rollout_path TEXT, name TEXT, model TEXT)')
                db.execute('INSERT INTO threads VALUES (?,?,?,?)',(A,str(rollout),'Synthetic conversation','gpt-6-astra'))
            requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                      {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'open_context_panel','arguments':{'thread_id':A}}}]
            result=subprocess.run([sys.executable,str(PLUGIN/'mcp_server.py')],input=''.join(json.dumps(x)+'\n' for x in requests),text=True,capture_output=True,timeout=15,
                                  env={**os.environ,'CODEX_HOME':str(home),'CONTEXT_OBSERVER_CODEX':str(home/'no-codex')})
            self.assertEqual(result.returncode,0,result.stderr)
            replies=[json.loads(x) for x in result.stdout.splitlines()]
            self.assertEqual(replies[0]['result']['serverInfo']['version'],'0.4.1')
            s=replies[1]['result']['_meta']['snapshot']
            self.assertEqual(s['threadId'],A);self.assertTrue(s['verified'])
            self.assertNotIn('PRIVATE-FIXTURE-MESSAGE',result.stdout)
            self.assertEqual(s['costs']['currentAuth']['mode'],'unknown')
            self.assertEqual(s['binding']['mode'],'fixed')
    def test_portable_marketplace(self):
        catalog=json.loads((ROOT/'.agents/plugins/marketplace.json').read_text())
        self.assertEqual(catalog['plugins'][0]['source']['path'],'./plugins/context-observer')
        config=json.loads((PLUGIN/'.mcp.json').read_text())['mcpServers']['context_observer']
        self.assertEqual(config['args'],['${PLUGIN_ROOT}/launch.py'])
        self.assertNotIn('/Users/',json.dumps(config))
        self.assertTrue((PLUGIN/'launch.py').is_file())
if __name__=='__main__':unittest.main()
