"""Optional strategy input, privacy, frozen replay and source-evidence contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from lean_agent import artifacts as a, harness as h, strategy_bank as sb, strategy_signals
import test_portfolio as fixtures

ROOT = Path(__file__).resolve().parents[1]


def bank():
    return {"schema_version": 1, "version": "test-v1", "scope": "final-adaptation", "strategies": [
        {"id": "test", "title": "Use an existing identity", "match": {},
         "guide": "Search the current context for a sufficient identity.", "risks": "Check assumptions.",
         "evidence": [{"problem": "current", "candidate_sha256": "a" * 64},
                      {"problem": "other", "candidate_sha256": "b" * 64}]}]}


class StrategyTests(unittest.TestCase):
    def settings(self):
        return {"bank": bank(), "top_k": 3}

    def test_current_problem_evidence_is_removed_from_mixed_card(self):
        value = sb.packet({"name": "current", "reference": "by rfl"}, self.settings())
        self.assertEqual(value["strategies"][0]["other_evidence_problems"], 1)
        text = json.dumps(value)
        self.assertNotIn('candidate_sha256', text)
        self.assertNotIn('"current"', text)
        self.assertNotIn('"other"', text)

    def test_single_problem_card_excluded_and_unknown_problem_falls_back(self):
        settings = self.settings()
        settings["bank"]["strategies"][0]["evidence"] = settings["bank"]["strategies"][0]["evidence"][:1]
        self.assertEqual(sb.packet({"name": "current", "reference": "by rfl"}, settings)["strategies"], [])
        self.assertEqual(len(sb.packet({"name": "unseen", "reference": "by rfl"}, settings)["strategies"]), 1)

    def test_hidden_scout_never_reads_reference_or_emits_retrieved_features(self):
        value = sb.packet({"name": "current"}, self.settings(), hidden=True)
        self.assertEqual(value["status"], "withheld_hidden_original")
        self.assertEqual(value["strategies"], [])
        self.assertNotIn("features", value)

    def test_signal_ignores_comments_strings_and_qualified_identifiers(self):
        counts = sb.features('by\n -- grind\n /- aesop /- grind -/ -/\n have s := "grind"\n exact X.grind\n grind')["counts"]
        self.assertEqual(counts["grind"], 1)
        self.assertEqual(counts["aesop"], 0)

    def test_invalid_settings_fail_before_request(self):
        for k in (True, 0, 4):
            with self.assertRaises(ValueError): sb.validate_settings({"bank": bank(), "top_k": k})
        value = bank(); value["strategies"].append(copy.deepcopy(value["strategies"][0]))
        with self.assertRaises(ValueError): sb.validate(value)
        value = bank(); value["strategies"][0]["match"] = {"tactic_min": {"grind": True}}
        with self.assertRaises(ValueError): sb.validate(value)

    def test_real_runner_snapshot_replay_and_scout_scope(self):
        fixture = fixtures.PortfolioTests("test_three_scoped_contexts_then_merger_share_one_budget_and_replay")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.config["agent"]["strategy_bank"] = self.settings()
        result = fixture.run_case()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(fixture.packets[0]["strategy_bank"]["status"], "withheld_hidden_original")
        self.assertEqual([p["strategy_bank"]["status"] for p in fixture.packets[1:]], ["retrieved"] * 3)
        snapshot = a.read(fixture.output / "input/config.json")["agent"]["strategy_bank"]
        self.assertEqual(snapshot, self.settings())
        self.assertIn("code/lean_agent/strategy_bank.py", a.read(fixture.output / "manifest.json")["files"])
        self.assertTrue(h.replay(fixture.output)["record_replay_passed"])

    def test_disabled_request_has_no_strategy_field(self):
        config = a.read(ROOT / "configs/actions-smoke.json")
        problem = {"name": "current", "reference": "theorem current : True := by trivial"}
        measured = {"valid": True, "tokens": 2, "environments": {"x": {"valid": True, "runs": [{"measurement": {"raw": 20}}]}}}
        state = h.initial_state(problem, measured, config)
        request = h.make_request(state, problem, config, "test")
        packet = json.loads(request["messages"][1]["content"])
        self.assertNotIn("strategy_bank", packet)
        self.assertNotIn("strategy_ids", packet["exploration"]["actions"]["propose"])

    def test_v2_bank_routes_by_structure_and_excludes_self_only_cards(self):
        settings = {"bank": a.read(ROOT / "configs/strategy-bank/team-v1.json"), "top_k": 3}
        sb.validate_settings(settings)
        statement = "theorem fresh (x : Polynomial ℝ) : x.natDegree ≤ 2"
        problem = {"name": "unseen", "statement": statement,
                   "reference": statement + " := by rw [Polynomial.natDegree_mul]; omega"}
        first = sb.packet(problem, settings)
        renamed = {**problem, "name": "different", "statement": statement.replace("fresh", "other"),
                   "reference": problem["reference"].replace("fresh", "other")}
        self.assertEqual(first, sb.packet(renamed, settings))
        self.assertIn("M19", [c["id"] for c in first["strategies"]])
        self.assertTrue(all(c["matched_signals"] for c in first["strategies"]))
        card = next(c for c in settings["bank"]["strategies"] if c["id"] == "M17")
        problem = {"name": card["evidence"][0]["problem"], "statement": "theorem x : True",
                   "reference": "let u : ℕ → ℤ := f; have h : Set.Finite (Set.Icc 0 1) := h; u (n+1)"}
        self.assertNotIn("M17", [c["id"] for c in sb.packet(problem, settings)["strategies"]])

    def test_signals_ignore_theorem_name_comments_and_strings(self):
        statement = "theorem Polynomial.natDegree_fake : True"
        code = statement + ' := by -- Polynomial.natDegree\n  have s := "HasDerivAt x f"\n  trivial'
        signals = strategy_signals.extract(statement, code)
        self.assertNotIn("polynomial_degree", signals)
        self.assertNotIn("derivative_expression", signals)

    def test_failed_guided_ids_are_excluded_but_environment_errors_are_not(self):
        settings = {**self.settings(), "contextual": True}
        request = {"best": {"code": "by rfl", "tokens": 2, "raw_heartbeats": 5},
                   "baseline": {"tokens": 4, "raw_heartbeats": 10},
                   "exploration": {"recent_actions": [{"action": {"strategy_ids": ["test"]},
                      "outcome": {"valid": False, "status": "proof_rejected"}}]}}
        problem = {"name": "fresh", "reference": "by rfl"}
        self.assertEqual(sb.for_request(problem, settings, request)["strategies"], [])
        request["exploration"]["recent_actions"][0]["outcome"]["status"] = "environment_failed"
        self.assertEqual(len(sb.for_request(problem, settings, request)["strategies"]), 1)


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StrategyScriptTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.PortfolioTests('test_three_scoped_contexts_then_merger_share_one_budget_and_replay')
        f.setUp()
        self.addCleanup(f.doCleanups)
        return f

    def test_configure_freezes_bank_rebases_paths_and_never_overwrites(self):
        f = self.fixture()
        source = ROOT / 'configs/actions-smoke.json'
        before = source.read_bytes()
        bank_file = f.root / 'bank.json'
        a.write(bank_file, bank())
        output = f.root / 'moved/config.json'
        module = script('configure_strategy_bank')
        config = module.configure(source, bank_file, output, contextual=True, search_policy='alternating-v1')
        self.assertEqual(config['agent']['strategy_bank']['bank'], bank())
        self.assertEqual(config['agent']['strategy_bank']['search_policy'], 'alternating-v1')
        for key in ('problem', 'template', 'project', 'prompt'):
            self.assertEqual(Path(config[key]), (source.parent / a.read(source)[key]).resolve())
        self.assertTrue(Path(config['agent']['corpus']).is_absolute())
        self.assertTrue(Path(config['model']['responses']).is_absolute())
        h.load_config(output)
        self.assertEqual(source.read_bytes(), before)
        old = output.read_bytes()
        with self.assertRaises(ValueError):
            module.configure(source, bank_file, output)
        self.assertEqual(output.read_bytes(), old)

    def test_trace_keeps_recommendation_selection_and_verification_separate(self):
        f = self.fixture()
        f.config['agent']['strategy_bank'] = {'bank': bank(), 'top_k': 1, 'search_policy': 'alternating-v1'}
        f.config['agent']['portfolio']['merger_evaluations'] = 2
        values = [fixtures.proposal(f'by rfl -- {i}') for i in range(5)]
        values[-1]['strategy_ids'] = ['test']
        f.run_case(values)
        rows = script('export_strategy_trace').export(f.output)
        self.assertEqual([r['search_mode'] for r in rows], ['withheld', 'free', 'free', 'free', 'guided'])
        self.assertEqual(rows[-1]['recommended_ids'], ['test'])
        self.assertEqual(rows[-1]['selected_ids'], ['test'])
        self.assertEqual(rows[-1]['application_status'], 'unreviewed')
        self.assertTrue(rows[-1]['verified'])
        self.assertTrue(all(r['verification_scope'] == 'attempt_receipt_only' for r in rows))
        self.assertTrue(all(r['all_required_versions_status'] == 'not_established_by_attempt_trace' for r in rows))
