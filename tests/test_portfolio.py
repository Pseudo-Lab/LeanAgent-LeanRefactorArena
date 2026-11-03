"""Real common-runner routing, scope, budget and replay with synthetic receipts."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import artifacts as a, harness as h, models, portfolio, search_policy
from test_harness import FakeEvaluator

ROOT = Path(__file__).resolve().parents[1]


def proposal(proof="by rfl", parent="c000", strategy="test route"):
    return {"action": "propose", "parent_id": parent, "strategy": strategy, "proof": proof}


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ.get("PROJECT_CACHE_DIR"))
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / "run"
        self.config = a.read(ROOT / "configs/smoke.json")
        for key in ("problem", "template", "project"):
            self.config[key] = str((ROOT / "configs" / self.config[key]).resolve())
        self.config["prompt"] = str(ROOT / "examples/actions/prompt.txt")
        self.config["limits"].update(max_calls=12, max_request_characters=80000)
        self.config["model"] = {"backend": "openrouter", "id": "synthetic/model", "provider": "synthetic",
                                "max_tokens": 100, "timeout_seconds": 1}
        self.config["agent"] = {
            "mode": "actions-v1", "corpus": str(ROOT / "examples/actions/corpus.json"),
            "portfolio": {"scout_evaluations": 1, "merger_evaluations": 1},
            "approach_policy": "exchange-v1",
        }
        self.path = self.root / "config.json"
        self.packets = []
        self.evaluator = FakeEvaluator()

    def run_case(self, responses=None, query=None):
        values = responses or [proposal("by rfl -- a"), proposal("by simpa -- b"),
                               proposal("by exact Nat.add_zero n -- c"),
                               {**proposal("by rfl -- combined", parent="c002", strategy="combine scouts"),
                                "source_candidate_ids": ["c001", "c002", "c003"]}]
        def fixed(body, model, step, fixtures):
            self.packets.append(json.loads(body["messages"][1]["content"]))
            return {"id": f"fixture-{step}", "choices": [{"message": {"content": a.canonical(values[step-1])}}],
                    "usage": {"cost": "0.01"}}
        self.path.write_text(json.dumps(self.config))
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-test-only"}):
            return h.run(self.path, self.output, evaluator=self.evaluator, query=query or fixed)

    def test_guard_bounds_noncompliant_reads_and_replays_honestly(self):
        self.config["agent"]["portfolio"]["progress_guard"] = "bounded-v1"
        self.config["limits"]["max_calls"] = 50
        reads = [{"action": "search", "query": "Nat.add_zero"}] * 32
        result = self.run_case(reads)
        self.assertEqual(result["stop_reason"], "portfolio_stalled")
        self.assertEqual(result["status"], "stopped")
        self.assertFalse(result["portfolio"]["complete"])
        self.assertEqual(result["portfolio"]["evaluations"], dict.fromkeys(portfolio.BRANCHES, 0))
        self.assertEqual(result["portfolio"]["calls"], dict.fromkeys(portfolio.BRANCHES, 8))
        self.assertEqual(result["portfolio"]["exits"], dict.fromkeys(portfolio.BRANCHES, "stalled"))
        forced = self.packets[2]
        self.assertEqual(set(forced["exploration"]["actions"]), {"propose", "repair"})
        self.assertEqual(forced["approach_policy"]["approach"], "submit_candidate")
        self.assertEqual(self.packets[8]["portfolio"]["branch"], "scout-b")
        self.assertIn("search", self.packets[8]["exploration"]["actions"])
        self.assertEqual(len(self.evaluator.calls), 2)  # baseline and final, no fake evaluations
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_guard_requests_candidate_after_four_distinct_reads_then_resets(self):
        self.config["agent"]["portfolio"]["progress_guard"] = "bounded-v1"
        reads = [{"action": "search", "query": f"missing{i}"} for i in range(4)]
        proofs = [proposal("by rfl -- a"), proposal("by rfl -- b"),
                  proposal("by rfl -- c"), proposal("by rfl -- merged")]
        result = self.run_case(reads + proofs)
        self.assertEqual(result["stop_reason"], "portfolio_complete")
        self.assertEqual(set(self.packets[4]["exploration"]["actions"]), {"propose", "repair"})
        self.assertEqual(self.packets[5]["portfolio"]["branch"], "scout-b")
        self.assertIn("search", self.packets[5]["exploration"]["actions"])
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_guard_malformed_responses_cannot_stall_forever(self):
        self.config["agent"]["portfolio"]["progress_guard"] = "bounded-v1"
        self.config["limits"]["max_calls"] = 50
        result = self.run_case([{"action": "invalid"}] * 32)
        self.assertEqual(result["stop_reason"], "portfolio_stalled")
        self.assertEqual(result["state"]["calls"], 32)
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_guard_caps_total_calls_even_with_intermittent_evaluations(self):
        config = {"agent": {"portfolio": {"scout_evaluations": 6, "merger_evaluations": 22,
                                           "progress_guard": "bounded-v1"}}}
        state = {}
        portfolio.initialize(state, config)
        for i in range(26):
            portfolio.record_progress(state, config, (i + 1) % 7 == 0)
        self.assertEqual(state["portfolio"]["active"], "scout-b")
        self.assertEqual(state["portfolio"]["evaluations"]["scout-a"], 3)
        self.assertEqual(state["portfolio"]["exits"]["scout-a"], "call_limit")

    def test_three_scoped_contexts_then_merger_share_one_budget_and_replay(self):
        result = self.run_case()
        self.assertEqual(result["stop_reason"], "portfolio_complete")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["state"]["cost_usd"], "0.04")
        self.assertEqual([p["portfolio"]["branch"] for p in self.packets], list(portfolio.BRANCHES))
        self.assertEqual(result["portfolio"]["evaluations"], dict.fromkeys(portfolio.BRANCHES, 1))
        for p in self.packets[:3]:
            self.assertEqual([c["candidate_id"] for c in p["exploration"]["candidates"]], ["c000"])
            self.assertEqual(p["best"]["sha256"], result["state"]["exploration"]["candidates"]["c000"]["sha256"])
            self.assertIsNone(p["latest"])
            self.assertNotIn("finish", p["exploration"]["actions"])
        self.assertNotIn("reference", self.packets[0]["problem"])
        self.assertEqual(self.packets[0]["best"]["code_ref"], "hidden original")
        self.assertIn("reference", self.packets[1]["problem"])
        merger = self.packets[-1]
        self.assertEqual(merger["approach_policy"]["approach"], "merge")
        self.assertEqual(len(merger["portfolio"]["scout_results"]), 3)
        self.assertEqual(len(merger["exploration"]["candidates"]), 4)
        self.assertEqual(result["state"]["exploration"]["candidates"]["c004"]["source_candidate_ids"],
                         ["c001", "c002", "c003"])
        self.assertEqual(len(self.evaluator.calls), 6)  # original + four proofs + final
        with patch.object(models, "query", side_effect=AssertionError("no model replay")), \
                patch.object(h.LeanEvaluator, "evaluate", side_effect=AssertionError("no Lean replay")):
            self.assertTrue(h.replay(self.output)["record_replay_passed"])
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        result = subprocess.run([sys.executable, "-B", str(self.output / "code/replay.py"),
                                 "replay", str(self.output)], cwd=self.root, env=env,
                                capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(result.stdout)["record_replay_passed"])

    def test_queries_do_not_open_merge_early_and_invalid_proofs_consume_quota(self):
        values = [{"action": "search", "query": "Nat"}, proposal("by False.elim (by trivial)"),
                  proposal("by rfl -- b"), proposal("by rfl -- c"), proposal("by simpa -- merge")]
        result = self.run_case(values)
        self.assertEqual([p["portfolio"]["branch"] for p in self.packets],
                         ["scout-a", "scout-a", "scout-b", "scout-c", "merge"])
        self.assertEqual(result["portfolio"]["calls"]["scout-a"], 2)
        self.assertFalse(result["state"]["exploration"]["candidates"]["c002"]["valid"])
        self.assertEqual(result["state"]["cost_usd"], "0.05")

    def test_hidden_original_and_other_scouts_cannot_be_read_or_used_as_parents(self):
        values = [{"action": "read_candidate", "candidate_id": "c000"},
                  {"action": "analyze", "candidate_id": "c000"},
                  proposal("by rfl -- a"),
                  {"action": "read_candidate", "candidate_id": "c003"},
                  proposal("by rfl -- illegal", parent="c003"), proposal("by rfl -- b"),
                  proposal("by rfl -- c"), proposal("by rfl -- merge", parent="c003")]
        result = self.run_case(values)
        for index in (1, 2, 4, 5):
            event = a.read(self.output / f"steps/{index:03}/event.json")
            self.assertTrue(event["rejection"])
            self.assertIsNone(event["state_after"]["latest"]["code"])
        self.assertEqual(result["portfolio"]["evaluations"], dict.fromkeys(portfolio.BRANCHES, 1))
        self.assertEqual(len(self.evaluator.calls), 6)

    def test_synthesis_cannot_reference_another_scout_before_merger(self):
        values = [proposal("by rfl -- a"),
                  {**proposal("by rfl -- illicit synthesis"), "source_candidate_ids": ["c001"]},
                  proposal("by rfl -- b"), proposal("by rfl -- c"), proposal("by rfl -- merge")]
        result = self.run_case(values)
        self.assertIn("Unknown source candidate", a.read(self.output / "steps/002/event.json")["rejection"])
        self.assertTrue(result["portfolio"]["complete"])
        self.assertEqual(len(self.evaluator.calls), 6)

    def test_hidden_original_in_multiline_corpus_is_rejected_before_query(self):
        corpus = {"schema_version": 1, "entries": [{"name": "original", "source": "fixture",
                   "text": a.read(Path(self.config["problem"]))["reference"]}]}
        path = self.root / "corpus.json"
        a.write(path, corpus)
        self.config["agent"]["corpus"] = str(path)
        with self.assertRaisesRegex(ValueError, "Hidden original proof"):
            self.run_case()
        self.assertEqual(self.packets, [])

    def test_cost_threshold_stops_scouts_before_merger_and_replays(self):
        self.config["limits"]["cost_stop_usd"] = "0.02"
        result = self.run_case()
        self.assertEqual(result["stop_reason"], "cost_limit")
        self.assertEqual(result["state"]["cost_usd"], "0.02")
        self.assertFalse(result["portfolio"]["complete"])
        self.assertEqual(len(self.packets), 2)
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_exchange_policy_also_runs_without_portfolio(self):
        self.config["agent"].pop("portfolio")
        self.config["limits"]["max_calls"] = 3
        result = self.run_case()
        self.assertNotIn("portfolio", result)
        self.assertNotIn("portfolio", self.packets[-1])
        self.assertIsNotNone(self.packets[-1]["approach_policy"]["latest_tradeoff"])
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_same_independent_discovery_is_charged_but_visible_duplicates_are_rejected(self):
        self.config["agent"]["portfolio"]["scout_evaluations"] = 2
        values = [proposal("by rfl -- shared"), proposal("by rfl -- shared"),
                  proposal("by rfl -- a2"), proposal("by rfl -- shared"), proposal("by rfl -- b2"),
                  proposal("by rfl -- shared"), proposal("by rfl -- c2"), proposal("by rfl -- merge")]
        result = self.run_case(values)
        self.assertIn("Duplicate", a.read(self.output / "steps/002/event.json")["rejection"])
        self.assertIn("by rfl -- shared", self.packets[1]["best"]["code"])
        self.assertNotIn("code_ref", self.packets[1]["best"])
        self.assertEqual(result["portfolio"]["evaluations"], {"scout-a": 2, "scout-b": 2, "scout-c": 2, "merge": 1})
        self.assertEqual(len(self.evaluator.calls), 9)

    def test_call_limit_before_barrier_retains_verified_best_and_reports_incomplete(self):
        self.config["limits"]["max_calls"] = 2
        result = self.run_case()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["stop_reason"], "call_limit")
        self.assertFalse(result["portfolio"]["complete"])
        self.assertEqual(result["portfolio"]["active"], "scout-c")
        self.assertTrue(result["final_valid"])
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_finish_cannot_skip_scout_quota(self):
        result = self.run_case([{"action": "finish"}, proposal("by rfl -- a"),
                                proposal("by rfl -- b"), proposal("by rfl -- c"), proposal("by rfl -- m")])
        self.assertIn("finish is disabled", a.read(self.output / "steps/001/event.json")["rejection"])
        self.assertTrue(result["portfolio"]["complete"])

    def test_unknown_cost_stops_all_later_contexts(self):
        def query(body, *args):
            self.packets.append(json.loads(body["messages"][1]["content"]))
            return {"choices": [{"message": {"content": a.canonical(proposal("by rfl"))}}]}
        result = self.run_case(query=query)
        self.assertEqual(result["stop_reason"], "unknown_cost")
        self.assertEqual(len(self.packets), 1)
        self.assertFalse(result["portfolio"]["complete"])
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_resealed_branch_owner_tampering_fails_replay(self):
        self.run_case()
        file = self.output / "steps/001/event.json"
        event = a.read(file)
        event["state_after"]["portfolio"]["owners"]["c001"] = "scout-b"
        file.write_text(a.canonical(event))
        (self.output / "artifacts.json").unlink()
        h.seal(self.output)
        with self.assertRaisesRegex(ValueError, "State transition differs"):
            h.replay(self.output)

    def test_quota_types_and_unknown_policy_are_rejected_before_dispatch(self):
        for bad in [True, 0, -1, 1.5, 101]:
            with self.assertRaises(ValueError):
                portfolio.validate({"scout_evaluations": bad})
        with self.assertRaises(ValueError):
            search_policy.validate("invented")

    def test_documented_fixture_configuration_completes_and_replays(self):
        result = h.run(ROOT / "configs/portfolio-smoke.json", self.output, evaluator=self.evaluator)
        self.assertEqual(result["stop_reason"], "portfolio_complete")
        self.assertEqual(result["state"]["calls"], 4)
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_default_six_each_then_twenty_two_merger_evaluations(self):
        self.config["agent"]["portfolio"] = {}
        self.config["limits"]["max_calls"] = 40
        result = self.run_case([proposal(f"by rfl -- route {i}") for i in range(40)])
        self.assertEqual([p["portfolio"]["branch"] for p in self.packets],
                         ["scout-a"] * 6 + ["scout-b"] * 6 + ["scout-c"] * 6 + ["merge"] * 22)
        self.assertEqual(result["portfolio"]["evaluations"],
                         {"scout-a": 6, "scout-b": 6, "scout-c": 6, "merge": 22})
        self.assertTrue(h.replay(self.output)["record_replay_passed"])


    def test_rounds_restart_scouts_from_the_incumbent_after_each_merger(self):
        self.config["agent"]["portfolio"] = {"scout_evaluations": 1, "merger_evaluations": 1, "rounds": 2}
        self.config["limits"]["max_calls"] = 8
        result = self.run_case([proposal(f"by rfl -- round route {i}") for i in range(8)])
        self.assertEqual([p["portfolio"]["branch"] for p in self.packets], list(portfolio.BRANCHES) * 2)
        self.assertEqual([p["portfolio"]["round"] for p in self.packets], [1] * 4 + [2] * 4)
        seeded = [p["portfolio"].get("seed_candidate_id") for p in self.packets[4:7]]
        self.assertTrue(all(seeded) and len(set(seeded)) == 1)
        self.assertEqual(result["portfolio"]["completed_rounds"],
                         [{"evaluations": dict.fromkeys(portfolio.BRANCHES, 1), "calls": dict.fromkeys(portfolio.BRANCHES, 1)}])
        self.assertTrue(result["portfolio"]["complete"])
        self.assertEqual(result["stop_reason"], "portfolio_complete")
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_merger_until_budget_runs_past_its_count_and_counts_as_complete(self):
        self.config["agent"]["portfolio"] = {"scout_evaluations": 1, "merger_evaluations": 1,
                                             "merger_until_budget": True}
        self.config["limits"]["max_calls"] = 7
        result = self.run_case([proposal(f"by rfl -- budget route {i}") for i in range(7)])
        self.assertEqual([p["portfolio"]["branch"] for p in self.packets],
                         ["scout-a", "scout-b", "scout-c"] + ["merge"] * 4)
        self.assertIsNone(self.packets[-1]["portfolio"]["remaining_evaluations"])
        self.assertEqual(self.packets[-1]["portfolio"]["stops_at"], "shared per-problem budget")
        self.assertEqual(result["portfolio"]["evaluations"]["merge"], 4)
        self.assertTrue(result["portfolio"]["complete"])
        self.assertEqual(result["status"], "completed")

    def test_default_portfolio_state_and_summary_keep_their_shape(self):
        state = {}
        portfolio.initialize(state, self.config)
        self.assertNotIn("round", state["portfolio"])
        self.assertNotIn("round", portfolio.summary(state, self.config))

    def test_round_and_budget_settings_are_validated(self):
        for bad in ({"rounds": 0}, {"rounds": 11}, {"rounds": True}, {"merger_until_budget": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                portfolio.validate(bad)
        portfolio.validate({"rounds": 3, "merger_until_budget": True})


class ExchangePolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = {"agent": {"mode": "actions-v1", "approach_policy": "exchange-v1"},
                       "limits": {"max_calls": 100}}
        self.state = h.initial_state({"reference": "original"}, self.result(10, 100), self.config)

    @staticmethod
    def result(tokens, raw):
        return {"valid": True, "tokens": tokens,
                "environments": {"fixed": {"valid": True, "runs": [{"measurement": {"raw": raw}}]}}}

    def state_with_best(self, tokens, raw):
        s = copy.deepcopy(self.state)
        for i in range(1, 3):
            row = h.candidate("proof" + str(i), self.result(tokens + 1 - i, raw + 1 - i), s["baseline"])
            cid = f"c{i:03}"
            s["exploration"]["candidates"][cid] = {**row, "valid": True, "strategy": "route", "step": i}
            s["exploration"]["history"].append({"candidate_id": cid})
        s["best"] = row
        s["calls"] = s["step"] = 2
        return s

    def test_exchange_is_exact_and_dominant_axis_selects_an_actual_instruction(self):
        length = self.state_with_best(9, 11)
        heartbeat = self.state_with_best(2, 91)
        a = search_policy.packet(length, self.config)
        b = search_policy.packet(heartbeat, self.config)
        self.assertEqual(a["raw_hb_per_token"], {"numerator": 10, "denominator": 1, "value": 10.0})
        self.assertEqual(a["approach"], "reduce_length")
        self.assertEqual(b["approach"], "reduce_heartbeat")
        self.assertNotEqual(a["instructions"], b["instructions"])
        self.assertEqual(length["baseline"], {"tokens": 10, "raw_heartbeats": 100})

    def test_failed_candidate_stagnation_and_final_window_change_approach(self):
        s = self.state_with_best(9, 11)
        s["latest"] = {"feedback": {"valid": False}}
        self.assertEqual(search_policy.packet(s, self.config)["approach"], "repair_or_reconsider")
        s["latest"] = None
        for i in range(3):
            s["exploration"]["history"].append({"candidate_id": "c002"})
        self.assertEqual(search_policy.packet(s, self.config)["approach"], "reconsider")
        s["calls"] = 99
        self.assertEqual(search_policy.packet(s, self.config)["approach"], "consolidate")

    def test_pareto_retains_nonwinning_tradeoff_and_does_not_mutate_state(self):
        s = self.state_with_best(9, 11)
        candidate = h.candidate("other", self.result(2, 90), s["baseline"])
        s["exploration"]["candidates"]["c003"] = {**candidate, "valid": True, "strategy": "different route"}
        before = a.canonical(s)
        packet = search_policy.packet(s, self.config)
        self.assertIn("c003", [r["candidate_id"] for r in packet["pareto_candidates"]])
        self.assertEqual(before, a.canonical(s))

    def test_tradeoff_reports_length_heartbeat_exchange_against_actual_parent(self):
        s = self.state_with_best(3, 131)
        row = s["exploration"]["candidates"]["c002"]
        row["parent_id"] = "c000"
        feedback = search_policy.packet(s, self.config)["latest_tradeoff"]
        self.assertEqual(feedback["delta_tokens"], -8)
        self.assertEqual(feedback["delta_raw_hb"], 30)
        self.assertEqual(feedback["delta_token_equivalent"]["value"], -5)
        self.assertTrue(feedback["strict_objective_improvement"])

    def test_scout_changes_approach_after_initial_broad_exploration(self):
        s = self.state_with_best(9, 11)
        context = {"branch": "scout-b", "remaining_evaluations": 4, "evaluated": 2}
        self.assertEqual(search_policy.packet(s, self.config, context)["approach"], "reduce_length")
        context.update(remaining_evaluations=2, evaluated=4)
        self.assertEqual(search_policy.packet(s, self.config, context)["approach"], "consolidate")


if __name__ == "__main__":
    unittest.main()
