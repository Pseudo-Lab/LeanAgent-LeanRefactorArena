"""Full fixture loop with deterministic compiler evidence, never a network call."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'src'))
from lean_agent import harness, preflight, status
from lean_agent.artifacts import read, write, sha, inventory
import adapter
import policy
import run as experiment_run


def response(proof, cost='0.01'):
    return {'id': 'fixture', 'choices': [{'message': {'content': json.dumps({'proof': proof})}}],
            'usage': {'cost': cost, 'prompt_tokens': 0, 'completion_tokens': 0}}


class FixtureLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.responses = self.root / 'responses.json'
        self.overrides = {}

    def fake_evaluate(self, folder, label, code, problem, env):
        directory = folder / label / 'fixed'
        directory.mkdir(parents=True)
        kind = self.overrides.get(label)
        if kind is None:
            kind = 'incomplete' if 'skip' in code else 'proof_error' if 'True.intro' in code else 'valid'
        valid = kind == 'valid'
        raw = 200 if 'rfl' in code else 500 if 'simpa' in code else 1000
        tokens = 2 if 'rfl' in code else 6 if 'simpa' in code else 14
        log = {'incomplete': 'error: unsolved goals\nn : Nat\n⊢ n + 0 = n\n',
               'proof_error': 'error: type mismatch\n',
               'environment': "error: unknown module prefix 'Absent'\n",
               'timeout': '', 'unknown': 'unrecognized compiler failure\n',
               'measurement': 'failed profiler\n', 'axioms': 'disallowed axiom\n', 'valid': ''}[kind]
        text = str(directory / 'check.lean') + ':1:1: ' + log if log else ''
        (directory / 'check.lean').write_text(code)
        (directory / 'check.log').write_text(text)
        row = {'source': 'check.lean', 'source_sha256': sha(code), 'log': 'check.log', 'log_sha256': sha(text),
               'returncode': 0 if valid else 1, 'timed_out': kind == 'timeout'}
        runs = [row]
        if valid:
            runs += [{'measurement': {'raw': raw + offset}} for offset in (-1, 0, 1)]
        if kind == 'measurement':
            row['returncode'] = 0
            (directory / 'measure-0.lean').write_text(code)
            (directory / 'measure-0.log').write_text('measurement error')
            runs.append({'source': 'measure-0.lean', 'source_sha256': sha(code), 'log': 'measure-0.log',
                         'log_sha256': sha('measurement error'), 'returncode': 1})
        error = None if valid else {'kind': 'axioms' if kind == 'axioms' else 'timeout' if kind == 'timeout' else 'compile', 'message': text}
        result = {'valid': valid, 'tokens': tokens, 'error': None if valid else {'kind': 'lean', 'message': 'failed'},
                  'environments': {'fixed': {'valid': valid, 'error': error, 'runs': runs}}}
        write(folder / (label + '-result.json'), result)
        fb = {'label': label, 'valid': valid, 'tokens': tokens, 'raw_hb': raw if valid else None,
              'hb_k': raw // 1000 if valid else None, 'seconds': 0, 'lean_compiles': len(runs),
              'errors': [] if valid else [error], 'validation_error': result['error']}
        write(folder / (label + '-feedback.json'), fb)
        return fb

    def prepare(self, name, responses=None, selected_policy='uniform-repair-v1', **kwargs):
        if not self.responses.exists():
            write(self.responses, responses or read(HERE / 'fixtures/responses.json'))
        out = self.root / name
        with patch.object(preflight, 'resolve_command', side_effect=lambda cmd, pin, project: cmd):
            experiment_run.prepare(out, selected_policy, self.responses, **kwargs)
        return out

    def execute(self, output):
        original = adapter.load_runner
        def load():
            runner = original()
            runner.evaluate = self.fake_evaluate
            return runner
        def preflight_check(env, root, evaluator):
            report = {'status': 'passed', 'commands': [], 'api_calls': 0}
            write(root / 'preflight.json', report)
            return report
        with patch.object(adapter, 'load_runner', side_effect=load), \
             patch.object(preflight, 'check', side_effect=preflight_check), redirect_stdout(io.StringIO()):
            return experiment_run.run(output)

    def test_both_arms_first_request_equal_and_failure_action_differs(self):
        a = self.prepare('a')
        b = self.prepare('b', selected_policy='state-aware-v1')
        for out in (a, b):
            result = self.execute(out)
            self.assertTrue(result['final_valid'])
            self.assertEqual(result['actual_api_cost_usd'], '0')
            self.assertEqual(result['calls'], 5)
            self.assertTrue(adapter.replay(out)['record_replay_passed'])
            self.assertEqual(status.inspect(out / 'SMOKE')['status'], 'completed')
        self.assertEqual(read(a/'SMOKE/attempt-001-request.json'), read(b/'SMOKE/attempt-001-request.json'))
        self.assertEqual(read(a/'SMOKE/attempt-002-decision.json')['decision']['action'], 'repair_current')
        self.assertEqual(read(b/'SMOKE/attempt-002-decision.json')['decision']['action'], 'replan_from_best')
        self.assertEqual(read(a/'SMOKE/attempt-001-observation.json')['goals'], None)
        self.assertEqual(read(a/'SMOKE/attempt-004-observation.json')['policy_state'], 'response_rejected')

    def test_final_allowed_call_improves_best_before_stop(self):
        out = self.prepare('final-call', [response('by skip'), response('by rfl')])
        result = self.execute(out)
        self.assertEqual(result['stop_reason'], 'call_limit')
        self.assertTrue(result['history'][-1]['improved'])
        self.assertEqual(result['selected_origin'], 'generated')
        self.assertEqual(result['calls'], 2)
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_duplicate_cost_is_retained_and_next_base_is_best(self):
        out = self.prepare('duplicate', [response('by skip'), response('by skip'), response('by rfl')])
        result = self.execute(out)
        decision = read(out/'SMOKE/attempt-003-decision.json')['decision']
        self.assertEqual(decision['reason'], 'duplicate')
        self.assertEqual(result['simulated_cost_usd'], '0.03')
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_safe_reservation_stops_before_any_fixture_dispatch(self):
        out = self.prepare('tiny', simulated_budget='0.01')
        result = self.execute(out)
        self.assertEqual(result['calls'], 0)
        self.assertEqual(result['selected_origin'], 'baseline')
        self.assertEqual(result['final_q'], 2)
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_improvement_is_kept_before_remaining_budget_stop(self):
        out = self.prepare('budget-end', [response('by rfl', '0.19'), response('by skip')], simulated_budget='0.2')
        result = self.execute(out)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['selected_origin'], 'generated')
        self.assertEqual(result['stop_reason'], 'remaining_budget_below_safe_request_bound')
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_baseline_failure_never_dispatches_or_reports_zero_score(self):
        out = self.prepare('bad-baseline')
        self.overrides = {'baseline': 'proof_error'}
        result = self.execute(out)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['calls'], 0)
        self.assertIsNone(result['final_q'])
        self.assertTrue(adapter.replay(out)['record_replay_passed'])
        self.assertEqual(status.inspect(out / 'SMOKE')['status'], 'failed')

    def test_top_level_strategy_and_runner_route_hints_never_reach_input(self):
        source = self.root/'source/P01'
        source.mkdir(parents=True)
        example = HERE.parents[1]/'examples/first-harness'
        p = read(example/'problem.json')
        write(source/'agent-input.json', {'problem': {'name': p['name'], 'statement': p['statement'], 'original': p['reference']},
              'context': {'api': 'Nat.add_zero'}, 'strategy_prompt': 'HIDDEN_ROUTE_HINT',
              'instructions': 'HIDDEN_ROUTE_HINT', 'output_protocol': 'HIDDEN_ROUTE_HINT', 'attempt_cap': 77})
        (source/'original.lean').write_text(p['reference'])
        write(source/'environment.json', {'environments': [{'project': str(example/'project'),
              'command': ['lean'], 'template': (example/'context.lean.in').read_text(), 'timeout_seconds': 30}]})
        out = self.prepare('sanitized', input_root=source.parent, pid='P01')
        inp = read(out/'P01/input.json')
        self.assertNotIn('HIDDEN_ROUTE_HINT', json.dumps(inp))
        self.assertNotIn('Use route comparisons to choose', inp['instructions'])
        self.assertEqual(read(out/'prompt-design.json')['case_prompts'], {'P01': ''})

    def test_uncertain_cost_never_retries_but_preserves_verified_best(self):
        out = self.prepare('unknown', [response('by rfl', None), response('by rfl')])
        result = self.execute(out)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['status'], 'stopped')
        self.assertIsNone(result['simulated_cost_usd'])
        self.assertEqual(result['selected_origin'], 'baseline')
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_receipt_bound_violation_stops(self):
        out = self.prepare('overcharge', [response('by rfl', '100'), response('by rfl')])
        result = self.execute(out)
        self.assertEqual(result['calls'], 1)
        self.assertEqual(result['stop_reason'], 'bound_violated')
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_environment_measurement_timeout_unknown_stop_generation(self):
        for kind in ('environment', 'measurement', 'timeout', 'unknown'):
            with self.subTest(kind=kind):
                out = self.prepare(kind)
                self.overrides = {'attempt-001': kind}
                result = self.execute(out)
                self.assertEqual(result['calls'], 1)
                self.assertEqual(result['stop_reason'], kind)
                self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_final_proof_failure_falls_back_and_reports_zero_improvement(self):
        out = self.prepare('fallback', [response('by rfl')])
        self.overrides = {'final-selected': 'proof_error'}
        result = self.execute(out)
        self.assertEqual((result['selected_origin'], result['final_q'], result['improvement']), ('baseline', 2, 0))
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_final_timeout_is_unresolved_without_successful_fallback(self):
        out = self.prepare('final-timeout', [response('by rfl')])
        self.overrides = {'final-selected': 'timeout'}
        result = self.execute(out)
        self.assertIsNone(result['final_q'])
        self.assertFalse(result['final_valid'])
        self.assertFalse((out/'SMOKE/selected.lean').exists())
        self.assertFalse((out/'SMOKE/final-baseline-result.json').exists())
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_final_fallback_failure_stays_unresolved(self):
        out = self.prepare('both-fail', [response('by rfl')])
        self.overrides = {'final-selected': 'proof_error', 'final-baseline': 'proof_error'}
        result = self.execute(out)
        self.assertIsNone(result['selected_origin'])
        self.assertIsNone(result['improvement'])
        self.assertTrue(adapter.replay(out)['record_replay_passed'])

    def test_changed_frozen_inputs_and_second_run_are_rejected(self):
        out = self.prepare('frozen')
        p = out/'SMOKE/input.json'
        original = p.read_bytes()
        p.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Frozen input'):
            experiment_run.check(out)
        p.write_bytes(original)
        self.execute(out)
        with self.assertRaisesRegex(ValueError, 'already started'):
            experiment_run.run(out)

    def test_replay_detects_tampering_and_recomputes_even_if_inventory_resealed(self):
        out = self.prepare('tamper')
        self.execute(out)
        p = out/'SMOKE/attempt-002-decision.json'
        record = read(p)
        record['decision']['action'] = 'optimize_best'
        p.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'artifacts changed'):
            adapter.replay(out)
        (out/'artifacts.json').write_text(json.dumps(inventory(out)))
        with self.assertRaisesRegex(ValueError, 'Policy decision'):
            adapter.replay(out)

    def test_relocated_archived_replay_uses_no_model_or_lean(self):
        out = self.prepare('original')
        self.execute(out)
        moved = self.root/'moved'
        shutil.move(str(out), moved)
        replay = moved/'code/repo/experiments/verification-repair-policy/run.py'
        p = subprocess.run([sys.executable, '-B', str(replay), 'replay', '--output', str(moved)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)['record_replay_passed'])


if __name__ == '__main__':
    unittest.main()
