"""Opt-in real Lean 4.26 checks. Fixture responses only; no API credentials."""
from contextlib import nullcontext, redirect_stdout
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'src'))
from lean_agent import diagnostics, status
from lean_agent.artifacts import read
import adapter
import policy
import run as experiment_run


@unittest.skipUnless(os.environ.get('REPAIR_POLICY_LEAN_TESTS') == '1', 'opt-in installed Lean tests')
class RealLeanTests(unittest.TestCase):
    def evidence(self):
        destination = os.environ.get('REPAIR_LEAN_EVIDENCE_DIR')
        if destination:
            folder = Path(destination) / self._testMethodName
            folder.mkdir(parents=True, exist_ok=False)
            return nullcontext(str(folder))
        return tempfile.TemporaryDirectory()

    def test_both_policy_loops_validate_and_replay_with_actual_lean(self):
        with self.evidence() as temporary, redirect_stdout(io.StringIO()):
            for selected_policy in policy.POLICIES:
                root = Path(temporary)/selected_policy
                experiment_run.prepare(root, selected_policy, HERE/'fixtures/responses.json')
                result = experiment_run.run(root)
                self.assertTrue(result['final_valid'])
                self.assertEqual(result['actual_api_calls'], 0)
                self.assertTrue(adapter.replay(root)['record_replay_passed'])
                folder = root/'SMOKE'
                self.assertEqual(read(folder/'attempt-001-observation.json')['policy_state'], 'incomplete')
                self.assertEqual(read(folder/'attempt-002-observation.json')['policy_state'], 'proof_error')
                second = read(folder/'attempt-002-decision.json')['decision']['action']
                self.assertEqual(second, 'repair_current' if selected_policy == policy.POLICIES[0] else 'replan_from_best')
                self.assertIsNotNone(status.inspect(folder)['final_result'])
                self.assertIn('by rfl', (folder/'selected.lean').read_text())

    def test_mixed_error_and_forbidden_axiom_never_become_incomplete(self):
        with self.evidence() as temporary, redirect_stdout(io.StringIO()):
            root = Path(temporary)/'mixed'
            experiment_run.prepare(root, policy.POLICIES[0], HERE/'fixtures/responses.json')
            folder = root/'SMOKE'
            problem = read(folder/'input.json')['problem']
            env = read(folder/'environment.json')
            runner = adapter.load_runner()
            cases = {'mixed': 'by\n  have h : True := False\n  skip', 'axiom': 'by sorry'}
            for label, body in cases.items():
                runner.evaluate(folder, label, problem['statement'] + ' := ' + body, problem, env)
                report = diagnostics.evaluation(read(folder/(label+'-result.json')), folder/label, folder, 'candidate')
                self.assertIn(policy.classify(report), {'proof_error', 'response_rejected'})


if __name__ == '__main__':
    unittest.main()
