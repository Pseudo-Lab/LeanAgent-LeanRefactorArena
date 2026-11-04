"""Main's OpenAI transport, role receipts and single-run lifecycle; no network."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import generation
from common import Stop, canonical, inventory, read, sha, shared
from generation_records import reconcile
from generation_runtime import GenerationRuntime
from generation_transport import OpenAITransport, plan_request
from lean_agent import accounting, openai_direct, status
from openrouter_transport import terminal_key
from test_contracts import evaluation
from test_generation import PLAN, settings, ledger


def receipt(role='root', *, status='completed', model='gpt-6.1-sol'):
    content = PLAN if role == 'planner' else {'proof': 'by trivial'}
    return {'id': 'resp-'+role, 'model': model, 'service_tier': 'default', 'status': status,
            'output': [{'type': 'message', 'role': 'assistant', 'content': [
                {'type': 'output_text', 'text': canonical(content)}]}],
            'usage': {'input_tokens': 1000, 'input_tokens_details': {'cached_tokens': 200, 'cache_write_tokens': 300},
                      'output_tokens': 500, 'output_tokens_details': {'reasoning_tokens': 400}, 'total_tokens': 1500}}


class DirectGeneration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.p = settings()
        self.p['backend'] = 'openai'

    def test_all_roles_use_main_http_normalizer_and_estimated_cost(self):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(receipt(role)).encode()) for role in ('planner', 'root', 'repair')]
        with patch.object(openai_direct.request, 'build_opener', return_value=opener), \
             patch.object(openai_direct, 'load_key', side_effect=AssertionError('No file/env key')):
            rt = GenerationRuntime(self.root, self.p, ledger(), OpenAITransport(self.p, enabled=True, key='sk-proj-fixture-only'))
            rt.repair_start = 0
            for role in ('planner', 'root', 'repair'):
                rt.dispatch(role, {})
        self.assertEqual(opener.open.call_count, 3)
        for call in opener.open.call_args_list:
            req = call.args[0]
            self.assertEqual(req.full_url, openai_direct.ENDPOINT)
            self.assertEqual(req.get_header('Authorization'), 'Bearer sk-proj-fixture-only')
            body = json.loads(req.data)
            self.assertEqual(body['model'], openai_direct.MODEL)
            self.assertEqual(body['reasoning'], {'effort': 'high'})
            self.assertEqual(body['service_tier'], 'default')
        report = reconcile(rt)
        self.assertIsNone(report['summary']['actual_api_cost_usd'])
        self.assertIsNone(report['summary']['reported_cost_usd'])
        self.assertEqual(Decimal(report['summary']['estimated_api_cost_usd']), Decimal('.02031'))
        self.assertEqual(report['summary']['estimated_api_cost_usd'], report['summary']['budget_debit_usd'])
        self.assertEqual(report['summary']['actual_api_calls'], 3)
        self.assertEqual({r['agent_id'] for r in report['receipts']}, {'planner', 'root', 'repair'})
        self.assertEqual(rt.cost_summary()['cost_basis'], 'usage_estimate')
        self.assertIsNone(rt.cost_summary()['actual_api_cost_usd'])
        self.assertNotIn('sk-proj-fixture-only', ''.join(p.read_text() for p in self.root.rglob('*.json')))
        replay = GenerationRuntime(self.root, self.p, ledger(), replay=True)
        replay.repair_start = 0
        with patch.object(openai_direct, 'request_once', side_effect=AssertionError('Replay API')):
            for role in ('planner', 'root', 'repair'):
                replay.dispatch(role, {})
        replay.tape.assert_complete()
        self.assertEqual(replay.ledger, rt.ledger)

    def test_terminal_accepts_project_key_and_rejects_other_provider(self):
        with patch('openrouter_transport.sys.stdin.isatty', return_value=True), \
             patch('openrouter_transport.getpass.getpass', return_value='  sk-proj-fixture-only  ') as prompt:
            self.assertEqual(terminal_key('openai'), 'sk-proj-fixture-only')
            self.assertEqual(prompt.call_args.args[0], 'OpenAI API key (hidden input): ')
        for key in ('sk-or-fixture-only', '', 'Bearer sk-proj-fixture', '"sk-proj-fixture"', 'sk-proj-fixture with-space'):
            with self.subTest(key=key), patch('openrouter_transport.sys.stdin.isatty', return_value=True), \
                 patch('openrouter_transport.getpass.getpass', return_value=key), self.assertRaises(ValueError):
                terminal_key('openai')

    def test_wrong_key_and_mutated_payload_never_reach_main_http(self):
        packet = {'role': 'planner'}
        planned = plan_request(self.p, packet, Decimal('.50'))
        with patch.object(openai_direct, 'request_once', side_effect=AssertionError('Unexpected API')):
            with self.assertRaises(ValueError):
                OpenAITransport(self.p, enabled=True, key='sk-or-wrong')(packet, planned, 1)
            changed = deepcopy(planned)
            changed['body']['service_tier'] = 'priority'
            with self.assertRaises(ValueError):
                OpenAITransport(self.p, enabled=True, key='sk-proj-fixture')(packet, changed, 1)

    def test_timeout_retains_unknown_charge_and_never_retries(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError('sk-proj-fixture-only')
        with patch.object(openai_direct.request, 'build_opener', return_value=opener):
            rt = GenerationRuntime(self.root, self.p, ledger(), OpenAITransport(self.p, enabled=True, key='sk-proj-fixture-only'))
            for _ in range(2):
                with self.assertRaisesRegex(Stop, 'unsettled_receipt'):
                    rt.dispatch('root', {})
        self.assertEqual(opener.open.call_count, 1)
        report = accounting.native_report(self.root)
        self.assertIsNone(report['summary']['estimated_api_cost_usd'])
        self.assertIsNone(report['summary']['actual_api_cost_usd'])
        self.assertEqual(report['summary']['unsettled_calls'], 1)
        self.assertNotIn('sk-proj-fixture-only', canonical(read(self.root/'calls/0001/response.json')))

    def test_incomplete_is_priced_and_snapshot_identity_is_preserved(self):
        raw = receipt(status='incomplete', model='gpt-6.1-sol-2026-09-29')
        rt = GenerationRuntime(self.root, self.p, ledger(), lambda *args: openai_direct.normalize(raw, self.p['pricing']))
        result = rt.dispatch('root', {})
        self.assertIsNone(result['choices'][0]['message']['content'])
        report = reconcile(rt)
        self.assertEqual(report['receipts'][0]['provider_model'], raw['model'])
        self.assertEqual(report['receipts'][0]['model'], openai_direct.MODEL)
        self.assertEqual(Decimal(report['summary']['estimated_api_cost_usd']), Decimal('.00677'))

    def test_bad_usage_or_model_is_unknown_not_free(self):
        bad = []
        for field in ('input_tokens_details', 'output_tokens_details'):
            raw = receipt(); raw['usage'][field] = None; bad.append(raw)
        raw = receipt(); del raw['usage']['input_tokens_details']['cache_write_tokens']; bad.append(raw)
        raw = receipt(); raw['model'] = 'unpriced'; bad.append(raw)
        raw = receipt(); raw['service_tier'] = 'priority'; bad.append(raw)
        for index, raw in enumerate(bad):
            with self.subTest(index=index):
                (self.root/str(index)).mkdir()
                rt = GenerationRuntime(self.root/str(index), self.p, ledger(), lambda *args: openai_direct.normalize(raw, self.p['pricing']))
                with self.assertRaisesRegex(Stop, 'unsettled_receipt'):
                    rt.dispatch('root', {})
                self.assertIsNone(accounting.native_report(rt.root)['summary']['budget_debit_usd'])

    def test_pending_request_and_normalized_receipt_tampering(self):
        (self.root/'pending').mkdir()
        rt = GenerationRuntime(self.root/'pending', self.p, ledger(), Mock(side_effect=KeyboardInterrupt))
        with self.assertRaises(KeyboardInterrupt):
            rt.dispatch('root', {})
        report = accounting.native_report(rt.root)
        self.assertIsNone(report['summary']['actual_api_cost_usd'])
        self.assertIsNone(report['summary']['estimated_api_cost_usd'])
        raw = openai_direct.normalize(receipt(), self.p['pricing'])
        raw['usage']['cost'] = '0'
        (self.root/'tampered').mkdir()
        rt = GenerationRuntime(self.root/'tampered', self.p, ledger(), Mock(return_value=raw))
        with self.assertRaisesRegex(ValueError, 'original provider receipt'):
            rt.dispatch('root', {})

    def prepare_suite(self):
        # Synthetic official-format metadata exercises preparation without relying
        # on ignored benchmark downloads or a real model/library installation.
        p = deepcopy(self.p)
        p['environment']['toolchain'] = 'leanprover/lean4:v4.26.0'
        ready = {'ready': True, 'problem_id': 'P02', 'problem': p['problem'], 'environment': p['environment'],
                 'limits': asdict(generation.p02_limits()), 'measurement_sources': {},
                 'fingerprint': {'git': {'head': 'fixture-pin'}}, 'baseline': evaluation()}
        reference = {'status': 'completed', 'reason': None, 'baseline': evaluation(), 'tactics': [], 'fingerprint': ready['fingerprint']}
        calibration = self.root/'calibration'
        calibration.mkdir()
        shared.atomic(calibration/'result.json', ready)
        shared.atomic(calibration/'artifacts.json', inventory(calibration))
        meta = {'name': p['problem']['name'], 'src': p['problem']['reference'], 'statement': p['problem']['statement'],
                'version_info': [{'v4.26.0': 'fixture-pin'}], 'file_path': 'Fixture.lean', 'url': 'fixture-only'}
        benchmark = self.root/'benchmark'
        benchmark.mkdir()
        shared.atomic(benchmark/'benchmark_data_warmup.jsonl', meta)
        shared.atomic(benchmark/'snapshot.json', {'arena_revision': 'fixture-only', 'files': {'benchmark_data_warmup.jsonl': {
            'sha256': sha((benchmark/'benchmark_data_warmup.jsonl').read_bytes()), 'url': 'fixture-only'}}})
        def reader(path):
            if str(path).endswith('experiments/problem-inputs/P02/agent-input.json'):
                return {'problem': {'original': p['problem']['reference']}, 'context': {}}
            return read(path)
        root = self.root/'suite'
        with patch('generation.competition.SNAPSHOT', str(benchmark)), patch('generation.read', side_effect=reader), \
             patch('generation.CONTROL', {**generation.CONTROL, 'max_steps': 1}), \
             patch('generation.fetch_endpoint', side_effect=AssertionError('OpenRouter metadata')):
            generation.prepare(root, calibration, backend='openai')
        return root, reference

    def test_direct_prepare_gate_run_completion_cost_and_replay(self):
        root, reference = self.prepare_suite()
        protocol = generation.check(root)
        self.assertEqual(protocol['condition_order'], [['repair-r1', 'recursive-repair-v1']])
        self.assertEqual(protocol['execution_scope'], 'personal-experiment')
        self.assertEqual(protocol['run_budget_usd'], protocol['suite_budget_usd'])
        self.assertEqual(protocol['suite_budget_usd'], '2.50')
        with patch('generation.terminal_key', side_effect=AssertionError('Paid gate key')):
            with self.assertRaisesRegex(ValueError, 'disabled'):
                generation.process(root)
        self.assertFalse((root/'reference').exists())
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(receipt(role)).encode()) for role in ('planner', 'root')]
        with patch('generation.reference_workflow', return_value=reference), \
             patch('generation.prepared.PreparedLeanEvaluator'), \
             patch('generation.terminal_key', return_value='sk-proj-fixture-only') as key, \
             patch('generation.fetch_endpoint', side_effect=AssertionError('OpenRouter metadata')), \
             patch('native.NativeLean.evaluate', return_value=evaluation(tokens=5)), \
             patch.object(openai_direct, 'load_key', side_effect=AssertionError('File/env key')), \
             patch.object(openai_direct.request, 'build_opener', return_value=opener), patch('builtins.print'):
            summary = generation.process(root, allow_paid=True)
        key.assert_called_once_with('openai')
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(summary['status'], 'completed')
        self.assertIsNone(summary['actual_api_cost_usd'])
        self.assertEqual(Decimal(summary['estimated_api_cost_usd']), Decimal('.01354'))
        self.assertEqual(summary['compatibility']['passed_versions'], 1)
        view = status.inspect(root/'runs/repair-r1')
        self.assertTrue(view['sealed'])
        self.assertEqual(view['status'], 'completed')
        moved = self.root/'relocated'
        shutil.move(root, moved)
        with patch('generation.reference_workflow', return_value=reference), \
             patch('generation.terminal_key', side_effect=AssertionError('Replay credentials')), \
             patch.object(openai_direct, 'request_once', side_effect=AssertionError('Replay network')), \
             patch('subprocess.Popen', side_effect=AssertionError('Replay Lean')):
            self.assertEqual(generation.process(moved, replay=True), summary)

    def test_direct_frozen_price_scope_and_backend_mutations_are_rejected(self):
        root, _ = self.prepare_suite()
        for field, value in [('execution_scope', 'competition-api-route'), ('pricing', {}), ('backend', 'openrouter')]:
            protocol = read(root/'protocol.json')
            changed = {**protocol, field: value}
            shared.atomic(root/'protocol.json', changed)
            shared.atomic(root/'frozen-inputs.json', inventory(root))
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError, AttributeError)):
                generation.check(root)
            shared.atomic(root/'protocol.json', protocol)
            shared.atomic(root/'frozen-inputs.json', inventory(root))


if __name__ == '__main__':
    unittest.main()
