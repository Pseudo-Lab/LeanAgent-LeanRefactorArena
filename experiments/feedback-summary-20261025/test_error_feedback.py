"""Manipulation and replay invariants; no solver performance is inferred here."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'first-harness-jwkweon')]
import harness as h
import error_feedback as f


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'input').mkdir()
        (self.root / 'input/summarizer-prompt.txt').write_text('Fixed test prompt')
        self.evaluation = self.root / 'steps/001/evaluation'
        (self.evaluation / 'fixed').mkdir(parents=True)
        self.log = 'test.lean:5:3: error: unsolved goals\ncase step\nn : Nat\nh : n = 0\n⊢ n + 0 = n\n'
        (self.evaluation / 'fixed/check.log').write_text(self.log)
        self.result = {'valid': False, 'environments': {'fixed': {
            'valid': False, 'error': {'kind': 'compile', 'message': 'fail'},
            'runs': [{'returncode': 1, 'timed_out': False, 'log': 'check.log'}]}},
            'error': {'kind': 'lean', 'message': 'failed'}}
        self.diagnostic = f.legacy._extract(self.log, str(self.root))
        self.summary = {**self.diagnostic, 'message': 'A goal remains unproved.',
                        'local_context': 'n : Nat', 'truncated': True}

    def call(self, mode='semantic_v1', replay=False):
        return f.format_feedback(self.result, None, 1600, str(self.root),
                                 self.evaluation, mode, replay=replay)

    def write_response(self, response):
        h.write(self.evaluation.parent / 'summary/response.json', response)

    def test_structured_condition_is_exact_legacy(self):
        self.assertEqual(self.call('structured_v1'),
            f.legacy.format_feedback(self.result, None, 1600, str(self.root),
                                     self.evaluation, 'structured_v1'))
        self.assertFalse((self.evaluation.parent / 'summary').exists())

    def test_accepted_output_and_replay_use_recorded_input_only(self):
        self.write_response(self.summary)
        expected = self.call()
        self.assertEqual(json.loads(expected['details']), self.summary)
        receipt = h.read(self.evaluation.parent / 'summary/receipt.json')
        self.assertEqual(receipt['status'], 'accepted')
        with patch.object(f.time, 'sleep', side_effect=AssertionError('Replay must not wait')):
            self.assertEqual(self.call(replay=True), expected)

    def test_invalid_response_falls_back_and_replays(self):
        self.write_response({**self.summary, 'goal': '⊢ False'})
        expected = self.call('structured_v1')
        self.assertEqual(self.call(), expected)
        self.assertEqual(h.read(self.evaluation.parent / 'summary/receipt.json')['status'], 'invalid')
        self.assertEqual(self.call(replay=True), expected)

    def test_replay_rejects_changed_response(self):
        self.write_response(self.summary)
        self.call()
        path = self.evaluation.parent / 'summary/response.json'
        path.write_text(h.canonical({**self.summary, 'message': 'Changed explanation'}))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.call(replay=True)

    def test_replay_rejects_changed_log(self):
        self.write_response(self.summary)
        self.call()
        (self.evaluation / 'fixed/check.log').write_text(self.log + '\nChanged log')
        with self.assertRaisesRegex(ValueError, 'request does not match'):
            self.call(replay=True)

    def test_success_and_non_compile_failures_never_request_summaries(self):
        for kind in ('timeout', 'environment', 'validation'):
            result = copy.deepcopy(self.result)
            result['environments']['fixed']['error']['kind'] = kind
            self.assertEqual(f.format_feedback(result, None, 1600, str(self.root), self.evaluation, 'semantic_v1'),
                f.legacy.format_feedback(result, None, 1600, str(self.root), self.evaluation, 'structured_v1'))
        self.assertFalse((self.evaluation.parent / 'summary').exists())

    def test_full_goal_cannot_be_shortened_when_it_fits(self):
        with self.assertRaisesRegex(ValueError, 'full goal'):
            f.validate_summary({**self.summary, 'goal': '⊢ n'}, self.diagnostic, 1600)

    def test_context_must_preserve_complete_lines_and_order(self):
        for context in ('h : n = 1', 'h : n = 0\nn : Nat', 'n : Na'):
            with self.assertRaisesRegex(ValueError, 'whole original lines'):
                f.validate_summary({**self.summary, 'local_context': context}, self.diagnostic, 1600)

    def test_metadata_budget_and_truncation_are_checked(self):
        for changed in ({'location': 'fake'}, {'case': 'other'},
                        {'message': ''}, {'message': 'X' * 1600},
                        {'truncated': False}, {'truncated': 1}):
            with self.assertRaises(ValueError):
                f.validate_summary({**self.summary, **changed}, self.diagnostic, 1600)

    def test_missing_goal_cannot_be_invented(self):
        diagnostic = {**self.diagnostic, 'goal': None}
        with self.assertRaisesRegex(ValueError, 'Invented goal'):
            f.validate_summary(self.summary, diagnostic, 1600)


if __name__ == '__main__':
    unittest.main()
