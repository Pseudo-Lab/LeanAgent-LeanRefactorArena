"""Prompt-only treatment and strict experimental budget, with mocked transport."""
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_driver import d, result
from lean_agent import artifacts as a, harness as h
import prompt_variants
import report


class PromptVariantTests(unittest.TestCase):
    def test_only_optimization_guidance_changes(self):
        context = "frozen source context"
        base = d.prompt_text(context, "baseline", True)
        treatment = d.prompt_text(context, "structure-repair-v1", True)
        self.assertNotEqual(base, treatment)
        self.assertEqual(base.replace(prompt_variants.BASELINE, "GUIDANCE"),
                         treatment.replace(prompt_variants.STRUCTURE_REPAIR, "GUIDANCE"))
        self.assertIn("three lookups", treatment)
        self.assertIn("further targeted lookup remains allowed", treatment)
        self.assertIn("stops before exceeding $1", base)
        self.assertIn("stops before exceeding $1", treatment)

    def test_pending_reservations_count_and_exact_cap_is_allowed(self):
        ledger = {"attempts": {"one": {"row": 2, "cost_usd": "0.60", "status": "settled"},
                               "two": {"row": 2, "cost_usd": None, "status": "pending", "maximum_request_cost_usd": "0.20"}}}
        self.assertTrue(d.request_fits_budget(ledger, 2, {"reserved_usd": "0.20"}, "1"))
        self.assertFalse(d.request_fits_budget(ledger, 2, {"reserved_usd": "0.200001"}, "1"))
        self.assertTrue(d.request_fits_budget(ledger, 3, {"reserved_usd": "1"}, "1"))

    def test_strict_stop_finishes_without_paid_call_and_audits_exact_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = d.folder(root, 2)
            problem = {"id": "test", "name": "test", "statement": "theorem test : True",
                       "reference": "theorem test : True := by trivial\n", "environments": ["primary", "secondary"]}
            config = d.configuration(problem, strict_cap=True)
            baseline = result()
            state = h.initial_state(problem, baseline, config)
            state["cost_usd"] = "0.999"
            for name, value in (("input/problem.json", problem), ("input/config.json", config),
                                ("baseline/result.json", baseline), ("state.json", state),
                                ("preflight.json", {"status": "ready"})):
                d.atomic(output / name, value)
            (output / "input/prompt.txt").write_text(d.prompt_text("context", "structure-repair-v1", True))
            d.atomic(root / "ledger.json", {"attempts": {"previous": {"row": 2, "status": "settled", "cost_usd": "0.999"}}})
            class Fake:
                def evaluate(self, code, problem, path, **kwargs):
                    return result(all_versions=kwargs.get("all_versions", False))
                def verify_environments(self, problem, *, full):
                    return {"primary": "fixed", "secondary": "fixed"}
            with patch.object(d, "verify_frozen"), patch.object(d, "evaluator", return_value=Fake()), \
                 patch.object(d, "dispatch", side_effect=AssertionError("Over-budget paid call")):
                summary = d.run_problem(root, 2)
            self.assertEqual(summary["stop_reason"], "next_request_would_exceed_budget")
            self.assertEqual(summary["status"], "completed")
            report.audit_budget_stop(output, summary, Decimal("0.999"), Decimal(1))
            stop = a.read(output / "budget-stop.json")
            stop["next_request_bound_usd"] = "9"
            d.atomic(output / "budget-stop.json", stop)
            with self.assertRaisesRegex(ValueError, "reconstruct"):
                report.audit_budget_stop(output, summary, Decimal("0.999"), Decimal(1))

    def test_dispatch_checks_strict_cap_again_before_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"limits": {"cost_cap_usd": "1.00"}}
            d.atomic(d.folder(root, 2) / "input/config.json", config)
            d.atomic(root / "ledger.json", {"attempts": {"previous": {"row": 2, "status": "settled", "cost_usd": "0.999"}}})
            body = d.transport.payload([{"role": "system", "content": "JSON"}, {"role": "user", "content": "test"}], d.MODEL)
            with patch.object(d, "verify_frozen"), patch.object(d.transport, "model_metadata", return_value={}), \
                    patch.object(d.transport, "query", side_effect=AssertionError("Must not dispatch")):
                with self.assertRaisesRegex(ValueError, "strict per-problem"):
                    d.dispatch(root, 2, 1, body, d.MODEL, root / "step")
            self.assertEqual(len(a.read(root / "ledger.json")["attempts"]), 1)
