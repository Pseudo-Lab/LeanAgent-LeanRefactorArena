"""Proposal-budget tests using deterministic local measurements; no Lean/API."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import harness
import subagent_trials as worker
from test_harness import FakeEvaluator


class ProposalBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'input').mkdir()
        (self.root / 'project').mkdir()
        (self.root / 'responses').mkdir()
        shutil.copyfile(harness.BASE / 'fixtures/problem.json', self.root / 'input/problem.json')
        shutil.copyfile(harness.BASE / 'fixtures/context.lean.in', self.root / 'input/context.lean.in')
        shutil.copyfile(harness.BASE / 'prompt.txt', self.root / 'input/prompt.txt')
        self.config = {'trial_id': 'unit', 'problem_id': 'smoke', 'max_proposals': 10}
        self.save_config()
        self.evaluator = FakeEvaluator()
        self.patcher = patch.object(worker, 'LeanEvaluator', return_value=self.evaluator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def save_config(self):
        (self.root / 'trial.json').write_text(json.dumps(self.config))

    def submit(self, index):
        response = self.root / f'responses/{index:03}.json'
        harness.write(response, {'proof': 'by rfl'})
        worker.submit(self.root, response)

    def freeze_baseline(self):
        result = {'valid': True, 'tokens': 10, 'error': None,
                  'environments': {'fixed': {'valid': True, 'error': None,
                      'runs': [{'measurement': {'raw': raw}} for raw in (900, 1000, 1100)]}}}
        harness.write(self.root / 'baseline/result.json', result)
        harness.write(self.root / 'baseline/fixed/archive.json', {'verified': True})
        self.config.update(baseline_mode='frozen', frozen_baseline_sha256=harness.digest(
            (self.root / 'baseline/result.json').read_bytes()))
        self.save_config()
        return result

    def baseline_files(self, root=None):
        return {str(p.relative_to(root or self.root)): p.read_bytes()
                for p in ((root or self.root) / 'baseline').rglob('*') if p.is_file()}

    def test_ten_steps_are_available_and_eleventh_is_rejected(self):
        worker.init(self.root)
        for step in range(1, 11):
            request = harness.read(self.root / f'requests/{step:03}.json')
            self.assertEqual(request['total_steps'], 10)
            self.assertEqual(request['step'], step)
            self.submit(step)
        self.assertFalse((self.root / 'requests/011.json').exists())
        with self.assertRaisesRegex(ValueError, 'exhausted its 10'):
            worker.submit(self.root, self.root / 'responses/010.json')
        worker.finish(self.root)
        summary = harness.read(self.root / 'summary.json')
        self.assertEqual(summary['proposal_count'], 10)
        self.assertTrue(summary['final_valid'])
        self.assertIsNone(summary['codex_cost_usd'])
        worker.replay(self.root)

    def test_ten_step_trial_cannot_finish_after_three(self):
        worker.init(self.root)
        for step in range(1, 4):
            self.submit(step)
        with self.assertRaisesRegex(ValueError, 'Exactly 10'):
            worker.finish(self.root)
        self.assertTrue((self.root / 'requests/004.json').exists())

    def test_three_step_setting_still_finishes_and_replays(self):
        self.config['max_proposals'] = 3
        self.save_config()
        worker.init(self.root)
        for step in range(1, 4):
            self.submit(step)
        worker.finish(self.root)
        worker.replay(self.root)

    def test_invalid_budgets_are_rejected_before_initialization(self):
        for value in (0, -1, True, 3.5, '10'):
            self.config['max_proposals'] = value
            self.save_config()
            with self.assertRaisesRegex(ValueError, 'positive integer'):
                worker.init(self.root)
        self.assertFalse((self.root / 'start.json').exists())

    def test_default_timeout_and_measured_baseline_remain_compatible(self):
        _, _, environment = worker.load(self.root)
        self.assertEqual(environment['timeout_seconds'], 180)
        worker.init(self.root)
        self.assertEqual(self.evaluator.calls, [self.root / 'baseline'])
        self.assertEqual(harness.read(self.root / 'requests/001.json')['baseline'],
                         harness.read(self.root / 'states/000.json')['baseline'])

    def test_configured_timeout_reaches_every_evaluation(self):
        self.config.update(lean_timeout_seconds=420, max_proposals=1)
        self.save_config()
        with patch.object(self.evaluator, 'evaluate', wraps=self.evaluator.evaluate) as evaluate:
            worker.init(self.root)
            self.submit(1)
            worker.finish(self.root)
        self.assertEqual(evaluate.call_count, 3)
        for call in evaluate.call_args_list:
            self.assertEqual(call.args[2][0]['timeout_seconds'], 420)

    def test_invalid_timeouts_are_rejected_before_initialization(self):
        for value in (0, -1, True, False, 3.5, '180', None):
            with self.subTest(timeout=value):
                self.config['lean_timeout_seconds'] = value
                self.save_config()
                with self.assertRaisesRegex(ValueError, 'lean_timeout_seconds.*positive integer'):
                    worker.init(self.root)
        self.assertFalse((self.root / 'start.json').exists())
        self.assertFalse((self.root / 'states').exists())
        self.assertEqual(self.evaluator.calls, [])

    def test_invalid_baseline_modes_are_rejected_before_initialization(self):
        for value in ('other', '', None, True, 1, []):
            with self.subTest(mode=value):
                self.config['baseline_mode'] = value
                self.save_config()
                with self.assertRaisesRegex(ValueError, 'baseline_mode'):
                    worker.init(self.root)
        self.assertFalse((self.root / 'start.json').exists())
        self.assertFalse((self.root / 'states').exists())

    def test_frozen_initial_requests_match_despite_different_live_observations(self):
        frozen = self.freeze_baseline()
        before = self.baseline_files()
        other = self.root / 'another-trial'
        shutil.copytree(self.root, other)
        for root, observation, tokens in ((self.root, 'first-live-host', 20),
                                         (other, 'second-live-host', 80)):
            # Live observations can change; initialization must never measure the proof.
            with patch.object(self.evaluator, 'evaluate', return_value={**frozen, 'tokens': tokens}) as evaluate, \
                    patch.object(self.evaluator, 'fingerprint', return_value={'host': observation}) as fingerprint:
                worker.init(root)
                evaluate.assert_not_called()
                fingerprint.assert_called_once()
            self.assertEqual(harness.read(root / 'start.json')['environment'], {'host': observation})
            self.assertEqual(self.baseline_files(root), before)
        self.assertEqual((self.root / 'requests/001.json').read_bytes(),
                         (other / 'requests/001.json').read_bytes())
        state = harness.read(self.root / 'states/000.json')
        self.assertEqual(state['baseline'], {'tokens': 10, 'raw_heartbeats': 1000})
        self.assertEqual(state['best']['rank_numerator'], 20000)
        self.assertEqual(state['best']['code'], harness.read(self.root / 'input/problem.json')['reference'])

    def test_frozen_ranking_finish_and_replay_use_common_baseline(self):
        self.config['max_proposals'] = 1
        self.freeze_baseline()
        before = self.baseline_files()
        worker.init(self.root)
        self.submit(1)
        worker.finish(self.root)
        summary = harness.read(self.root / 'summary.json')
        self.assertEqual(summary['baseline'], {'tokens': 10, 'raw_heartbeats': 1000,
                                               'raw_samples': [900, 1000, 1100]})
        self.assertEqual(summary['selected']['rank_numerator'], 4000)
        self.assertEqual(summary['selected_local_score'], 0.2)
        self.assertEqual(self.evaluator.calls,
                         [self.root / 'steps/001/evaluation', self.root / 'final'])
        self.assertEqual(self.baseline_files(), before)
        with patch.object(worker, 'LeanEvaluator', side_effect=AssertionError('external call')):
            worker.replay(self.root)

    def test_frozen_original_remains_fallback_for_rejected_candidate(self):
        self.config['max_proposals'] = 1
        self.freeze_baseline()
        worker.init(self.root)
        response = self.root / 'responses/001.json'
        harness.write(response, {'proof': 'by exact False.elim (by contradiction)'})
        worker.submit(self.root, response)
        worker.finish(self.root)
        summary = harness.read(self.root / 'summary.json')
        self.assertEqual(summary['selected']['code'],
                         harness.read(self.root / 'input/problem.json')['reference'])
        self.assertEqual(summary['selected']['raw_samples'], [900, 1000, 1100])
        self.assertEqual(summary['selected_local_score'], 1)
        worker.replay(self.root)

    def test_invalid_frozen_receipts_fail_before_initialization_writes(self):
        result = self.freeze_baseline()
        path = self.root / 'baseline/result.json'
        for receipt in (None, '', 'not-a-hash', '0' * 64):
            with self.subTest(receipt=receipt):
                self.config['frozen_baseline_sha256'] = receipt
                self.save_config()
                with self.assertRaisesRegex(ValueError, '[Ff]rozen baseline'):
                    worker.init(self.root)
        invalid_results = [None, {}, {**result, 'valid': False}, {**result, 'tokens': True},
                           {**result, 'tokens': 0}, {**result, 'environments': {}},
                           {**result, 'environments': {'fixed': {'valid': True,
                               'runs': [{'measurement': {'raw': 0}}]}}},
                           {**result, 'environments': {'fixed': {'valid': True,
                               'runs': [{'measurement': {'raw': -1}}]}}}]
        for value in invalid_results:
            with self.subTest(result=value):
                path.write_text(harness.canonical(value))
                self.config['frozen_baseline_sha256'] = harness.digest(path.read_bytes())
                self.save_config()
                with self.assertRaisesRegex(ValueError, 'Invalid frozen baseline receipt'):
                    worker.init(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Invalid frozen baseline receipt'):
            worker.init(self.root)
        self.assertFalse((self.root / 'start.json').exists())
        self.assertFalse((self.root / 'states').exists())
        self.assertFalse((self.root / 'requests').exists())
        self.assertEqual(self.evaluator.calls, [])

    def test_frozen_receipt_tampering_blocks_submit_finish_and_resealed_replay(self):
        self.config['max_proposals'] = 1
        self.freeze_baseline()
        worker.init(self.root)
        path = self.root / 'baseline/result.json'
        original = path.read_bytes()
        path.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.submit(1)
        self.assertFalse((self.root / 'steps').exists())
        path.write_bytes(original)
        worker.submit(self.root, self.root / 'responses/001.json')
        path.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            worker.finish(self.root)
        self.assertFalse((self.root / 'selected.lean').exists())
        path.write_bytes(original)
        worker.finish(self.root)
        path.write_bytes(original + b'\n')
        # A newly sealed archive cannot bypass the separately pinned baseline digest.
        (self.root / 'artifacts.json').unlink()
        harness.seal(self.root)
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            worker.replay(self.root)


if __name__ == '__main__':
    unittest.main()
