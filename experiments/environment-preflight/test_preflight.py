"""Feature-1 unit and gate tests; compiler outputs are explicitly simulated."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import baseline
import preflight
import run


class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness, cls.evaluator, cls.main_root = baseline.load()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ["PROJECT_CACHE_DIR"])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.compiler = self.root / "compiler/bin/lean"
        self.compiler.parent.mkdir(parents=True)
        self.compiler.write_text("fake compiler bytes; never executed")
        self.compiler.chmod(0o700)
        self.input = self.root / "inputs"
        shutil.copytree(baseline.HERE / "baseline/main", self.input)
        self.path = self.input / "configs/smoke.json"
        self.config = json.loads(self.path.read_bytes())
        self.config["lean"]["command"][0] = str(self.compiler)
        self.path.write_text(json.dumps(self.config))
        self.project = self.input / "examples/first-harness/project"
        self.template = self.input / "examples/first-harness/context.lean.in"
        self.output = self.root / "result"
        self.invocations = []

    def compiler_execute(self, command, cwd, timeout, **kwargs):
        self.invocations.append(command)
        output, rc = "", 0
        if "--version" in command:
            output = "Lean (version 4.26.0, simulated-test-compiler)\n"
        elif "--print-prefix" in command:
            output = str(self.compiler.parent.parent) + "\n"
        elif "MissingModule" in Path(command[-1]).read_text():
            output, rc = "error: unknown module prefix 'MissingModule'\n", 1
        return {"command": command, "returncode": rc, "timed_out": False,
                "seconds": 0.001, "output": output, "stderr": ""}

    def execute(self, *, continue_run=True):
        with patch.object(self.evaluator, "execute", side_effect=self.compiler_execute):
            return run.execute(self.path, self.output, continue_run=continue_run)

    def assert_failure_without_model(self, stage):
        with patch.object(self.harness.models, "query", side_effect=AssertionError("Model must not be called")):
            result = self.execute()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], stage)
        self.assertEqual(result["model_requests"], 0)
        self.assertEqual(result["api_calls"], 0)
        self.assertFalse((self.output / "harness").exists())
        self.assertTrue((self.output / "artifacts.json").exists())
        return result

    def test_normal_check_compiles_no_candidate_and_injects_no_import(self):
        result = self.execute(continue_run=False)
        self.assertEqual(result["status"], "ready")
        source = (self.output / "checks/context/context.lean").read_text()
        self.assertNotIn("import Lean", source)
        self.assertNotIn("theorem", source)
        self.assertNotIn("refactor_eval", source)
        report = json.loads((self.output / "preflight.json").read_bytes())
        self.assertEqual(report["compiler_invocations"], 3)
        self.assertEqual(report["context_compilations"], 1)
        for command in report["commands"]:
            self.assertEqual(baseline.sha((self.output / command["log"]).read_bytes()), command["log_sha256"])

    def test_missing_compiler_never_calls_model(self):
        self.config["lean"]["command"] = [str(self.root / "absent/bin/lean")]
        self.path.write_text(json.dumps(self.config))
        result = self.assert_failure_without_model("environment")
        self.assertEqual(result["error"]["reason"], "compiler_not_found")
        self.assertEqual(self.invocations, [])

    def test_pin_mismatch_stops_before_executing_compiler(self):
        (self.project / "lean-toolchain").write_text("leanprover/lean4:v4.25.0\n")
        result = self.assert_failure_without_model("environment")
        self.assertEqual(result["error"]["reason"], "toolchain_mismatch")
        self.assertEqual(self.invocations, [])

    def test_missing_pin_file_is_recorded(self):
        (self.project / "lean-toolchain").unlink()
        result = self.assert_failure_without_model("environment")
        self.assertEqual(result["error"]["reason"], "missing_toolchain_file")

    def test_actual_compiler_version_mismatch_preserves_log(self):
        original = self.compiler_execute
        def wrong_version(*args, **kwargs):
            result = original(*args, **kwargs)
            result["output"] = result["output"].replace("4.26.0", "4.25.0")
            return result
        self.compiler_execute = wrong_version
        self.assert_failure_without_model("environment")
        self.assertIn("4.25.0", (self.output / "checks/environment/01.log").read_text())

    def test_missing_import_is_context_failure_not_proof_failure(self):
        self.template.write_text("import MissingModule\n" + self.template.read_text())
        result = self.assert_failure_without_model("context")
        self.assertEqual(result["error"]["reason"], "context_compile_failed")
        self.assertEqual(result["error"]["kind"], "unknown")
        self.assertIn("MissingModule", (self.output / "checks/context/03.log").read_text())

    def test_malformed_template_stops_during_config(self):
        self.template.write_text("{{DECLARATION}}\n")
        self.assert_failure_without_model("config")
        self.assertEqual(self.invocations, [])

    def test_missing_config_gets_persistent_diagnostic(self):
        self.path.unlink()
        result = self.assert_failure_without_model("config")
        self.assertTrue((self.output / result["diagnostic_log"]).exists())

    def test_external_dependencies_are_not_silently_supported(self):
        (self.project / "lake-manifest.json").write_text('{"packages":[{"name":"Mathlib"}]}')
        result = self.assert_failure_without_model("config")
        self.assertIn("dependency-free", result["error"]["message"])

    def test_subprocess_start_exception_is_logged(self):
        def fail(*args, **kwargs):
            raise PermissionError("simulated executable access denied")
        self.compiler_execute = fail
        result = self.assert_failure_without_model("environment")
        self.assertEqual(result["error"]["reason"], "process_start_failed")
        self.assertIn("PermissionError", (self.output / "checks/environment/01.log").read_text())

    def test_local_timeout_is_not_reported_as_proof_error(self):
        original = self.compiler_execute
        def slow(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[0][-1].endswith("context.lean"):
                result.update(timed_out=True, returncode=-9, output="partial context output")
            return result
        self.compiler_execute = slow
        result = self.assert_failure_without_model("context")
        self.assertEqual(result["error"]["kind"], "timeout")
        self.assertIn("partial", (self.output / "checks/context/03.log").read_text())

    def test_fingerprint_execute_hook_is_restored_on_failure(self):
        self.template.write_text("import MissingModule\n" + self.template.read_text())
        original = self.evaluator.execute
        self.assert_failure_without_model("context")
        self.assertIs(self.evaluator.execute, original)

    def test_uninstalled_elan_toolchain_does_not_invoke_shim(self):
        home = self.root / "elan"
        shim = home / "bin/lean"
        shim.parent.mkdir(parents=True)
        shim.write_text("do not execute this installer")
        shim.chmod(0o700)
        self.config["lean"]["command"][0] = str(shim)
        self.path.write_text(json.dumps(self.config))
        with patch.dict(os.environ, {"ELAN_HOME": str(home)}):
            result = self.assert_failure_without_model("environment")
        self.assertEqual(result["error"]["reason"], "toolchain_not_installed")
        self.assertEqual(self.invocations, [])

    def test_installed_elan_shim_resolves_to_prepared_binary(self):
        home = self.root / "elan"
        shim = home / "bin/lean"
        compiler = home / "toolchains/leanprover--lean4---v4.26.0/bin/lean"
        for path in (shim, compiler):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not executed")
            path.chmod(0o700)
        command = preflight.resolve_command([str(shim), "-j1"], "leanprover/lean4:v4.26.0", self.project, elan_home=home)
        self.assertEqual(command, [str(compiler), "-j1"])

    def test_overridden_elan_home_does_not_execute_default_launcher(self):
        shim = self.root / ".elan/bin/lean"
        shim.parent.mkdir(parents=True)
        shim.write_text("default launcher must not execute")
        shim.chmod(0o700)
        with patch.object(Path, "home", return_value=self.root), self.assertRaises(preflight.CheckFailed) as raised:
            preflight.resolve_command([str(shim)], "leanprover/lean4:v4.26.0", self.project,
                                      elan_home=self.root / "other-elan")
        self.assertEqual(raised.exception.reason, "toolchain_not_installed")

    def test_live_api_backend_is_rejected_without_calling_provider(self):
        self.config["model"] = {"backend": "openrouter", "id": "test-model", "provider": "test-provider",
                                "max_tokens": 100, "timeout_seconds": 10, "temperature": 0}
        self.path.write_text(json.dumps(self.config))
        result = self.assert_failure_without_model("config")
        self.assertIn("fixture", result["error"]["message"])

    def test_existing_output_and_dangling_symlink_are_not_overwritten(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.execute()
        self.output.rmdir()
        self.output.symlink_to(self.root / "does-not-exist")
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertTrue(self.output.is_symlink())

    def test_normal_harness_retains_selection_and_replay(self):
        def evaluate(_self, code, problem, envs, output, repetitions):
            output.mkdir(parents=True)
            if "False.elim" in code:
                return {"valid": False, "tokens": 2, "error": {"kind": "lean"},
                        "environments": {"fixed": {"valid": False, "runs": [], "error": {"kind": "compile"}}}}
            tokens = 2 if "rfl" in code else 6 if "simpa" in code else 14
            return {"valid": True, "tokens": tokens, "error": None,
                    "environments": {"fixed": {"valid": True, "error": None,
                                               "runs": [{"measurement": {"raw": tokens * 100}}] * repetitions}}}
        with patch.object(self.evaluator.LeanEvaluator, "evaluate", evaluate):
            result = self.execute()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_requests"], 3)
        self.assertEqual(result["api_calls"], 0)
        self.assertTrue(result["replay"]["record_replay_passed"])
        self.assertIn("rfl", (self.output / "harness/selected.lean").read_text())
        with patch.object(self.harness.models, "query", side_effect=AssertionError("model called")), \
                patch.object(self.evaluator, "execute", side_effect=AssertionError("compiler called")):
            self.assertTrue(self.harness.replay(self.output / "harness")["record_replay_passed"])

    def test_environment_change_before_main_run_stops_before_model(self):
        original = run.launch_config
        def changed(config, command, root):
            path = original(config, command, root)
            (root / "input/project/lakefile.toml").write_text('name = "changed"\n')
            return path
        with patch.object(run, "launch_config", side_effect=changed), \
                patch.object(self.harness.models, "query", side_effect=AssertionError("model called")):
            result = self.execute()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["model_requests"], 0)
        self.assertIn("differs", result["error"]["message"])

    def test_run_lock_freezes_implementation_and_inputs_before_probes(self):
        original = self.compiler_execute
        def inspect(*args, **kwargs):
            record = json.loads((self.output / "run-lock.json").read_bytes())
            for key in ("code/run.py", "code/preflight.py", "code/lean_agent/harness.py", "input/problem.json", "planning/design.json"):
                self.assertEqual(record["files_before_compiler_execution"][key], baseline.sha((self.output / key).read_bytes()))
            return original(*args, **kwargs)
        self.compiler_execute = inspect
        self.assertEqual(self.execute(continue_run=False)["status"], "ready")


if __name__ == "__main__":
    unittest.main()
