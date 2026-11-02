"""Evidence audits must reject coherent-looking but mismatched receipts."""
import json
from pathlib import Path
import tempfile
import unittest

import report


class ReportAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.problem={'name':'sample'}
        self.code='theorem sample : True := by trivial\n'
        self.template='{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n{{DECLARATION}}\n'

    def fixture(self,axioms=None,source_code=None):
        folder=self.root/'fixed';folder.mkdir()
        runs=[]
        for index in range(4):
            nonce=f'{index:032x}' if index else None
            source=report.render(self.template,source_code or self.code,'sample',nonce)
            measurement={'target':'sample','raw':100,'scaled':0,'axioms':axioms or ['propext']}
            log=f'REFACTOR_EVAL {nonce} {json.dumps(measurement)}\n' if nonce else ''
            src=f'{index}.lean';name=f'{index}.log'
            (folder/src).write_text(source);(folder/name).write_text(log)
            row={'source':src,'log':name,'source_sha256':report.h.digest(source),
                 'log_sha256':report.h.digest(log),'returncode':0,'timed_out':False}
            if nonce:row['measurement']=measurement
            runs.append(row)
        report.h.write(self.root/'result.json',{'valid':True,'environments':{'fixed':{'valid':True,'runs':runs}}})

    def audit(self,nonces=None):
        return report.audit_evaluation(self.root,self.problem,self.template,self.code,
                                       nonces if nonces is not None else set())

    def test_valid_fresh_receipts(self):
        self.fixture();nonces=set();self.assertTrue(self.audit(nonces)['valid'])
        self.assertEqual(len(nonces),3)

    def test_reused_nonce_rejected(self):
        self.fixture()
        with self.assertRaises(AssertionError):self.audit({f'{1:032x}'})

    def test_matching_hashes_do_not_hide_wrong_candidate(self):
        self.fixture(source_code='theorem sample : True := by exact True.intro\n')
        with self.assertRaises(AssertionError):self.audit()

    def test_disallowed_axiom_rejected(self):
        self.fixture(axioms=['sorryAx'])
        with self.assertRaises(AssertionError):self.audit()

    def test_log_mutation_rejected(self):
        self.fixture();(self.root/'fixed/1.log').write_text('replaced')
        with self.assertRaises(AssertionError):self.audit()

    def test_dispatch_freshness_and_order(self):
        design={'planned_trials':[{'id':'first'},{'id':'second'}],'max_solver_parallelism':2}
        events=[{'event':'dispatched','trial_id':name,'agent':name,'fork_turns':'none'}
                for name in ('first','second')]
        events += [{'event':'completed','trial_id':name} for name in ('second','first')]
        path=self.root/'dispatch.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in events))
        self.assertEqual(report.audit_dispatch(self.root,design)['fresh_agents'],2)
        events[1]['agent']='first'
        path.write_text('\n'.join(json.dumps(e) for e in events))
        with self.assertRaises(AssertionError):report.audit_dispatch(self.root,design)

    def summary_fixture(self):
        state={'baseline':{'tokens':10,'raw_heartbeats':100},'best':{'tokens':2,'raw_heartbeats':20},
               'attempts':[{'valid':True},{'valid':False}],'step':2}
        summary={'baseline':dict(state['baseline']),'selected':dict(state['best']),
                 'valid_proposals':1,'proposal_count':2,'final_valid':True,'environment_unchanged':True}
        return summary,state

    def test_failed_final_cannot_enter_comparison(self):
        summary,state=self.summary_fixture();summary['final_valid']=False
        with self.assertRaisesRegex(AssertionError,'Final verification failed'):
            report.audit_final_summary(summary,state,{'valid':False})

    def test_summary_cannot_substitute_baseline_or_validity_count(self):
        summary,state=self.summary_fixture();summary['baseline']['raw_heartbeats']=200
        with self.assertRaisesRegex(AssertionError,'baseline differs'):
            report.audit_final_summary(summary,state,{'valid':True})
        summary,state=self.summary_fixture();summary['valid_proposals']=2
        with self.assertRaisesRegex(AssertionError,'validity count differs'):
            report.audit_final_summary(summary,state,{'valid':True})

    def test_only_recorded_preflight_failures_are_excluded(self):
        failed={'status':'failed','error':'Less than 1 GiB free; coordinator must inspect'}
        completed={'status':'completed'}
        recovery={'manifest':{'failed_preflight_invocations':[failed]}}
        self.assertEqual(report.completed_bridge_calls([failed,completed],recovery),[completed])
        with self.assertRaisesRegex(AssertionError,'Unaccounted'):
            report.completed_bridge_calls([failed,completed],None)

    def test_other_failed_evaluations_cannot_be_waived(self):
        failed={'status':'failed','error':'Environment failed'}
        recovery={'manifest':{'failed_preflight_invocations':[failed]}}
        with self.assertRaises(AssertionError):report.completed_bridge_calls([failed],recovery)

    def test_unknown_bridge_status_rejected(self):
        with self.assertRaises(AssertionError):report.completed_bridge_calls([{'status':'pending'}],None)


if __name__=='__main__':unittest.main()
