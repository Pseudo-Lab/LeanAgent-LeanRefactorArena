"""Native package integration: simulated compiler receipts, no model API calls."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import artifacts, diagnostics, harness, models, status
from lean_agent.evaluator.lean import LeanEvaluator, render

REPO = Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("PROJECT_CACHE_DIR"))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.compiler = self.root / "compiler/bin/lean"
        self.compiler.parent.mkdir(parents=True)
        self.compiler.write_text("simulated compiler; not executable code")
        self.compiler.chmod(0o700)
        shutil.copytree(REPO / "examples/first-harness", self.root / "example")
        self.config = artifacts.read(REPO / "configs/smoke.json")
        for key, name in {"problem": "problem.json", "template": "context.lean.in", "project": "project", "prompt": "prompt.txt"}.items():
            self.config[key] = str(self.root / "example" / name)
        self.config["model"]["responses"] = str(self.root / "example/responses.json")
        self.config["lean"]["command"][0] = str(self.compiler)
        self.path, self.output = self.root / "config.json", self.root / "run"
        self.invocations = []

    def compiler_execute(self, command, cwd, timeout, **kwargs):
        self.invocations.append(command)
        output, rc = "", 0
        if "--version" in command:
            output = "Lean (version 4.26.0, simulated-test-compiler)\n"
        elif "--print-prefix" in command:
            output = str(self.compiler.parent.parent) + "\n"
        else:
            source = Path(command[-1]).read_text()
            if "MissingModule" in source:
                output, rc = "error: unknown module prefix 'MissingModule'\n", 1
            elif "False.elim" in source:
                output, rc = f"{command[-1]}:4:25: error: tactic 'assumption' failed\n⊢ False\n", 1
            elif '#refactor_eval "' in source:
                nonce, name = re.search(r'#refactor_eval "([^"]+)" "([^"]+)"', source).groups()
                raw = 2000 if "rfl" in source else 6000
                output = "REFACTOR_EVAL " + nonce + " " + json.dumps(
                    {"target": name, "raw": raw, "scaled": raw // 1000, "axioms": []}) + "\n"
        return {"command": command, "returncode": rc, "timed_out": False,
                "seconds": 0.001, "output": output, "stderr": ""}

    def execute(self, **kwargs):
        self.path.write_text(json.dumps(self.config))
        return harness.run(self.path, self.output, evaluator=LeanEvaluator(self.compiler_execute), **kwargs)

    def read(self, path):
        return artifacts.read(self.output / path)

    def first_response(self, value):
        path = Path(self.config["model"]["responses"])
        values = artifacts.read(path)
        values[0] = value
        path.write_text(json.dumps(values))

    def test_preflight_check_only_compiles_context_without_model_or_proof(self):
        with patch.object(models, "query", side_effect=AssertionError("unexpected call")):
            self.assertEqual(self.execute(check_only=True)["status"], "ready")
        report = self.read("preflight.json")
        self.assertEqual(report["compiler_invocations"], 3)
        self.assertEqual(report["context_compilations"], 1)
        source = (self.output / "checks/context/context.lean").read_text()
        self.assertNotIn("theorem", source)
        self.assertNotIn("import Lean", source)
        self.assertIn("example : True := True.intro", source)
        self.assertEqual(status.inspect(self.output)["status"], "ready")
        self.assertIsNone(status.inspect(self.output)["final_result"])
        with self.assertRaisesRegex(ValueError, "no completed execution"):
            harness.replay(self.output)

    def test_preflight_failures_gate_all_model_calls_and_preserve_cause(self):
        for mode, reason in (("missing", "compiler_not_found"), ("pin", "toolchain_mismatch"),
                             ("version", "fingerprint_failed"), ("context", "context_compile_failed")):
            with self.subTest(mode=mode):
                case = RuntimeTests(); case.setUp()
                try:
                    if mode == "missing":
                        case.config["lean"]["command"][0] += "-absent"
                    elif mode == "pin":
                        (case.root / "example/project/lean-toolchain").write_text("leanprover/lean4:v4.25.0")
                    elif mode == "context":
                        path = case.root / "example/context.lean.in"
                        path.write_text("import MissingModule\n" + path.read_text())
                    else:
                        original = case.compiler_execute
                        def wrong(command, *args, **kwargs):
                            row = original(command, *args, **kwargs)
                            if "--version" in command:
                                row["output"] = "Lean (version 4.25.0, simulated)\n"
                            return row
                        case.compiler_execute = wrong
                    with patch.object(models, "query", side_effect=AssertionError("unexpected call")):
                        with self.assertRaises(ValueError):
                            case.execute()
                    self.assertEqual(case.read("result.json")["error"]["reason"], reason)
                    self.assertEqual(case.read("result.json")["model_requests"], 0)
                    self.assertEqual(status.inspect(case.output)["status"], "failed")
                    self.assertEqual(status.inspect(case.output)["usage_cost"]["entries"], 0)
                    self.assertFalse((case.output / "baseline").exists())
                finally:
                    case.doCleanups()

    def test_proof_feedback_preserves_original_and_replays_after_relocation(self):
        self.execute()
        report = self.read("diagnostics/candidate-001.json")
        self.assertEqual(report["kind"], "proof")
        original = self.read("steps/001/evaluation/result.json")
        self.assertEqual(original["environments"]["fixed"]["error"]["kind"], "compile")
        packet = json.loads(self.read("steps/002/request.json")["messages"][1]["content"])
        feedback = packet["latest"]["feedback"]
        self.assertEqual(feedback["diagnosis"]["kind"], "proof")
        self.assertIn("⊢ False", feedback["details"])
        self.assertNotIn(str(self.output), feedback["details"])
        self.assertLessEqual(len(feedback["details"]), self.config["limits"]["max_feedback_characters"])
        for ref in report["evidence"]:
            self.assertEqual(artifacts.sha((self.output / ref["path"]).read_bytes()), ref["sha256"])
        moved = self.root / "moved"
        shutil.move(self.output, moved)
        with patch.object(models, "query", side_effect=AssertionError("unexpected call")), patch.object(LeanEvaluator, "execute", side_effect=AssertionError("unexpected compiler")):
            self.assertTrue(harness.replay(moved)["record_replay_passed"])
            self.assertEqual(status.inspect(moved)["status"], "completed")

    def test_invalid_unicode_and_deep_json_are_lossless_response_failures(self):
        for index, value in enumerate(('{"proof":"by exact \\ud800"}', '{"proof":"by exact \ud800"}', "[" * 129 + "0" + "]" * 129)):
            with self.subTest(index=index):
                self.output = self.root / f"run-{index}"
                self.first_response(value)
                self.execute()
                self.assertEqual(self.read("steps/001/response.json")["choices"][0]["message"]["content"], value)
                self.assertEqual(self.read("diagnostics/model-001.json")["kind"], "response")
                self.assertFalse((self.output / "steps/001/candidate.lean").exists())
                self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_unknown_api_outcomes_never_retry(self):
        for index, (raw, kind) in enumerate((({"transport_error": "TimeoutError", "http_status": None}, "api"),
                                            ({"transport_error": "HTTPError", "http_status": 429}, "api"),
                                            ({"transport_error": "JSONDecodeError", "http_status": None}, "response"))):
            with self.subTest(raw=raw):
                self.output = self.root / f"run-{index}"
                with patch.object(models, "query", return_value=raw) as query:
                    result = self.execute()
                self.assertEqual(query.call_count, 1)
                self.assertEqual(result["status"], "stopped")
                self.assertEqual(result["stop_reason"], "unknown_cost")
                report = self.read("diagnostics/model-001.json")
                self.assertEqual(report["kind"], kind)
                self.assertFalse(report["automatic_retry"])
                self.assertEqual(report["billing"], "unknown")
                self.assertIsNone(status.inspect(self.output)["final_result"])
                self.assertTrue(harness.replay(self.output)["record_replay_passed"])

    def test_measurement_failures_remain_distinct_from_proof_errors(self):
        self.first_response('{"proof":"by rfl"}')
        original = self.compiler_execute
        for mode in ("missing", "schema", "type", "wrapper"):
            with self.subTest(mode=mode):
                self.output = self.root / mode
                def broken(command, *args, **kwargs):
                    row = original(command, *args, **kwargs)
                    if "steps/001/evaluation" in command[-1] and "measure-" in command[-1]:
                        if mode == "missing":
                            row["output"] = "no report\n"
                        elif mode == "wrapper":
                            row.update(returncode=1, output="error: wrapper failed\n")
                        else:
                            row["output"] = row["output"].replace('"axioms": []', '"other": []' if mode == "schema" else '"axioms": null')
                    return row
                self.compiler_execute = broken
                self.execute()
                self.assertEqual(self.read("diagnostics/candidate-001.json")["kind"], "measurement")
                self.assertTrue(harness.replay(self.output)["record_replay_passed"])
                if mode != "wrapper":
                    self.assertEqual(self.read("result.json")["model_requests"], 1)
                    self.assertEqual(self.read("summary.json")["stop_reason"], "environment_failed")

    def test_timeout_signal_and_missing_import_classification(self):
        self.first_response('{"proof":"by rfl"}')
        original = self.compiler_execute
        for mode, kind in (("timeout", "timeout"), ("signal", "unknown"), ("import", "environment")):
            with self.subTest(mode=mode):
                self.output = self.root / mode
                def broken(command, *args, **kwargs):
                    row = original(command, *args, **kwargs)
                    if "steps/001/evaluation" in command[-1]:
                        row.update(returncode=-9 if mode != "import" else 1,
                                   timed_out=mode == "timeout", output="error: unknown module prefix 'MissingModule'" if mode == "import" else "")
                    return row
                self.compiler_execute = broken
                self.execute()
                self.assertEqual(self.read("diagnostics/candidate-001.json")["kind"], kind)

    def test_interrupt_and_unexpected_exception_seal_actual_stage(self):
        for index, exc in enumerate((KeyboardInterrupt(), SystemExit(7), RuntimeError("injected"))):
            with self.subTest(exc=type(exc).__name__):
                self.output = self.root / f"run-{index}"
                with self.assertRaises(type(exc)):
                    self.execute(query=lambda *a: (_ for _ in ()).throw(exc))
                result = self.read("result.json")
                self.assertEqual(result["stage"], "model")
                self.assertEqual(result["model_requests"], 1)
                self.assertEqual(result["status"], "failed" if isinstance(exc, RuntimeError) else "interrupted")
                self.assertEqual(status.inspect(self.output)["status"], result["status"])
                self.assertTrue((self.output / "steps/001/request.json").exists())
                self.assertFalse((self.output / "steps/001/response.json").exists())
                with self.assertRaisesRegex(ValueError, "Incomplete run"):
                    harness.replay(self.output)

    def test_live_status_is_read_only_and_does_not_infer_liveness(self):
        def observed(*args):
            before = artifacts.inventory(self.output)
            view = status.inspect(self.output)
            self.assertEqual(view["status"], "incomplete")
            self.assertEqual(view["incomplete_stages"][0]["stage"], "model")
            self.assertEqual(view["process_state"], "unknown")
            self.assertIsNone(view["final_result"])
            self.assertEqual(before, artifacts.inventory(self.output))
            return models.query(*args)
        self.execute(query=observed)
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "completed")
        self.assertEqual(view["latest_verified_candidate"]["stage"], "candidate")
        self.assertEqual(view["final_result"]["stage"], "final")

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "requires POSIX")
    def test_real_child_killed_during_second_candidate_retains_first(self):
        code = '''
import os, signal
from test_runtime_integration import RuntimeTests
case = RuntimeTests(); case.setUp()
case.first_response('{"proof":"by rfl"}')
print(case.output, flush=True)
original = case.compiler_execute
def kill(command, *args, **kwargs):
    if "steps/002/evaluation" in command[-1]:
        os.kill(os.getpid(), signal.SIGKILL)
    return original(command, *args, **kwargs)
case.compiler_execute = kill
case.execute()
'''
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(REPO / "src"), str(REPO / "tests"))))
        child = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr)
        output = Path(child.stdout.strip())
        self.addCleanup(shutil.rmtree, output.parent)
        view = status.inspect(output)
        self.assertEqual(view["status"], "incomplete")
        self.assertEqual(view["incomplete_stages"][0]["stage"], "candidate")
        self.assertEqual(view["incomplete_stages"][0]["details"]["attempt"], 2)
        self.assertEqual(view["usage_cost"]["entries"], 2)
        self.assertEqual(view["usage_cost"]["reported_cost_usd"], "0")
        self.assertEqual(view["latest_verified_candidate"]["source"], "steps/001/candidate.lean")
        self.assertIsNone(view["final_result"])

    def test_status_rejects_modified_evidence_and_partial_tail(self):
        self.execute()
        journal = self.output / "events.jsonl"
        data = journal.read_bytes()
        journal.write_bytes(data + b'{"unfinished":')
        view = status.inspect(self.output)
        self.assertTrue(view["partial_trailing_record"])
        self.assertIsNone(view["final_result"])
        journal.write_bytes(data)
        (self.output / "selected.lean").write_text("tampered")
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "unknown")
        self.assertIsNone(view["final_result"])

    def test_resealed_lifecycle_or_journal_inconsistency_is_rejected(self):
        self.execute()
        path = self.output / "result.json"
        original = path.read_bytes()
        value = self.read("result.json")
        value["status"] = "stopped"
        path.write_text(json.dumps(value))
        (self.output / "artifacts.json").unlink()
        harness.seal(self.output)
        with self.assertRaisesRegex(ValueError, "Lifecycle result"):
            harness.replay(self.output)
        path.write_bytes(original)
        journal = self.output / "events.jsonl"
        rows = journal.read_text().splitlines()
        value = json.loads(rows[0]); value["sequence"] = 99
        rows[0] = json.dumps(value)
        journal.write_text("\n".join(rows) + "\n")
        (self.output / "artifacts.json").unlink()
        harness.seal(self.output)
        with self.assertRaisesRegex(ValueError, "Stage journal"):
            harness.replay(self.output)

    def test_final_failure_never_exposes_completed_result(self):
        original = self.compiler_execute
        def failed(command, *args, **kwargs):
            row = original(command, *args, **kwargs)
            if "/final/" in command[-1]:
                row.update(returncode=1, output="error: final failed")
            return row
        self.compiler_execute = failed
        self.execute()
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "stopped")
        self.assertEqual(view["final_verification"]["status"], "failed")
        self.assertIsNotNone(view["latest_verified_candidate"])
        self.assertIsNone(view["final_result"])


class ContextRenderingTests(unittest.TestCase):
    code = "theorem checked : True := by trivial\n"

    def template(self, prefix):
        return "import Lean\n{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n" + prefix + "{{DECLARATION}}\n"

    def test_target_documentation_stays_attached_inside_measurement(self):
        prefix = "/-- Target documentation /- nested comment -/ and more. -/\n"
        template = self.template(prefix)
        measured = render(template, self.code, "checked", "nonce")
        self.assertEqual(measured.count(prefix), 1)
        self.assertLess(measured.index('#refactor_eval "nonce"'), measured.index(prefix))
        self.assertIn(prefix + self.code, measured)
        self.assertEqual(render(template, self.code, "checked", None),
                         "import Lean\n\n\n" + prefix + self.code + "\n")

    def test_scoped_prefixes_stay_in_order_inside_measured_command(self):
        prefix = "set_option maxHeartbeats 0 in\nomit x in\nopen Nat in\n/-- Target doc. -/\n"
        measured = render(self.template("variable (x : Nat)\n" + prefix), self.code, "checked", "nonce")
        self.assertLess(measured.index("variable (x : Nat)"), measured.index('#refactor_eval "nonce"'))
        self.assertIn(prefix + self.code, measured)
        self.assertLess(measured.index('#refactor_eval "nonce"'), measured.index(prefix))

    def test_previous_declarations_and_unscoped_open_are_not_moved(self):
        context = "/-- Earlier doc. -/\ntheorem earlier : True := by trivial\nopen Nat\n"
        measured = render(self.template(context + "/-- Target doc. -/\n"), self.code, "checked", "nonce")
        self.assertLess(measured.index(context), measured.index('#refactor_eval "nonce"'))
        self.assertLess(measured.index('#refactor_eval "nonce"'), measured.index('/-- Target doc. -/'))


if __name__ == "__main__":
    unittest.main()
