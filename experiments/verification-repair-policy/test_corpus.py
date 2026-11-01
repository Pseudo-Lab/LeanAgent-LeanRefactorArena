"""Denominators, uncertainty, historical best and no-model corpus boundaries."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from common import HERE, read, sha
from corpus import CorpusRuntime, case_workflow, summarize
from test_contracts import protocol, evaluation


class CorpusContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.rt=CorpusRuntime(self.root,protocol(),libraries=Mock())
        self.case={'id':'one','problem_id':'P01','history_id':'history','historical_status':'proof_error',
                   'duplicate_of':None,'code':'theorem demo : True := by skip',
                   'best_before':{'code':self.rt.problem['reference']}}
        self.reference={'status':'completed','baseline':evaluation(),'tactics':['trivial']}

    def test_baseline_failure_stays_unmeasured_without_candidate_work(self):
        self.reference.update(status='stopped',reason='baseline_unverified',baseline=evaluation(False,error='timeout'))
        with patch.object(self.rt,'evaluate') as evaluate:
            result=case_workflow(self.rt,self.case,self.reference)
        evaluate.assert_not_called()
        self.assertIsNone(result['recovered'])
        self.assertIsNone(result['reproduced_failure'])
        self.assertIsNone(result['final_q'])

    def test_candidate_timeout_is_not_proof_failure(self):
        with patch.object(self.rt,'evaluate',side_effect=[evaluation(False,error='timeout'),evaluation()]), \
             patch('corpus.repair_candidate') as repair:
            result=case_workflow(self.rt,self.case,self.reference)
        repair.assert_not_called()
        self.assertIsNone(result['reproduced_failure'])
        self.assertIsNone(result['recovered'])
        self.assertTrue(result['final_valid'])

    def test_policy_rejection_does_not_enter_native_repair(self):
        rejected={'valid':False,'tokens':None,'environments':{},'error':{'kind':'policy'}}
        with patch.object(self.rt,'evaluate',side_effect=[rejected,evaluation()]),patch('corpus.repair_candidate') as repair:
            result=case_workflow(self.rt,self.case,self.reference)
        repair.assert_not_called()
        self.assertEqual(result['reason'],'policy_rejected')
        self.assertIs(result['recovered'],False)

    def test_recovery_does_not_imply_improvement_or_selection(self):
        repaired={**evaluation(tokens=20)}
        proof='theorem demo : True := by trivial'
        with patch.object(self.rt,'evaluate',side_effect=[evaluation(False),evaluation()]), \
             patch('corpus.repair_candidate',return_value={'status':'verified','nodes':[{}],'code':proof,'evaluation':repaired}):
            result=case_workflow(self.rt,self.case,self.reference)
        self.assertTrue(result['recovered'])
        self.assertFalse(result['improves_historical_best'])
        self.assertEqual(result['selected_origin'],'original')

    def test_final_proof_failure_falls_back_and_timeout_remains_unknown(self):
        for kind in ('compile','timeout'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                rt=CorpusRuntime(Path(d),protocol(),libraries=Mock())
                repaired={'status':'verified','nodes':[{}],'code':'theorem demo : True := by trivial','evaluation':evaluation(tokens=1)}
                with patch.object(rt,'evaluate',side_effect=[evaluation(False),evaluation(False,error=kind),evaluation()]) as evaluate, \
                     patch('corpus.repair_candidate',return_value=repaired):
                    result=case_workflow(rt,self.case,self.reference)
                if kind=='compile':
                    self.assertEqual(result['selected_origin'],'original')
                    self.assertEqual(evaluate.call_count,3)
                else:
                    self.assertIsNone(result['final_valid'])
                    self.assertIsNone(result['final_q'])
                    self.assertEqual(evaluate.call_count,2)

    def test_unknown_and_duplicates_have_separate_denominators(self):
        rows=[]
        for index,(recovery,duplicate) in enumerate([(True,None),(True,'0'),(False,None),(None,None)]):
            rows.append({'id':str(index),'problem_id':'P01','duplicate_of':duplicate,'reason':'observed',
                         'reproduced_failure':None if recovery is None else True,'native_extracted':recovery,
                         'recovered':recovery,'actual_api_calls':0})
        summary=summarize(rows)
        self.assertEqual(summary['all_occurrences']['recovery_rate_measured'],2/3)
        self.assertEqual(summary['unique_candidates']['recovery_rate_measured'],1/2)
        self.assertEqual(summary['all_occurrences']['recovery_unmeasured'],1)
        self.assertIsNone(summary['recursive_repair_effect'])

    def test_pinned_library_path_is_explicit_and_model_dispatch_is_blocked(self):
        self.rt.environment['lean_path']='/pinned/library'
        with patch('runtime.execute',return_value={}) as execute:
            self.rt._execute(['lean'],self.root,10)
        self.assertEqual(execute.call_args.kwargs['lean_path'],'/pinned/library')
        self.rt.libraries.verify.assert_called_once_with(full=False)
        with self.assertRaisesRegex(AssertionError,'forbidden'):
            self.rt.dispatch('repair',{})

    def test_committed_corpus_is_complete_and_has_no_future_best(self):
        corpus=read(HERE/'evaluation/corpus.json')
        self.assertEqual(corpus['counts'],{'histories':36,'generated':88,'nonpassing':49,'unique_nonpassing':44})
        history_failures=sum(not c['eligible'] for h in corpus['histories'] for c in h['candidates'])
        self.assertEqual(history_failures,len(corpus['cases']))
        seen={}
        for case in corpus['cases']:
            self.assertEqual(sha(case['code']),case['code_sha256'])
            self.assertLess(case['best_before']['source_call'],case['call'])
            if case['duplicate_of']:
                other=seen[case['duplicate_of']]
                self.assertEqual((case['problem_id'],case['code']),(other['problem_id'],other['code']))
            seen[case['id']]=case


if __name__=='__main__':
    unittest.main()
