"""final60 orchestrator: driver hooks, row worker, supervisor and assembly (no network, no Lean).

The transport component (catalog/transport/ledger/money and openrouter_transport) is
replaced by local fakes with the contract's signatures. They are installed per test
through patch.dict(sys.modules), so they never leak into the transport's own tests.
"""
from __future__ import annotations

import contextlib
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DRIVER_DIR = ROOT / "experiments/final-batch-next"
if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

import driver as d  # noqa: E402  (the module object report.py also imports)
import report  # noqa: E402
import resources  # noqa: E402
from lean_agent import artifacts as a, harness as h, models  # noqa: E402
import lean_agent.final60 as package  # noqa: E402
from lean_agent.final60 import assemble as assembly, orchestrator as o, rowworker as rw, supervisor as sup  # noqa: E402
from lean_agent.final60.contracts import CAP_USD, OPENROUTER_ENDPOINT, Receipt, Route, RowState  # noqa: E402

MODEL = dict(o.DEFAULT_MODEL)


def evaluation(tokens=10, heartbeat=100, *, all_versions=False):
    env = {"valid": True, "runs": [{"measurement": {"raw": heartbeat}}]}
    return {"valid": True, "tokens": tokens, "environments": {"primary": env, **({"secondary": env} if all_versions else {})}}


class Evaluator:
    """Compile oracle: every candidate verifies (2 tokens, 50 raw HB); evidence files are real."""

    def evaluate(self, code, problem, path, **kwargs):
        measured = json.loads(a.canonical(evaluation(2, 50, all_versions=kwargs.get("all_versions", False))))
        for environment, row in measured["environments"].items():
            destination = Path(path) / environment
            destination.mkdir(parents=True, exist_ok=True)
            log = "Synthetic compiler evidence; Lean was not invoked."
            (destination / "source.lean").write_text(code)
            (destination / "compile.log").write_text(log)
            for run in row["runs"]:
                run.update(source="source.lean", source_sha256=a.sha(code), log="compile.log", log_sha256=a.sha(log))
        return measured

    def verify_environments(self, problem, *, full):
        return {"primary": "verified"}


class Crash(Exception):
    pass


class FakeWorld:
    """Fake transport component: SQLite-like ledger, dispatch_guarded, catalog, adapter, mock."""

    def __init__(self):
        self.rows = {}            # sub-attempt id -> record
        self.calls = {}           # attempt id -> HTTP sends
        self.budget_exceeded_on = set()
        self.crash_on = set()
        self.api_disabled_on = set()
        self.recover_status = "lost_conservative"
        world = self

        class BudgetExceeded(Exception):
            pass

        class ApiDisabled(Exception):
            pass

        class CostLedger:
            def __init__(self, path, *, cap_usd=CAP_USD):
                self.path, self.cap = path, cap_usd

            def spent(self, problem):
                return sum((Decimal(r["cost_usd"]) for r in world.rows.values()
                            if r["problem"] == problem and r["cost_usd"] is not None), Decimal(0))

            def open_attempts(self, *, run_root=None):
                return [{"attempt_id": key, **value} for key, value in world.rows.items() if value["status"] == "sent"]

            def recover(self, attempt_id, *, step_dir, key):
                record = world.rows[attempt_id]
                cost = Decimal(0) if world.recover_status == "void" else Decimal(record["bound"])
                record.update(status=world.recover_status, cost_usd=str(cost))
                return Receipt(attempt_id, world.recover_status, cost, None, None, None, OPENROUTER_ENDPOINT, "lost-bound")

            def attempts(self, problem=None):
                return [{"attempt_id": key, **value} for key, value in world.rows.items()
                        if problem is None or value["problem"] == problem]

        def dispatch_guarded(body, spec, *, ledger, problem, attempt_id, run_root, step_dir, key, transport=None,
                             max_unbilled_retries=5):
            assert spec == "spec:" + MODEL["catalog_key"]
            if attempt_id in world.budget_exceeded_on:
                raise BudgetExceeded("would exceed the cap")
            if attempt_id in world.api_disabled_on:
                raise ApiDisabled("402")
            world.calls[attempt_id] = world.calls.get(attempt_id, 0) + 1
            sub = f"{attempt_id}#r{world.calls[attempt_id]}"
            world.rows[sub] = {"problem": problem, "status": "sent", "bound": "0.05", "cost_usd": None}
            d.atomic(step_dir / "request.json", body)
            d.atomic(step_dir / "cost-bound.json", {"reserved_usd": "0.05"})
            d.atomic(step_dir / "endpoint.json", {"endpoint": OPENROUTER_ENDPOINT})
            if attempt_id in world.crash_on:
                world.crash_on.discard(attempt_id)
                raise Crash("worker killed after send")
            responder = transport.respond if transport is not None else world.respond
            raw = {"id": "gen-" + sub, "model": MODEL["id"], "provider": "OpenAI",
                   "choices": [{"message": {"content": responder(body)}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "cost": 0.01}}
            d.atomic(step_dir / "provider-response.json", raw)
            normalized = json.loads(json.dumps(raw))
            normalized["usage"]["cost"] = "0.01"
            normalized["_cost_receipt"] = {"cost_usd": "0.01", "basis": "usage", "provider_response_sha256": a.sha(a.canonical(raw))}
            d.atomic(step_dir / "response.json", normalized)
            d.atomic(step_dir / "cost-receipt.json", normalized["_cost_receipt"])
            world.rows[sub].update(status="settled", cost_usd="0.01")
            receipt = Receipt(attempt_id, "settled", Decimal("0.01"), raw["id"], raw["model"], "OpenAI", OPENROUTER_ENDPOINT, "usage", 200)
            return types.SimpleNamespace(raw=raw, normalized=normalized, receipt=receipt, bound=None, http_calls=1)

        class MockOpenRouter:
            def __init__(self, responder, *, cost_usd=Decimal("0.01")):
                self.respond = responder

        def audit_step(step_dir, item):
            response = a.read(step_dir / "response.json")
            errors = []
            if Decimal(str(response["usage"]["cost"])) != Decimal(item["cost_usd"]):
                errors.append("response cost differs from ledger")
            if response.get("id") != item["response_id"]:
                errors.append("response identity differs")
            return errors

        self.money = types.ModuleType("lean_agent.final60.money")
        self.money.dispatch_guarded, self.money.ApiDisabled = dispatch_guarded, ApiDisabled
        self.ledger = types.ModuleType("lean_agent.final60.ledger")
        self.ledger.CostLedger, self.ledger.BudgetExceeded = CostLedger, BudgetExceeded
        self.catalog = types.ModuleType("lean_agent.final60.catalog")
        self.catalog.spec_for_model = lambda model: "spec:" + model["catalog_key"]
        self.transport = types.ModuleType("lean_agent.final60.transport")
        self.transport.MockOpenRouter = MockOpenRouter
        self.adapter = types.ModuleType("openrouter_transport")
        self.adapter.ENDPOINT = OPENROUTER_ENDPOINT
        self.adapter.PRICING = {"model": MODEL["id"], "source": "test fixture"}
        self.adapter.payload = lambda messages, model: models.payload(messages, model)
        self.adapter.request_cost = lambda body: {"reserved_usd": "0.05", "input_token_bound": 1,
                                                  "output_token_bound": 1, "basis": "test bound"}
        self.adapter.audit_step = audit_step
        self.adapter.load_key = lambda path: "test-key-not-real"
        self.packets = []

    def respond(self, body):
        packet = json.loads(body["messages"][1]["content"])
        self.packets.append(packet)
        action = {"action": "propose", "parent_id": "c000", "strategy": packet["portfolio"]["route"],
                  "proof": "by trivial -- " + packet["portfolio"]["branch"] + f" {len(self.packets)}"}
        if packet["portfolio"]["branch"] == "merge":
            action["source_candidate_ids"] = [cid for cid in ("c001", "c002", "c003")
                                              if cid in packet["exploration"]["candidates"]] or ["c000"]
        return json.dumps(action)

    @contextlib.contextmanager
    def installed(self):
        modules = {"openrouter_transport": self.adapter, "lean_agent.final60.money": self.money,
                   "lean_agent.final60.ledger": self.ledger, "lean_agent.final60.catalog": self.catalog,
                   "lean_agent.final60.transport": self.transport}
        with patch.dict(sys.modules, modules), contextlib.ExitStack() as stack:
            for name in ("money", "ledger", "catalog", "transport"):
                stack.enter_context(patch.object(package, name, modules["lean_agent.final60." + name], create=True))
            yield self


PROBLEM = {"id": "test", "row": 1, "name": "test", "source": "synthetic fixture", "environments": ["primary", "secondary"],
           "statement": "theorem test : True", "reference": "theorem test : True := by trivial\n"}


def settings(*, skip_llm=False, dry_run=False, prior="0", route_sha="", portfolio=None):
    portfolio = None if skip_llm else (portfolio or {"scout_evaluations": 1, "merger_evaluations": 1,
                                                     "progress_guard": "bounded-v1"})
    return {"schema": d.FINAL60_SCHEMA, "row": 1, "name": "test", "cap_usd": "2.99", "prior_cost_usd": prior,
            "effective_cap_usd": str(Decimal("2.99") - Decimal(prior)), "model": dict(MODEL), "skip_llm": skip_llm,
            "portfolio": portfolio, "prompt_addendum": "Prefer short closers.", "route_sha256": route_sha,
            "cost_ledger": "../../final60.sqlite", "run_dir": "../..", "compiler_slots": 4, "dry_run": dry_run,
            "role_models": {}, "role_models_requested": {}}


def make_root(run_dir, *, skip_llm=False, dry_run=False):
    """A sealed-looking final60 row root (inputs, baseline, state, authorization) without Lean."""
    root = Path(run_dir) / "rows/F001"
    output = d.folder(root, 1)
    route_bytes = b'{"row": 1}\n'
    (output / "input").mkdir(parents=True)
    (output / "input/route.json").write_bytes(route_bytes)
    value = settings(skip_llm=skip_llm, dry_run=dry_run, route_sha=a.sha(route_bytes))
    config = d.final60_configuration(PROBLEM, value)
    for name, item in (("problem", PROBLEM), ("config", config), ("final60", value),
                       ("warm-start", d.warm_start.snapshot(None, PROBLEM, reason="explicit_cold_start")),
                       ("prompt-policy", d.prompt_variants.policy("baseline", True)),
                       ("action-corpus", {"schema_version": 1, "entries": []})):
        d.atomic(output / "input" / (name + ".json"), item)
    (output / "input/prompt.txt").write_text("test")
    d.atomic(output / "baseline/result.json", evaluation())
    d.atomic(output / "state.json", h.initial_state(PROBLEM, evaluation(), config))
    d.atomic(output / "preflight.json", {"status": "ready"})
    d.atomic(root / "ledger.json", {"schema_version": 1, "attempts": {}})
    d.atomic(root / "authorization.json", {
        "rows": [1], "dataset_sha256": "synthetic", "per_problem_target_usd": value["effective_cap_usd"],
        "last_call_may_overshoot": False, "verification_policy": d.VERIFICATION_POLICY, "provider": "OpenRouter",
        "api_endpoint": OPENROUTER_ENDPOINT, "cap_usd": "2.99", "prior_cost_usd": "0",
        "cost_ledger": "../../final60.sqlite", "compiler_slots": 4, "dry_run": dry_run})
    return root, output


class DriverHookTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)
        self.world = FakeWorld()
        os.environ["OPENROUTER_API_KEY"] = "test-key-not-real"
        self.addCleanup(os.environ.pop, "OPENROUTER_API_KEY", None)

    def run_row(self, root):
        with self.world.installed(), patch.object(d, "verify_frozen"), \
                patch.object(d, "evaluator", return_value=Evaluator()):
            return d.run_problem(root, 1)

    def attempts(self, root):
        return a.read(root / "ledger.json")["attempts"]

    def test_full_row_settles_one_attempt_per_step_and_passes_both_audits(self):
        root, output = make_root(self.run_dir)
        summary = self.run_row(root)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["provider"], "OpenRouter")
        self.assertEqual(summary["stop_reason"], "portfolio_complete")
        attempts = self.attempts(root)
        self.assertEqual(sorted(attempts), [f"F001-{step:04}" for step in range(1, 5)])
        self.assertTrue(all(item["status"] == "settled" and item["cost_usd"] == "0.01" for item in attempts.values()))
        self.assertEqual(summary["cost_usd"], "0.04")
        self.assertNotIn("reference", self.world.packets[0]["problem"])   # scout-a hides the original
        with self.world.installed():
            built = report.build_report(root)
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        d.atomic(root / "report.json", built)
        checker, _ = assembly.checker("check_submission_provenance")
        selected = (output / "selected.lean").read_text()
        self.assertNotEqual(selected, PROBLEM["reference"])
        result = checker.check([{"name": "test", "statement": PROBLEM["statement"], "reference": PROBLEM["reference"]}],
                               [{"name": "test", "proof": selected}], [checker.RunRoot(root)], [], [], Decimal("3"))
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["rows"][0]["cost_usd"], "0.04")
        # A complete row resumes without any further call.
        with self.world.installed(), patch.object(d, "verify_frozen"), \
                patch.object(d, "dispatch", side_effect=AssertionError("no repeat call")):
            self.assertEqual(d.run_problem(root, 1), summary)

    def test_ledger_budget_exceeded_breaks_to_selection_without_a_charge(self):
        root, _ = make_root(self.run_dir)
        self.world.budget_exceeded_on.add("F001-0002")
        summary = self.run_row(root)
        self.assertEqual(summary["stop_reason"], "ledger_budget_exceeded")
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(list(self.attempts(root)), ["F001-0001"])
        with self.world.installed():
            built = report.build_report(root)
        self.assertTrue(built["audit_passed"], built["audit_errors"])

    def test_api_disabled_is_global_and_stops_every_row_cleanly(self):
        root, _ = make_root(self.run_dir)
        self.world.api_disabled_on.add("F001-0001")
        summary = self.run_row(root)
        self.assertEqual(summary["stop_reason"], "api_disabled")
        self.assertTrue((self.run_dir / "api-disabled.json").exists())
        self.assertEqual(self.attempts(root), {})
        self.assertEqual(d.final60_stop_reason(root, 1), "api_disabled")

    def test_soft_stop_and_skip_llm_select_the_original_without_calls(self):
        for flag in ("stop-exploration.json", None):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as temp:
                root, output = make_root(temp, skip_llm=flag is None)
                if flag:
                    d.atomic(Path(temp) / flag, {"reason": "deadline soft stop"})
                summary = self.run_row(root)
                self.assertEqual(summary["stop_reason"], "stop_exploration" if flag else "skip_llm")
                self.assertEqual(summary["status"], "stopped")
                self.assertEqual(summary["calls"], 0)
                self.assertEqual((output / "selected.lean").read_text(), PROBLEM["reference"])
                with self.world.installed():
                    built = report.build_report(root)
                self.assertTrue(built["audit_passed"], built["audit_errors"])

    def test_killed_worker_resumes_without_duplicate_attempt_or_second_send(self):
        root, _ = make_root(self.run_dir)
        self.world.crash_on.add("F001-0002")
        with self.assertRaises(Crash):
            self.run_row(root)
        self.assertEqual(self.attempts(root)["F001-0002"]["status"], "pending")
        summary = self.run_row(root)
        self.assertEqual(self.world.calls["F001-0002"], 1)          # never re-sent
        attempts = self.attempts(root)
        self.assertEqual(len(attempts), len(set(attempts)))
        lost = attempts["F001-0002"]
        self.assertEqual((lost["status"], lost["response_id"], lost["cost_usd"]), ("settled", "lost-F001-0002", "0.05"))
        self.assertEqual(summary["cost_usd"], str(sum(Decimal(item["cost_usd"]) for item in attempts.values())))
        with self.world.installed():
            built = report.build_report(root)
        self.assertTrue(built["audit_passed"], built["audit_errors"])

    def test_unsent_interrupted_step_is_released_and_dispatched_again(self):
        root, _ = make_root(self.run_dir)
        self.world.crash_on.add("F001-0001")
        self.world.recover_status = "void"
        with self.assertRaises(Crash):
            self.run_row(root)
        summary = self.run_row(root)
        self.assertEqual(self.world.calls["F001-0001"], 2)
        self.assertEqual(summary["cost_usd"], "0.04")
        self.assertTrue(any(path.name.startswith("unsent-") for path in (d.folder(root, 1) / "steps/0001").iterdir()))

    def test_dry_run_roots_use_the_mock_transport(self):
        root, _ = make_root(self.run_dir, dry_run=True)
        os.environ.pop("OPENROUTER_API_KEY")
        summary = self.run_row(root)
        self.assertGreater(summary["calls"], 0)
        self.assertEqual(self.world.packets, [])          # the sealed mock answered, not the test model
        self.assertTrue(all(item["status"] == "settled" for item in self.attempts(root).values()))
        self.assertEqual(len(self.attempts(root)), summary["calls"])

    def test_inputs_validation_prompt_and_cap(self):
        root, output = make_root(self.run_dir)
        value = a.read(output / "input/final60.json")
        config = a.read(output / "input/config.json")
        self.assertEqual(config["limits"]["cost_cap_usd"], "2.99")
        self.assertEqual(config["limits"]["cost_stop_usd"], "2.99")
        self.assertEqual(config["model"]["backend"], "openrouter")
        legacy = d.prompt_text("ctx", "baseline", True)
        hinted = d.prompt_text("ctx", "baseline", True, value["prompt_addendum"])
        self.assertEqual(hinted.replace("Prefer short closers.\n", ""), legacy)
        self.assertTrue(hinted.endswith("<original_context>\nctx\n</original_context>\n"))
        inputs = output / "input"
        policy = a.read(inputs / "prompt-policy.json")
        d.final60_validate(inputs, value, PROBLEM, policy)
        for change, message in ((dict(cap_usd="3.50", effective_cap_usd="3.50"), "cap"),
                                (dict(effective_cap_usd="2.00"), "cap"),
                                (dict(model={**MODEL, "backend": "openai"}), "OpenRouter"),
                                (dict(skip_llm=True), "skip_llm"),
                                (dict(prompt_addendum="<original_context>"), "addendum")):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                d.final60_validate(inputs, {**value, **change}, PROBLEM, policy)
        with self.assertRaisesRegex(ValueError, "strict"):
            d.final60_validate(inputs, value, PROBLEM, {"variant": "baseline", "strict_cap": False})
        seeded = d.warm_start.snapshot(None, PROBLEM, reason="explicit_cold_start")
        seeded["candidate"] = {"code": "x"}
        d.atomic(inputs / "warm-start.json", seeded)
        with self.assertRaisesRegex(ValueError, "warm-start"):
            d.final60_validate(inputs, value, PROBLEM, policy)

    def test_seal_writes_openrouter_authorization_and_freezes_money_modules(self):
        root, output = make_root(self.run_dir)
        (root / "authorization.json").unlink()
        (root / "ledger.json").unlink()
        files = [d.HERE / "driver.py", d.HERE / "resources.py"]
        with self.world.installed(), patch.object(d, "validate_inputs"), \
                patch.object(d, "implementation_files", side_effect=lambda final60=False: files) as frozen, \
                patch.dict(os.environ, {"FINAL60_COMPILER_SLOTS": "5"}):
            d.seal_inputs(root, [1])
        frozen.assert_called_with(True)
        authorization = a.read(root / "authorization.json")
        self.assertEqual((authorization["provider"], authorization["api_endpoint"]), ("OpenRouter", OPENROUTER_ENDPOINT))
        self.assertEqual(authorization["per_problem_target_usd"], "2.99")
        self.assertFalse(authorization["last_call_may_overshoot"])
        self.assertEqual(authorization["compiler_slots"], 5)
        self.assertIn(str(output / "input/final60.json"), a.read(root / "frozen.json"))
        with self.assertRaisesRegex(ValueError, "never resealed"):
            d.reseal(root)
        listed = d.implementation_files(final60=True)
        self.assertTrue(all((d.h.BASE / "final60" / name).resolve() in listed for name in d.FINAL60_MONEY_FILES))

    def test_compiler_parallelism_fails_closed_for_final60_roots(self):
        legacy = self.run_dir / "legacy"
        legacy.mkdir()
        self.assertEqual(d.compiler_parallelism(legacy), 1)
        root, output = make_root(self.run_dir)
        d.atomic(root / "authorization.json", {**a.read(root / "authorization.json"), "compiler_slots": None})
        value = a.read(output / "input/final60.json")
        d.atomic(output / "input/final60.json", {**value, "compiler_slots": 1})
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FINAL60_COMPILER_SLOTS", None)
            with self.assertRaisesRegex(ValueError, "2..8"):
                d.compiler_parallelism(root)
            with patch.dict(os.environ, {"FINAL60_COMPILER_SLOTS": "6"}):
                self.assertEqual(d.compiler_parallelism(root), 6)

    def test_pool_slots_and_absolute_memory_rule(self):
        self.assertTrue(resources.admits({"available_gib": 10.0}, 5, reserve_gib=6, gib_per_compile=3.5))
        self.assertFalse(resources.admits({"available_gib": 9.0}, 0, reserve_gib=6, gib_per_compile=3.5))
        self.assertTrue(resources.admits({"free_percent": 80}, 5))      # team rule unchanged when unset
        self.assertFalse(resources.admits({"free_percent": 60}, 5))
        with self.assertRaises(ValueError):
            with resources.compiler_slot(self.run_dir / "lock", slots=9):
                pass
        held = []
        lock = self.run_dir / "pool.lock"
        with patch.dict(os.environ, {"FINAL60_MEM_RESERVE_GIB": "1", "FINAL60_GIB_PER_COMPILE": "1",
                                     "FINAL60_ADMISSION_SPACING_S": "0", "FINAL60_RESOURCE_WAIT_S": "5"}), \
                patch.object(resources, "memory_snapshot", return_value={"free_percent": 50, "available_gib": 30.0}):
            with contextlib.ExitStack() as stack:
                for _ in range(6):
                    stack.enter_context(resources.compiler_slot(lock, slots=6))
                    held.append(1)
                busy = sum(sup.lock_held(Path(str(lock) + f".slot-{n}")) for n in range(6))
        self.assertEqual((len(held), busy), (6, 6))


def dataset_rows():
    return [{"name": f"Final.t{row}", "source": "synthetic", "statement": f"theorem t{row} : True",
             "src": f"theorem t{row} : True := by\n  trivial\n"} for row in range(1, 61)]


@contextlib.contextmanager
def fake_dataset(directory):
    path = Path(directory) / "dataset.jsonl"
    raw = "".join(json.dumps(row) + "\n" for row in dataset_rows()).encode()
    path.write_bytes(raw)
    with patch.object(o, "DATASET_SHA", o.sha_bytes(raw)):
        yield path


def publish_row(layout, row, proof, *, provider="OpenRouter", dry_run=False, audit=True, cost="0.40"):
    """A minimal published OpenRouter root as the row worker leaves it."""
    root, folder = layout.row_root(row), layout.row_folder(row)
    name = f"Final.t{row}"
    d.atomic(folder / "input/problem.json", {"name": name, "row": row})
    (folder / "selected.lean").write_text(proof)
    d.atomic(root / "authorization.json", {"provider": provider, "dry_run": dry_run,
             "api_endpoint": OPENROUTER_ENDPOINT if provider == "OpenRouter" else "https://api.openai.com/v1/chat/completions"})
    d.atomic(root / "ledger.json", {"attempts": {f"F{row:03}-0001": {"row": row, "step": 1, "status": "settled",
                                                                     "cost_usd": cost, "served_provider": "OpenAI"}}})
    report_bytes = o.json_bytes({"audit_passed": audit, "rows": []})
    (root / "report.json").write_bytes(report_bytes)
    o.atomic_json(root / "published.json", {"row": row, "origin": "openrouter-run", "selected_sha256": o.sha_text(proof),
                                            "report_sha256": o.sha_bytes(report_bytes), "at": o.now_iso()})


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name) / "run"
        self.layout = o.Layout(self.run_dir)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.dataset = stack.enter_context(fake_dataset(temp.name))

    def assemble(self, **kwargs):
        return assembly.assemble(self.run_dir, final=kwargs.pop("final", False), dataset=self.dataset, **kwargs)

    def submission(self):
        return [json.loads(line) for line in (self.run_dir / "submission.jsonl").read_text().splitlines()]

    def test_unready_rows_still_give_sixty_originals_that_pass_both_checks(self):
        result = self.assemble(final=True)
        self.assertEqual((result["rows"], result["improved"], result["checks"]["passed"]), (60, 0, True))
        rows = self.submission()
        self.assertEqual([row["proof"] for row in rows], [row["src"] for row in dataset_rows()])
        benchmark = [json.loads(line) for line in (self.run_dir / "provenance-benchmark.jsonl").read_text().splitlines()]
        self.assertEqual(benchmark[0]["reference"], dataset_rows()[0]["src"])
        self.assertIn("Upload this file once", (self.run_dir / "SUBMIT-READY.txt").read_text())

    def test_published_openrouter_row_is_used_and_bad_rows_fall_back(self):
        publish_row(self.layout, 2, "theorem t2 : True := trivial\n")
        publish_row(self.layout, 3, "theorem t3 : True := by simp\n", dry_run=True)
        publish_row(self.layout, 4, "theorem t4 : True := by exact trivial\n", provider="OpenAI direct")
        publish_row(self.layout, 5, "theorem t5 : True := by decide\n", audit=False)
        publish_row(self.layout, 6, "theorem t6 : True := by\n  sorry\n")
        publish_row(self.layout, 7, "theorem t7 : True := by\n  exact True.intro\n")
        publish_row(self.layout, 8, "theorem t8 : True := by\n  constructor\n", cost="3.10")
        o.atomic_bytes(self.layout.non_openrouter, (json.dumps({"name": "x", "source": "codex",
                       "proof": "theorem t7 : True := by\n  exact True.intro\n"}) + "\n").encode())
        result = self.assemble()
        proofs = {row["name"]: row["proof"] for row in self.submission()}
        self.assertEqual(proofs["Final.t2"], "theorem t2 : True := trivial\n")
        for row in (3, 4, 5, 6, 7, 8):
            self.assertEqual(proofs[f"Final.t{row}"], dataset_rows()[row - 1]["src"], row)
        self.assertEqual(result["improved"], 1)
        self.assertTrue(result["checks"]["passed"])
        report_rows = {row["row"]: row for row in o.read_json(self.run_dir / "report.json")["rows"]}
        self.assertIn("checker", report_rows[6]["fallback_reason"])
        self.assertIn("non-OpenRouter", report_rows[7]["fallback_reason"])
        self.assertIn("2.99", report_rows[8]["fallback_reason"])
        self.assertIn("dry-run", report_rows[3]["fallback_reason"])

    def test_changed_selection_after_publication_is_not_submitted(self):
        publish_row(self.layout, 2, "theorem t2 : True := trivial\n")
        (self.layout.row_folder(2) / "selected.lean").write_text("theorem t2 : True := by trivial\n")
        self.assemble()
        self.assertEqual(self.submission()[1]["proof"], dataset_rows()[1]["src"])

    def test_nested_dashboard_proofs_are_flattened(self):
        folder = self.run_dir.parent / "dash"
        nested = {"problems": [{"name": "Final.t9", "proof": "theorem t9 : True := by\n  exact True.intro\n",
                                "alternatives": [{"proof": "theorem t9 : True := by\n  constructor\n"}]}]}
        o.atomic_json(folder / "final-results.json", nested)
        (folder / "run/steps/0001").mkdir(parents=True)
        (folder / "run/steps/0001/candidate.lean").write_text("theorem t9 : True := by\n  simp\n")
        (folder / "run/steps/0001/check.lean").write_text("import X\ntheorem t9 : True := by\n  simp\n")
        found = o.collect_non_openrouter([folder])
        self.assertEqual(sorted(row["proof"].split(":=", 1)[1].strip() for row in found),
                         ["by\n  constructor", "by\n  exact True.intro", "by\n  simp"])


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)
        self.layout = o.Layout(self.run_dir)
        o.atomic_json(self.layout.plan, {"rows": [{"row": row, "ready": row in (1, 2, 3), "priority": row}
                                                  for row in range(1, 61)], "ready": [1, 2, 3]})
        self.now = 1_000_000.0
        self.spawned, self.assembled = [], []
        self.opts = o.RunOptions(run_dir=self.run_dir, rows=[1, 2, 3, 4], max_rows=2,
                                 deadline=o.parse_deadline("2026-11-04T20:59:59+09:00"), poll_seconds=0)
        self.opts.deadline = o.datetime.fromtimestamp(self.now + 10 * 3600, tz=o.timezone.utc)
        # Coverage of the planned rows is fixed by the fixture, not by this machine's environments.
        fixed = patch.object(sup, "refresh_coverage", side_effect=lambda layout, opts: o.read_json(layout.plan))
        fixed.start()
        self.addCleanup(fixed.stop)

    def supervisor(self, memory=30.0):
        test = self

        class Child:
            def __init__(self, row):
                self.row, self.code, self.pid = row, None, 1000 + row

            def poll(self):
                return self.code

        def popen(command, **kwargs):
            row = int(command[command.index("--row") + 1])
            child = Child(row)
            test.spawned.append(child)
            return child

        return sup.Supervisor(self.run_dir, self.opts, clock=lambda: self.now, sleep=lambda s: None, popen=popen,
                              memory=lambda: memory,
                              assembler=lambda run_dir, final, dataset=None: self.assembled.append(final) or {"improved": 0})

    def test_spawns_by_priority_up_to_max_rows_and_never_duplicates_a_live_row(self):
        held = self.layout.row_root(3) / "worker.lock"
        held.parent.mkdir(parents=True)
        with held.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)           # an adopted live worker for F003
            supervisor = self.supervisor()
            supervisor.tick()
            # The adopted F003 counts toward --max-rows 2, so only F002 (next priority) starts.
            self.assertEqual([child.row for child in self.spawned], [2])
            self.opts.max_rows = 3
            supervisor.tick()
            self.assertEqual([child.row for child in self.spawned], [2, 1])
            supervisor.tick()
            self.assertEqual(len(self.spawned), 2)
            self.assertNotIn(3, [child.row for child in self.spawned])
            self.assertNotIn(4, [child.row for child in self.spawned])   # environments not ready

    def test_memory_gate_blocks_new_workers(self):
        self.supervisor(memory=4.0).tick()
        self.assertEqual(self.spawned, [])

    def test_crash_backoff_retryable_exit_and_fallback_after_eight_crashes(self):
        self.opts.max_rows = 4
        supervisor = self.supervisor()
        supervisor.tick()
        first = next(child for child in self.spawned if child.row == 2)
        o.save_rowstate(self.layout, RowState(row=2, status="exploring"))
        first.code = 1
        supervisor.tick()
        control = o.read_json(self.layout.control_path(2))
        self.assertEqual(control["crashes"], {"exploring": 1})
        self.assertEqual(control["next_start_at"], self.now + 60)
        self.assertEqual(sum(child.row == 2 for child in self.spawned), 1)    # backing off
        self.now += 61
        supervisor.tick()
        second = [child for child in self.spawned if child.row == 2][-1]
        second.code = rw.EXIT_RETRYABLE
        supervisor.tick()
        self.assertEqual(o.read_json(self.layout.control_path(2))["crashes"], {"exploring": 1})
        control = o.read_json(self.layout.control_path(2))
        control["crashes"] = {"exploring": 7}
        o.atomic_json(self.layout.control_path(2), control)
        self.now += 61
        supervisor.tick()
        [child for child in self.spawned if child.row == 2][-1].code = 1
        supervisor.tick()
        self.assertEqual(o.load_rowstate(self.layout, 2).status, "fallback")
        self.assertEqual(o.read_json(self.layout.row_root(2) / "published.json")["origin"], "original")

    def test_deadline_soft_stop_and_final_assemblies(self):
        supervisor = self.supervisor()
        self.now = self.opts.deadline_epoch() - 99 * 60
        supervisor.tick()
        self.assertTrue((self.run_dir / "stop-exploration.json").exists())
        self.now = self.opts.deadline_epoch() - 50 * 60
        supervisor.tick()
        self.assertIn(True, self.assembled)
        self.now = self.opts.deadline_epoch() - 19 * 60
        before = len(self.spawned)
        supervisor.tick()
        self.assertTrue(supervisor.closed)
        self.assertEqual(len(self.spawned), before)
        self.now = self.opts.deadline_epoch() + 1
        self.assertTrue(supervisor.tick())

    def test_second_supervisor_exits_busy(self):
        self.layout.supervisor.mkdir(parents=True, exist_ok=True)
        with (self.layout.supervisor / "supervisor.lock").open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            self.assertEqual(self.supervisor().run(), sup.EXIT_BUSY)


class RowWorkerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)
        self.layout = o.Layout(self.run_dir)
        self.opts = o.RunOptions(run_dir=self.run_dir, dry_run=True)
        self.calls = []

    def fake_driver(self):
        test, layout = self, self.layout

        class Driver:
            def locked(self, path, blocking=True):
                return contextlib.nullcontext()

            def transport_for(self, config):
                return types.SimpleNamespace(load_key=lambda path: "unused")

            def verify_frozen(self, root):
                test.calls.append("verify_frozen")

            def prepare_inputs(self, root, rows, **kwargs):
                test.calls.append(("prepare_inputs", kwargs))
                settings = o.read_json(layout.row_folder(1) / "input/final60.json")
                test.assertEqual(settings["effective_cap_usd"], "2.99")
                test.assertTrue(settings["dry_run"])

            def seal_inputs(self, root, rows):
                test.calls.append("seal_inputs")
                o.atomic_json(Path(root) / "frozen.json", {})

            def preflight(self, root, rows):
                test.calls.append("preflight")
                o.atomic_json(layout.row_folder(1) / "preflight.json", {"status": "ready"})

            def run_problem(self, root, row):
                test.calls.append("run_problem")
                (layout.row_folder(1) / "selected.lean").write_text("theorem t1 : True := trivial\n")
                o.atomic_json(layout.row_folder(1) / "summary.json", {"status": "completed"})

        class Report:
            def build_report(self, root):
                return {"audit_passed": True, "audit_errors": [], "rows": [{
                    "row": 1, "final": {"tokens": 1}, "local_score_estimate": 70.0, "known_cost_usd": "1.2",
                    "calls": 30, "status": "completed"}]}

        return Driver(), Report()

    def test_row_worker_prepares_explores_and_publishes(self):
        problem = {"row": 1, "name": "Final.t1", "source": "synthetic", "statement": "theorem t1 : True",
                   "reference": "theorem t1 : True := by\n  trivial\n", "environments": ["e"]}
        o.atomic_json(self.layout.row_folder(1) / "input/problem.json", problem)
        with patch.dict(os.environ), patch.object(rw, "driver_modules", return_value=self.fake_driver()), \
                patch.object(rw, "coverage", return_value={1: {"missing": []}}), \
                patch.object(rw, "load_dataset", return_value=[]), \
                patch.object(rw, "problem_packet", return_value=problem), \
                patch.dict(sys.modules, {"lean_agent.final60.golf": None}):
            state = rw.run_row(self.run_dir, 1, self.opts)
        self.assertEqual(state.status, "published")
        self.assertEqual(state.score_estimate, 70.0)
        names = [call if isinstance(call, str) else call[0] for call in self.calls]
        self.assertEqual(names, ["prepare_inputs", "seal_inputs", "preflight", "run_problem"])
        self.assertEqual(self.calls[0][1], {"workers": 1, "cold_start": True, "prompt_variant": "baseline", "strict_cap": True})
        published = o.read_json(self.layout.row_root(1) / "published.json")
        self.assertEqual(published["origin"], "openrouter-run")
        self.assertEqual(published["report_sha256"], o.sha_bytes((self.layout.row_root(1) / "report.json").read_bytes()))
        route = o.read_json(self.layout.row_folder(1) / "input/route.json")
        settings = o.read_json(self.layout.row_folder(1) / "input/final60.json")
        self.assertEqual(settings["route_sha256"], o.sha_bytes((self.layout.row_folder(1) / "input/route.json").read_bytes()))
        self.assertEqual(route["row"], 1)
        self.assertIn("unavailable", o.read_json(self.layout.worker_path(1))["golf"])

    def test_second_worker_for_a_live_row_refuses(self):
        path = self.layout.row_root(5) / "worker.lock"
        path.parent.mkdir(parents=True)
        with path.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            with self.assertRaises(rw.WorkerBusy):
                rw.run_row(self.run_dir, 5, self.opts)

    def test_resource_timeouts_are_retryable(self):
        try:
            raise RuntimeError("Timed out waiting for safe compiler capacity")
        except RuntimeError as exc:
            self.assertTrue(rw.resource_error(exc))
        self.assertFalse(rw.resource_error(ValueError("No all-version compatible final candidate")))

    def test_exploration_clock_already_spent_sets_row_stop_flag(self):
        worker = rw.RowWorker.__new__(rw.RowWorker)
        worker.layout, worker.row, worker.opts = self.layout, 1, self.opts
        worker.root, worker.folder = self.layout.row_root(1), self.layout.row_folder(1)
        worker.state = RowState(row=1, status="preflighted")
        worker.driver = types.SimpleNamespace(run_problem=lambda root, row: None)
        worker.update_worker(exploration_started_at=0)
        worker.explore({})
        self.assertEqual(o.read_json(self.layout.row_root(1) / "stop-exploration.json")["reason"], "row exploration clock")
        worker.explore({"exploring": 3})
        self.assertTrue((self.layout.row_root(1) / "salvage.json").exists())


class CliTests(unittest.TestCase):
    def test_rows_deadline_and_fallback_route(self):
        self.assertEqual(o.parse_rows("11-13,41"), [11, 12, 13, 41])
        with self.assertRaises(ValueError):
            o.parse_rows("0-3")
        with self.assertRaises(ValueError):
            o.parse_deadline("2026-11-04T20:59:59")
        route = o.fallback_route({"row": 7, "name": "x", "source": "s", "reference": "abc"})
        self.assertIsInstance(route, Route)
        h.portfolio.validate(route.portfolio)
        self.assertTrue(route.portfolio["merger_until_budget"])

    def test_vendored_checkers_are_byte_identical_to_their_sources(self):
        record = o.read_json(ROOT / "src/lean_agent/final60/checks/SOURCES.json")
        for name, item in record["files"].items():
            vendored = (ROOT / "src/lean_agent/final60/checks" / name).read_bytes()
            self.assertEqual(o.sha_bytes(vendored), item["sha256"], name)
            if (ROOT / item["source"]).exists():
                self.assertEqual((ROOT / item["source"]).read_bytes(), vendored, name)


if __name__ == "__main__":
    unittest.main()
