import importlib.util,json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'plugins/context-observer'
sys.path.insert(0,str(ROOT))
from mcp_server import Monitor,host_thread,dispatch,URI
from server import Collector
from composition import Composition, text_tokens
A='11111111-1111-1111-1111-111111111111'
B='22222222-2222-2222-2222-222222222222'

class PluginTests(unittest.TestCase):
    def monitor(self):
        m=Monitor()
        m.snapshot=lambda id:{'threadId':id,'verified':True}
        return m

    def test_metadata(self):
        self.assertEqual(host_thread({'x-codex-turn-metadata':json.dumps({'thread_id':A})}),A)
        self.assertEqual(host_thread({'openai/threadId':B}),B)
        self.assertIsNone(host_thread({'openai/session':A}))
        self.assertIsNone(host_thread({'threadId':'../../some-file'}))

    def test_no_recent_session_guess(self):
        r=self.monitor().call('open_context_panel',{}, {})
        self.assertTrue(r['isError'])
        self.assertNotIn('snapshot',r['_meta'])

    def test_independent_panels_stay_fixed_despite_host_switch(self):
        m=self.monitor()
        a=m.call('open_context_panel',{}, {'threadId':A})['_meta']['binding']
        b=m.call('open_context_panel',{}, {'threadId':B})['_meta']['binding']
        self.assertEqual(m.call('read_context_panel',{'binding':a},{})['_meta']['snapshot']['threadId'],A)
        self.assertEqual(m.call('read_context_panel',{'binding':b},{})['_meta']['snapshot']['threadId'],B)
        self.assertEqual(m.call('read_context_panel',{'binding':a},{'threadId':B})['_meta']['snapshot']['threadId'],A)
        self.assertEqual(m.call('read_context_panel',{'binding':b},{'threadId':A})['_meta']['snapshot']['threadId'],B)
        with self.assertRaises(ValueError): m.call('read_context_panel',{'binding':'unknown'}, {})

    def test_host_wins_over_manual_id(self):
        r=self.monitor().call('open_context_panel',{'thread_id':B},{'threadId':A})
        self.assertEqual(r['structuredContent']['threadId'],A)

    def test_resource_is_self_contained(self):
        r=dispatch('resources/read',{'uri':URI},self.monitor())
        html=r['contents'][0]['text']
        self.assertNotIn('src="/app.js"',html)
        self.assertTrue('__PLUGIN_SCRIPT__' not in html,'O HTML ainda contém um marcador de compilação.')
        self.assertIn('read_context_panel',html)

    def test_expired_binding_cannot_retarget_to_current_host(self):
        m=self.monitor()
        for meta in ({'threadId':B},{}):
            with self.assertRaisesRegex(ValueError,'Vínculo expirado'):
                m.call('read_context_panel',{'binding':'expired'},meta)
        self.assertEqual(len(m.bindings),0)

    def test_fixed_panel_still_collects_new_measurements(self):
        m=self.monitor()
        calls=[]
        def snapshot(id):
            calls.append(id)
            return {'threadId':id,'verified':True,'measurement':len(calls)}
        m.snapshot=snapshot
        opened=m.call('open_context_panel',{}, {'threadId':A})
        binding=opened['_meta']['binding']
        updated=m.call('read_context_panel',{'binding':binding},{'threadId':B})['_meta']['snapshot']
        self.assertEqual(updated['measurement'],2)
        self.assertEqual(calls,[A,A])
        self.assertEqual(updated['binding']['mode'],'fixed')

    def test_compaction_timeline_ignores_repeated_pre_compaction_measurement(self):
        c=Collector('/unused',A)
        c.consume({'type':'session_meta','payload':{'id':A}})
        def measurement(at,inp,total,window=1000):
            return {'type':'event_msg','timestamp':at,'payload':{'type':'token_count','info':{
                'last_token_usage':{'input_tokens':inp},'total_token_usage':{'total_tokens':total},'model_context_window':window}}}
        old=measurement('2026-10-16T10:00:00Z',900,4000)
        c.consume(old)
        c.consume({'type':'compacted','timestamp':'2026-10-16T10:00:02Z','payload':{'replacement_history':[]}})
        c.consume({'type':'event_msg','payload':{'type':'context_compacted'}})
        c.consume(old)
        self.assertIsNone(c.last)
        self.assertIsNone(c.compaction_history[0]['after'])
        self.assertEqual(c.compactions,1)
        c.consume(measurement('2026-10-16T10:00:04Z',200,4200))
        self.assertEqual(c.compaction_history[0]['differenceTokens'],700)
        c.consume(measurement('2026-10-16T10:00:06Z',250,4450))
        self.assertEqual(c.compaction_history[0]['after']['input'],200)
        c.consume({'type':'compacted','payload':{'replacement_history':[]}})
        c.consume(measurement('2026-10-16T10:00:08Z',280,4730,2000))
        self.assertEqual(c.compaction_history[1]['differenceTokens'],-30)
        self.assertEqual(c.compaction_history[1]['after']['window'],2000)

    def test_compaction_rebuilds_readable_history_without_old_tokens(self):
        c=Composition()
        msg=lambda text:{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}
        c.consume('response_item',msg('old '*1000))
        c.consume('session_meta',{'base_instructions':{'text':'old base'}})
        c.rebuild_after_compaction({'replacement_history':[msg('retained'),{'type':'compaction','encrypted_content':'SECRET'}]})
        c.consume('response_item',msg('new'))
        s=c.snapshot(); rows={r['id']:r for r in s['rows']}
        self.assertEqual(rows['messages']['tokens'],text_tokens('retained')+text_tokens('new'))
        self.assertIsNone(rows['base']['tokens'])
        self.assertEqual(s['encryptedBlocksExcluded'],1)
        self.assertTrue(s['replacementHistoryAvailable'])
        self.assertNotIn('SECRET',json.dumps(s))
        c.consume('world_state',{'state':{'host_skills':{'body':'new catalog'}}})
        self.assertEqual(next(r['tokens'] for r in c.snapshot()['rows'] if r['id']=='skills'),text_tokens('new catalog'))

    def test_missing_replacement_counts_only_new_records_and_next_compaction_resets(self):
        c=Composition()
        c.consume('response_item',{'type':'function_call','arguments':'old'})
        c.rebuild_after_compaction({})
        self.assertTrue(c.snapshot()['compactionInvalidated'])
        self.assertTrue(all(r['tokens'] is None for r in c.snapshot()['rows']))
        c.consume('response_item',{'type':'function_call','arguments':'new'})
        self.assertEqual(next(r['tokens'] for r in c.snapshot()['rows'] if r['id']=='tool_io'),text_tokens('new'))
        c.rebuild_after_compaction({'replacement_history':[]})
        self.assertTrue(all(r['tokens'] is None for r in c.snapshot()['rows']))

if __name__=='__main__': unittest.main()
