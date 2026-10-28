"""Status queries against live, sealed, interrupted and hard-killed fixture runs."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch

import baseline
import status
import test_diagnostics


class StatusTests(unittest.TestCase):
    setUpClass = classmethod(test_diagnostics.DiagnosticsTests.setUpClass.__func__)
    setUp = test_diagnostics.DiagnosticsTests.setUp
    execute = test_diagnostics.DiagnosticsTests.execute
    compiler_execute = test_diagnostics.DiagnosticsTests.compiler_execute
    set_first_response = test_diagnostics.DiagnosticsTests.set_first_response
    read = test_diagnostics.DiagnosticsTests.read

    def test_normal_run_is_sealed_with_separate_latest_and_final_candidates(self):
        result = self.execute()
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "completed")
        self.assertTrue(view["sealed"])
        self.assertEqual(view["incomplete_stages"], [])
        self.assertEqual(view["last_completed_stage"]["stage"], "replay")
        self.assertEqual(view["latest_verified_candidate"]["stage"], "candidate")
        self.assertEqual(view["final_result"]["stage"], "final")
        self.assertEqual(view["final_result"]["sha256"], result["selected_sha256"])
        self.assertEqual(view["process_state"], "unknown")
        self.assertEqual(view["diagnostics"][0]["kind"], "proof")

    def test_live_query_does_not_infer_death_or_modify_files(self):
        query = self.harness.models.query
        def observed(*args, **kwargs):
            before = baseline.artifact_hashes(self.output)
            view = status.inspect(self.output)
            self.assertEqual(view["status"], "incomplete")
            self.assertEqual(view["incomplete_stages"][0]["stage"], "model")
            self.assertEqual(view["incomplete_stages"][0]["details"]["attempt"], args[2])
            self.assertEqual(view["process_state"], "unknown")
            self.assertIsNone(view["final_result"])
            self.assertEqual(before, baseline.artifact_hashes(self.output))
            return query(*args, **kwargs)
        with patch.object(self.harness.models, "query", side_effect=observed):
            self.assertEqual(self.execute()["status"], "completed")

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "requires POSIX SIGKILL")
    def test_hard_kill_during_second_candidate_keeps_first_verified_candidate(self):
        self.set_first_response('{"proof":"by rfl"}')
        code = '''
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from test_diagnostics import DiagnosticsTests
case = DiagnosticsTests()
case.setUpClass()
case.root = Path(sys.argv[2])
case.compiler = case.root / "compiler/bin/lean"
case.path = case.root / "inputs/configs/smoke.json"
case.output = case.root / "result"
case.invocations = []
original = case.compiler_execute
def kill(command, *args, **kwargs):
    if "steps/002/evaluation" in command[-1]:
        os.kill(os.getpid(), signal.SIGKILL)
    return original(command, *args, **kwargs)
case.compiler_execute = kill
case.execute()
'''
        child = subprocess.run([sys.executable, "-c", code, str(baseline.HERE), str(self.root)],
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr)
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "artifacts.json").exists())
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "incomplete")
        self.assertEqual(view["incomplete_stages"][0]["stage"], "candidate")
        self.assertEqual(view["incomplete_stages"][0]["details"]["attempt"], 2)
        self.assertEqual(view["latest_verified_candidate"]["attempt"], 1)
        self.assertIsNone(view["final_result"])
        self.assertEqual(view["process_state"], "unknown")

    def test_graceful_interrupt_is_terminal_not_an_open_stage(self):
        with patch.object(self.harness.models, "query", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "interrupted")
        self.assertEqual(view["incomplete_stages"], [])
        self.assertEqual(view["latest_failure"]["stage"], "model")
        self.assertIsNone(view["final_result"])

    def test_final_verification_alone_is_not_a_completed_run(self):
        original = self.compiler_execute
        def interrupt_at_last_fingerprint(command, *args, **kwargs):
            if "--version" in command and (self.output / "harness/final/result.json").exists():
                view = status.inspect(self.output)
                self.assertEqual(view["final_verification"]["status"], "passed")
                self.assertIsNone(view["final_result"])
                raise KeyboardInterrupt()
            return original(command, *args, **kwargs)
        self.compiler_execute = interrupt_at_last_fingerprint
        with self.assertRaises(KeyboardInterrupt):
            self.execute()
        self.assertIsNone(status.inspect(self.output)["final_result"])

    def test_failed_preflight_has_context_diagnosis_and_no_verified_candidate(self):
        self.template.write_text("import MissingModule\n" + self.template.read_text())
        self.execute()
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "failed")
        self.assertEqual(view["latest_failure"]["stage"], "context")
        self.assertEqual(view["diagnostics"][0]["kind"], "environment")
        self.assertIsNone(view["latest_verified_candidate"])

    def test_check_only_is_ready_but_has_no_final_proof(self):
        self.execute(continue_run=False)
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "ready")
        self.assertEqual(view["last_completed_stage"]["stage"], "context")
        self.assertIsNone(view["final_result"])

    def test_partial_last_line_preserves_previous_open_stage(self):
        self.output.mkdir()
        journal = status.Journal(self.output)
        journal.start("candidate", {"attempt": 2})
        with journal.path.open("ab") as stream:
            stream.write(b'{"schema_version": 1, "sequence": 2, "event": "fin')
        view = status.inspect(self.output)
        self.assertTrue(view["partial_trailing_record"])
        self.assertEqual(view["status"], "incomplete")
        self.assertEqual(view["incomplete_stages"][0]["details"]["attempt"], 2)

    def test_corrupt_complete_record_is_unknown_not_completed(self):
        self.execute()
        with (self.output / "events.jsonl").open("ab") as stream:
            stream.write(b'not-json\n')
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "unknown")
        self.assertTrue(view["record_error"])
        self.assertIsNone(view["final_result"])

    def test_missing_seal_does_not_claim_completion(self):
        self.execute()
        (self.output / "artifacts.json").unlink()
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "incomplete")
        self.assertIsNone(view["final_result"])

    def test_changed_selected_proof_invalidates_status_evidence(self):
        self.execute()
        (self.output / "harness/selected.lean").write_text("changed")
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "unknown")
        self.assertTrue(view["record_error"])
        self.assertIsNone(view["final_result"])

    def test_legacy_run_without_journal_is_unknown(self):
        self.output.mkdir()
        (self.output / "result.json").write_text('{"status":"completed"}')
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "unknown")
        self.assertIsNone(view["final_result"])

    def test_malformed_candidate_record_returns_unknown_without_crashing(self):
        self.output.mkdir()
        journal = status.Journal(self.output)
        start = journal.start("candidate", {"attempt": 1})
        journal.finish(start, "passed", candidate="corrupt")
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "unknown")
        self.assertIn("Invalid verified-candidate", status.describe(view))

    def test_stopped_run_does_not_promote_final_verification_to_completed_result(self):
        with patch.object(self.harness.models, "query", return_value={"transport_error": "TimeoutError", "http_status": None}):
            self.execute()
        view = status.inspect(self.output)
        self.assertEqual(view["status"], "stopped")
        self.assertEqual(view["final_verification"]["status"], "passed")
        self.assertIsNone(view["final_result"])
        self.assertTrue(any(row["kind"] == "api" for row in view["diagnostics"]))

    def test_status_cli_works_after_relocation_without_compiler_or_model(self):
        self.execute()
        target = self.root / "moved run"
        shutil.copytree(self.output, target)
        child = subprocess.run([sys.executable, "-B", str(target / "code/status.py"), str(target), "--json"],
                               cwd=self.root, env={**os.environ, "PATH": ""},
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout)["status"], "completed")


if __name__ == "__main__":
    unittest.main()
