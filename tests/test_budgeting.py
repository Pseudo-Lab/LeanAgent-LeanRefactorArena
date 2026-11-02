"""Strict pre-dispatch caps and auditable budget stops; no paid requests."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import artifacts as a, budgeting, harness, models
from test_harness import FakeEvaluator

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("live_p02", REPO / "experiments/action-candidate-memory/live_p02.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class BudgetingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = a.read(REPO / "configs/smoke.json")
        for key in ("problem", "template", "project", "prompt"):
            self.config[key] = str((REPO / "configs" / self.config[key]).resolve())
        self.config["model"] = live.MODEL
        self.config["limits"].update(max_calls=12, cost_cap_usd="0.15")
        self.path, self.output = self.root / "config.json", self.root / "run"
        self.calls = 0

    def query(self, body, model, step, fixtures):
        self.calls += 1
        return {"choices": [{"message": {"content": '{"proof":"by rfl"}'}}], "usage": {"cost": "0.04"}}

    def run_case(self):
        self.path.write_text(json.dumps(self.config))
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-only"}):
            return harness.run(self.path, self.output, evaluator=FakeEvaluator(), query=self.query)

    def test_reservation_stops_before_dispatch_and_replays_without_billing_a_denied_call(self):
        result = self.run_case()
        stop = a.read(self.output / "budget-stop.json")
        self.assertEqual(result["stop_reason"], "budget_reservation")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["state"]["calls"], self.calls)
        self.assertGreater(self.calls, 0)
        self.assertLessEqual(float(result["state"]["cost_usd"]), 0.15)
        self.assertGreater(float(stop["spent_usd"]) + float(stop["reserved_usd"]), 0.15)
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])
        stop["reserved_usd"] = "0"
        (self.output / "budget-stop.json").write_text(a.canonical(stop))
        (self.output / "artifacts.json").unlink()
        harness.seal(self.output)
        with self.assertRaisesRegex(ValueError, "Budget stop differs"):
            harness.replay(self.output)

    def test_zero_dispatch_is_a_valid_finalized_run_when_no_request_fits(self):
        self.config["limits"]["cost_cap_usd"] = "0.0001"
        result = self.run_case()
        self.assertEqual(self.calls, 0)
        self.assertEqual(result["state"]["cost_usd"], "0")
        self.assertEqual(result["stop_reason"], "budget_reservation")
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_unknown_charge_stops_before_any_further_dispatch(self):
        def query(*args):
            self.calls += 1
            return {"choices": [{"message": {"content": '{"proof":"by rfl"}'}}]}
        self.query = query
        result = self.run_case()
        self.assertEqual(self.calls, 1)
        self.assertEqual(result["stop_reason"], "unknown_cost")
        self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def endpoint(self):
        return {"tag": "openai", "model_id": live.MODEL["id"], "context_length": 1050000,
            "max_completion_tokens": 128000,
            "supported_parameters": ["max_tokens", "reasoning", "response_format", "seed"],
            "pricing": {"prompt": "0.000002", "completion": "0.00001", "input_cache_write": "0.0000025",
                "overrides": [{"min_prompt_tokens": 272000, "prompt": "0.000004", "completion": "0.000015"}]}}

    def body(self):
        return models.payload([{"role": "system", "content": "Return JSON"},
                               {"role": "user", "content": "가나다"}], live.MODEL)

    def test_utf8_bound_and_reachable_cache_price_tiers(self):
        body = self.body()
        bound = budgeting.reservation(body, {"cost_usd": "0"}, self.config)
        self.assertEqual(bound["input_token_bound"], len(json.dumps(body, ensure_ascii=False).encode()) + 4096)
        endpoint = self.endpoint()
        live.validate_endpoint(endpoint, body, bound)
        endpoint["pricing"]["input_cache_write"] = "0.000003"
        with self.assertRaisesRegex(ValueError, "price exceeds"):
            live.validate_endpoint(endpoint, body, bound)
        endpoint = self.endpoint()
        endpoint["pricing"]["overrides"][0]["min_prompt_tokens"] = 100
        with self.assertRaisesRegex(ValueError, "price exceeds"):
            live.validate_endpoint(endpoint, body, bound)

    def transport(self):
        a.write(self.root / "inputs/whole.json", self.config)
        a.write(self.root / "authorization.json", live.AUTH)
        a.write(self.root / "budget.json", {**live.AUTH, "attempts": {}})
        a.write(self.root / "frozen.json", {})
        harness.snapshot_code(self.root / "whole")
        return live.BudgetQuery(self.root, "whole")

    def test_transport_durably_reserves_before_dispatch_and_rejects_condition_overrun(self):
        query, body = self.transport(), self.body()
        dispatched = []
        def response(*args):
            ledger = a.read(self.root / "budget.json")
            self.assertEqual(list(ledger["attempts"].values())[-1]["status"], "reserved")
            dispatched.append(True)
            return {"usage": {"cost": "0.04"}}
        with patch.object(live.c, "http", return_value={"data": {"endpoints": [self.endpoint()]}}), \
                patch.object(models, "query", side_effect=response):
            for step in range(1, 4):
                query(body, live.MODEL, step)
            with self.assertRaisesRegex(ValueError, "reservation refused"):
                query(body, live.MODEL, 4)
        self.assertEqual(len(dispatched), 3)

    def test_transport_unknown_billing_blocks_the_other_condition(self):
        query, body = self.transport(), self.body()
        with patch.object(live.c, "http", return_value={"data": {"endpoints": [self.endpoint()]}}), \
                patch.object(models, "query", return_value={}) as dispatched:
            query(body, live.MODEL, 1)
            with self.assertRaisesRegex(ValueError, "Unknown/pending"):
                query(body, live.MODEL, 2)
        self.assertEqual(dispatched.call_count, 1)

    def test_default_comparison_uses_actual_cost_threshold_and_allows_last_response_to_cross(self):
        query, body = self.transport(), self.body()
        auth = live.authorization()
        live.budget_conditions(self.config, auth)
        self.assertEqual(self.config["limits"]["cost_stop_usd"], "0.15")
        self.assertIsNone(self.config["limits"]["max_calls"])
        self.assertNotIn("cost_cap_usd", self.config["limits"])
        (self.root / "inputs/whole.json").write_text(a.canonical(self.config))
        (self.root / "authorization.json").write_text(a.canonical(auth))
        (self.root / "budget.json").write_text(a.canonical({**auth, "attempts": {}}))
        with patch.object(live.c, "http", return_value={"data": {"endpoints": [self.endpoint()]}}), \
                patch.object(models, "query", return_value={"usage": {"cost": "0.04"}}) as dispatched:
            for step in range(1, 5):
                query(body, live.MODEL, step)
            with self.assertRaisesRegex(ValueError, "reservation refused"):
                query(body, live.MODEL, 5)
        self.assertEqual(dispatched.call_count, 4)
        self.assertEqual(sum(float(row["cost_usd"]) for row in a.read(self.root / "budget.json")["attempts"].values()), 0.16)


if __name__ == "__main__":
    unittest.main()
