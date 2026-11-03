"""No-network regression checks for paid-call concurrency and crash recovery."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import weakref
import gc
import unittest
from unittest.mock import patch

from lean_agent import artifacts as a, harness as h, models

spec = importlib.util.spec_from_file_location("final_driver", Path(__file__).with_name("driver.py"))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def raw(action=None):
    return {"id": "test-generation", "model": d.MODEL["id"], "provider": "OpenAI",
            "service_tier": "default",
            "choices": [{"message": {"content": json.dumps(action or {"action": "search", "query": "True"})}}],
            "usage": {"cost": "0.005", "prompt_tokens": 100, "completion_tokens": 480, "total_tokens": 580,
                      "completion_tokens_details": {"reasoning_tokens": 380}}}


def result(tokens=10, heartbeat=100, *, all_versions=False):
    env = {"valid": True, "runs": [{"measurement": {"raw": heartbeat}}]}
    return {"valid": True, "tokens": tokens, "environments": {"primary": env, **({"secondary": env} if all_versions else {})}}


class DriverTests(unittest.TestCase):
    def test_frozen_allocator_abort_rejects_candidate_without_environment_stop(self):
        original = {"valid": False, "environments": {"primary": {
            "valid": False, "error": {"kind": "compile", "message":
                "libc++abi: lean::memory_exception: excessive memory consumption detected at 'interpreter'"},
            "runs": [{"returncode": -6, "command": ["lean", "candidate.lean", "-j1", "-M4096"]}]}}}
        guarded = d.guard_compiler_signal(original)
        self.assertFalse(guarded["valid"])
        self.assertFalse(h.environment_failed(guarded))
        self.assertEqual(guarded["error"]["resource"], "lean_allocator_limit")
        self.assertEqual(original["environments"]["primary"]["error"]["kind"], "compile")
        for field, value in [("returncode", -9), ("command", ["lean", "candidate.lean"])]:
            altered = json.loads(json.dumps(original))
            altered["environments"]["primary"]["runs"][0][field] = value
            self.assertTrue(h.environment_failed(d.guard_compiler_signal(altered)))
        unexplained = json.loads(json.dumps(original))
        unexplained["environments"]["primary"]["error"]["message"] = "unexpected abort"
        self.assertTrue(h.environment_failed(d.guard_compiler_signal(unexplained)))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        d.atomic(self.root / "ledger.json", {"schema_version": 1, "attempts": {}})
        self.body = d.transport.payload([{"role": "system", "content": "test"}, {"role": "user", "content": "test"}],
                                       {**d.MODEL, "max_tokens": 1024})

    def tearDown(self):
        self.temp.cleanup()

    def test_two_live_dispatches_overlap_and_both_settle(self):
        barrier = threading.Barrier(2)
        errors = []
        def query(*args):
            barrier.wait(timeout=3)
            return raw()
        def worker(row):
            try:
                d.dispatch(self.root, row, 1, self.body, d.MODEL, self.root / str(row))
            except Exception as exc:
                errors.append(exc)
        with patch.object(d, "verify_frozen"), patch.object(d.transport, "model_metadata", return_value={}), \
                patch.object(d.transport, "query", side_effect=query):
            threads = [threading.Thread(target=worker, args=(row,)) for row in (1, 2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
        self.assertEqual(errors, [])
        ledger = a.read(self.root / "ledger.json")
        self.assertEqual(len(ledger["attempts"]), 2)
        self.assertTrue(all(item["status"] == "settled" for item in ledger["attempts"].values()))

    def test_unknown_cost_blocks_next_dispatch_without_retry(self):
        with patch.object(d, "verify_frozen"), patch.object(d.transport, "model_metadata", return_value={}), \
                patch.object(d.transport, "query", return_value={"transport_error": "TimeoutError"}) as query:
            with self.assertRaisesRegex(ValueError, "Unknown"):
                d.dispatch(self.root, 1, 1, self.body, d.MODEL, self.root / "first")
            with self.assertRaisesRegex(ValueError, "unresolved"):
                d.dispatch(self.root, 2, 1, self.body, d.MODEL, self.root / "second")
            self.assertEqual(query.call_count, 1)

    def test_lost_pending_dispatch_blocks_batch(self):
        ledger = {"attempts": {"F001-0001": {"status": "pending", "row": 1}}}
        with self.assertRaisesRegex(ValueError, "Lost pending"):
            d.check_dispatchable(self.root, ledger)

    def test_saved_response_recovers_settlement_without_call(self):
        step = self.root / "step"
        d.atomic(step / "provider-response.json", raw())
        d.atomic(step / "response.json", d.transport.normalize(raw()))
        d.atomic(step / "cost-bound.json", {"reserved_usd": "0.10"})
        d.atomic(self.root / "ledger.json", {"attempts": {"F001-0001": {"row": 1, "status": "pending"}}})
        d.recover_pending(self.root, 1, 1, step)
        self.assertEqual(a.read(self.root / "ledger.json")["attempts"]["F001-0001"]["cost_usd"], "0.005")

    def test_recovery_rejects_normalized_content_or_raw_hash_tampering(self):
        step = self.root / "step"
        original = raw()
        normalized = d.transport.normalize(original)
        d.atomic(step / "provider-response.json", original)
        altered = json.loads(a.canonical(normalized))
        altered["choices"][0]["message"]["content"] = '{"action":"finish"}'
        d.atomic(step / "response.json", altered)
        d.atomic(self.root / "ledger.json", {"attempts": {"F001-0001": {"row": 1, "status": "pending"}}})
        with self.assertRaisesRegex(ValueError, "Normalized response differs"):
            d.recover_pending(self.root, 1, 1, step)
        d.atomic(step / "response.json", normalized)
        d.atomic(self.root / "ledger.json", {"attempts": {"F001-0001": {"row": 1, "status": "settled", "cost_usd": "0.005",
                 "response_id": original["id"], "provider_response_sha256": "wrong-hash"}}})
        with self.assertRaisesRegex(ValueError, "ledger hash"):
            d.recover_pending(self.root, 1, 1, step)

    def test_primary_improvement_defers_other_versions_without_claiming_compatibility(self):
        baseline = result()
        problem = {"statement": "theorem test : True", "reference": "theorem test : True := by trivial\n"}
        state = h.initial_state(problem, baseline)
        class IncompatibleEvaluator:
            def evaluate(self, code, problem, path, **kwargs):
                raise AssertionError("Exploration must not invoke other versions")
        measured = d.check_improvement_compatibility(IncompatibleEvaluator(), problem,
                      "theorem test : True := by exact newLemma\n", result(2, 50), state, baseline, self.root / "step")
        self.assertTrue(measured["valid"])
        self.assertIsNone(measured["compatibility_check"]["valid"])
        self.assertEqual(measured["compatibility_check"]["status"], "deferred_until_final_selection")
        self.assertIsNotNone(h.metrics(measured))

    def test_threshold_resume_does_not_repeat_settled_response(self):
        output = d.folder(self.root, 1)
        problem = {"id": "test", "name": "test", "statement": "theorem test : True",
                   "reference": "theorem test : True := by trivial\n"}
        config = {"model": {**d.MODEL, "max_tokens": 128},
                  "limits": {"max_calls": None, "cost_stop_usd": "1.00", "max_proof_characters": 24000,
                             "max_feedback_characters": 7000, "max_request_characters": 190000},
                  "agent": {"mode": "actions-v1", "corpus": "action-corpus.json", "allow_finish": False}}
        d.atomic(output / "input/problem.json", problem)
        d.atomic(output / "input/config.json", config)
        d.atomic(output / "input/action-corpus.json", {"schema_version": 1, "entries": []})
        (output / "input/prompt.txt").write_text("test")
        baseline = result()
        d.atomic(output / "baseline/result.json", baseline)
        state = h.initial_state(problem, baseline, config)
        state["cost_usd"] = "0.999"
        d.atomic(output / "state.json", state)
        d.atomic(output / "preflight.json", {"status": "ready"})
        step = output / "steps/0001"
        d.atomic(step / "request.json", d.make_request(state, problem, config, "test"))
        original = raw(action={"action": "propose", "parent_id": "c000", "strategy": "reuse", "proof": "by trivial"})
        normalized = d.transport.normalize(original)
        d.atomic(step / "provider-response.json", original)
        d.atomic(step / "response.json", normalized)
        d.atomic(step / "cost-bound.json", {"reserved_usd": "0.10"})
        d.atomic(self.root / "ledger.json", {"attempts": {"seed": {"row": 1, "status": "settled", "cost_usd": "0.999"},
                                                              "F001-0001": {"row": 1, "status": "settled", "cost_usd": "0.005",
                                                                  "response_id": original["id"], "provider_response_sha256": normalized["_cost_receipt"]["provider_response_sha256"]}}})
        class FakeEvaluator:
            def evaluate(self, code, problem, path, **kwargs):
                return result(2, 50, all_versions=kwargs.get("all_versions", False))
            def verify_environments(self, problem, *, full):
                if not full:
                    raise AssertionError("Expected full final content verification")
                return {"primary": "verified"}
        with patch.object(d, "verify_frozen"), patch.object(d, "evaluator", return_value=FakeEvaluator()), \
                patch.object(d, "dispatch", side_effect=AssertionError("Duplicate paid call")):
            summary = d.run_problem(self.root, 1)
        self.assertEqual(summary["cost_usd"], "1.004")
        self.assertEqual(summary["calls"], 1)
        self.assertEqual(summary["stop_reason"], "cost_limit")
        self.assertTrue(a.read(output / "final/environment-fingerprints.json")["full_content_verification"])

    def test_large_request_compacts_sources_without_mutating_repair_or_archive(self):
        statement = "theorem test : True"
        problem = {"id": "large", "name": "test", "statement": statement,
                   "reference": statement + " := by\n -- " + "λ" * 27000 + "\n trivial\n"}
        config = {"model": d.MODEL, "limits": {"max_calls": None, "cost_stop_usd": "1.00", "max_proof_characters": 90000,
                   "max_feedback_characters": 7000, "max_request_characters": 190000},
                  "agent": {"mode": "actions-v1", "corpus": "unused", "allow_finish": False}}
        baseline = result()
        state = h.initial_state(problem, baseline, config)
        best = h.candidate(statement + " := by\n -- " + "λ" * 80000 + "\n trivial\n", result(2, 50), h.metrics(baseline))
        state["best"] = best
        state["exploration"]["best_candidate_id"] = "c001"
        state["exploration"]["candidates"]["c001"] = {**best, "valid": True, "parent_id": "c000", "strategy": "branch", "step": 1, "feedback": None}
        failed = statement + " := by\n -- " + "λ" * 80000 + "\n exact missing\n"
        feedback = {"status": "proof_rejected", "valid": False, "details": "unknown constant missing", "issues": []}
        state["exploration"]["candidates"]["c002"] = {"code": failed, "valid": False, "parent_id": "c001", "strategy": "repair", "step": 2, "feedback": feedback}
        state["latest"] = {"code": failed, "feedback": feedback}
        before = a.canonical(state)
        body = d.make_request(state, problem, config, "JSON guidance\n" + "x" * 40000)
        packet = json.loads(body["messages"][1]["content"])
        self.assertEqual(packet["exploration"]["repair_context"]["code"], failed)
        self.assertEqual(packet["best"]["code_ref"]["candidate_id"], "c001")
        self.assertEqual(packet["problem"]["reference_ref"]["candidate_id"], "c000")
        self.assertEqual(a.canonical(state), before)
        self.assertLess(d.transport.request_cost(body)["input_token_bound"], 240000)

    def test_prelaunch_reseal_changes_only_timeout_and_forbids_billed_reseal(self):
        output = d.folder(self.root, 1)
        config_path = output / "input/config.json"
        config = {"model": {**d.MODEL, "timeout_seconds": 300}, "limits": {"cost_stop_usd": "1.00"}}
        d.atomic(config_path, config)
        d.atomic(self.root / "authorization.json", {"rows": [1], "verification_policy": d.VERIFICATION_POLICY})
        implementation = self.root / "implementation.py"
        implementation.write_text("new implementation\n")
        old_code = self.root / "code/implementation.py"
        old_code.parent.mkdir()
        old_code.write_text("old implementation\n")
        d.atomic(self.root / "frozen.json", {str(config_path): a.sha(config_path.read_bytes()), str(implementation): "old-source-sha"})
        with patch.object(d, "implementation_files", return_value=[implementation]), patch.object(d, "REPO", self.root):
            d.reseal(self.root)
            expected = json.loads(a.canonical(config)); expected["model"]["timeout_seconds"] = 900
            self.assertEqual(a.read(config_path), expected)
            self.assertEqual((self.root / "code/implementation.py").read_text(), "new implementation\n")
            self.assertEqual(len(list((self.root / "prelaunch-reseals").glob("*/receipt.json"))), 1)
            d.atomic(self.root / "ledger.json", {"attempts": {"already-dispatched": {"status": "pending"}}})
            with self.assertRaisesRegex(ValueError, "forbidden after any API"):
                d.reseal(self.root)

    def test_ensure_preflight_never_runs_paid_worker_after_failed_check(self):
        with patch.object(d, "preflight", side_effect=ValueError("invalid baseline")) as checked, \
                patch.object(d, "run_problem") as paid:
            with self.assertRaisesRegex(ValueError, "invalid baseline"):
                d.run_with_preflight(self.root, 1, True)
            checked.assert_called_once_with(self.root, [1])
            paid.assert_not_called()

    def test_failed_future_frames_release_evaluator_maps(self):
        references = []
        class LargeEvaluator:
            pass
        def fail():
            evaluator = LargeEvaluator()
            references.append(weakref.ref(evaluator))
            raise ValueError("worker failed")
        with d.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fail)
            try:
                future.result()
            except ValueError as exc:
                self.assertIsNotNone(references[0]())
                self.assertEqual(d.compact_worker_failure(exc), {"error_type": "ValueError", "message": "worker failed"})
        gc.collect()
        self.assertIsNone(references[0]())

    def test_compatibility_diagnosis_uses_failed_version_evidence(self):
        step = self.root / "steps/0001"
        path = step / "compatibility/result.json"
        failed = {"valid": False, "environments": {"older": {"valid": False, "error": {"kind": "compile", "message": "unknown constant foo"}}}}
        d.atomic(path, failed)
        selection = {"valid": False, "compatibility_check": {"valid": False, "path": str(path)}}
        with patch.object(d.diagnostics, "evaluation", return_value={"kind": "proof"}) as diagnosed, \
                patch.object(d.h, "step_diagnosis", side_effect=AssertionError("Primary measurement diagnosis is wrong")):
            self.assertEqual(d.candidate_diagnosis({}, None, selection, step, self.root, {}), {"kind": "proof"})
            diagnosed.assert_called_once_with(failed, path.parent, self.root, "candidate")

    def test_missing_row_inputs_refuse_seal_without_authorization_or_ledger(self):
        with self.assertRaisesRegex(ValueError, "missing complete inputs"):
            d.seal_inputs(self.root, [1])
        self.assertFalse((self.root / "authorization.json").exists())
        self.assertFalse((self.root / "frozen.json").exists())
        # setUp created an empty ledger; sealing must leave it exactly empty.
        self.assertEqual(a.read(self.root / "ledger.json"), {"schema_version": 1, "attempts": {}})

    def test_split_input_and_seal_matches_original_prepare_and_reuses_complete_rows(self):
        class FakeEvaluator:
            def load_problem(self, row):
                return a.read(d.REPO / "sources/final/problems" / f"F{row:03}.json")
            def source_context(self, problem):
                return {"corpus": {"schema_version": 1, "entries": []}, "prompt_context": "original context",
                        "metadata": {"row": problem["row"]}}
        fixture_repo = self.root / "repository"
        (fixture_repo / "examples/actions").mkdir(parents=True)
        (fixture_repo / "examples/actions/prompt.txt").write_text((d.REPO / "examples/actions/prompt.txt").read_text())
        for row in (1, 2):
            d.atomic(fixture_repo / "sources/final/problems" / f"F{row:03}.json", {
                "id": f"F{row:03}", "row": row, "dataset_sha256": d.DATASET_SHA,
                "name": "sample", "statement": "theorem sample : True",
                "reference": "theorem sample : True := by trivial", "environments": ["fixture"]})
        implementation = fixture_repo / "controller.py"
        implementation.write_text("# frozen fixture implementation\n")
        combined, split = self.root / "combined", self.root / "split"
        with patch.object(d, "REPO", fixture_repo), \
             patch.object(d, "implementation_files", return_value=[implementation]), \
             patch.object(d, "evaluator", return_value=FakeEvaluator()):
            d.prepare(combined, [1, 2], workers=2)
            d.prepare_inputs(split, [1, 2], workers=1)
            for name in ("authorization.json", "ledger.json", "frozen.json"):
                self.assertFalse((split / name).exists())
            with patch.object(FakeEvaluator, "source_context", side_effect=AssertionError("Complete input must be reused")):
                d.prepare_inputs(split, [1, 2], workers=1)
            d.seal_inputs(split, [1, 2])
        for row in (1, 2):
            for name in d.INPUT_FILES:
                self.assertEqual((d.folder(combined, row) / "input" / name).read_bytes(),
                                 (d.folder(split, row) / "input" / name).read_bytes())
        first, second = a.read(combined / "authorization.json"), a.read(split / "authorization.json")
        first.pop("created_at"); second.pop("created_at")
        self.assertEqual(first, second)
        d.verify_frozen(combined)
        d.verify_frozen(split)

    def test_legacy_batch_is_rejected_before_locks_or_writes(self):
        d.atomic(self.root / "authorization.json", {"rows": [1]})
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for operation in (lambda: d.run_problem(self.root, 1), lambda: d.prepare_inputs(self.root, [1]),
                          lambda: d.seal_inputs(self.root, [1]), lambda: d.reseal(self.root)):
            with self.assertRaisesRegex(ValueError, "new batch root"):
                operation()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_saved_evaluation_cannot_be_reused_for_different_candidate(self):
        class Fake:
            def evaluate(self, code, problem, path, **kwargs):
                return result()
        destination = self.root / "evaluation"
        d.evaluate_cached(Fake(), "one", {"id": "problem"}, destination, repetitions=1)
        with self.assertRaisesRegex(ValueError, "different candidate"):
            d.evaluate_cached(Fake(), "two", {"id": "problem"}, destination, repetitions=1)

    def test_final_selection_falls_back_and_fresh_measurement_bypasses_cache(self):
        output = d.folder(self.root, 1)
        problem = {"id": "test", "name": "test", "statement": "theorem test : True",
                   "reference": "theorem test : True := by trivial\n", "environments": ["primary", "secondary"]}
        config = {"model": d.MODEL, "limits": {"max_calls": None, "cost_stop_usd": "1.00"},
                  "agent": {"mode": "actions-v1", "allow_finish": False}}
        baseline = result()
        state = h.initial_state(problem, baseline, config)
        better = h.candidate("theorem test : True := by exact newLemma\n", result(2, 50), h.metrics(baseline))
        fallback = h.candidate("theorem test : True := by exact True.intro\n", result(3, 60), h.metrics(baseline))
        state.update(cost_usd="1.00", calls=2, step=2, best=better)
        for cid, candidate in (("c001", better), ("c002", fallback)):
            state["exploration"]["candidates"][cid] = {**candidate, "valid": True}
        for name, value in (("input/problem.json", problem), ("input/config.json", config),
                            ("baseline/result.json", baseline), ("state.json", state),
                            ("preflight.json", {"status": "ready"})):
            d.atomic(output / name, value)
        (output / "input/prompt.txt").write_text("test")
        calls = []
        class Fake:
            def verify_environments(self, problem, *, full):
                return {"primary": "fixed", "secondary": "fixed"}
            def evaluate(self, code, problem, path, **kwargs):
                calls.append((code, kwargs))
                value = result(3, 60, all_versions=kwargs.get("all_versions", False))
                if "newLemma" in code:
                    value["valid"] = False
                    value["environments"]["secondary"].update(valid=False,
                        error={"kind": "compile", "message": "unknown constant newLemma"})
                return value
        with patch.object(d, "verify_frozen"), patch.object(d, "evaluator", return_value=Fake()), \
             patch.object(d, "dispatch", side_effect=AssertionError("No paid request during final selection")):
            summary = d.run_problem(self.root, 1)
        self.assertEqual(summary["selected"]["sha256"], fallback["sha256"])
        self.assertTrue(summary["all_versions_valid"])
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[0][1]["all_versions"])
        self.assertTrue(calls[1][1]["all_versions"])
        self.assertEqual(calls[2][1]["repetitions"], 3)
        self.assertTrue(calls[2][1]["fresh"])


if __name__ == "__main__":
    unittest.main()
