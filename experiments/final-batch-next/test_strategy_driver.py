"""Optional Bank preparation and shared request routing in the durable batch."""
import contextlib
import io
import unittest
from unittest.mock import patch

from lean_agent import artifacts as a, harness as h
import test_portfolio_driver as fixtures
from test_portfolio_driver import d, report, result


def settings():
    return {"top_k": 1, "contextual": True, "search_policy": "alternating-v1",
            "bank": {"schema_version": 1, "version": "synthetic", "scope": "warmup",
                     "strategies": [{"id": "S1", "title": "Synthetic strategy", "match": {},
                         "guide": "Inspect the current goal.", "risks": "Check assumptions.",
                         "evidence": [{"problem": "other", "candidate_sha256": "a" * 64}]}]}}


class StrategyBatchTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.PortfolioBatchTests('test_batch_finishes_below_threshold_after_merger_and_resumes_without_calls')
        f.setUp()
        self.addCleanup(f.doCleanups)
        return f

    def test_disabled_default_and_frozen_settings_copy(self):
        f = self.fixture()
        self.assertNotIn('strategy_bank', d.configuration(f.problem)['agent'])
        bank = settings()
        config = d.configuration(f.problem, strategy_settings=bank)
        bank['bank']['strategies'][0]['guide'] = 'changed externally'
        self.assertNotEqual(config['agent']['strategy_bank'], bank)
        self.assertIn(h.BASE / 'strategy_bank.py', d.implementation_files())
        self.assertIn(h.BASE / 'strategy_signals.py', d.implementation_files())

    def test_cli_freezes_requested_bank_and_rejects_live_changes(self):
        f = self.fixture()
        bank = f.root / 'bank.json'
        a.write(bank, settings()['bank'])
        flags = ['--strategy-bank', str(bank), '--strategy-top-k', '1',
                 '--strategy-contextual', '--strategy-search-policy', 'alternating-v1']
        with patch.object(d.sys, 'argv', ['driver.py', 'inputs', '--root', str(f.root), '--rows', '1', *flags]), \
                patch.object(d, 'prepare_inputs') as prepare:
            d.main()
        self.assertEqual(prepare.call_args.kwargs['strategy_settings'], settings())
        for args in [['run', *flags], ['inputs', '--strategy-search-policy', 'alternating-v1']]:
            with patch.object(d.sys, 'argv', ['driver.py', *args, '--root', str(f.root)]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                d.main()

    def test_sealed_bank_is_reused_and_changed_settings_are_refused(self):
        f = self.fixture()
        f.config['agent']['strategy_bank'] = settings()
        path = f.output / 'input/config.json'
        d.atomic(path, f.config)
        before = path.read_bytes()
        d.atomic(f.root / 'frozen.json', {})
        d.atomic(f.root / 'authorization.json', {'rows': [1], 'verification_policy': d.VERIFICATION_POLICY})
        with patch.object(d, 'verify_frozen'):
            d.prepare(f.root, [1])
            d.prepare(f.root, [1], strategy_settings=settings())
            changed = {**settings(), 'top_k': 2}
            with self.assertRaisesRegex(ValueError, 'fresh batch root'):
                d.prepare(f.root, [1], strategy_settings=changed)
        self.assertEqual(path.read_bytes(), before)

    def test_durable_batch_uses_shared_mixed_modes_and_keeps_report_audit(self):
        f = self.fixture()
        f.config['agent']['strategy_bank'] = settings()
        f.config['agent']['portfolio'].update(merger_evaluations=2, progress_guard='bounded-v1')
        d.atomic(f.output / 'input/config.json', f.config)
        d.atomic(f.output / 'state.json', h.initial_state(f.problem, result(), f.config))
        values = [{'action': 'propose', 'parent_id': 'c000', 'strategy': 'fixture',
                   'proof': f'by trivial -- candidate {i}'} for i in range(5)]
        values[-1]['strategy_ids'] = ['S1']
        summary = f.run_batch(values)
        self.assertEqual(summary['stop_reason'], 'portfolio_complete')
        self.assertEqual([p['strategy_bank'].get('search_mode', 'withheld') for p in f.packets],
                         ['withheld', 'free', 'free', 'free', 'guided'])
        self.assertEqual(f.packets[-1]['strategy_bank']['strategies'][0]['id'], 'S1')
        self.assertTrue(report.audit_portfolio(f.output, summary, f.attempts()))


if __name__ == '__main__':
    unittest.main()
