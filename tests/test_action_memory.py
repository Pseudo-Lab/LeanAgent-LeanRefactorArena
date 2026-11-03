"""Persistent retrieval/failure reminders and paid-accounting replay; no API/Lean."""
import json

from lean_agent import action_memory as m, actions, artifacts as a, harness as h, portfolio
import test_actions


class PersistentMemoryTests(test_actions.ActionTests):
    # Reuse the action harness integration fixtures, including its full replay tests.
    def setUp(self):
        super().setUp()
        self.config["agent"]["persistent_memory"] = True

    def test_old_lookup_and_failure_remain_visible_after_window_and_restart(self):
        values = [{"action": "search", "query": "Nat.add_zero"},
                  {"action": "propose", "parent_id": "c000", "strategy": "bad elimination", "proof": "by exact False.elim"}]
        values += [{"action": "analyze", "candidate_id": "c000"}] * 7
        self.replace_responses(values)
        output = self.run_case()
        state = json.loads(a.canonical(output["state"]))
        view = actions.view(state, self.config)
        self.assertTrue(all(row["step"] > 2 for row in view["recent_actions"]))
        memory = view["persistent_memory"]
        self.assertTrue(any(row["action"].get("query") == "Nat.add_zero" for row in memory["lookups"]))
        self.assertEqual(memory["failed_strategies"][0]["strategy"], "bad elimination")
        self.assertEqual(memory["failed_strategies"][0]["candidate_id"], "c002")
        self.assertEqual(memory["consecutive_lookups"], 7)
        self.assertIn("next_action_guidance", memory)
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_repeated_search_reuses_observation_but_still_accounts_paid_turn(self):
        self.replace_responses([{"action": "search", "query": "Nat.add_zero"},
                                {"action": "search", "query": "  nat.add_zero  "}])
        output = self.run_case()
        history = output["state"]["exploration"]["history"]
        self.assertEqual(history[1]["observation"]["matches"], history[0]["observation"]["matches"])
        self.assertEqual(history[1]["observation"]["memory_reuse"]["first_step"], 1)
        self.assertEqual(output["state"]["calls"], 2)
        self.assertTrue(h.replay(self.output)["record_replay_passed"])

    def test_offsets_and_different_candidates_are_distinct(self):
        first = {"action": "read_candidate", "candidate_id": "c000"}
        history = [{"step": 1, "action": first, "observation": {"text": "first"}, "rejection": None}]
        self.assertIsNotNone(m.recall(history, {**first, "offset": 0}))
        self.assertIsNone(m.recall(history, {**first, "offset": 3000}))
        self.assertIsNone(m.recall(history, {**first, "candidate_id": "c001"}))

    def test_exact_name_beats_broad_text_and_generic_words(self):
        corpus = {"entries": [{"name": "A.noise", "source": "test", "text": "theorem eq denote suffix irrel " * 100},
                              {"name": "Lambda.denote_suffix_irrel", "source": "test", "text": "target type"}]}
        result = m.search("theorem eq Lambda.denote_suffix_irrel", corpus, a.sha)
        self.assertEqual(result["matches"][0]["name"], "Lambda.denote_suffix_irrel")
        self.assertEqual(result["matches"][0]["match_kind"], "exact-name")
        self.assertEqual(m.search("theorem eq", corpus, a.sha)["matches"], [])

    def test_prompt_bound_does_not_truncate_durable_archive(self):
        memory = {"history": [], "candidates": {}}
        for i in range(200):
            memory["history"].append({"step": i + 1, "action": {"action": "inspect", "name": str(i)},
                                      "observation": {"text": "x" * 3000}, "rejection": None})
            memory["candidates"][str(i)] = {"valid": False, "strategy": "s" * 300 + str(i),
                "parent_id": "c000", "feedback": {"details": "x" * 7000, "diagnosis": "d" * 3000}}
        before = a.canonical(memory)
        result = m.view(memory)
        self.assertLessEqual(len(a.canonical(result)), m.MAX_PACKET_CHARACTERS)
        self.assertGreater(result["omitted_lookups"], 0)
        self.assertGreater(result["omitted_failed_strategies"], 0)
        self.assertEqual(a.canonical(memory), before)

    def test_portfolio_scoped_history_does_not_leak_other_scouts(self):
        self.config["agent"]["portfolio"] = {"scout_evaluations": 1, "merger_evaluations": 1}
        problem = {"reference": "theorem x : True := by trivial"}
        result = {"valid": True, "tokens": 10, "environments": {"test": {"valid": True, "runs": [{"measurement": {"raw": 10}}]}}}
        state = h.initial_state(problem, result, self.config)
        state["exploration"]["history"] = [{"step": 1, "branch": "scout-b",
            "action": {"action": "search", "query": "secret"}, "observation": {"matches": [], "total_matches": 0}, "rejection": None}]
        scoped = portfolio.scoped_state(state, self.config)
        self.assertEqual(actions.view(scoped, self.config)["persistent_memory"]["lookup_count"], 0)
