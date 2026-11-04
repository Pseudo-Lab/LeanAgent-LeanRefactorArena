"""Optional Bank preparation and shared request routing in the durable batch."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import actions, artifacts as a, harness as h
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
        # Integration: PR #62 freezes a prompt policy in every prepared row.
        d.atomic(f.output / 'input/prompt-policy.json', d.prompt_variants.policy())
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


def measured(tokens=4, hb=40, all_versions=False):
    env = {"valid": True, "runs": [{"measurement": {"raw": hb}} for _ in range(3)]}
    return {"valid": True, "tokens": tokens,
            "environments": {"primary": env, **({"secondary": copy.deepcopy(env)} if all_versions else {})}}


class NonPortfolioAlternationTests(unittest.TestCase):
    """Without portfolio, alternating-v1 counts model proposals only (#62 seed, #49 children excluded)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.problem = {"id": "F002", "row": 2, "name": "test", "source": "strata", "dataset_sha256": d.DATASET_SHA,
                        "statement": "theorem test : True", "reference": "theorem test : True := by trivial\n",
                        "environments": ["primary", "secondary"]}
        self.config = d.configuration(self.problem, None, strategy_settings=settings())
        self.output = d.folder(self.root, 2)

    def modes(self, state, *, autosolver_after=()):
        seen = []
        for i in range(5):
            body = d.make_request(state, self.problem, self.config, "JSON actions")
            packet = json.loads(body["messages"][1]["content"])
            seen.append(packet["strategy_bank"]["search_mode"])
            raw = {"choices": [{"message": {"content": json.dumps({"action": "propose", "parent_id": "c000",
                   "strategy": f"step {i}", "proof": f"by trivial -- {i}"})}}], "usage": {"cost": "0.01"}}
            action, code, observation = actions.prepare(raw, state, self.problem, self.config, {"entries": []},
                                                        h.parse_proof)
            state = h.advance(state, raw, code, measured(9 - i % 3, 90), None, state["baseline"], self.config,
                              str(self.output), action=action, observation=observation)
            if i in autosolver_after:
                # The real child insertion (harness.apply_automatic) with a replayed native search.
                with patch.object(h.autosolver, "replay_search", return_value={"candidate_code": code + " -- auto"}), \
                        patch.object(h.autosolver, "summary",
                                     return_value={"attempts": 1, "inspections": 1, "native_seconds": 0.0}):
                    h.apply_automatic(state, code, {"search": {}, "evaluation": measured(3, 30)}, state["baseline"],
                                      self.config, str(self.output))
        return seen, state

    def test_cold_start_warm_start_and_autosolver_children_keep_free_first_alternation(self):
        expected = ["free", "guided", "free", "guided", "free"]
        cold = h.initial_state(self.problem, measured(10, 100), self.config)
        self.assertEqual(self.modes(copy.deepcopy(cold))[0], expected)
        code = "theorem test : True := by exact True.intro\n"
        manifest = self.root / "manifest.json"
        d.atomic(manifest, {"schemaVersion": 1, "auditPassed": True, "datasetSha256": d.DATASET_SHA,
            "problems": [{"row": 2, "name": "test", "source": "strata", "proof": code, "candidateHash": a.sha(code),
                          "runId": "historical-best", "versions": [{"environment": e, "status": "pass"}
                                                                   for e in self.problem["environments"]]}]})
        seed = d.warm_start.snapshot(manifest, self.problem)
        warm = d.warm_start.seed_state(copy.deepcopy(cold), seed, self.problem, measured(), measured(all_versions=True))
        self.assertIn("seed-best", warm["exploration"]["candidates"])
        self.assertEqual(self.modes(warm)[0], expected)
        modes, state = self.modes(copy.deepcopy(cold), autosolver_after=(0,))
        self.assertIn("c001-auto", state["exploration"]["candidates"])
        self.assertEqual(modes, expected)


if __name__ == '__main__':
    unittest.main()
