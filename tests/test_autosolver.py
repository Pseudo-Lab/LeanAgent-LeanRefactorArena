"""Native search decisions, one-charge ancestry, scope and offline replay."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import artifacts as a, autosolver, harness as h, models
from test_harness import FakeEvaluator
ROOT=Path(__file__).resolve().parents[1]


def native_report(code, closed=False, kind='proof'):
    goal={'target':'n + 0 = n','local_context':[{'name':'n','type':'Nat','value':None,'implementation_detail':False}]}
    start=code.index('by');end=len(code.rstrip())
    if closed:
        inner=code.index('by',code.index('exact ('))
        states=[{'start':len(code[:inner].encode()),'end':len(code[:end].encode()),
                 'syntax_kind':'Lean.Parser.Term.byTactic','depth':0,'before':[goal],'after':[]}]
        errors=[]
    else:
        body=start+2
        while code[body].isspace():body+=1
        pos=len(code[:body].encode())
        states=[{'start':pos,'end':len(code[:end].encode()),'syntax_kind':'Lean.Parser.Tactic.exact',
                 'depth':0,'before':[goal],'after':[goal]}]
        errors=[{'position':pos,'message':'unknown identifier','code':None}]
    return {'kind':kind,'source_sha256':a.sha(code),'errors':errors,'tactics':states,
            'blocks':[{'start':len(code[:start].encode()),'end':len(code[:end].encode())}],
            'seconds':0.01,'returncode':0 if closed else 1}


class NativeFake(FakeEvaluator):
    def __init__(self, kind='proof', reject_verified=False):
        super().__init__();self.inspections=[];self.kind=kind;self.reject_verified=reject_verified
    def inspect_native(self,code,problem,environment,output,*,timeout,memory):
        self.inspections.append(code)
        result=native_report(code,'rfl' in code,self.kind)
        a.write(output/'result.json',result)
        return result
    def evaluate(self,code,problem,environments,output,runs):
        if self.reject_verified and output.name=='evaluation' and output.parent.name=='autosolver':
            code+='\n-- False.elim'
        return super().evaluate(code,problem,environments,output,runs)


class AutoSolverTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir=os.environ.get('PROJECT_CACHE_DIR'));self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.output=self.root/'run'
        self.config=a.read(ROOT/'configs/actions-smoke.json')
        for k in ['problem','template','project','prompt']:
            self.config[k]=str((ROOT/'configs'/self.config[k]).resolve())
        self.config['agent']['corpus']=str(ROOT/'examples/actions/corpus.json')
        self.config['agent']['autosolver']={'tactics':['rfl'],'max_attempts':1}
        self.config['model']={'backend':'openrouter','id':'synthetic/model','provider':'test','max_tokens':100,'timeout_seconds':1}
        self.config['limits']['max_calls']=1
        self.config['limits']['max_request_characters']=100000
        self.packets=[];self.dispatched=0
    def run_case(self,evaluator=None,actions=None,unknown_cost=False):
        actions=actions or [{'action':'propose','parent_id':'c000','strategy':'attempt','proof':'by False.elim (by trivial)'}]
        self.evaluator=evaluator or NativeFake()
        def query(body,*args):
            self.packets.append(json.loads(body['messages'][1]['content']))
            action=actions[self.dispatched];self.dispatched+=1
            return {'id':str(self.dispatched),'choices':[{'message':{'content':a.canonical(action)}}],
                    'usage':{} if unknown_cost else {'cost':'0.01'}}
        a.write(self.root/'config.json',self.config)
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic-only'}):
            return h.run(self.root/'config.json',self.output,evaluator=self.evaluator,query=query)
    def test_one_paid_call_registers_failed_parent_and_verified_automatic_child(self):
        result=self.run_case();s=result['state'];memory=s['exploration']
        self.assertFalse(memory['candidates']['c001']['valid'])
        child=memory['candidates']['c001-auto'];self.assertTrue(child['valid']);self.assertEqual(child['parent_id'],'c001')
        self.assertEqual(memory['best_candidate_id'],'c001-auto');self.assertEqual(s['cost_usd'],'0.01')
        self.assertEqual(s['calls'],1);self.assertEqual(result['autosolver']['model_calls'],0)
        self.assertEqual(result['autosolver']['verified_candidates'],1)
        self.assertEqual(len(self.evaluator.calls),4)  # original, raw failure, derived verification, final
        self.assertEqual(len(self.evaluator.inspections),2)
        with patch.object(models,'query',side_effect=AssertionError('no API replay')), \
             patch.object(NativeFake,'inspect_native',side_effect=AssertionError('no native replay')):
            self.assertTrue(h.replay(self.output)['record_replay_passed'])
    def test_next_request_can_read_automatic_candidate_and_keeps_both_ancestries(self):
        self.config['limits']['max_calls']=2
        result=self.run_case(actions=[{'action':'propose','parent_id':'c000','strategy':'test','proof':'by False.elim (by trivial)'},
                                      {'action':'read_candidate','candidate_id':'c001-auto'}])
        packet=self.packets[1]
        self.assertEqual(packet['exploration']['best_candidate_id'],'c001-auto')
        self.assertTrue(packet['latest']['feedback']['autosolver']['verified'])
        self.assertEqual(result['state']['cost_usd'],'0.02')
        self.assertTrue(h.replay(self.output)['record_replay_passed'])
    def test_local_completion_does_not_bypass_full_verification(self):
        result=self.run_case(NativeFake(reject_verified=True))
        self.assertFalse(result['state']['exploration']['candidates']['c001-auto']['valid'])
        self.assertEqual(result['state']['exploration']['best_candidate_id'],'c000')
        self.assertEqual(result['autosolver']['verified_candidates'],0)
        self.assertTrue(h.replay(self.output)['record_replay_passed'])
    def test_timeout_or_missing_native_support_preserves_original_feedback_and_best(self):
        result=self.run_case(NativeFake(kind='extraction_unavailable'))
        self.assertEqual(result['state']['latest']['feedback']['autosolver']['status'],'unavailable')
        self.assertNotIn('c001-auto',result['state']['exploration']['candidates'])
        self.assertEqual(result['state']['exploration']['best_candidate_id'],'c000')
        self.assertTrue(h.replay(self.output)['record_replay_passed'])
    def test_unknown_model_cost_never_starts_native_search(self):
        result=self.run_case(unknown_cost=True)
        self.assertEqual(result['stop_reason'],'unknown_cost');self.assertEqual(self.evaluator.inspections,[])
        self.assertFalse((self.output/'steps/001/autosolver').exists())
        self.assertTrue(h.replay(self.output)['record_replay_passed'])
    def test_portfolio_quota_counts_proposals_and_auto_children_keep_owner_after_barrier(self):
        self.config['agent']['portfolio']={'scout_evaluations':1,'merger_evaluations':1}
        self.config['limits']['max_calls']=4
        actions=[{'action':'propose','parent_id':'c000','strategy':str(i),'proof':f'by False.elim (by trivial) -- {i}'} for i in range(4)]
        result=self.run_case(actions=actions);scope=result['state']['portfolio']
        self.assertEqual(result['stop_reason'],'portfolio_complete')
        self.assertEqual(scope['evaluations'],{'scout-a':1,'scout-b':1,'scout-c':1,'merge':1})
        for step,branch in enumerate(['scout-a','scout-b','scout-c','merge'],1):
            self.assertEqual(scope['owners'][f'c{step:03}-auto'],branch)
        for packet in self.packets[1:3]:
            self.assertEqual([r['candidate_id'] for r in packet['exploration']['candidates']],['c000'])
            self.assertIsNone(packet['latest'])
        self.assertTrue(h.replay(self.output)['record_replay_passed'])
    def test_resealed_native_decision_tampering_is_rejected(self):
        self.run_case();p=self.output/'steps/001/autosolver/search.json';data=a.read(p)
        data['outcome']['candidate_code']='theorem forged : True := by trivial'
        p.write_text(a.canonical(data));(self.output/'artifacts.json').unlink();h.seal(self.output)
        with self.assertRaisesRegex(ValueError,'outcome differs'):
            h.replay(self.output)
    def test_search_budget_and_tactic_config_are_bounded(self):
        for settings in [{'tactics':['rfl\nrun_tac unsafe']},{'max_attempts':True},{'search_seconds':float('inf')}]:
            with self.assertRaises(ValueError):autosolver.validate(settings)
        config=copy.deepcopy(self.config);config['agent']['autosolver']={'tactics':['rfl'],'search_seconds':1}
        code=a.read(Path(self.config['problem']))['reference']
        observed=[]
        def invoke(source,timeout,memory):
            observed.append(source);return native_report(source),2.0
        result=autosolver._search(autosolver.settings(config),code,invoke)
        self.assertEqual(result['status'],'time_limit');self.assertEqual(len(observed),1)


if __name__=='__main__':unittest.main()
