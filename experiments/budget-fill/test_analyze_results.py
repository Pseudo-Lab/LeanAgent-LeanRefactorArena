"""Post-analysis regressions; no provider, Lean or actual experiment mutations."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import analyze_results as a


class AnalysisTests(unittest.TestCase):
    def test_live_or_unverifiable_manager_is_not_finalized(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            a.write_json(root/'operator/started.json',{'pid':12345})
            a.write_json(root/'operator/finished.json',{'status':'needs_review'})
            with self.assertRaisesRegex(ValueError,'still alive'):
                a.assert_manager_exited(root,probe=lambda pid,sig:None)
            with self.assertRaisesRegex(ValueError,'Cannot verify'):
                a.assert_manager_exited(root,probe=Mock(side_effect=PermissionError()))
            self.assertTrue(a.assert_manager_exited(root,probe=Mock(side_effect=ProcessLookupError()))['process_exited'])

    def test_missing_finished_evidence_prevents_result_package_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'run';output=Path(temp)/'result';report=Path(temp)/'REPORT.md'
            with self.assertRaises(FileNotFoundError):a.finalize(root,output,report)
            self.assertFalse(output.exists());self.assertFalse(report.exists())

    def test_stopped_verified_trial_is_terminal_but_not_quota_complete(self):
        trials=[{'arm':arm,'row':row,'status':'completed','receipt_audit_passed':True,'proof_audit_passed':True}
                for arm in a.ARMS for row in a.ROWS]
        trials[-1]['status']='stopped'
        flags=a.terminal_flags(trials)
        self.assertTrue(flags['all_trials_terminal']);self.assertFalse(flags['all_trials_completed'])
        self.assertEqual(flags['stopped_trials'],1)
        trials[-1]['proof_audit_passed']=False
        self.assertFalse(a.terminal_flags(trials)['all_trials_terminal'])
        with self.assertRaisesRegex(ValueError,'six authorized'):a.terminal_flags(trials[:-1])

    def test_summary_score_or_actual_sample_mismatch_fails(self):
        baseline={'tokens':100,'raw_heartbeats':1000,'raw_samples':[1000]*3}
        final={'tokens':50,'raw_heartbeats':400,'raw_samples':[400]*3}
        summary={'baseline':baseline,'final':final}
        self.assertEqual(a.checked_metrics(summary,baseline,final,lambda x:x),(baseline,final))
        changed=deepcopy(summary);changed['final']['tokens']=1
        with self.assertRaisesRegex(ValueError,'score inputs'):a.checked_metrics(changed,baseline,final,lambda x:x)
        one={**final,'raw_samples':[400]}
        with self.assertRaisesRegex(ValueError,'three actual'):a.checked_metrics({'baseline':baseline,'final':one},baseline,one,lambda x:x)

    def fixture(self):
        before={'sha256':'best','valid':True,'step':7,'tokens':50,'raw_heartbeats':500}
        later={'sha256':'later','valid':True,'step':10,'tokens':40,'raw_heartbeats':400}
        state={'exploration':{'candidates':{'c007':before,'c010':later}}}
        steps=[{'step':9,'reduced_output':False,'best_sha256_after':'best'},
               {'step':10,'reduced_output':True,'spent_before_usd':'2.77','cost_usd':'.03','output_tokens':7000,
                'request_best_sha256':'best','reservation_usd':'.23','valid_candidate':True,'best_sha256_after':'best','finish_reason':'stop'},
               {'step':11,'reduced_output':True,'spent_before_usd':'2.80','cost_usd':'.04','output_tokens':4000,
                'reservation_usd':'.20','valid_candidate':True,'best_sha256_after':'best','finish_reason':'stop'}]
        return state,steps,{'tokens':100,'raw_heartbeats':1000}

    def test_same_selected_source_does_not_claim_tail_gain(self):
        state,steps,baseline=self.fixture()
        result=a.tail_observation(state,{'selected':{'sha256':'best'}},steps,baseline)
        self.assertEqual(result['tail_cost_usd'],'0.07')
        self.assertEqual(result['incremental_selected_primary_screening_score_delta'],0)
        self.assertFalse(result['selected_source_created_in_tail'])
        self.assertTrue(result['selected_source_unchanged_from_pre_tail'])

    def test_new_selected_source_records_screening_gain_and_scope(self):
        state,steps,baseline=self.fixture()
        result=a.tail_observation(state,{'selected':{'sha256':'later'}},steps,baseline)
        self.assertTrue(result['selected_source_created_in_tail'])
        self.assertAlmostEqual(result['incremental_selected_primary_screening_score_delta'],20/3)
        self.assertIn('not independently remeasured',result['score_delta_scope'])

if __name__=='__main__':unittest.main()
