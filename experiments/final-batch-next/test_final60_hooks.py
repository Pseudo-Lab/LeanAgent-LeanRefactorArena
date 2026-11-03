"""No-network regression checks for the driver's final60 hooks (verify3 budget-safety and smoke findings).

Scenario A: a sealed prior_cost_usd must bound every HTTP sub-attempt of the live dispatch path
(driver.final60_dispatch -> money.dispatch_guarded), lost-response retries included.
Scenario B: a step whose first sub-attempt is lost (charged at its bound) and whose retry succeeds
is not a bound violation: no api-frozen.json, no false ledger flag, a clean audit.
Plus: final60_root recognises every sealed final60 transport (the OpenAI-direct development wire
took the legacy path and crashed on restart), report.py audits such roots with their own adapter,
and run_problem's final selection skips a timed-out candidate instead of failing the row.
"""
import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("PROJECT_CACHE_DIR", tempfile.mkdtemp(prefix="final60-hooks-cache-"))

from lean_agent import artifacts as a, harness as h   # noqa: E402
from lean_agent.final60 import catalog, money, transport as t   # noqa: E402
from lean_agent.final60.contracts import Receipt   # noqa: E402

spec = importlib.util.spec_from_file_location("final_driver_hooks", Path(__file__).with_name("driver.py"))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
import openrouter_transport as adapter   # noqa: E402
import report   # noqa: E402

ACTION = json.dumps({"action": "search", "query": "theorem"})
MODEL = catalog.driver_model()
ROW = 17


def body_for(step):
    packet = {"problem": {"statement": "theorem t : True", "reference": "theorem t : True := by trivial"},
              "step": step, "text": "x" * 2000}
    return adapter.payload([{"role": "system", "content": "system prompt"},
                            {"role": "user", "content": json.dumps(packet)}], MODEL)


def make_root(run_dir, *, prior, row=ROW, cap="2.99"):
    root = run_dir / "rows" / f"F{row:03}"
    effective = Decimal(cap) - Decimal(prior)
    d.atomic(root / "ledger.json", {"schema_version": 1, "attempts": {}})
    d.atomic(root / "authorization.json", {
        "rows": [row], "per_problem_target_usd": str(effective), "last_call_may_overshoot": False,
        "provider": "OpenRouter", "api_endpoint": t.ENDPOINT, "transport": "mock", "cap_usd": cap,
        "prior_cost_usd": str(prior), "cost_ledger": "../../final60.sqlite", "compiler_slots": 2, "dry_run": True,
        "final60_schema": d.FINAL60_SCHEMA})
    settings = {"schema": d.FINAL60_SCHEMA, "row": row, "cap_usd": cap, "prior_cost_usd": str(prior),
                "effective_cap_usd": str(effective), "model": MODEL, "transport": "mock", "dry_run": True,
                "cost_ledger": "../../final60.sqlite", "run_dir": "../.."}
    d.atomic(d.folder(root, row) / "input/final60.json", settings)
    d.atomic(d.folder(root, row) / "input/config.json", {"model": MODEL, "limits": {"cost_cap_usd": str(effective)}})
    return root


class Final60HookTests(unittest.TestCase):
    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp(prefix="final60-hooks-"))
        original = money.dispatch_guarded

        def no_sleep(*args, **kwargs):
            kwargs.setdefault("sleep", lambda seconds: None)
            return original(*args, **kwargs)
        self.patches = [patch.object(money, "dispatch_guarded", no_sleep)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def responder(self, outcomes):
        calls = []

        def respond(body, spec=None, index=None):
            calls.append(index)
            return outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        item = patch.object(d, "final60_dry_responder", respond)
        item.start()
        self.patches.append(item)
        return calls

    def settle_earlier(self, root, ledger, attempt, usd):
        bound = t.request_bound(body_for(1), catalog.spec_for_model(MODEL))
        ledger.reserve(problem=f"F{ROW:03}", attempt_id=attempt + "#r0", bound=bound, run_root=str(root),
                       model=MODEL["id"], provider="openai", api_endpoint=t.ENDPOINT, request_sha256="x")
        ledger.mark_sent(attempt + "#r0")
        ledger.settle(Receipt(attempt_id=attempt + "#r0", status="settled", cost_usd=Decimal(usd), generation_id="gen-1",
                              model=MODEL["id"], provider="OpenAI", api_endpoint=t.ENDPOINT, basis="usage", http_status=200))
        saved = a.read(root / "ledger.json")
        saved["attempts"][attempt] = {"row": ROW, "step": 1, "status": "settled", "cost_usd": usd,
                                      "maximum_request_cost_usd": "0.20", "request_sha256": "x"}
        d.atomic(root / "ledger.json", saved)

    def test_sealed_prior_bounds_lost_retries_on_the_live_dispatch_path(self):
        # Scenario A: prior 1.00 outside this root, cap 2.99, effective 1.99, 1.80 already spent here.
        root = make_root(self.run_dir, prior="1.00")
        ledger = d.final60_ledger(root, ROW)
        self.assertEqual(ledger.prior(f"F{ROW:03}"), Decimal("1.00"))
        d.final60_ledger(root, ROW)                       # idempotent
        self.settle_earlier(root, ledger, f"F{ROW:03}-0001", "1.80")
        body = body_for(2)
        bound = Decimal(adapter.request_cost(body)["reserved_usd"])
        self.assertTrue(d.request_fits_budget(a.read(root / "ledger.json"), ROW, adapter.request_cost(body), "1.99"))
        self.assertGreater(Decimal("1.80") + 2 * bound, Decimal("1.99"))   # a second lost sub-attempt would cross it
        self.responder([t.MockOpenRouter.timeout()] * 3)
        step_dir = d.folder(root, ROW) / "steps" / "0002"
        step_dir.mkdir(parents=True)
        d.final60_dispatch(root, ROW, 2, body, MODEL, step_dir)
        item = a.read(root / "ledger.json")["attempts"][f"F{ROW:03}-0002"]
        spent = d.problem_spend(a.read(root / "ledger.json"), ROW)
        self.assertEqual(item["status"], "settled")
        self.assertEqual(item["http_calls"], 1)                         # the cap refused the second resend
        self.assertEqual(Decimal(item["cost_usd"]), bound)
        self.assertLessEqual(spent, Decimal("1.99"))
        self.assertLessEqual(Decimal("1.00") + spent, Decimal("2.99"))
        self.assertEqual(ledger.spent(f"F{ROW:03}"), Decimal("1.00") + spent)   # the mirror counts the prior
        self.assertFalse(item.get("bound_violated", False))
        self.assertFalse((root / "api-frozen.json").exists())
        # A prior that disagrees with the locked ledger is refused, never silently replaced.
        authorization = a.read(root / "authorization.json")
        authorization["prior_cost_usd"] = "0.50"
        d.atomic(root / "authorization.json", authorization)
        with self.assertRaises(ValueError):
            d.final60_ledger(root, ROW)

    def test_cost_ledger_env_override_is_honoured(self):
        root = make_root(self.run_dir, prior="0")
        override = self.run_dir / "shared.sqlite"
        with patch.dict(os.environ, {"FINAL60_COST_LEDGER": str(override)}):
            self.assertEqual(d.final60_ledger(root).path, override.resolve())
        self.assertEqual(d.final60_ledger(root).path, (root / "../../final60.sqlite").resolve())

    def test_lost_then_successful_sub_attempt_is_not_a_bound_violation(self):
        # Scenario B: the step total (lost bound + completion) exceeds one bound; the evidence says False.
        root = make_root(self.run_dir, prior="0")
        body = body_for(1)
        bound = Decimal(adapter.request_cost(body)["reserved_usd"])
        self.responder([t.MockOpenRouter.timeout(), ACTION])
        step_dir = d.folder(root, ROW) / "steps" / "0001"
        step_dir.mkdir(parents=True)
        normalized = d.final60_dispatch(root, ROW, 1, body, MODEL, step_dir)
        item = a.read(root / "ledger.json")["attempts"][f"F{ROW:03}-0001"]
        receipt = normalized["_cost_receipt"]
        self.assertEqual([entry["status"] for entry in receipt["sub_attempts"]], ["lost_conservative", "settled"])
        self.assertGreater(Decimal(item["cost_usd"]), bound)
        self.assertFalse(receipt["bound_violated"])
        self.assertFalse(item.get("bound_violated", False))
        self.assertFalse((root / "api-frozen.json").exists())
        self.assertIsNone(d.final60_stop_reason(root, ROW))
        self.assertEqual(adapter.audit_step(step_dir, item), [])
        # Recovery of a saved multi-sub-attempt step settles it the same way.
        saved = a.read(root / "ledger.json")
        saved["attempts"][f"F{ROW:03}-0001"] = {k: v for k, v in item.items()
                                                 if k in ("row", "step", "owner_pid", "api_endpoint", "request_sha256",
                                                          "started_at", "maximum_request_cost_usd")}
        saved["attempts"][f"F{ROW:03}-0001"].update(status="pending", cost_usd=None)
        d.atomic(root / "ledger.json", saved)
        d.recover_pending(root, ROW, 1, step_dir)
        recovered = a.read(root / "ledger.json")["attempts"][f"F{ROW:03}-0001"]
        self.assertEqual((recovered["status"], recovered["cost_usd"]), ("settled", item["cost_usd"]))
        self.assertFalse(recovered.get("bound_violated", False))
        self.assertFalse((root / "api-frozen.json").exists())
        self.assertEqual(adapter.audit_step(step_dir, recovered), [])

    def test_real_violation_still_freezes_the_row(self):
        root = make_root(self.run_dir, prior="0")
        body = body_for(1)
        self.responder([ACTION])
        step_dir = d.folder(root, ROW) / "steps" / "0001"
        step_dir.mkdir(parents=True)
        normalized = d.final60_dispatch(root, ROW, 1, body, MODEL, step_dir)
        normalized["_cost_receipt"]["bound_violated"] = True
        saved = a.read(root / "ledger.json")
        saved["attempts"][f"F{ROW:03}-0001"].update(status="pending")
        d.atomic(root / "ledger.json", saved)
        d.final60_settle(root, ROW, 1, adapter.request_cost(body), normalized, None, MODEL)
        self.assertTrue(a.read(root / "ledger.json")["attempts"][f"F{ROW:03}-0001"]["bound_violated"])
        self.assertTrue((root / "api-frozen.json").exists())
        self.assertEqual(d.final60_stop_reason(root, ROW), "row_api_frozen")

    def test_final60_root_recognises_every_sealed_transport(self):
        for name, fields, expected in (
                ("openrouter", {"provider": "OpenRouter", "transport": "openrouter"}, True),
                ("mock", {"provider": "OpenRouter", "transport": "mock", "dry_run": True}, True),
                ("openai", {"provider": "OpenAI direct", "transport": "openai",
                            "api_endpoint": "https://api.openai.com/v1/chat/completions"}, True),
                ("schema only", {"provider": "OpenAI direct", "final60_schema": d.FINAL60_SCHEMA}, True),
                ("legacy", {"provider": "OpenAI direct", "api_endpoint": "https://api.openai.com/v1/chat/completions"}, False)):
            with self.subTest(name=name):
                root = self.run_dir / name.replace(" ", "-")
                d.atomic(root / "authorization.json", {"rows": [1], **fields})
                self.assertIs(d.final60_root(root), expected)
        self.assertFalse(d.final60_root(self.run_dir / "missing"))

    def test_report_audits_openai_direct_roots_with_their_own_adapter(self):
        openai = report.openrouter_transport_for({"provider": "OpenAI direct", "transport": "openai"})
        self.assertEqual(openai.__name__, "openai_direct_transport")
        self.assertTrue(callable(openai.audit_step) and callable(openai.request_cost))
        self.assertEqual(report.openrouter_transport_for({"provider": "OpenRouter"}).__name__, "openrouter_transport")
        self.assertIsNone(report.openrouter_transport_for({"provider": "OpenAI direct"}))

    def test_final_selection_skips_incompatible_candidates(self):
        ok = {"valid": True, "runs": []}
        timeout = {"valid": False, "error": {"kind": "timeout", "message": "wall clock"}, "runs": []}
        compile_failure = {"valid": False, "error": {"kind": "compile", "message": "error: unsolved goals"}, "runs": []}
        sandbox = {"valid": False, "error": {"kind": "environment", "message": "bwrap: Can't find source path"}, "runs": []}
        self.assertEqual(d.final_candidate_disposition({"valid": True, "environments": {"a": ok, "b": ok}}), "valid")
        self.assertEqual(d.final_candidate_disposition({"valid": False, "environments": {"a": ok, "b": timeout}}), "timeout")
        self.assertEqual(d.final_candidate_disposition({"valid": False, "environments": {"a": compile_failure, "b": ok}}), "skip")
        self.assertEqual(d.final_candidate_disposition({"valid": False, "environments": {"a": ok, "b": sandbox}}), "environment")
        aborted = d.guard_compiler_signal({"valid": False, "environments": {"a": {
            "valid": False, "error": {"kind": "compile", "message": "lean::memory_exception: excessive memory consumption"},
            "runs": [{"returncode": 134, "command": ["bwrap", "--", "lean", "c.lean", "-M16384"]}]}}})
        self.assertTrue(h.environment_failed(aborted))
        self.assertEqual(d.final_candidate_disposition(aborted), "skip")


if __name__ == "__main__":
    unittest.main()
