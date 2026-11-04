"""Formatter and local-worker control-flow checks; no compiler or model calls."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import harness as h
from error_feedback import format_feedback
from test_harness import FakeEvaluator

spec = importlib.util.spec_from_file_location('feedback_ablation_worker', HERE / 'worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def failed_result(kind='compile'):
    return {'valid': False, 'tokens': 2, 'error': {'kind': 'lean', 'message': 'failed'},
            'environments': {'fixed': {'valid': False, 'error': {'kind': kind, 'message': 'tail only'},
                                      'runs': [{'returncode': 1, 'timed_out': False, 'log': 'check.log'}]}}}


class FormatterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.evaluation = self.root / 'evaluation'
        (self.evaluation / 'fixed').mkdir(parents=True)
        self.log = self.evaluation / 'fixed/check.log'

    def feedback(self, result=None, rejection=None, mode='structured_v1'):
        return format_feedback(result or failed_result(), rejection, 1600,
                               str(self.root), self.evaluation, mode)

    def test_first_error_survives_warning_heavy_log_and_tail(self):
        prefix = str(self.evaluation / 'fixed/check.lean')
        self.log.write_text('\n'.join(f'{prefix}:{i}:1: warning: warning {i}' for i in range(200))
                            + f'\n{prefix}:201:3: error: first actual failure\n'
                            + 'case left\nn : Nat\nh : n = 1\n⊢ n + 1 = 2\n'
                            + f'{prefix}:202:4: error: later failure\n' + 'later tail\n' * 900)
        value = json.loads(self.feedback()['details'])
        self.assertEqual(value, {'location': '<RUN>/evaluation/fixed/check.lean:201:3',
                                'message': 'first actual failure', 'case': 'left',
                                'goal': '⊢ n + 1 = 2', 'local_context': 'n : Nat\nh : n = 1',
                                'truncated': False})
        self.assertGreater(self.log.stat().st_size, 4000)

    def test_canonical_json_cap_accounts_for_escaping_and_unicode(self):
        self.log.write_text('check.lean:9:2: error: ' + '핵심 "\\\t' * 400
                            + '\ncase goal\n' + '\n'.join(f'h{i} : ' + '로컬 "\\\t' * 100 for i in range(40))
                            + '\n⊢ ' + '결론 "\\' * 500)
        details = self.feedback()['details']
        value = json.loads(details)
        self.assertLessEqual(len(details), 1600)
        self.assertEqual(details, h.canonical(value))
        self.assertTrue(value['truncated'])
        self.assertTrue(value['message'].startswith('핵심 "\\\t'))
        self.assertGreater(len(value['message']), len(value['local_context']))
        self.assertNotIn(str(self.root), details)

    def test_tagged_first_error_precedes_later_ordinary_error_and_warnings(self):
        self.log.write_text('check.lean:1:1: warning(lean.unusedVariables): unused variable\n'
                            'check.lean:5:3: error(lean.unknownIdentifier): Unknown identifier `missing`\n'
                            'first diagnostic continuation\n'
                            'check.lean:6:2: warning(lean.unusedVariables): another warning\n'
                            'check.lean:7:1: error: unsolved goals\ncase later\nx : Nat\n⊢ x = 0\n')
        value = json.loads(self.feedback()['details'])
        self.assertEqual(value['location'], 'check.lean:5:3')
        self.assertEqual(value['message'],
                         'error(lean.unknownIdentifier): Unknown identifier `missing`\nfirst diagnostic continuation')
        self.assertIsNone(value['case'])
        self.assertIsNone(value['goal'])
        self.assertEqual(value['local_context'], '')
        self.assertFalse(value['truncated'])

    def test_first_goal_case_and_context_do_not_include_other_cases_or_diagnostics(self):
        self.log.write_text('check.lean:5:1: error: unsolved goals\n'
                            'case first\na : Nat\n⊢ a = a\n  ∧ True\n\n'
                            'case second\nb : Bool\n⊢ b = true\n'
                            'check.lean:8:1: error: another error\ncase third\nc : Nat\n⊢ c = 9\n')
        value = json.loads(self.feedback()['details'])
        self.assertEqual(value['case'], 'first')
        self.assertEqual(value['goal'], '⊢ a = a\n  ∧ True')
        self.assertEqual(value['local_context'], 'a : Nat')
        self.assertEqual(value['message'], 'unsolved goals')

    def test_goal_without_case_and_multiline_error(self):
        self.log.write_text('check.lean:5:1: warning: earlier\n'
                            'check.lean:6:2: error: tactic failed\nadditional explanation\n'
                            'α : Type\nx : α\n⊢ x = x\n')
        value = json.loads(self.feedback()['details'])
        self.assertIsNone(value['case'])
        self.assertEqual(value['message'], 'tactic failed\nadditional explanation')
        self.assertEqual(value['local_context'], 'α : Type\nx : α')
        self.assertEqual(value['goal'], '⊢ x = x')

    def test_unlocated_and_nonstandard_compiler_messages(self):
        for log, message in [('warning: skip\nerror: fatal compiler failure\n', 'fatal compiler failure'),
                             ('fatal compiler process exited unexpectedly\n', 'fatal compiler process exited unexpectedly')]:
            with self.subTest(log=log):
                self.log.write_text(log)
                value = json.loads(self.feedback()['details'])
                self.assertIsNone(value['location'])
                self.assertEqual(value['message'], message)

    def test_success_parse_rejection_and_noncompile_feedback_are_exact(self):
        valid = {'valid': True, 'tokens': 2, 'error': None,
                 'environments': {'fixed': {'valid': True, 'error': None,
                                           'runs': [{'measurement': {'raw': 200}}]}}}
        for mode in ('legacy', 'structured_v1'):
            for result, rejection in [(valid, None), (None, 'invalid response'),
                                      (failed_result('timeout'), None),
                                      (failed_result('environment'), None),
                                      (failed_result('axioms'), None)]:
                with self.subTest(mode=mode, rejection=rejection, result=result):
                    self.assertEqual(format_feedback(result, rejection, 1600, str(self.root),
                                                     self.evaluation, mode),
                                     h.feedback(result, rejection, 1600, str(self.root)))

    def test_legacy_compile_feedback_exact_and_structured_other_fields_unchanged(self):
        result = failed_result()
        original = copy.deepcopy(result)
        self.log.write_text('check.lean:1:2: error: unsolved goals\n⊢ True\n')
        legacy = h.feedback(result, None, 1600, str(self.root))
        self.assertEqual(self.feedback(result, mode='legacy'), legacy)
        structured = self.feedback(result)
        self.assertEqual({k: v for k, v in structured.items() if k != 'details'},
                         {k: v for k, v in legacy.items() if k != 'details'})
        self.assertEqual(result, original)

    def test_missing_archive_is_a_visible_error(self):
        with self.assertRaises(FileNotFoundError):
            self.feedback()
        result = failed_result()
        result['environments']['fixed']['runs'] = []
        with self.assertRaisesRegex(ValueError, 'no archived failing run'):
            self.feedback(result)

    def test_read_first_failed_run_after_successful_check(self):
        result = failed_result()
        result['environments']['fixed']['runs'].insert(0, {'returncode': 0, 'log': 'missing-success.log'})
        self.log.write_text('check.lean:4:2: error: measured compilation failure')
        self.assertEqual(json.loads(self.feedback(result)['details'])['message'],
                         'measured compilation failure')


class ArchivedFakeEvaluator(FakeEvaluator):
    def evaluate(self, code, problem, environments, output, runs):
        result = super().evaluate(code, problem, environments, output, runs)
        if not result['valid']:
            folder = output / 'fixed'
            folder.mkdir()
            log = str(folder / 'check.lean') + ':17:2: error: unsolved goals\ncase proof\nn : Nat\n⊢ n = 0\n'
            (folder / 'check.log').write_text(log)
            row = result['environments']['fixed']
            row['runs'] = [{'returncode': 1, 'timed_out': False, 'log': 'check.log'}]
        return result


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'input').mkdir()
        (self.root / 'project').mkdir()
        for source, target in [('fixtures/problem.json', 'problem.json'),
                               ('fixtures/context.lean.in', 'context.lean.in'), ('prompt.txt', 'prompt.txt')]:
            shutil.copyfile(h.BASE / source, self.root / 'input' / target)
        self.config = {'trial_id': 'unit', 'problem_id': 'smoke', 'max_proposals': 3}
        self.save_config()
        self.evaluator = ArchivedFakeEvaluator()
        patcher = patch.object(worker, 'LeanEvaluator', return_value=self.evaluator)
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def save_config(self):
        (self.root / 'trial.json').write_text(json.dumps(self.config))

    def test_structured_submit_finish_and_replay_share_archived_formatter(self):
        self.config['error_feedback_mode'] = 'structured_v1'
        self.save_config()
        worker.init(self.root)
        for step, response in enumerate([{'proof': 'by exact False.elim (by contradiction)'},
                                         {'wrong': 'parse rejection'}, {'proof': 'by rfl'}], 1):
            path = self.root / f'responses/{step}.json'
            h.write(path, response)
            worker.submit(self.root, path)
        feedback = h.read(self.root / 'states/001.json')['latest']['feedback']
        self.assertEqual(json.loads(feedback['details'])['goal'], '⊢ n = 0')
        self.assertEqual(h.read(self.root / 'states/002.json')['latest']['feedback']['status'], 'response_rejected')
        self.assertEqual(h.read(self.root / 'requests/002.json')['latest']['feedback'], feedback)
        worker.finish(self.root)
        self.assertTrue(h.read(self.root / 'summary.json')['final_valid'])
        with patch.object(worker, 'LeanEvaluator', side_effect=AssertionError('external call')), \
                patch.object(worker, 'format_feedback', wraps=format_feedback) as formatter:
            worker.replay(self.root)
        self.assertEqual(formatter.call_count, 3)
        self.assertEqual(formatter.call_args_list[0].args[4], self.root / 'steps/001/evaluation')
        self.assertTrue(all(call.args[5] == 'structured_v1' for call in formatter.call_args_list))

    def test_default_legacy_submit_details_exact(self):
        worker.init(self.root)
        response = self.root / 'response.json'
        h.write(response, {'proof': 'by exact False.elim (by contradiction)'})
        worker.submit(self.root, response)
        result = h.read(self.root / 'steps/001/evaluation/result.json')
        self.assertEqual(h.read(self.root / 'states/001.json')['latest']['feedback'],
                         h.feedback(result, None, 1600, str(self.root)))

    def test_invalid_modes_rejected_before_initialization_or_evaluator_writes(self):
        for mode in ('', 'structured', None, True, [], {}):
            with self.subTest(mode=mode):
                self.config['error_feedback_mode'] = mode
                self.save_config()
                before = {str(path.relative_to(self.root)): path.read_bytes()
                          for path in self.root.rglob('*') if path.is_file()}
                with self.assertRaisesRegex(ValueError, 'error_feedback_mode'):
                    worker.init(self.root)
                after = {str(path.relative_to(self.root)): path.read_bytes()
                         for path in self.root.rglob('*') if path.is_file()}
                self.assertEqual(after, before)
        self.assertEqual(self.evaluator.calls, [])


if __name__ == '__main__':
    unittest.main()
