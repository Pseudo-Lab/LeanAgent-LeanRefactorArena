"""The reference fast path must retain real compile/counter/axiom rejection."""
from contextlib import nullcontext
import json
import fcntl
import os
from pathlib import Path
import re
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments/final-batch-next'))
from evaluator import FinalEvaluator, WRAPPER, PRIVATE_WRAPPER


class SinglePassReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('PROJECT_CACHE_DIR'))
        self.addCleanup(self.temp.cleanup)
        self.code = 'theorem test : True := by trivial'
        self.problem = {'statement': 'theorem test : True', 'reference': self.code,
                        'name': 'test', 'environments': ['test-env']}
        self.evaluator = object.__new__(FinalEvaluator)
        self.evaluator.cache = None
        self.evaluator.load_problem = lambda _: self.problem
        self.evaluator._compiler_lock = nullcontext
        self.evaluator._state = lambda _: {}
        self.evaluator._context = lambda *_: {'prefix': 'import Lean\n', 'suffix': ''}
        self.evaluator._invoke = Mock(side_effect=self.success)
        self.evaluator._audit_frontier = Mock(return_value=(
            {'returncode': 0, 'timed_out': False}, ['sorryAx'], {'kind': 'axioms', 'message': 'sorryAx'}))

    def success(self, source, *_):
        nonce = re.search(r'#refactor_eval "([a-f0-9]+)" "test"', source).group(1)
        report = {'target': 'test', 'raw': 12345, 'scaled': 12, 'axioms': []}
        return {'returncode': 0, 'timed_out': False}, f'REFACTOR_EVAL {nonce} {json.dumps(report)}'

    def evaluate(self, **kw):
        return self.evaluator.evaluate(self.code, self.problem, Path(self.temp.name) / 'result',
                                       trusted_reference=True, reference_single_pass=True, **kw)

    def test_one_instrumented_compile_retains_the_measured_counter(self):
        result = self.evaluate()
        self.assertTrue(result['valid'])
        self.evaluator._invoke.assert_called_once()
        self.assertEqual(result['environments']['test-env']['median_raw_heartbeats'], 12345)
        self.assertEqual(len(result['environments']['test-env']['runs']), 1)

    def test_actual_compiler_failure_is_not_hidden_by_omitting_the_duplicate_check(self):
        self.evaluator._invoke.side_effect = None
        self.evaluator._invoke.return_value = ({'returncode': 1, 'timed_out': False}, 'Lean type error')
        result = self.evaluate()
        self.assertFalse(result['valid'])
        self.assertEqual(result['environments']['test-env']['error']['kind'], 'compile')

    def test_success_exit_without_authenticated_counter_is_invalid(self):
        self.evaluator._invoke.side_effect = None
        self.evaluator._invoke.return_value = ({'returncode': 0, 'timed_out': False}, '')
        self.assertFalse(self.evaluate()['valid'])

    def test_sorry_axiom_still_requires_frontier_audit_and_is_rejected(self):
        def forbidden(source, *args):
            record, log = self.success(source, *args)
            return record, log.replace('"axioms": []', '"axioms": ["sorryAx"]')
        self.evaluator._invoke.side_effect = forbidden
        result = self.evaluate()
        self.assertFalse(result['valid'])
        self.evaluator._audit_frontier.assert_called_once()
        self.assertEqual(result['environments']['test-env']['error']['kind'], 'axioms')

    def test_mode_cannot_bypass_candidate_policy_or_changed_reference(self):
        with self.assertRaisesRegex(ValueError, 'exact frozen reference'):
            self.evaluator.evaluate(self.code, self.problem, Path(self.temp.name) / 'other', reference_single_pass=True)
        self.problem['reference'] += ' '
        self.assertFalse(self.evaluate()['valid'])
        self.evaluator._invoke.assert_not_called()

    @unittest.skipUnless(os.environ.get('ARENA_WRAPPER_HYGIENE_LEAN'),
                         'Set ARENA_WRAPPER_HYGIENE_LEAN and ARENA_COMPILER_LOCK for native regression')
    def test_native_public_and_private_helpers_do_not_capture_a_section_name_type(self):
        with Path(os.environ['ARENA_COMPILER_LOCK']).open('a+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            for private, wrapper in [(False, WRAPPER), (True, PRIVATE_WRAPPER)]:
                source = Path(self.temp.name) / ('private.lean' if private else 'public.lean')
                source.write_text(('module\npublic import Lean\n' if private else 'import Lean\n') +
                    'namespace Collision\nvariable {Name : Type}\n' + wrapper +
                    '\nset_option Elab.async false in\n#refactor_eval "hygiene-check" "Collision.target"\n' +
                    'theorem target : True := by trivial\nend Collision\n')
                for compiler in os.environ['ARENA_WRAPPER_HYGIENE_LEAN'].split(os.pathsep):
                    with self.subTest(compiler=compiler, private=private):
                        result = subprocess.run([compiler, str(source), '-j1', '-M4096'],
                                                text=True, capture_output=True, timeout=120)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn('REFACTOR_EVAL hygiene-check', result.stdout)


if __name__ == '__main__':
    unittest.main()
