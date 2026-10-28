"""Native receipts, interrupted calls, frozen replay and installed CLI regressions."""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from lean_agent import artifacts, harness, models, status, usage_cost as costs
import test_harness as harness_tests
from test_harness import FakeEvaluator, REPO


class UsageIntegrationTests(unittest.TestCase):
    setUp = harness_tests.HarnessTests.setUp
    save = harness_tests.HarnessTests.save

    def execute(self, query=None, check_only=False, evaluator=None):
        self.save()
        return harness.run(self.path, self.output, evaluator=evaluator or FakeEvaluator(),
                           query=query, check_only=check_only)

    def report(self):
        return artifacts.read(self.output / 'usage-cost.json')

    def configure_prices(self):
        prices = copy.deepcopy(costs.NO_PRICES)
        prices.update(rate_card_id='test-only', source='synthetic', as_of='2026-10-28')
        prices['models']['fixture-v1'] = {'input_per_million': '2', 'output_per_million': '10'}
        self.prices = self.root / 'prices.json'
        self.prices.write_text(json.dumps(prices))
        self.config['usage_cost'] = {'prices': 'prices.json'}

    def test_failed_proof_is_counted_and_live_status_accumulates_pending_calls(self):
        def query(*args):
            view = status.inspect(self.output)['usage_cost']
            self.assertEqual(view['entries'], args[2])
            self.assertEqual(view['unknown_cost_entries'], 1)
            self.assertIsNone(view['reported_cost_usd'])
            self.assertEqual(Decimal(view['reported_cost_known_subtotal_usd']), Decimal('.1') * (args[2]-1))
            response = models.query(*args)
            response['usage'].update(cost='.1', prompt_tokens=100, completion_tokens=10)
            return response
        self.execute(query)
        summary = self.report()['summary']
        self.assertEqual(summary['reported_cost_usd'], '0.3')
        self.assertEqual(summary['tokens']['input_tokens']['total'], 300)
        self.assertIsNone(summary['estimated_token_cost_usd'])
        self.assertEqual(artifacts.read(self.output / 'steps/001/event.json')['state_after']['latest']['feedback']['valid'], False)
        self.assertEqual(status.inspect(self.output)['usage_cost']['reported_cost_usd'], '0.3')
        self.assertTrue(harness.replay(self.output)['usage_cost_replay_passed'])

    def test_estimates_do_not_change_unknown_billing_stop(self):
        self.configure_prices()
        def query(*args):
            response = models.query(*args)
            response['usage'] = {'prompt_tokens': 100, 'completion_tokens': 10}
            return response
        result = self.execute(query)
        self.assertEqual(result['stop_reason'], 'unknown_cost')
        self.assertEqual(result['state']['calls'], 1)
        self.assertEqual(result['state']['cost_usd'], '0')
        self.assertIsNone(self.report()['summary']['reported_cost_usd'])
        self.assertEqual(self.report()['summary']['estimated_token_cost_usd'], '0.0003')
        self.assertTrue(harness.replay(self.output)['usage_cost_replay_passed'])

    def test_interruption_preserves_unknown_call_and_original_exception(self):
        def query(*args):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.execute(query)
        report = self.report()
        self.assertEqual(report['receipts'][0]['status'], 'incomplete')
        self.assertEqual(report['summary']['unknown_cost_entries'], 1)
        self.assertIsNone(report['summary']['accounted_cost_usd'])
        self.assertEqual(status.inspect(self.output)['status'], 'interrupted')

    def test_cost_threshold_keeps_both_reports_and_frozen_price_estimates(self):
        self.configure_prices()
        self.config['limits']['cost_stop_usd'] = '0.15'

        def query(*args):
            response = models.query(*args)
            response['usage'].update(cost='0.1', prompt_tokens=100, completion_tokens=10)
            return response

        result = self.execute(query)
        self.assertEqual(result['stop_reason'], 'cost_limit')
        self.assertEqual(result['state']['calls'], 2)
        report = self.report()['summary']
        usage = artifacts.read(self.output / 'usage-summary.json')
        self.assertEqual(report['reported_cost_usd'], usage['reported_cost_usd'])
        self.assertEqual(report['reported_cost_usd'], '0.2')
        self.assertEqual(report['estimated_token_cost_usd'], '0.0006')
        self.assertEqual(usage['tokens']['input_tokens']['median'], 100)
        self.assertTrue(harness.replay(self.output)['usage_cost_replay_passed'])

    def test_malformed_usage_preserves_billing_in_both_native_reports(self):
        def query(*args):
            response = models.query(*args)
            response['usage'].update(cost='0.1', prompt_tokens=-1)
            return response

        self.execute(query)
        report = self.report()
        usage = artifacts.read(self.output / 'usage-summary.json')
        self.assertEqual(report['summary']['reported_cost_usd'], '0.3')
        self.assertEqual(usage['reported_cost_usd'], '0.3')
        self.assertTrue(all(row['usage_error'] for row in report['receipts']))
        self.assertTrue(harness.replay(self.output)['usage_cost_replay_passed'])

    def test_partial_response_is_unavailable_until_complete(self):
        def query(*args):
            path = self.output / 'steps' / f'{args[2]:03}' / 'response.json'
            path.write_bytes(b'{')
            view = status.inspect(self.output)
            self.assertIsNone(view['usage_cost'])
            self.assertIn('usage_cost_error', view)
            path.unlink()
            return models.query(*args)
        self.execute(query)
        self.assertEqual(self.report()['summary']['entries'], 3)

    def test_invalid_envelope_stays_unknown_without_losing_harness_result(self):
        result = self.execute(lambda *args: [])
        self.assertEqual(result['stop_reason'], 'unknown_cost')
        self.assertEqual(self.report()['summary']['unknown_cost_entries'], 1)
        self.assertEqual(self.report()['receipts'][0]['status'], 'failed')

    def test_check_without_dispatch_is_explicit_zero_and_no_model_call(self):
        self.execute(lambda *args: self.fail('called'), check_only=True)
        summary = self.report()['summary']
        self.assertEqual(summary['entries'], 0)
        self.assertEqual(summary['reported_cost_usd'], '0')
        self.assertEqual(status.inspect(self.output)['usage_cost']['entries'], 0)
        with self.assertRaises(ValueError):
            costs.build_report([], 'api', costs.NO_PRICES)

    def test_baseline_failure_has_no_calls_or_cost(self):
        class Broken(FakeEvaluator):
            def evaluate(self, *args):
                raise RuntimeError('baseline failed')
        with self.assertRaisesRegex(RuntimeError, 'baseline failed'):
            self.execute(evaluator=Broken())
        self.assertEqual(self.report()['summary']['entries'], 0)
        self.assertEqual(status.inspect(self.output)['usage_cost']['reported_cost_usd'], '0')

    def test_price_snapshot_and_archived_replay_survive_relocation(self):
        self.configure_prices()
        self.execute()
        self.prices.unlink()
        moved = self.root / 'moved'
        shutil.move(self.output, moved)
        with patch.object(models, 'query', side_effect=AssertionError('paid call')):
            self.assertTrue(harness.replay(moved)['usage_cost_replay_passed'])
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        completed = subprocess.run([sys.executable, '-B', str(moved / 'code/replay.py'), 'replay', str(moved)],
                                   cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)['usage_cost_replay_passed'])

    def test_resealed_cost_tampering_is_recomputed_and_rejected(self):
        self.execute()
        report = self.report()
        report['summary']['reported_cost_usd'] = '100'
        (self.output / 'usage-cost.json').write_text(json.dumps(report))
        (self.output / 'artifacts.json').unlink()
        harness.seal(self.output)
        with self.assertRaisesRegex(ValueError, 'Usage/cost report'):
            harness.replay(self.output)
        self.assertIsNone(status.inspect(self.output)['usage_cost'])

    def test_recording_rejects_budget_policy_configuration(self):
        self.config['usage_cost'] = {'budget_usd': '2.8'}
        self.save()
        with self.assertRaisesRegex(ValueError, 'only an optional prices'):
            harness.load_config(self.path)

    def test_real_usage_only_evidence_matches_verified_experiment(self):
        base = REPO / 'experiments/usage-cost/examples'
        prices = artifacts.read(base / 'observed-prices.json')
        api = costs.build_report(artifacts.read(base / 'observed-api-records.json'), 'api', prices)
        sub = costs.build_report(artifacts.read(base / 'observed-subagent-records.json'), 'subagent', prices)
        self.assertEqual(api['summary']['entries'], 6)
        self.assertEqual(Decimal(api['summary']['reported_cost_usd']), Decimal('0.2011327'))
        self.assertEqual(Decimal(api['summary']['reported_cost_usd']), Decimal(api['summary']['estimated_token_cost_usd']))
        self.assertEqual(sub['summary']['entries'], 3)
        self.assertIsNone(sub['summary']['reported_cost_usd'])
        self.assertEqual(sub['summary']['estimated_token_cost_usd'], '0.1259104')


if __name__ == '__main__':
    unittest.main()
