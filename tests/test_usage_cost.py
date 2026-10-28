import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lean_agent.usage_cost import codex_turn_records, make_receipt, normalize_usage, summarize, validate_prices

HERE = Path(__file__).resolve().parent
PRICES = {
    "schema_version": 1, "currency": "USD", "rate_card_id": "test-only-v1",
    "source": "synthetic unit test prices, not a commercial model", "as_of": "2026-10-27",
    "models": {"test-model": {"input_per_million": "2", "cached_input_per_million": "0.5",
                              "output_per_million": "10"}},
}


def event(mode="subagent", **changes):
    value = {"run_id": "r1", "agent_id": "a1", "event_id": "t1", "model": "test-model",
             "usage_scope": "exclusive_delta", "status": "completed"}
    usage = {"input_tokens": 1000, "cached_input_tokens": 200, "output_tokens": 100,
             "reasoning_output_tokens": 80}
    if mode == "api":
        value["response"] = {"model": "test-model", "usage": usage}
    else:
        value["usage"] = usage
    value.update(changes)
    return value


class AccountingTests(unittest.TestCase):
    def receipt(self, value=None, mode="subagent", prices=None):
        return make_receipt(value or event(mode), mode, prices or PRICES)

    def test_cached_input_and_reasoning_not_double_counted(self):
        receipt = self.receipt()
        # 800*2 + 200*.5 + 100*10 = 2700 per million.
        self.assertEqual(receipt["estimated_token_cost_usd"], "0.0027")
        self.assertIsNone(receipt["reported_cost_usd"])
        self.assertEqual(receipt["accounting_basis"], "token_estimate")

    def test_provider_cost_takes_precedence_without_losing_estimate(self):
        value = event("api")
        value["response"]["usage"]["cost"] = "0.0042"
        receipt = self.receipt(value, "api")
        self.assertEqual(receipt["accounted_cost_usd"], "0.0042")
        self.assertEqual(receipt["estimated_token_cost_usd"], "0.0027")
        self.assertEqual(receipt["accounting_basis"], "provider_reported")

    def test_zero_provider_cost_is_known(self):
        value = event("api", response={"usage": {"cost": 0}})
        receipt = self.receipt(value, "api")
        self.assertEqual(receipt["accounted_cost_usd"], "0")
        self.assertIsNone(receipt["estimated_token_cost_usd"])

    def test_api_can_estimate_without_reported_cost(self):
        value = event("api", response={"usage": {
            "prompt_tokens": 1000, "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 200},
            "completion_tokens_details": {"reasoning_tokens": 80}, "total_tokens": 1100}})
        self.assertEqual(self.receipt(value, "api")["accounted_cost_usd"], "0.0027")

    def test_missing_usage_stays_unknown_and_blocks_budget_decision(self):
        unknown = self.receipt(event(event_id="t2", usage=None, status="failed"))
        summary = summarize([self.receipt(), unknown], "1")
        self.assertIsNone(summary["accounted_cost_usd"])
        self.assertEqual(summary["accounted_cost_known_subtotal_usd"], "0.0027")
        self.assertEqual(summary["unknown_cost_entries"], 1)
        self.assertEqual(summary["budget_status"], "unknown")
        self.assertIsNone(summary["remaining_accounted_usd"])

    def test_failed_attempt_with_known_usage_is_not_discarded(self):
        receipt = self.receipt(event(status="failed"))
        self.assertEqual(summarize([receipt])["accounted_cost_usd"], "0.0027")

    def test_missing_model_rate_is_not_zero(self):
        receipt = self.receipt(event(model="not-priced"))
        self.assertIsNone(receipt["estimated_token_cost_usd"])
        self.assertEqual(receipt["estimate_unavailable_reason"], "missing_model_rates")

    def test_unreported_cache_assumption_is_visible(self):
        receipt = self.receipt(event(usage={"input_tokens": 1000, "output_tokens": 100}))
        self.assertEqual(receipt["estimated_token_cost_usd"], "0.003")
        self.assertIn("unreported_cache_reads_priced_as_uncached", receipt["estimate_assumptions"])

    def test_nonzero_cache_reads_require_cache_price(self):
        prices = copy.deepcopy(PRICES)
        del prices["models"]["test-model"]["cached_input_per_million"]
        receipt = self.receipt(prices=prices)
        self.assertEqual(receipt["estimate_unavailable_reason"], "missing_cached_input_rate")

    def test_cache_writes_need_explicit_rate_and_are_not_ordinary_input(self):
        usage = {"input_tokens": 1000, "output_tokens": 100,
                 "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100}}
        self.assertEqual(self.receipt(event(usage=usage))["estimate_unavailable_reason"], "missing_cache_write_rate")
        prices = copy.deepcopy(PRICES)
        prices["models"]["test-model"]["cache_write_per_million"] = "3"
        self.assertEqual(self.receipt(event(usage=usage), prices=prices)["estimated_token_cost_usd"], "0.0028")

    def test_invalid_counts_and_totals_are_rejected(self):
        invalid = [{"input_tokens": -1}, {"input_tokens": True}, {"input_tokens": 1.5},
                   {"input_tokens": 100, "cached_input_tokens": 101},
                   {"output_tokens": 5, "reasoning_output_tokens": 6},
                   {"input_tokens": 10, "output_tokens": 10, "total_tokens": 21},
                   {"input_tokens": 10, "prompt_tokens": 11}]
        for usage in invalid:
            with self.subTest(usage=usage), self.assertRaises(ValueError):
                normalize_usage(usage)

    def test_invalid_money_is_rejected(self):
        for amount in ("NaN", "Infinity", "-1", True, None):
            prices = copy.deepcopy(PRICES)
            prices["models"]["test-model"]["input_per_million"] = amount
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                validate_prices(prices)

    def test_model_mismatch_and_rollup_usage_are_rejected(self):
        with self.assertRaises(ValueError):
            self.receipt(event("api", response={"model": "different"}), "api")
        for scope in (None, "cumulative", "inclusive"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.receipt(event(usage_scope=scope))

    def test_duplicate_delivery_does_not_double_charge(self):
        receipt = self.receipt()
        self.assertEqual(summarize([receipt, receipt])["entries"], 1)
        changed = self.receipt(event(usage=None))
        with self.assertRaises(ValueError):
            summarize([receipt, changed])

    def test_separate_agents_and_turns_are_all_counted(self):
        receipts = [self.receipt(), self.receipt(event(agent_id="a2")), self.receipt(event(event_id="t2"))]
        summary = summarize(receipts, "0.01")
        self.assertEqual(summary["accounted_cost_usd"], "0.0081")
        self.assertEqual(summary["remaining_accounted_usd"], "0.0019")
        self.assertEqual(summary["budget_status"], "below_limit")
        self.assertEqual(summarize(receipts, "0.0081")["budget_status"], "exhausted")

    def test_modes_and_price_snapshots_cannot_be_mixed(self):
        with self.assertRaises(ValueError):
            summarize([self.receipt(), self.receipt(event("api", event_id="t2"), "api")])
        prices = copy.deepcopy(PRICES)
        prices["as_of"] = "2026-10-28"
        with self.assertRaises(ValueError):
            summarize([self.receipt(), self.receipt(event(event_id="t2"), prices=prices)])

    def test_codex_completed_failed_and_interrupted_turns(self):
        events = [{"type": "thread.started", "thread_id": "thread"},
                  {"type": "turn.started"}, {"type": "turn.completed", "usage": event()["usage"]},
                  {"type": "turn.started"}, {"type": "turn.failed"}, {"type": "turn.started"}]
        records = codex_turn_records(events, run_id="r", agent_id="a", model="test-model")
        self.assertEqual([r["status"] for r in records], ["completed", "failed", "incomplete"])
        summary = summarize([self.receipt(r) for r in records])
        self.assertEqual(summary["unknown_cost_entries"], 2)
        self.assertIsNone(summary["accounted_cost_usd"])

    def test_empty_codex_export_and_partial_usage_do_not_mean_free(self):
        records = codex_turn_records([], run_id="r", agent_id="a", model="test-model")
        self.assertIsNone(self.receipt(records[0])["accounted_cost_usd"])
        self.assertIsNone(self.receipt(event(status="incomplete"))["accounted_cost_usd"])
        with self.assertRaises(ValueError):
            codex_turn_records([{"type": "turn.completed"}], run_id="r", agent_id="a", model="test-model")

    def test_cli_both_modes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("PROJECT_CACHE_DIR")) as directory:
            root = Path(directory)
            (root / "prices.json").write_text(json.dumps(PRICES))
            for mode in ("api", "subagent"):
                (root / "events.json").write_text(json.dumps([event(mode)]))
                command = [sys.executable, "-m", "lean_agent.usage_cost", "--mode", mode,
                           "--input", str(root / "events.json"), "--prices", str(root / "prices.json"),
                           "--output", str(root / (mode + ".json"))]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = (root / (mode + ".json")).read_bytes()
                report = json.loads(output)
                self.assertEqual(report["summary"]["accounted_cost_usd"], "0.0027")
                self.assertEqual(report["price_snapshot"], PRICES)
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual((root / (mode + ".json")).read_bytes(), output)


if __name__ == "__main__":
    unittest.main()
