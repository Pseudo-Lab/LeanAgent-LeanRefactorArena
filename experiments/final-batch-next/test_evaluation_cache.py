"""Cache and evaluator integration without Lean, network, or live run writes."""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from evaluator import FinalEvaluator, digest
from evaluation_cache import EvaluationCache, cacheable


class FixtureEvaluator(FinalEvaluator):
    def __init__(self, cache_root):
        self.cache = EvaluationCache(cache_root)
        self.calls = []
        self._prepared = {name: Mock() for name in ("v1", "v2")}
        self.context_revision = "original-context"
        self.failure = None

    def load_problem(self, problem):
        return problem

    def _compiler_lock(self):
        return nullcontext()

    def _state(self, environment_id):
        return {"id": environment_id}

    def _context(self, problem, environment_id):
        return {"prefix": "", "suffix": "\n", "module": None}

    def _cache_identity(self, code, problem, state, context, repetitions, trusted_reference):
        return {"candidate_sha256": digest(code), "problem": problem, "environment": state,
                "context": self.context_revision, "repetitions": repetitions,
                "trusted_reference": trusted_reference}

    def _invoke(self, source, state, context, folder, label):
        self.calls.append((state["id"], label))
        source_path = folder / (label + ".lean")
        source_path.write_text(source)
        rc, timed_out, text = 0, False, ""
        if self.failure:
            rc, timed_out, text = self.failure
        elif "exact missing" in source:
            rc, text = 1, "error: unknown identifier missing"
        else:
            match = re.search(r'#refactor_eval "([^"]+)" "([^"]+)"', source)
            if match:
                text = "REFACTOR_EVAL " + match[1] + " " + json.dumps(
                    {"target": match[2], "raw": 1000, "scaled": 1, "axioms": []})
        log = folder / (label + ".log")
        log.write_text(text)
        return {"source": source_path.name, "source_sha256": digest(source),
                "log": log.name, "log_sha256": digest(text), "seconds": 9,
                "returncode": rc, "timed_out": timed_out}, text


class CacheIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ev = FixtureEvaluator(self.root / "cache")
        self.code = "theorem test : True := by trivial\n"
        self.problem = {"id": "test", "statement": "theorem test : True", "name": "test",
                        "reference": self.code, "environments": ["v1", "v2"]}

    def evaluate(self, name, **kwargs):
        return self.ev.evaluate(self.code, self.problem, self.root / name, **kwargs)

    def test_repeated_candidate_reuses_evidence_and_survives_process_restart(self):
        self.assertTrue(self.evaluate("first")["valid"])
        self.assertEqual(len(self.ev.calls), 2)
        self.ev = FixtureEvaluator(self.root / "cache")
        cached = self.evaluate("restart")
        self.assertTrue(cached["valid"])
        self.assertEqual(self.ev.calls, [])
        self.ev._prepared["v1"].verify.assert_called_once_with(full=False)
        row = cached["environments"]["v1"]
        self.assertEqual(row["cache"]["compiler_invocations"], 0)
        for run in row["runs"]:
            for field in ("source", "log"):
                path = self.root / "restart/v1" / run[field]
                self.assertEqual(digest(path.read_text()), run[field + "_sha256"])

    def test_all_versions_reuses_primary_and_executes_only_missing_version(self):
        self.evaluate("primary")
        result = self.evaluate("compatibility", all_versions=True)
        self.assertTrue(result["valid"])
        self.assertEqual(self.ev.calls, [("v1", "check"), ("v1", "measure-1"),
                                        ("v2", "check"), ("v2", "measure-1")])
        self.assertTrue(result["environments"]["v1"]["cache"]["hit"])
        self.assertNotIn("cache", result["environments"]["v2"])

    def test_warm_cache_hit_does_not_acquire_compiler_lock(self):
        self.evaluate("first")
        self.ev._states = {"v1": {"id": "v1"}}
        self.ev._contexts = {(None, "v1"): {"prefix": "", "suffix": "\n", "module": None}}
        self.ev.calls.clear()
        with patch.object(self.ev, "_compiler_lock", side_effect=AssertionError("compiler busy")):
            result = self.evaluate("busy-compiler")
        self.assertTrue(result["valid"])
        self.assertEqual(result["timing"]["compiler_lock_wait_seconds"], 0)
        self.assertEqual(result["timing"]["new_compiler_invocations"], 0)
        self.assertEqual(self.ev.calls, [])

    def test_warm_cache_hit_still_rejects_changed_environment(self):
        self.evaluate("first")
        self.ev._states = {"v1": {"id": "v1"}}
        self.ev._contexts = {(None, "v1"): {"prefix": "", "suffix": "\n", "module": None}}
        self.ev._prepared["v1"].verify.side_effect = ValueError("library changed")
        with patch.object(self.ev, "_compiler_lock", side_effect=AssertionError("compiler busy")):
            result = self.evaluate("changed-library")
        self.assertFalse(result["valid"])
        self.assertEqual(result["environments"]["v1"]["error"]["kind"], "environment")

    def test_host_sandbox_failure_is_environment_stop_and_not_cached(self):
        self.ev.failure = (71, False, "sandbox-exec: sandbox_apply: Operation not permitted")
        for name in ("denied-one", "denied-two"):
            result = self.evaluate(name)
            self.assertFalse(result["valid"])
            self.assertEqual(result["environments"]["v1"]["error"]["kind"], "environment")
        self.assertEqual(len(self.ev.calls), 2)

    def test_fresh_final_measurement_does_not_reuse_or_replace_cached_samples(self):
        self.evaluate("first")
        self.ev.calls.clear()
        result = self.evaluate("final", repetitions=3, fresh=True)
        self.assertEqual(len(self.ev.calls), 4)
        self.assertNotIn("cache", result["environments"]["v1"])
        self.ev.calls.clear()
        self.evaluate("again")
        self.assertEqual(self.ev.calls, [])

    def test_context_candidate_repetitions_and_trust_changes_do_not_hit(self):
        self.evaluate("first")
        self.ev.context_revision = "changed-source"
        self.evaluate("context")
        self.code = "theorem test : True := by exact True.intro\n"
        self.evaluate("candidate")
        self.evaluate("measurements", repetitions=3)
        self.code = self.problem["reference"]
        self.evaluate("trusted", trusted_reference=True)
        self.assertEqual(len(self.ev.calls), 12)

    def test_trusted_reference_cache_cannot_bypass_candidate_gate(self):
        self.code = "theorem test : True := by sorry\n"
        self.problem["reference"] = self.code
        self.assertTrue(self.evaluate("trusted", trusted_reference=True)["valid"])
        self.ev.calls.clear()
        result = self.evaluate("candidate")
        self.assertFalse(result["valid"])
        self.assertEqual(self.ev.calls, [])

    def test_compile_rejection_reuses_but_timeout_and_resource_failure_do_not(self):
        self.code = "theorem test : True := by exact missing\n"
        self.assertFalse(self.evaluate("bad1")["valid"])
        self.assertFalse(self.evaluate("bad2")["valid"])
        self.assertEqual(len(self.ev.calls), 1)
        self.code = self.problem["reference"]
        for i, failure in enumerate(((-9, True, "timeout"), (-9, False, "killed"),
                                     (1, False, "maximum memory consumption reached"))):
            self.ev.failure = failure
            before = len(self.ev.calls)
            self.evaluate(f"resource{i}a")
            self.evaluate(f"resource{i}b")
            self.assertEqual(len(self.ev.calls) - before, 2)

    def test_tampered_cache_fails_closed_without_compilation(self):
        self.evaluate("first")
        path = next((self.root / "cache").glob("*/evidence/check.log"))
        path.write_text("altered")
        self.ev.calls.clear()
        result = self.evaluate("again")
        self.assertFalse(result["valid"])
        self.assertEqual(result["environments"]["v1"]["error"]["kind"], "environment")
        self.assertEqual(self.ev.calls, [])

    def test_cache_publication_failure_cannot_leave_a_successful_result(self):
        with patch.object(self.ev.cache, "publish", side_effect=ValueError("evidence changed")):
            result = self.evaluate("first")
        self.assertFalse(result["valid"])
        self.assertEqual(result["environments"]["v1"]["error"]["kind"], "environment")

    def test_export_audit_checks_reused_result_and_candidate_identity(self):
        self.evaluate("first")
        result = self.evaluate("again")["environments"]["v1"]
        self.ev.cache.audit_reuse(result, problem=self.problem, code=self.code, environment="v1")
        altered = deepcopy(result)
        altered["runs"][1]["measurement"]["raw"] = 0
        with self.assertRaisesRegex(ValueError, "differs from original"):
            self.ev.cache.audit_reuse(altered, problem=self.problem, code=self.code, environment="v1")
        with self.assertRaisesRegex(ValueError, "different candidate"):
            self.ev.cache.audit_reuse(result, problem=self.problem, code=self.code + "\n", environment="v1")

    def test_environment_change_blocks_an_otherwise_valid_cache_hit(self):
        self.evaluate("first")
        self.ev._prepared["v1"].verify.side_effect = ValueError("Prepared library files changed")
        self.ev.calls.clear()
        result = self.evaluate("again")
        self.assertFalse(result["valid"])
        self.assertIn("files changed", result["environments"]["v1"]["error"]["message"])
        self.assertEqual(self.ev.calls, [])

    def test_interrupted_evaluation_reuses_completed_environment_on_restart(self):
        self.evaluate("completed-primary")
        partial = self.root / "interrupted/v2"
        partial.mkdir(parents=True)
        (partial / "check.log").write_text("incomplete")
        # Partial output has no published cache entry, so v2 must run again.
        self.ev = FixtureEvaluator(self.root / "cache")
        result = self.evaluate("restart", all_versions=True)
        self.assertTrue(result["valid"])
        self.assertEqual(self.ev.calls, [("v2", "check"), ("v2", "measure-1")])

    def test_cache_key_changes_with_each_identity_field(self):
        identity = {"source": "a", "context": "b", "compiler": "c", "environment": "v1",
                    "implementation": "d", "repetitions": 1, "trusted_reference": False}
        original = self.ev.cache.key(identity)
        for field in identity:
            changed = deepcopy(identity)
            changed[field] = "changed"
            self.assertNotEqual(self.ev.cache.key(changed), original, field)

    def test_axiom_and_compile_failure_policy_excludes_transient_failures(self):
        row = {"valid": False, "runs": [{"returncode": 1, "timed_out": False}],
               "error": {"kind": "compile", "message": "unknown identifier x"}}
        self.assertTrue(cacheable(row))
        for message in ("unknown module prefix Foo", "out of memory", "maximum heartbeats exceeded",
                        "no such file", "permission denied"):
            changed = deepcopy(row)
            changed["error"]["message"] = message
            self.assertFalse(cacheable(changed))

    def test_real_identity_includes_compiler_setup_source_and_measurement_policy(self):
        ev = FinalEvaluator.__new__(FinalEvaluator)
        ev.repo = self.root / "identity-repo"
        ev.root = ev.repo / "sources/final"
        def put(path, content):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        put(ev.repo / "manifest.json", "{}")
        put(ev.repo / "project/lake-manifest.json", "{}")
        put(ev.repo / "project/Test.lean", "original source")
        put(ev.repo / "project/.lake/build/ir/Test.setup.json", "{}")
        compiler = ev.root / "toolchains/v1/bin/lean"
        put(compiler, "compiler-one")
        for name in ("prepared.py", "evaluator/lean.py"):
            put(ev.repo / "src/lean_agent" / name, "implementation")
        state = {"id": "v1", "version": "v1", "project": "project",
                 "prepared_environment": "manifest.json", "prepared_manifest_sha256": digest("{}"),
                 "manifest_sha256": digest("{}")}
        put(ev.root / "environments/v1/environment.json", json.dumps(state))
        context = {"module": "Test", "location": {"file_path": "Test.lean"},
                   "source_sha256": digest("original source")}
        identity = ev._cache_identity(self.code, self.problem, state, context, 1, False)
        self.assertNotEqual(identity, ev._cache_identity(self.code, self.problem, state, context, 3, False))
        self.assertNotEqual(identity, ev._cache_identity(self.code, self.problem, state, context, 1, True))
        compiler.write_text("compiler-two")
        self.assertNotEqual(identity, ev._cache_identity(self.code, self.problem, state, context, 1, False))
        put(ev.repo / "project/Test.lean", "changed source")
        with self.assertRaisesRegex(ValueError, "source changed"):
            ev._cache_identity(self.code, self.problem, state, context, 1, False)
        context["source_sha256"] = digest("changed source")
        put(ev.repo / "project/.lake/build/ir/Test.setup.json", '{"changed":true}')
        with self.assertRaisesRegex(ValueError, "setup changed"):
            ev._cache_identity(self.code, self.problem, state, context, 1, False)


if __name__ == "__main__":
    unittest.main()
