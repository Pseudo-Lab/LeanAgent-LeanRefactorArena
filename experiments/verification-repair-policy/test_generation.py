"""Network-free Controller, transport and suite boundary tests."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from common import Limits, Stop, canonical, read
from controller import generation_loop
from generation import CONTROL, ORDER, prepare, process
from generation_runtime import GenerationRuntime
from generation_transport import OpenAITransport, ScriptedTransport, parse_plan, payload, plan_request
from lean_agent import openai_direct
from runtime import envelope
from test_contracts import protocol, evaluation

PLAN = {'routes': [{'id': 'a', 'strategy': 'Direct constructors'},
                   {'id': 'b', 'strategy': 'Eliminate assumptions'}], 'lessons': ['Keep every case.']}


def settings(**values):
    return protocol(backend='fixture', run_id='baseline-r1', run_budget_usd='.70',
                    pricing=openai_direct.PRICING, controller={**CONTROL, 'max_steps': 3}, **values)


def ledger():
    return {'per_trial_usd': '.70', 'total_usd': '2.80', 'max_trials': 400, 'attempts': {}}


def response(role, proof='by trivial'):
    return {'role': role, 'content': PLAN if role == 'planner' else {'proof': proof}}


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def runtime(self, responses=(), config=None, budget=None):
        return GenerationRuntime(self.root, config or settings(), budget or ledger(), ScriptedTransport(responses))

    def test_planner_schema_duplicate_keys_and_routes(self):
        self.assertEqual(parse_plan({'choices': [{'message': {'content': canonical(PLAN)}}]}), PLAN)
        for content in ('{"routes":[],"lessons":[],"routes":[]}',
                        canonical({**PLAN, 'routes': [PLAN['routes'][0]]*2}),
                        canonical({**PLAN, 'lessons': [None]})):
            with self.assertRaises(ValueError):
                parse_plan({'choices': [{'message': {'content': content}}]})

    def test_paid_transport_default_blocks_before_credentials_or_http(self):
        with patch.object(openai_direct, 'load_key') as key, patch('generation_transport.request.build_opener') as http:
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                OpenAITransport(settings())({}, {}, 1)
            key.assert_not_called()
            http.assert_not_called()

    def test_role_payload_and_affordable_worst_case_bound(self):
        p = settings()
        for role in ('planner', 'root', 'repair'):
            packet = {'role': role, 'call_id': 'baseline-r1/call-001'}
            planned = plan_request(p, packet, Decimal('.14'))
            self.assertLessEqual(Decimal(planned['reserved_usd']), Decimal('.14'))
            self.assertEqual(planned['body']['tools'], [])
            self.assertEqual(planned['body'], payload(p, {**packet, 'call_id': 'repair-r2/call-001'},
                                                     planned['body']['max_output_tokens']))
            self.assertIsNone(plan_request(p, packet, Decimal('.001')))

    def test_all_roles_share_run_and_suite_budget(self):
        p = settings()
        p['run_budget_usd'] = '.04'
        rt = self.runtime([response('planner'), response('root'), response('repair')], config=p)
        rt.dispatch('planner', {})
        rt.dispatch('root', {})
        rt.repair_start = 0
        rt.dispatch('repair', {})
        with self.assertRaisesRegex(Stop, 'budget_limit'):
            rt.dispatch('root', {})
        self.assertEqual(rt.cost_summary()['role_calls'], {'planner': 1, 'root': 1, 'repair': 1})
        self.assertEqual(rt.cost_summary()['simulated_cost_usd'], '0.03')
        self.assertEqual(read(self.root/'budget.json'), rt.ledger)

    def test_uncertain_receipt_blocks_next_run(self):
        rt = self.runtime([{'role': 'root', 'raw': envelope('by trivial', None)}])
        with self.assertRaisesRegex(Stop, 'unsettled_receipt'):
            rt.dispatch('root', {})
        other = self.root/'other'
        other.mkdir()
        p = settings()
        p['run_id'] = 'repair-r1'
        worker = Mock()
        next_rt = GenerationRuntime(other, p, rt.ledger, worker)
        with self.assertRaisesRegex(Stop, 'unsettled_receipt'):
            next_rt.dispatch('planner', {})
        worker.assert_not_called()

    def test_reservation_is_durable_before_callback_and_final_phase_has_no_dispatch(self):
        rt = self.runtime()
        def call(packet, planned, timeout):
            self.assertEqual(read(self.root/'budget.json')['attempts'][packet['call_id']]['status'], 'reserved')
            return envelope('by trivial')
        rt.worker = call
        rt.dispatch('root', {})
        rt.finalizing = True
        with self.assertRaisesRegex(Stop, 'final_verification_no_dispatch'):
            rt.dispatch('root', {})

    def test_final_time_is_reserved_and_repair_deadline_is_independent(self):
        rt = self.runtime(config=settings(limits=asdict(Limits(lean_seconds=60, run_seconds=1800, repair_seconds=600))))
        with patch.object(rt, 'now', return_value=1321):
            with self.assertRaisesRegex(Stop, 'final_verification_reserve'):
                rt.check_time()
            rt.finalizing = True
            self.assertEqual(rt.check_time(), 1321)
        rt.finalizing, rt.repair_start = False, 100
        with patch.object(rt, 'now', return_value=701):
            with self.assertRaisesRegex(Stop, 'repair_time_limit'):
                rt.check_time(repair=True)
            self.assertEqual(rt.check_time(), 701)

    def test_round_robin_stagnation_duplicate_rejection_and_exact_replay(self):
        responses = [response('planner'), response('root'), response('root'), response('root')]
        p = settings()
        p['controller']['repeated_failure'] = 3
        rt = self.runtime(responses, p)
        reference = {'status': 'completed', 'reason': None, 'baseline': evaluation(), 'tactics': []}
        with patch.object(rt.native, 'evaluate', return_value=evaluation(tokens=5)) as native:
            result = generation_loop(rt, reference)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(native.call_count, 2)  # One candidate + final, two duplicate evaluations blocked.
        self.assertEqual([row['duplicate'] for row in result['attempts']], [False, True, True])
        self.assertEqual([row['attempts'] for row in result['routes']], [2, 1])
        self.assertEqual(result['role_calls'], {'planner': 1, 'root': 3, 'repair': 0})
        replay_rt = GenerationRuntime(self.root, p, ledger(), replay=True)
        self.assertEqual(generation_loop(replay_rt, reference), result)
        replay_rt.tape.assert_complete()

    def test_repeated_failure_replans_with_native_goals_and_route_history(self):
        rows = [response('planner'), response('root', 'by skip'), response('root', 'by exact bad'),
                response('planner'), response('root', 'by trivial')]
        rt = self.runtime(rows)
        reference = {'status': 'completed', 'baseline': evaluation(), 'tactics': [], 'reason': None}
        observed = {'kind': 'proof', 'errors': [{'message': "Alternative 'app' has not been provided", 'position': 0}],
                    'tactics': [], 'blocks': []}
        with patch.object(rt.native, 'evaluate', side_effect=[evaluation(False), evaluation(False), evaluation(), evaluation()]), \
             patch.object(rt.native, 'inspect', return_value=observed):
            result = generation_loop(rt, reference)
        self.assertEqual([p['trigger'] for p in result['plans']], ['start', 'repeated_failure'])
        self.assertEqual(sum(r['failures'].get('missing_alternative', 0) for r in result['routes']), 2)

    def test_unknown_current_attempt_is_kept_and_final_original_is_checked(self):
        rt = self.runtime([response('planner'), {'role': 'root', 'raw': envelope('by trivial', None)}])
        reference = {'status': 'completed', 'baseline': evaluation(), 'tactics': [], 'reason': None}
        with patch.object(rt.native, 'evaluate', return_value=evaluation()) as native:
            result = generation_loop(rt, reference)
        self.assertEqual(result['stop_reason'], 'unsettled_receipt')
        self.assertEqual(len(result['attempts']), 1)
        self.assertTrue(result['final_valid'])
        self.assertEqual(result['status'], 'stopped')
        native.assert_called_once()

    def test_final_proof_failure_falls_back_but_timeout_stays_unknown(self):
        reference = {'status': 'completed', 'baseline': evaluation(), 'tactics': [], 'reason': None}
        for kind, calls, valid in [('compile', 3, True), ('timeout', 2, None)]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                p = settings()
                p['controller']['max_steps'] = 1
                rt = GenerationRuntime(Path(directory), p, ledger(), ScriptedTransport([response('planner'), response('root')]))
                with patch.object(rt.native, 'evaluate', side_effect=[evaluation(tokens=5), evaluation(False, error=kind), evaluation()]) as native:
                    result = generation_loop(rt, reference)
                self.assertEqual(native.call_count, calls)
                self.assertEqual(result['final_valid'], valid)
                if valid:
                    self.assertEqual(result['selected_origin'], 'original')
                    self.assertEqual(result['final_q'], 2)

    def test_suite_paid_gate_even_with_valid_frozen_inputs(self):
        fixture = {'problem': settings()['problem'], 'environment': settings()['environment'],
                   'limits': asdict(Limits()), 'responses': {name: [] for name, _ in ORDER}}
        path = self.root/'suite'
        prepare(path, fixture=fixture)
        with patch('generation.check', return_value={**settings(), 'backend': 'openai'}), \
             patch.object(openai_direct, 'load_key') as key:
            with self.assertRaisesRegex(ValueError, 'disabled'):
                process(path)
            key.assert_not_called()
        self.assertFalse((path/'reference').exists())


if __name__ == '__main__':
    unittest.main()
