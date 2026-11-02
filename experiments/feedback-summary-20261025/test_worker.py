"""Run the inherited budget/baseline checks against the new worker bridge."""
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent / 'first-harness-jwkweon'
sys.path[:0] = [str(HERE), str(HARNESS)]
import harness as h
import test_subagent_trials as inherited

spec = importlib.util.spec_from_file_location('summary_worker', HERE / 'worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
inherited.worker = worker
OriginalFake = inherited.FakeEvaluator
LOG = 'unit.lean:1:1: error: unsolved goals\nn : Nat\n⊢ n = n\n'


class ArchivedFake(OriginalFake):
    def evaluate(self, code, problem, environments, output, runs):
        result = super().evaluate(code, problem, environments, output, runs)
        row = result['environments']['fixed']
        if (row.get('error') or {}).get('kind') == 'compile':
            (output / 'fixed').mkdir()
            (output / 'fixed/check.log').write_text(LOG)
            row['runs'] = [{'returncode': 1, 'timed_out': False, 'log': 'check.log'}]
        return result


inherited.FakeEvaluator = ArchivedFake
ProposalBudgetTests = inherited.ProposalBudgetTests


class SemanticBridgeTests(inherited.ProposalBudgetTests):
    # unittest inherits test methods, so expose only this extra test separately
    # through the explicit load_tests suite below.
    def test_semantic_failure_finish_and_replay_without_external_calls(self):
        self.config.update(max_proposals=1, error_feedback_mode='semantic_v1')
        self.freeze_baseline()
        (self.root / 'input/summarizer-prompt.txt').write_text('Fixed test prompt')
        worker.init(self.root)
        diagnostic = worker.format_feedback.__globals__['legacy']._extract(LOG, str(self.root))
        summary = {**diagnostic, 'message': 'The goal remains unproved.', 'truncated': True}
        h.write(self.root / 'steps/001/summary/response.json', summary)
        response = self.root / 'responses/001.json'
        h.write(response, {'proof': 'by exact False.elim (by contradiction)'})
        worker.submit(self.root, response)
        self.assertEqual(h.read(self.root / 'steps/001/summary/receipt.json')['status'], 'accepted')
        worker.finish(self.root)
        from unittest.mock import patch
        with patch.object(worker, 'LeanEvaluator', side_effect=AssertionError('external Lean call')):
            worker.replay(self.root)


def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(ProposalBudgetTests)
    suite.addTest(SemanticBridgeTests('test_semantic_failure_finish_and_replay_without_external_calls'))
    return suite


if __name__ == '__main__':
    unittest.main()
