"""Offline regression checks for shared limits, provenance and acceptance boundaries."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from common import Limits, Stop, canonical, read, sha, shared
from runtime import Runtime, Tape, envelope
from native import patch_site, splice
from adapter import workflow


def protocol(**overrides):
    value = {'limits': asdict(Limits()), 'problem': {'name': 'demo', 'statement': 'theorem demo : True',
             'reference': 'theorem demo : True := by exact True.intro\n'}, 'condition': 'planner-worker-v1',
             'environment': {'template': '{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n{{DECLARATION}}',
                             'project': '/unused', 'command': ['lean'], 'id': 'fixed'},
             'environment_sha256': 'fixed', 'simulated_reservation_usd': '0.02', 'simulated_budget_usd': '1',
             'tactics': ['rfl'], 'context': {}}
    value.update(overrides)
    return value


def evaluation(valid=True, tokens=10, error='compile'):
    return {'valid': valid, 'tokens': tokens, 'error': None if valid else {'kind': 'lean'},
            'environments': {'fixed': {'valid': valid, 'error': None if valid else {'kind': error},
              'runs': [{'measurement': {'raw': 1000, 'scaled': 1}}] if valid else []}}}


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def runtime(self, worker=None, **overrides):
        return Runtime(self.root, protocol(**overrides), worker or (lambda request: envelope('by trivial')))

    def test_shared_budget_covers_root_and_repair_before_dispatch(self):
        worker = Mock(return_value=envelope('by trivial', '0.02'))
        rt = self.runtime(worker, simulated_budget_usd='0.02')
        rt.dispatch('root', {})
        with self.assertRaisesRegex(Stop, 'budget_or_call_limit'):
            rt.dispatch('repair', {})
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(read(self.root/'budget.json'), rt.ledger)

    def test_uncertain_and_excess_receipts_block_further_calls(self):
        for cost in (None, '0.03'):
            with self.subTest(cost=cost), tempfile.TemporaryDirectory() as d:
                worker = Mock(return_value=envelope('by trivial', cost))
                rt = Runtime(Path(d), protocol(), worker)
                with self.assertRaisesRegex(Stop, 'unsettled_receipt'):
                    rt.dispatch('root', {})
                with self.assertRaisesRegex(Stop, 'budget_or_call_limit'):
                    rt.dispatch('repair', {})
                self.assertEqual(worker.call_count, 1)
                self.assertTrue(rt.cost_summary()['unknown_cost'])
                self.assertIsNone(rt.cost_summary()['simulated_cost_usd'])

    def test_request_and_reservation_durable_before_worker(self):
        def worker(request):
            self.assertEqual(read(self.root/'budget.json')['attempts'][request['call_id']]['status'], 'reserved')
            requests = list((self.root/'tape').glob('*-request.json'))
            self.assertEqual(read(sorted(requests)[-1])['kind'], 'worker')
            return envelope('by trivial')
        self.runtime(worker).dispatch('repair', {'goal': {'target': 'True'}})

    def test_dispatch_failure_keeps_reservation(self):
        def fail(request):
            raise RuntimeError('fixture transport interrupted')
        rt = self.runtime(fail)
        with self.assertRaises(RuntimeError):
            rt.dispatch('repair', {})
        self.assertEqual(rt.ledger['attempts']['call-001']['status'], 'reserved')
        self.assertTrue(rt.cost_summary()['unknown_cost'])

    def test_global_call_fuse_and_repair_call_fuse(self):
        rt = self.runtime(limits=asdict(Limits(run_calls=2, repair_calls=1)))
        rt.dispatch('root', {})
        rt.dispatch('repair', {})
        with self.assertRaisesRegex(Stop, 'repair_call_limit'):
            rt.dispatch('repair', {})
        with self.assertRaisesRegex(Stop, 'budget_or_call_limit'):
            rt.dispatch('root', {})
        self.assertEqual(len(rt.ledger['attempts']), 2)

    def test_clock_limits_prevent_native_or_worker_start(self):
        rt = self.runtime()
        rt.repair_start = 1
        with patch.object(rt, 'now', return_value=121), patch.object(rt.native, 'inspect') as inspect:
            with self.assertRaisesRegex(Stop, 'repair_time_limit'):
                rt.inspect('unused')
            inspect.assert_not_called()
        with patch.object(rt, 'now', return_value=600):
            with self.assertRaisesRegex(Stop, 'run_time_limit'):
                rt.dispatch('root', {})

    def test_lean_fuse_blocks_before_compile(self):
        rt = self.runtime()
        rt.repair_lean_calls = rt.limits.lean_calls
        with patch.object(rt.native, 'inspect') as inspect:
            with self.assertRaisesRegex(Stop, 'lean_call_limit'):
                rt.inspect('unused')
            inspect.assert_not_called()

    def test_replay_does_not_execute_and_rejects_changed_decisions(self):
        tape = Tape(self.root)
        tape.call('worker', {'node': 'n1'}, lambda: {'proof': 'by trivial'})
        replay = Tape(self.root, replay=True)
        self.assertEqual(replay.call('worker', {'node': 'n1'}, lambda: self.fail('callback executed')), {'proof': 'by trivial'})
        replay.assert_complete()
        with self.assertRaisesRegex(ValueError, 'differs'):
            Tape(self.root, replay=True).call('worker', {'node': 'other'})

    def test_utf8_byte_edit_preserves_surrounding_context_and_rejects_stale_range(self):
        source = 'theorem α (β : Prop) : True := by\n  skip\n'
        start = len(source[:source.index('skip')].encode())
        site = {'start': start, 'end': start+4, 'append': False, 'indent': 2, 'source_sha256': sha(source)}
        edited, region = patch_site(source, site, 'by trivial')
        self.assertTrue(edited.startswith('theorem α (β : Prop) : True := by\n  exact (by'))
        self.assertEqual(edited.encode()[region[0]:region[0]+2], b'by')
        with self.assertRaisesRegex(ValueError, 'Stale'):
            patch_site(source+' ', site, 'by trivial')
        unicode_start = len('theorem '.encode())
        with self.assertRaises(UnicodeDecodeError):
            splice(source, unicode_start+1, unicode_start+2, 'x')

    def test_subproof_guard_blocks_sorry_commands_and_statement_injection(self):
        source = 'theorem demo : True := by skip'
        site = {'start': len(source)-4, 'end': len(source), 'append': False, 'indent': 2, 'source_sha256': sha(source)}
        for proof in ('by sorry', 'by admit', 'by\n  run_tac pure ()', 'by trivial\ntheorem other : False := by sorry'):
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                patch_site(source, site, proof)

    def test_duplicate_root_is_not_evaluated(self):
        rt = self.runtime(lambda request: envelope('by exact True.intro'))
        with patch.object(rt, 'preflight', return_value={'status':'passed'}), \
             patch.object(rt, 'availability', return_value=['rfl']), \
             patch.object(rt, 'evaluate', return_value=evaluation()) as evaluate:
            result = workflow(rt)
        self.assertEqual(result['stop_reason'], 'duplicate')
        self.assertEqual([c.args[1] for c in evaluate.call_args_list], ['baseline', 'final-selected'])

    def test_final_proof_failure_falls_back_but_timeout_stays_unknown(self):
        for kind in ('compile', 'timeout'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                rt = Runtime(Path(d), protocol(), lambda request: envelope('by trivial'))
                rows = [evaluation(), evaluation(tokens=1), evaluation(False,error=kind), evaluation()]
                with patch.object(rt, 'preflight', return_value={'status':'passed'}), \
                     patch.object(rt, 'availability', return_value=['rfl']), \
                     patch.object(rt, 'evaluate', side_effect=rows) as evaluate:
                    result = workflow(rt)
                if kind == 'compile':
                    self.assertEqual(result['selected_origin'], 'baseline')
                    self.assertEqual(result['final_q'], 2)
                    self.assertEqual(evaluate.call_count, 4)
                else:
                    self.assertIsNone(result['final_valid'])
                    self.assertIsNone(result['final_q'])
                    self.assertEqual(evaluate.call_count, 3)

    def test_invalid_baseline_never_dispatches(self):
        worker=Mock()
        rt=self.runtime(worker)
        with patch.object(rt, 'preflight', return_value={'status':'passed'}), \
             patch.object(rt, 'availability', return_value=['rfl']), \
             patch.object(rt, 'evaluate', return_value=evaluation(False)):
            result=workflow(rt)
        worker.assert_not_called()
        self.assertIsNone(result['final_q'])


if __name__ == '__main__':
    unittest.main()
