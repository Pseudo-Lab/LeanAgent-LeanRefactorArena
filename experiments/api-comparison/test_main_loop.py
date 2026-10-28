import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
import main_loop as loop
from lean_agent import harness as h, models

sys.path.insert(0, str(loop.REPO / "tests"))
from test_harness import FakeEvaluator


class MainLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("PROJECT_CACHE_DIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = h.read(loop.REPO / "configs/smoke.json")
        for key in ("problem", "template", "project", "prompt"):
            config[key] = str((loop.REPO / "configs" / config[key]).resolve())
        config["model"] = {"backend": "openrouter", "id": loop.c.MODEL, "provider": "openai",
            "reasoning_effort": "high", "max_tokens": loop.c.MAX_OUTPUT,
            "max_price": {k: float(v) for k, v in loop.c.PRICE_CAPS.items()}, "timeout_seconds": 300}
        self.config = config
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(config))
        h.write(self.root / "prepared-files.json", {})
        h.write(self.root / "budget.json", {"total_usd": "2", "per_trial_usd": "2", "max_trials": 3, "attempts": {}})
        self.endpoint = {"tag": "openai", "model_id": loop.c.MODEL, "context_length": 1050000,
            "pricing": {"prompt": "0.000002", "completion": "0.00001", "input_cache_write": "0.0000025"},
            "supported_parameters": ["max_tokens", "reasoning", "response_format"], "max_completion_tokens": 128000}
        self.http = Mock(return_value={"data": {"endpoints": [self.endpoint]}})
        self.responses = h.read(loop.REPO / "examples/first-harness/responses.json")

    def response(self, body, model, step, fixtures):
        return {"model": loop.c.MODEL, "choices": [{"message": {"content": self.responses[step-1]}}],
                "usage": {"cost": "0.01", "prompt_tokens": 1000, "completion_tokens": 100}}

    def run_fake(self, query):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-test-key"}):
            return h.run(self.config_path, self.root / "harness", evaluator=FakeEvaluator(),
                         query=loop.BudgetQuery(self.root, http=self.http, query=query))

    def test_reasoning_and_caps_are_in_the_actual_recorded_wire(self):
        config, _ = h.load_config(self.config_path)
        payload = models.payload([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], config["model"])
        self.assertEqual(payload, loop.c.wire_request(payload["messages"]))
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["reasoning"], {"effort": "high"})

    def test_reject_invalid_price_caps(self):
        for value in [{"prompt": -1, "completion": 15}, {"prompt": True, "completion": 15}, {"prompt": 5}]:
            config = copy.deepcopy(self.config)
            config["model"]["max_price"] = value
            self.config_path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                h.load_config(self.config_path)

    def test_real_main_loop_receives_feedback_and_replays(self):
        query = Mock(side_effect=self.response)
        result = self.run_fake(query)
        self.assertEqual(result["state"]["calls"], 3)
        self.assertEqual(result["state"]["cost_usd"], "0.03")
        self.assertTrue(result["final_valid"])
        second = h.read(self.root / "harness/steps/002/request.json")
        packet = json.loads(second["messages"][1]["content"])
        self.assertIsNotNone(packet["latest"])
        self.assertFalse(packet["latest"]["feedback"]["valid"])
        for i in range(1, 4):
            self.assertEqual(h.read(self.root / f"harness/steps/{i:03}/request.json"),
                             h.read(self.root / f"transport/{i:03}/request.json"))
        with patch.object(models, "query", side_effect=AssertionError("No model during replay")):
            self.assertTrue(h.replay(self.root / "harness")["record_replay_passed"])

    def test_insufficient_budget_never_dispatches(self):
        ledger = h.read(self.root / "budget.json")
        ledger["attempts"]["earlier"] = {"status": "settled", "reserved_usd": "1.99", "cost_usd": "1.99"}
        loop.c.atomic(self.root / "budget.json", ledger)
        query = Mock(side_effect=self.response)
        with self.assertRaisesRegex(ValueError, "Budget reservation refused"):
            self.run_fake(query)
        query.assert_not_called()

    def test_unknown_cost_stops_main_before_another_dispatch(self):
        def unknown(body, model, step, fixtures):
            raw = self.response(body, model, step, fixtures)
            raw["usage"].pop("cost")
            return raw
        query = Mock(side_effect=unknown)
        result = self.run_fake(query)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(result["stop_reason"], "unknown_cost")
        self.assertEqual(h.read(self.root / "budget.json")["attempts"]["step-001"]["status"], "uncertain")
        self.assertTrue(h.replay(self.root / "harness")["record_replay_passed"])

    def test_budget_adapter_allows_more_than_three_calls_and_blocks_after_threshold(self):
        self.config["limits"].update(max_calls=None, cost_stop_usd="0.055")
        self.config_path.write_text(json.dumps(self.config))
        ledger = h.read(self.root / "budget.json")
        ledger.update(max_trials=None, stop_at_usd="0.055", mode="threshold")
        auth = {k: v for k, v in ledger.items() if k != "attempts"}
        h.write(self.root / "authorization.json", auth)
        loop.c.atomic(self.root / "budget.json", ledger)
        def response(body, model, step, fixtures):
            return self.response(body, model, ((step-1) % 3)+1, fixtures)
        query = Mock(side_effect=response)
        result = self.run_fake(query)
        self.assertEqual(query.call_count, 6)
        self.assertEqual(result["state"]["cost_usd"], "0.06")
        self.assertEqual(result["stop_reason"], "cost_limit")
        self.assertTrue(h.replay(self.root / "harness")["record_replay_passed"])
        # Even a caller bypassing the main gate cannot dispatch another request.
        body = h.read(self.root / "harness/steps/006/request.json")
        with self.assertRaisesRegex(ValueError, "threshold already reached"):
            loop.BudgetQuery(self.root, http=self.http, query=query)(body, self.config["model"], 7)
        self.assertEqual(query.call_count, 6)


if __name__ == "__main__":
    unittest.main()
