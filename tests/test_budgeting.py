"""Strict pre-dispatch caps and auditable budget stops; no paid requests."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import artifacts as a, budgeting, harness, models
from test_harness import FakeEvaluator

REPO = Path(__file__).resolve().parents[1]
# Fixed synthetic-test ceilings; no experiment launcher or live price lookup.
MODEL = {"backend": "openrouter", "id": "openai/gpt-6.1-sol", "provider": "openai",
         "reasoning_effort": "high", "max_tokens": 4096, "timeout_seconds": 180,
         "seed": 42, "max_price": {"prompt": 2.5, "completion": 10}}


class BudgetingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = a.read(REPO / "configs/smoke.json")
        for key in ("problem", "template", "project", "prompt"):
            self.config[key] = str((REPO / "configs" / self.config[key]).resolve())
        self.config["model"] = MODEL
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

    def test_reservation_uses_utf8_wire_bound_and_transmitted_price_ceilings(self):
        body = models.payload([{"role": "system", "content": "Return JSON"},
                               {"role": "user", "content": "가나다"}], MODEL)
        bound = budgeting.reservation(body, {"cost_usd": "0"}, self.config)
        self.assertEqual(bound["input_token_bound"], len(json.dumps(body, ensure_ascii=False).encode()) + 4096)
        self.assertEqual(bound["output_token_bound"], MODEL["max_tokens"])
        self.assertEqual(bound["request_sha256"], a.sha(a.canonical(body)))


if __name__ == "__main__":
    unittest.main()
