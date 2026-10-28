import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys

spec = importlib.util.spec_from_file_location("comparison", Path(__file__).with_name("compare.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
sys.path.insert(0, str(Path(__file__).parent))
import report


class BudgetTests(unittest.TestCase):
    def ledger(self):
        return {"per_trial_usd": "2", "total_usd": "10", "max_trials": 5, "attempts": {}}

    def test_boundary_and_total(self):
        ledger = self.ledger()
        for i in range(5):
            c.reserve(ledger, str(i), Decimal("2"))
            self.assertEqual(c.settle(ledger, str(i), {"usage": {"cost": 2}}), "settled")
        with self.assertRaises(ValueError):
            c.reserve(ledger, "six", Decimal("0.01"))
        with self.assertRaises(ValueError):
            c.reserve(self.ledger(), "large", Decimal("2.0000001"))
        ledger = self.ledger()
        ledger["total_usd"] = "1.99"
        with self.assertRaises(ValueError):
            c.reserve(ledger, "one", Decimal("2"))

    def test_uncertain_and_duplicate_block_dispatch(self):
        for raw in [{}, {"usage": {"cost": None}}, {"usage": {"cost": -1}}, {"usage": {"cost": True}}]:
            ledger = self.ledger()
            c.reserve(ledger, "one", Decimal("0.5"))
            self.assertEqual(c.settle(ledger, "one", raw), "uncertain")
            with self.assertRaises(ValueError):
                c.reserve(ledger, "next", Decimal("0.5"))
        ledger = self.ledger()
        c.reserve(ledger, "one", Decimal("1"))
        c.settle(ledger, "one", {"usage": {"cost": "0.1"}})
        with self.assertRaises(ValueError):
            c.reserve(ledger, "one", Decimal("1"))

    def test_overcharge_blocks_future_calls(self):
        ledger = self.ledger()
        c.reserve(ledger, "one", Decimal("0.5"))
        self.assertEqual(c.settle(ledger, "one", {"usage": {"cost": "0.50001"}}), "bound_violated")
        with self.assertRaises(ValueError):
            c.reserve(ledger, "two", Decimal("0.5"))

    def test_wire_and_pricing(self):
        body = c.wire_request([{"role": "system", "content": "Return JSON"}, {"role": "user", "content": "가나다"}])
        self.assertNotIn("temperature", body)
        self.assertFalse(body["provider"]["allow_fallbacks"])
        endpoint = {"tag": "openai", "model_id": c.MODEL, "context_length": 1050000,
            "pricing": {"prompt": "0.000002", "completion": "0.00001", "input_cache_write": "0.0000025",
                "overrides": [{"min_prompt_tokens": 272000, "prompt": "0.000004", "completion": "0.000015", "input_cache_write": "0.000005"}]},
            "supported_parameters": ["max_tokens", "reasoning", "response_format"], "max_completion_tokens": 128000}
        bound = c.reservation(endpoint, body)
        self.assertLess(bound, Decimal("2"))
        self.assertGreater(bound, Decimal("0.24576"))
        altered = copy.deepcopy(endpoint)
        altered["pricing"]["overrides"][0]["completion"] = "0.000016"
        with self.assertRaises(ValueError):
            c.reservation(altered, body)
        altered = copy.deepcopy(body)
        altered["tools"] = [{"type": "web_search"}]
        with self.assertRaises(ValueError):
            c.input_bound(altered)
        body["messages"][1]["content"] = "x" * 120000
        with self.assertRaises(ValueError):
            c.reservation(endpoint, body)

    def test_dotenv_literal_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("OPENROUTER='literal-$(do-not-execute)' # comment\n")
            self.assertEqual(c.load_key(path), "literal-$(do-not-execute)")
            path.write_text("OPENROUTER=one\nOPENROUTER_API_KEY=two\n")
            with self.assertRaises(ValueError):
                c.load_key(path)

    def test_durable_reservation_and_frozen_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = self.ledger()
            c.reserve(ledger, "one", Decimal("1"))
            c.atomic(root / "budget.json", ledger)
            self.assertEqual(c.read(root / "budget.json")["attempts"]["one"]["status"], "reserved")
            (root / "input.txt").write_text("original")
            c.write(root / "frozen.json", {"input.txt": c.sha("original")})
            c.check_frozen(root)
            (root / "input.txt").write_text("modified")
            with self.assertRaises(ValueError):
                c.check_frozen(root)

    def test_comparison_excludes_supplementary_runs_and_preserves_unknown_cost(self):
        rows = []
        for backend, count in [("openrouter", 5), ("subagent", 3)]:
            for i in range(1, count + 1):
                rows.append({"trial": f"{backend}-{i:02}", "backend": backend,
                    "candidate_valid": i > 3, "improved": i > 3, "final_valid": True,
                    "cost_usd": "0.1" if backend == "openrouter" else None,
                    "estimated_token_cost_usd": "0.2", "generation_seconds": i,
                    "runtime_tool_items": []})
        groups = report.summarize({"trials": rows})
        self.assertEqual(groups["openrouter"]["completed_trials"], 5)
        self.assertEqual(groups["openrouter"]["candidate_valid"], 0)
        self.assertEqual(groups["openrouter"]["final_valid"], 3)
        self.assertEqual(groups["openrouter"]["comparison_reported_cost_usd"], "0.3")
        self.assertIsNone(groups["subagent"]["comparison_reported_cost_usd"])


if __name__ == "__main__":
    unittest.main()
