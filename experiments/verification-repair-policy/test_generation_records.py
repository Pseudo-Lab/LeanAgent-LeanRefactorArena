"""Shared status/cost contracts, replay integrity and exact selection; no API/Lean."""
from copy import deepcopy
from decimal import Decimal
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from common import inventory, read, shared
from controller import generation_loop
from generation import ORDER, prepare, process
from generation_records import reconcile
from generation_runtime import GenerationRuntime
from generation_transport import ScriptedTransport
from lean_agent import accounting, harness, status
from openrouter_transport import normalize
from test_generation import settings, ledger, response
from test_contracts import evaluation
from test_openrouter_generation import endpoint, receipt


class GenerationRecords(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = {'status': 'completed', 'baseline': evaluation(), 'tactics': [], 'reason': None}

    def suite(self, unknown=False):
        p = settings()
        rows = {name: [response('planner'), response('root')] for name, _ in ORDER}
        if unknown:
            rows[ORDER[0][0]][1] = {'role': 'root', 'raw': {'usage': {}, 'choices': []}}
        fixture = {'problem': p['problem'], 'environment': p['environment'], 'limits': p['limits'],
                   'controller': {'max_steps': 1}, 'responses': rows}
        path = self.root/'suite'
        prepare(path, fixture=fixture)
        with patch('generation.reference_workflow', return_value=self.reference), \
             patch('native.NativeLean.evaluate', return_value=evaluation(tokens=5)), patch('builtins.print'):
            process(path)
        return path

    def replay(self, path):
        with patch('generation.reference_workflow', return_value=self.reference), \
             patch('subprocess.Popen', side_effect=AssertionError('Replay spawned a process')), \
             patch('generation.terminal_key', side_effect=AssertionError('Replay requested credentials')), \
             patch('openrouter_transport.OpenRouterTransport.__call__', side_effect=AssertionError('Replay called API')):
            return process(path, replay=True)

    def test_completion_status_cost_cli_and_relocation(self):
        path = self.suite()
        for run_id, _ in ORDER:
            child = path/'runs'/run_id
            view = status.inspect(child)
            self.assertEqual(view['status'], 'completed')
            self.assertTrue(view['sealed'])
            self.assertEqual(view['final_result']['sha256'], read(child/'result.json')['selected_sha256'])
            self.assertEqual(view['usage_cost']['actual_api_cost_usd'], '0')
            self.assertEqual(view['usage_cost']['simulated_cost_usd'], '0.02')
        report = accounting.native_report(path)
        self.assertEqual(report['summary']['entries'], 8)
        self.assertEqual(report['summary']['actual_api_calls'], 0)
        self.assertEqual(Decimal(report['summary']['budget_debit_usd']), Decimal('.08'))
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(accounting.main(['--mode', 'api', '--format', 'recorded-run', '--input', str(path)]), 0)
            self.assertIn('"actual_api_cost_usd": "0"', output.getvalue())
        moved = self.root/'moved'
        shutil.move(path, moved)
        self.assertEqual(accounting.native_report(moved), report)
        self.assertEqual(self.replay(moved), read(moved/'summary.json'))

    def test_unknown_receipt_seals_stopped_and_blocks_later_runs(self):
        path = self.suite(unknown=True)
        view = status.inspect(path/'runs'/ORDER[0][0])
        self.assertEqual(view['status'], 'stopped')
        self.assertTrue(view['sealed'])
        self.assertIsNone(view['final_result'])
        self.assertIsNone(view['usage_cost']['budget_debit_usd'])
        self.assertEqual(view['usage_cost']['unsettled_calls'], 1)
        self.assertEqual(len(list((path/'runs').iterdir())), 1)
        self.replay(path)

    def test_failed_replay_never_seals_a_success(self):
        with patch('generation.verify_execution', side_effect=ValueError('replay failed')):
            with self.assertRaisesRegex(ValueError, 'replay failed'):
                self.suite()
        path = self.root/'suite'
        self.assertFalse((path/'artifacts.json').exists())
        for child in (path/'runs').iterdir():
            view = status.inspect(child)
            self.assertEqual(view['status'], 'incomplete')
            self.assertFalse(view['sealed'])
            self.assertIsNone(view['final_result'])

    def test_resealed_cost_receipt_source_and_lifecycle_tampering_are_rejected(self):
        pristine = self.suite()
        for target in ('usage-cost.json', 'calls/0001/response.json', 'selected.lean', 'result.json'):
            path = self.root/('copy-'+target.replace('/', '-'))
            shutil.copytree(pristine, path)
            child = path/'runs'/ORDER[0][0]
            file = child/target
            if target == 'selected.lean':
                file.write_text('theorem changed : True := by trivial')
            else:
                value = read(file)
                if target == 'usage-cost.json':
                    value['summary']['reported_cost_usd'] = '100'
                elif target == 'result.json':
                    value['replay']['record_replay_passed'] = False
                else:
                    value['usage']['cost'] = '0.02'
                shared.atomic(file, value)
            shared.atomic(child/'artifacts.json', inventory(child))
            shared.atomic(path/'artifacts.json', inventory(path))
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.replay(path)

    def test_original_provider_receipts_all_roles_and_guard_debit_reconcile(self):
        p = settings()
        p.update(backend='openrouter', endpoint=endpoint())
        responses = [normalize({**receipt(), 'id': f'request-{i}'}, endpoint()) for i in range(3)]
        rt = GenerationRuntime(self.root, p, ledger(), Mock(side_effect=responses))
        rt.repair_start = 0
        for role in ('planner', 'root', 'repair'):
            rt.dispatch(role, {})
        report = reconcile(rt)
        self.assertEqual(report['summary']['entries'], 3)
        self.assertEqual(Decimal(report['summary']['reported_cost_usd']), Decimal('.003'))
        self.assertEqual(Decimal(report['summary']['budget_debit_usd']), Decimal('.00759'))
        self.assertEqual({r['agent_id'] for r in report['receipts']}, {'planner', 'root', 'repair'})

    def test_interrupt_keeps_pending_receipt_and_never_claims_zero_cost(self):
        p = settings()
        p.update(backend='openrouter', endpoint=endpoint())
        rt = GenerationRuntime(self.root, p, ledger(), Mock(side_effect=KeyboardInterrupt))
        with self.assertRaises(KeyboardInterrupt):
            rt.dispatch('planner', {})
        view = status.inspect(self.root)
        self.assertEqual(view['status'], 'incomplete')
        self.assertFalse(view['sealed'])
        self.assertIsNone(view['usage_cost']['actual_api_cost_usd'])
        self.assertIsNone(view['usage_cost']['remaining_guard_usd'])
        self.assertEqual(view['usage_cost']['entries'], 1)
        self.assertEqual(view['usage_cost']['unsettled_calls'], 1)

    def test_selection_matches_main_for_ties_and_does_not_reset_stagnation(self):
        outputs = ['by trivial', 'by constructor']
        selected = []
        for index, proofs in enumerate((outputs, outputs[::-1])):
            path = self.root/str(index)
            path.mkdir()
            p = settings()
            p['controller']['max_steps'] = 2
            rt = GenerationRuntime(path, p, ledger(), ScriptedTransport(
                [response('planner')]+[response('root', text) for text in proofs]))
            value = evaluation(tokens=5)
            value['environments']['fixed']['runs'][0]['measurement']['raw'] = 1500
            with patch.object(rt.native, 'evaluate', return_value=value):
                result = generation_loop(rt, self.reference)
            ranked = [harness.candidate(p['problem']['statement']+' := '+proof+'\n', value,
                                       harness.metrics(self.reference['baseline'])) for proof in proofs]
            expected = min(ranked, key=harness.ranking)['sha256']
            self.assertEqual(result['selected_sha256'], expected)
            self.assertTrue(all(not row['improved'] for row in result['attempts']))
            self.assertTrue(result['attempts'][0]['selection_changed'])
            selected.append(result['selected_sha256'])
        self.assertEqual(selected[0], selected[1])

    def test_integer_selection_distinguishes_values_rounded_to_same_float(self):
        p = settings()
        p['controller']['max_steps'] = 2
        baseline = evaluation()
        baseline['environments']['fixed']['runs'][0]['measurement']['raw'] = 10**18
        worse, better = evaluation(tokens=5), evaluation(tokens=5)
        worse['environments']['fixed']['runs'][0]['measurement']['raw'] = 10**18+1
        better['environments']['fixed']['runs'][0]['measurement']['raw'] = 10**18
        rt = GenerationRuntime(self.root, p, ledger(), ScriptedTransport(
            [response('planner'), response('root', 'by trivial'), response('root', 'by constructor')]))
        with patch.object(rt.native, 'evaluate', side_effect=[worse, better, better]):
            result = generation_loop(rt, {**self.reference, 'baseline': baseline})
        self.assertEqual(result['attempts'][0]['q'], result['attempts'][1]['q'])
        self.assertTrue(result['attempts'][1]['improved'])
        self.assertEqual(result['selected_code'], p['problem']['statement']+' := by constructor\n')


if __name__ == '__main__':
    unittest.main()
