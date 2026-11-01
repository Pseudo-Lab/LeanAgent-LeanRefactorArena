"""OpenRouter routing, list-price accounting and the $2.50 cap; no network."""
from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from common import HERE, Stop, read
from generation import RUN_BUDGET, SUITE_BUDGET, prepare, check
from generation_runtime import GenerationRuntime
from openrouter_transport import OpenRouterTransport, normalize, payload, plan_request, validate_endpoint
from test_generation import settings, ledger


def endpoint():
    return read(HERE/'integration/openrouter-endpoint.json')


def receipt(cost='0.001', finish='stop'):
    return {'id': 'test-receipt', 'model': 'openai/gpt-6.1-sol-20260929', 'provider': 'OpenAI',
            'choices': [{'finish_reason': finish, 'message': {'content': '{"proof":"by trivial"}'}}],
            'usage': {'cost': cost, 'prompt_tokens': 1000, 'completion_tokens': 100,
                      'prompt_tokens_details': {'cached_tokens': 300, 'cache_write_tokens': 200},
                      'completion_tokens_details': {'reasoning_tokens': 40}}}


class OpenRouterGeneration(unittest.TestCase):
    def config(self):
        p = settings()
        p.update(backend='openrouter', endpoint=endpoint(), run_budget_usd=RUN_BUDGET)
        return p

    def test_all_roles_use_same_provider_schema_cache_and_budget_ceiling(self):
        p = self.config()
        for role in ('planner', 'root', 'repair'):
            packet = {'role': role, 'call_id': 'baseline-r1/call-001'}
            plan = plan_request(p, packet, Decimal('.125') if role == 'planner' else Decimal(RUN_BUDGET))
            body = plan['body']
            self.assertEqual(body['provider']['only'], ['openai'])
            self.assertFalse(body['provider']['allow_fallbacks'])
            self.assertEqual(body['model'], 'openai/gpt-6.1-sol')
            self.assertEqual(body['response_format']['json_schema']['strict'], True)
            self.assertEqual(body['messages'][1]['content'][0]['prompt_cache_breakpoint'], {'mode': 'explicit'})
            self.assertNotIn('call_id', body['messages'][1]['content'][1]['text'])
            self.assertLessEqual(Decimal(plan['reserved_usd']), Decimal(RUN_BUDGET))
            self.assertIsNone(plan_request(p, packet, Decimal('.001')))

    def test_unknown_pricing_or_routing_fails_closed(self):
        for change in ({'tag': 'openai/flex'}, {'model_id': 'other/model'},
                       {'pricing': {**endpoint()['pricing'], 'completion': '0.5'}},
                       {'pricing': {**endpoint()['pricing'], 'discount': '.5'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_endpoint({**endpoint(), **change})

    def test_list_price_includes_reasoning_and_guards_discounts(self):
        value = normalize(receipt(), endpoint())
        self.assertEqual(Decimal(value['usage']['cost']), Decimal('.00253'))
        self.assertEqual(value['openrouter_accounting']['provider_reported_usd'], '0.001')
        incomplete = normalize(receipt('0.004', finish='length'), endpoint())
        self.assertIsNone(incomplete['choices'][0]['message']['content'])
        self.assertEqual(incomplete['usage']['cost'], '0.004')

    def test_missing_receipt_or_usage_never_becomes_free(self):
        for raw in (receipt(None), {'error': 'timeout'}, {**receipt(), 'provider': 'other'}):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize(raw, endpoint())['usage']['cost'])
        raw = receipt()
        del raw['usage']['prompt_tokens_details']['cache_write_tokens']
        self.assertIsNone(normalize(raw, endpoint())['usage']['cost'])

    def test_disabled_transport_and_mock_http_use_only_openrouter(self):
        p = self.config()
        packet = {'role': 'root'}
        planned = plan_request(p, packet, Decimal(RUN_BUDGET))
        with patch('openrouter_transport.models.load_key') as key:
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                OpenRouterTransport(p, dotenv=Path('unused'))(packet, planned, 1)
            key.assert_not_called()
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(receipt()).encode())
        with patch('openrouter_transport.models.load_key', return_value='sk-or-local-test-placeholder'), \
             patch('openrouter_transport.request.build_opener', return_value=opener):
            raw = OpenRouterTransport(p, enabled=True, dotenv=Path('unused'))(packet, planned, 1)
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(opener.open.call_args.args[0].full_url, 'https://openrouter.ai/api/v1/chat/completions')
        self.assertEqual(raw['cost_basis'], 'max_provider_reported_and_list_price')

    def test_malformed_usage_stops_further_calls_and_preserves_charge(self):
        raw = receipt()
        raw['usage']['prompt_tokens_details'] = None
        normalized = normalize(raw, endpoint())
        self.assertIsNone(normalized['usage']['cost'])
        self.assertEqual(normalized['openrouter_accounting']['provider_reported_usd'], '0.001')
        for usage in (None, [], 7):
            self.assertIsNone(normalize({**receipt(), 'usage': usage}, endpoint())['usage']['cost'])
        for choices in (None, {}, [None]):
            value = normalize({**receipt(), 'choices': choices}, endpoint())
            self.assertIsNone(value['choices'][0]['message']['content'])
            self.assertEqual(Decimal(value['usage']['cost']), Decimal('.00253'))
        with tempfile.TemporaryDirectory() as d:
            transport = Mock(return_value=normalized)
            rt = GenerationRuntime(Path(d), self.config(), ledger(), transport)
            with self.assertRaises(Stop):
                rt.dispatch('root', {})
            with self.assertRaises(Stop):
                rt.dispatch('repair', {})
            self.assertEqual(transport.call_count, 1)
            self.assertTrue(rt.cost_summary()['unknown_cost'])

    def test_provider_charge_and_guard_debit_remain_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            rt = GenerationRuntime(Path(d), self.config(), ledger(), lambda *args: normalize(receipt(), endpoint()))
            rt.dispatch('root', {})
            summary = rt.cost_summary()
            self.assertEqual(summary['actual_api_cost_usd'], '0.001')
            self.assertEqual(Decimal(summary['budget_debit_usd']), Decimal('.00253'))
            self.assertEqual(summary['actual_api_calls'], 1)

    def test_suite_freezes_four_equal_caps_and_rejects_over_budget_edits(self):
        with tempfile.TemporaryDirectory() as d:
            p = settings()
            fixture = {'problem': p['problem'], 'environment': p['environment'], 'limits': p['limits'], 'responses': {}}
            root = Path(d)/'suite'
            saved = prepare(root, fixture=fixture)
            self.assertEqual(Decimal(saved['run_budget_usd'])*4, Decimal('2.50'))
            self.assertEqual(saved['suite_budget_usd'], SUITE_BUDGET)
            check(root)
            value = read(root/'protocol.json')
            value['suite_budget_usd'] = '2.80'
            (root/'protocol.json').write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
                check(root)


if __name__ == '__main__':
    unittest.main()
