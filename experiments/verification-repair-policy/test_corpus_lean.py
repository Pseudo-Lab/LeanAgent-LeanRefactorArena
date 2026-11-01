"""Small actual-Lean check of the corpus adapter; not a performance sample."""
from dataclasses import asdict
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common import Limits, REPO, TACTICS
from corpus import reference_workflow, case_workflow
from runtime import Runtime
from lean_agent import preflight


@unittest.skipUnless(os.environ.get('REPAIR_RUN_LEAN_TESTS')=='1','Opt-in actual Lean 4.26 check')
class CorpusLean(unittest.TestCase):
    def test_shared_original_auto_repair_and_process_free_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            project=REPO/'examples/first-harness/project'
            statement='theorem demo (P : Prop) (h : P) : P'
            problem={'name':'demo','statement':statement,'reference':statement+' := by exact h\n'}
            environment={'id':'core','project':str(project),'toolchain':'leanprover/lean4:v4.26.0',
                         'command':preflight.resolve_command(['lean','-j1'],'leanprover/lean4:v4.26.0',project),
                         'timeout_seconds':10,'template':'{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n{{DECLARATION}}\n'}
            protocol={'problem':problem,'environment':environment,'environment_sha256':'core','limits':asdict(Limits()),
                      'tactics':list(TACTICS),'simulated_budget_usd':'0','simulated_reservation_usd':'0.02'}
            (root/'reference').mkdir()
            (root/'case').mkdir()
            reference=reference_workflow(Runtime(root/'reference',protocol))
            self.assertEqual(reference['status'],'completed')
            case={'id':'test','problem_id':'core','history_id':'test','historical_status':'incomplete',
                  'duplicate_of':None,'code':statement+' := by skip','best_before':{'code':problem['reference']}}
            result=case_workflow(Runtime(root/'case',protocol),case,reference)
            self.assertTrue(result['recovered'])
            self.assertEqual(result['actual_api_calls'],0)
            with patch('subprocess.Popen',side_effect=AssertionError('Replay started process')):
                rt=Runtime(root/'reference',protocol,replay=True)
                self.assertEqual(reference_workflow(rt),reference);rt.tape.assert_complete()
                rt=Runtime(root/'case',protocol,replay=True)
                self.assertEqual(case_workflow(rt,case,reference),result);rt.tape.assert_complete()


if __name__=='__main__':
    unittest.main()
