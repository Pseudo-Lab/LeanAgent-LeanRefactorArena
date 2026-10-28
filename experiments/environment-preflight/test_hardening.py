"""Regressions for the three adversarial-audit findings; no API calls."""
import json
import signal
import unittest
from unittest.mock import patch

import baseline
import diagnostics
import replay
import test_diagnostics


class HardeningTests(unittest.TestCase):
    setUpClass = classmethod(test_diagnostics.DiagnosticsTests.setUpClass.__func__)
    setUp = test_diagnostics.DiagnosticsTests.setUp
    execute = test_diagnostics.DiagnosticsTests.execute
    compiler_execute = test_diagnostics.DiagnosticsTests.compiler_execute
    set_first_response = test_diagnostics.DiagnosticsTests.set_first_response
    read = test_diagnostics.DiagnosticsTests.read

    def assert_response_rejected(self, text):
        self.set_first_response(text)
        result = self.execute()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_requests"], 3)
        self.assertEqual(self.read("diagnostics/model-001.json")["kind"], "response")
        self.assertFalse((self.output / "harness/steps/001/candidate.lean").exists())
        self.assertFalse((self.output / "harness/steps/001/evaluation").exists())
        raw = self.read("harness/steps/001/response.json")
        self.assertEqual(raw["choices"][0]["message"]["content"], text)
        packet = json.loads(self.read("harness/steps/002/request.json")["messages"][1]["content"])
        self.assertEqual(packet["latest"]["feedback"]["diagnosis"]["kind"], "response")
        self.assertTrue(replay.replay(self.output)["record_replay_passed"])

    def test_escaped_lone_surrogate_rejected_before_candidate_write(self):
        self.assert_response_rejected('{"proof":"by exact \\ud800"}')

    def test_literal_lone_surrogate_receipt_is_preserved_and_rejected(self):
        self.assert_response_rejected('{"proof":"by exact \ud800"}')

    def test_deep_json_is_response_failure_and_replayable(self):
        self.config["limits"]["max_proof_characters"] = 20000
        self.path.write_text(json.dumps(self.config))
        self.assert_response_rejected("[" * 10000 + "0" + "]" * 10000)

    def test_valid_unicode_surrogate_pair_is_accepted(self):
        self.set_first_response(json.dumps({"proof": "by /- 😀 -/ rfl"}))
        result = self.execute()
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(self.read("diagnostics/candidate-001.json")["kind"])

    def test_nesting_guard_ignores_brackets_inside_escaped_json_strings(self):
        text = json.dumps({"proof": 'by /- \\"' + "[" * 1000 + ' -/ rfl'})
        diagnostics.validate_response_text(text)
        with self.assertRaisesRegex(ValueError, "nesting depth"):
            diagnostics.validate_response_text("[" * 129 + "0" + "]" * 129)

    def test_ctrl_c_records_interruption_and_preserves_signal_behavior(self):
        original_hooks = self.harness.advance, self.harness.parse_proof, self.harness.canonical
        def interrupt(*args, **kwargs):
            signal.raise_signal(signal.SIGINT)
        with patch.object(self.harness.models, "query", side_effect=interrupt) as query:
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        result = self.read("result.json")
        self.assertEqual((result["status"], result["stage"]), ("interrupted", "model"))
        self.assertEqual(result["error"]["exception_type"], "KeyboardInterrupt")
        self.assertEqual(query.call_count, 1)
        self.assertEqual(result["model_requests"], 1)
        self.assertTrue((self.output / "harness/steps/001/request.json").exists())
        self.assertFalse((self.output / "harness/steps/001/response.json").exists())
        self.assertFalse((self.output / "harness/summary.json").exists())
        self.assertTrue((self.output / "artifacts.json").exists())
        self.assertEqual(original_hooks, (self.harness.advance, self.harness.parse_proof, self.harness.canonical))
        with self.assertRaisesRegex(ValueError, "Incomplete experiment: interrupted at model"):
            replay.replay(self.output)

    def test_interruption_during_candidate_keeps_actual_stage(self):
        original = self.compiler_execute
        def interrupt(command, *args, **kwargs):
            if "steps/001/evaluation" in command[-1]:
                raise KeyboardInterrupt()
            return original(command, *args, **kwargs)
        self.compiler_execute = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.execute()
        self.assertEqual(self.read("result.json")["stage"], "candidate")
        self.assertEqual(self.read("result.json")["status"], "interrupted")

    def test_unexpected_runtime_exception_is_failed_not_ready(self):
        with patch.object(self.harness.models, "query", side_effect=RuntimeError("injected runtime failure")):
            result = self.execute()
        self.assertEqual((result["status"], result["stage"]), ("failed", "model"))
        self.assertEqual(result["error"]["exception_type"], "RuntimeError")
        self.assertEqual(self.read("diagnostics/failure.json")["kind"], "unknown")

    def test_system_exit_is_recorded_then_reraised(self):
        with patch.object(self.harness.models, "query", side_effect=SystemExit(7)):
            with self.assertRaises(SystemExit) as raised:
                self.execute()
        self.assertEqual(raised.exception.code, 7)
        self.assertEqual(self.read("result.json")["status"], "interrupted")

    def test_malformed_measurement_retains_result_exception_and_log(self):
        self.set_first_response('{"proof":"by rfl"}')
        original = self.compiler_execute
        for mutation in ("missing_raw", "invalid_axioms"):
            with self.subTest(mutation=mutation):
                self.output = self.root / mutation
                def execute(command, *args, **kwargs):
                    result = original(command, *args, **kwargs)
                    if "steps/001/evaluation" in command[-1] and "measure-1.lean" in command[-1]:
                        prefix, nonce, payload = result["output"].split(" ", 2)
                        data = json.loads(payload)
                        if mutation == "missing_raw":
                            del data["raw"]
                        else:
                            data["axioms"] = None
                        result["output"] = f"{prefix} {nonce} " + json.dumps(data) + "\n"
                    return result
                self.compiler_execute = execute
                result = self.execute()
                self.assertEqual(result["status"], "stopped")
                self.assertEqual(result["model_requests"], 1)
                report = self.read("diagnostics/candidate-001.json")
                self.assertEqual(report["kind"], "measurement")
                row = self.read("harness/steps/001/evaluation/result.json")["environments"]["fixed"]
                self.assertFalse(row["valid"])
                self.assertEqual(row["error"]["exception_type"], "KeyError" if mutation == "missing_raw" else "TypeError")
                logs = [ref for ref in report["evidence"] if ref["path"].endswith("measure-1.log")]
                self.assertEqual(len(logs), 1)
                self.assertEqual(logs[0]["sha256"], baseline.sha((self.output / logs[0]["path"]).read_bytes()))
                self.assertEqual(self.read("harness/initial-state.json")["best"],
                                 self.read("harness/summary.json")["state"]["best"])
                self.assertTrue(replay.replay(self.output)["record_replay_passed"])

    def test_key_error_outside_measurement_is_not_misclassified(self):
        original = self.compiler_execute
        def execute(command, *args, **kwargs):
            if "steps/001/evaluation" in command[-1]:
                raise KeyError("injected before first check receipt")
            return original(command, *args, **kwargs)
        self.compiler_execute = execute
        result = self.execute()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.read("diagnostics/failure.json")["kind"], "unknown")

    def test_malformed_baseline_and_final_measurements_keep_their_stages(self):
        original = self.compiler_execute
        for stage in ("baseline", "final"):
            with self.subTest(stage=stage):
                self.output = self.root / stage
                def execute(command, *args, **kwargs):
                    result = original(command, *args, **kwargs)
                    if f"harness/{stage}/" in command[-1] and "measure-1.lean" in command[-1]:
                        prefix, nonce, payload = result["output"].split(" ", 2)
                        data = json.loads(payload)
                        del data["raw"]
                        result["output"] = f"{prefix} {nonce} " + json.dumps(data) + "\n"
                    return result
                self.compiler_execute = execute
                result = self.execute()
                self.assertEqual(result["status"], "failed" if stage == "baseline" else "stopped")
                report = self.read(f"diagnostics/{stage}.json")
                self.assertEqual((report["kind"], report["stage"]), ("measurement", stage))
                if stage == "baseline":
                    self.assertEqual(result["model_requests"], 0)
                    self.assertEqual(result["failure_diagnosis"], "diagnostics/baseline.json")
                else:
                    self.assertIsNone(self.read("harness/summary.json")["final"])
                    self.assertTrue(replay.replay(self.output)["record_replay_passed"])


if __name__ == "__main__":
    unittest.main()
