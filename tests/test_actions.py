"""Action/candidate integration, budget accounting and offline replay contracts."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import actions, artifacts, harness, models
from test_harness import FakeEvaluator

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "examples/actions"


class ActionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copytree(FIXTURES, self.root / "fixtures")
        self.config = artifacts.read(REPO / "configs/actions-smoke.json")
        for key in ("problem", "template", "project", "prompt"):
            self.config[key] = str((REPO / "configs" / self.config[key]).resolve())
        self.config["agent"]["corpus"] = str(self.root / "fixtures/corpus.json")
        self.config["model"]["responses"] = str(self.root / "fixtures/responses.json")
        self.path, self.output = self.root / "config.json", self.root / "run"

    def run_case(self, evaluator=None, **kwargs):
        self.path.write_text(json.dumps(self.config))
        return harness.run(self.path, self.output, evaluator=evaluator or FakeEvaluator(), **kwargs)

    def replace_responses(self, values):
        self.config["limits"]["max_calls"] = len(values)
        Path(self.config["model"]["responses"]).write_text(json.dumps([
            json.dumps(value) if not isinstance(value, str) else value for value in values]))

    def test_tools_failed_parent_repair_and_worse_branch_survive_and_replay(self):
        evaluator = FakeEvaluator()
        result = self.run_case(evaluator)
        memory = result["state"]["exploration"]
        self.assertEqual(result["stop_reason"], "agent_finished")
        self.assertEqual(result["state"]["calls"], 10)
        self.assertEqual(len(evaluator.calls), 6)  # baseline + four proposals + final
        self.assertFalse(memory["candidates"]["c004"]["valid"])
        self.assertEqual(memory["candidates"]["c005"]["parent_id"], "c004")
        self.assertTrue(memory["candidates"]["c006"]["valid"])
        self.assertGreater(memory["candidates"]["c006"]["rank_numerator"], memory["candidates"]["c005"]["rank_numerator"])
        self.assertEqual(memory["candidates"]["c008"]["parent_id"], "c006")
        self.assertIn("rfl", result["state"]["best"]["code"])
        self.assertEqual(memory["best_candidate_id"], "c008")
        search = artifacts.read(self.output / "steps/002/event.json")["observation"]
        self.assertEqual(search["matches"][0]["name"], "Nat.add_zero")
        with patch.object(models, "query", side_effect=AssertionError("No API in replay")), \
                patch.object(harness.LeanEvaluator, "evaluate", side_effect=AssertionError("No Lean in replay")):
            self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_replay_uses_frozen_corpus_and_archived_code_from_another_directory(self):
        self.run_case()
        Path(self.config["agent"]["corpus"]).unlink()
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        replay = subprocess.run([sys.executable, "-B", str(self.output / "code/replay.py"),
                                 "replay", str(self.output)], cwd=self.root, env=env,
                                capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(replay.stdout)["record_replay_passed"])

    def test_resealed_observation_tampering_is_detected(self):
        self.run_case()
        path = self.output / "steps/002/event.json"
        event = artifacts.read(path)
        event["observation"]["matches"] = []
        path.write_text(artifacts.canonical(event))
        (self.output / "artifacts.json").unlink()
        harness.seal(self.output)
        with self.assertRaisesRegex(ValueError, "State transition differs"):
            harness.replay(self.output)

    def test_tool_actions_count_toward_cost_and_calls(self):
        self.config["model"] = {"backend": "openrouter", "id": "test/model", "provider": "test",
                                "max_tokens": 100, "timeout_seconds": 1}
        self.config["limits"].update(max_calls=10, cost_stop_usd="0.025")
        requests = []
        def query(body, model, step, fixtures):
            requests.append(body)
            return {"choices": [{"message": {"content": '{"action":"search","query":"Nat"}'}}],
                    "usage": {"cost": "0.01"}}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-test-key"}):
            result = self.run_case(query=query)
        self.assertEqual(len(requests), 3)
        self.assertEqual(result["state"]["cost_usd"], "0.03")
        self.assertEqual(result["stop_reason"], "cost_limit")
        self.assertEqual(len(result["state"]["exploration"]["candidates"]), 1)
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_unknown_billing_stops_tool_loop_and_failed_final_is_not_completed(self):
        def query(body, model, step, fixtures):
            return {"choices": [{"message": {"content": '{"action":"finish"}'}}], "usage": {}}
        result = self.run_case(query=query)
        self.assertEqual(result["stop_reason"], "unknown_cost")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["state"]["calls"], 1)
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])
        self.output = self.root / "failed-final"
        self.replace_responses([{"action": "finish"}])
        result = self.run_case(FakeEvaluator(fail_final=True))
        self.assertEqual(result["status"], "stopped")
        self.assertFalse(result["final_valid"])
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_invalid_actions_are_rejections_without_evaluation(self):
        self.replace_responses([
            {"action": "propose", "parent_id": "missing", "strategy": "bad", "proof": "by rfl"},
            {"action": "repair", "parent_id": "c000", "strategy": "bad", "proof": "by rfl"},
            {"action": "search", "query": "Nat", "path": "/arbitrary/file"},
            '{"action":"finish","action":"search"}',
            {"action": "inspect", "name": "Nat.add_zero", "offset": True},
            {"action": "shell", "command": "anything"},
            '{"action":"search","query":NaN}',
            {"action": "finish"},
        ])
        evaluator = FakeEvaluator()
        result = self.run_case(evaluator)
        self.assertEqual(len(evaluator.calls), 2)
        self.assertEqual(len(result["state"]["exploration"]["candidates"]), 1)
        self.assertTrue(all(row["rejection"] for row in result["state"]["exploration"]["history"][:-1]))
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_bounded_context_preserves_full_archive_and_can_read_evicted_candidate(self):
        self.config["agent"].update(history_limit=1, candidate_limit=1)
        self.run_case()
        packet = json.loads(artifacts.read(self.output / "steps/010/request.json")["messages"][1]["content"])
        memory = packet["exploration"]
        self.assertEqual(len(memory["recent_actions"]), 1)
        self.assertLessEqual(len(memory["candidates"]), 3)
        self.assertEqual(memory["candidate_count"], 5)
        observation = memory["recent_actions"][0]["observation"]
        self.assertEqual(observation["candidate_id"], "c004")
        self.assertIn("False.elim", observation["text"])
        self.assertFalse(observation["valid"])

    def test_pagination_and_deterministic_search(self):
        text = "a" * 3100
        self.assertEqual(actions.page(text, 0)["next_offset"], 3000)
        self.assertEqual(actions.page(text, 3000)["text"], "a" * 100)
        self.assertIsNone(actions.page(text, 3000)["next_offset"])
        with self.assertRaises(ValueError):
            actions.page(text, 3101)

    def test_repair_context_survives_tool_call_and_feedback_is_not_repeated_in_history(self):
        self.replace_responses([
            {"action": "propose", "parent_id": "c000", "strategy": "broken", "proof": "by exact False.elim (by assumption)"},
            {"action": "search", "query": "Nat"},
            {"action": "repair", "parent_id": "c001", "strategy": "fix", "proof": "by rfl"},
            {"action": "finish"},
        ])
        result = self.run_case()
        packet = json.loads(artifacts.read(self.output / "steps/003/request.json")["messages"][1]["content"])
        context = packet["exploration"]["repair_context"]
        self.assertEqual(context["candidate_id"], "c001")
        self.assertIn("False.elim", context["code"])
        self.assertTrue(context["instructions"])
        self.assertNotIn("feedback", packet["exploration"]["recent_actions"][0])
        self.assertIn("feedback", result["state"]["exploration"]["history"][0])
        before_tool = json.loads(artifacts.read(self.output / "steps/002/request.json")["messages"][1]["content"])
        self.assertNotIn("code", before_tool["latest"])
        self.assertEqual(before_tool["latest"]["feedback_ref"], "exploration.repair_context.feedback")
        self.assertNotIn("code", before_tool["best"])

    def test_threshold_mode_cannot_finish_before_cost_target(self):
        self.config["agent"]["allow_finish"] = False
        self.config["model"] = {"backend": "openrouter", "id": "test/model", "provider": "test",
                                "max_tokens": 100, "timeout_seconds": 1}
        self.config["limits"].update(max_calls=None, cost_stop_usd="0.025")
        requests = []
        responses = [{"action": "finish"},
            {"action": "propose", "parent_id": "c000", "strategy": "simple", "proof": "by rfl"},
            {"action": "read_candidate", "candidate_id": "c002"}]
        def query(body, model, step, fixtures):
            requests.append(body)
            return {"choices": [{"message": {"content": json.dumps(responses[step - 1])}}],
                    "usage": {"cost": "0.01"}}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-only"}):
            result = self.run_case(query=query)
        self.assertEqual(result["stop_reason"], "cost_limit")
        self.assertEqual(result["state"]["calls"], 3)
        self.assertEqual(result["state"]["cost_usd"], "0.03")
        self.assertNotIn("finish", json.loads(requests[0]["messages"][1]["content"])["exploration"]["actions"])
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_search_can_find_related_local_helper_without_claiming_requested_name_exists(self):
        state = {"step": 0, "exploration": {"candidates": {}}}
        corpus = {"schema_version": 1, "entries": [{"name": "Local helper declarations", "source": "original packet",
            "text": "theorem List.Subset.app : List.Subset a c → b.Subset c → (a ++ b).Subset c"}]}
        raw = {"choices": [{"message": {"content": json.dumps({"action": "search", "query": "List.append_subset_append append_subset"})}}]}
        _, _, observation = actions.prepare(raw, state, {}, self.config, corpus, None)
        hit = observation["matches"][0]
        self.assertEqual(hit["name"], "Local helper declarations")
        self.assertEqual(hit["match_kind"], "identifier-components")
        self.assertIn("subset", hit["matched_terms"])
        self.assertIn("List.Subset.app", hit["excerpt"])

    def test_action_config_and_corpus_are_validated_before_execution(self):
        bad = copy.deepcopy(self.config)
        for settings in ({"mode": "unknown"}, {**bad["agent"], "history_limit": True},
                         {**bad["agent"], "candidate_limit": 0}):
            with self.subTest(settings=settings):
                self.config["agent"] = settings
                self.path.write_text(json.dumps(self.config))
                with self.assertRaises(ValueError):
                    harness.load_config(self.path)
        entry = {"name": "x", "source": "test", "text": "x"}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            actions.validate_corpus({"schema_version": 1, "entries": [entry, entry]})


if __name__ == "__main__":
    unittest.main()
