"""Feature 2 exercises real harness/evaluator code with simulated process receipts."""
import json
from pathlib import Path
import re
import shutil
import unittest
from unittest.mock import patch

import baseline
import diagnostics
import replay
import test_preflight


class DiagnosticsTests(unittest.TestCase):
    setUpClass = classmethod(test_preflight.PreflightTests.setUpClass.__func__)
    setUp = test_preflight.PreflightTests.setUp
    execute = test_preflight.PreflightTests.execute

    def compiler_execute(self, command, cwd, timeout, **kwargs):
        result = test_preflight.PreflightTests.compiler_execute(self, command, cwd, timeout, **kwargs)
        if not command[-1].endswith(".lean") or result["returncode"]:
            return result
        source = Path(command[-1]).read_text()
        if "False.elim" in source:
            result.update(returncode=1, output=f"{command[-1]}:4:25: error: tactic 'assumption' failed\n⊢ False\n")
        elif '#refactor_eval "' in source:
            nonce, name = re.search(r'#refactor_eval "([^"]+)" "([^"]+)"', source).groups()
            raw = 2000 if "  rfl" in source else 6000
            result["output"] = "REFACTOR_EVAL " + nonce + " " + json.dumps(
                {"target": name, "raw": raw, "scaled": raw // 1000, "axioms": []}) + "\n"
        return result

    def read(self, name):
        return json.loads((self.output / name).read_bytes())

    def set_first_response(self, content):
        path = self.input / "examples/first-harness/responses.json"
        values = json.loads(path.read_bytes())
        values[0] = content
        path.write_text(json.dumps(values))

    def fault(self, mode, stage="steps/001/evaluation"):
        self.set_first_response('{"proof":"by rfl"}')
        original = self.compiler_execute
        def execute(command, *args, **kwargs):
            result = original(command, *args, **kwargs)
            if stage not in command[-1]:
                return result
            is_measure = "measure-" in command[-1]
            if mode == "missing_report" and is_measure:
                result["output"] = "simulated success without a measurement report\n"
            elif mode == "wrapper_error" and is_measure:
                result.update(returncode=1, output="error: simulated measurement wrapper error\n")
            elif mode == "timeout":
                result.update(returncode=-9, timed_out=True, output="partial output before local timeout\n")
            elif mode == "signal":
                result.update(returncode=-9, output="")
            elif mode == "missing_import":
                result.update(returncode=1, output="error: unknown module prefix 'MissingAfterPreflight'\n")
            elif mode == "ambiguous":
                result.update(returncode=2, output="unrecognized compiler failure\n")
            elif mode == "axioms" and is_measure:
                result["output"] = result["output"].replace('"axioms": []', '"axioms": ["sorryAx"]')
            return result
        self.compiler_execute = execute

    def test_proof_error_is_in_next_request_and_original_is_preserved(self):
        result = self.execute()
        self.assertEqual(result["status"], "completed")
        report = self.read("diagnostics/candidate-001.json")
        self.assertEqual(report["kind"], "proof")
        original = self.read("harness/steps/001/evaluation/result.json")
        self.assertEqual(original["environments"]["fixed"]["error"]["kind"], "compile")
        self.assertEqual(report["original_error"]["error"], original["error"])
        packet = json.loads(self.read("harness/steps/002/request.json")["messages"][1]["content"])
        feedback = packet["latest"]["feedback"]
        self.assertEqual(feedback["diagnosis"]["kind"], "proof")
        self.assertIn("assumption", feedback["details"])
        self.assertIn("⊢ False", feedback["details"])
        self.assertNotIn(str(self.output), feedback["details"])
        self.assertLessEqual(len(feedback["details"]), self.config["limits"]["max_feedback_characters"])
        self.assertNotIn("False.elim", (self.output / "harness/selected.lean").read_text())
        for ref in report["evidence"]:
            self.assertEqual(baseline.sha((self.output / ref["path"]).read_bytes()), ref["sha256"])

    def test_malformed_json_skips_compiler_then_continues(self):
        self.set_first_response("not-json")
        result = self.execute()
        self.assertEqual(result["model_requests"], 3)
        self.assertEqual(self.read("diagnostics/model-001.json")["kind"], "response")
        self.assertFalse((self.output / "harness/steps/001/evaluation").exists())
        self.assertTrue(result["replay"]["record_replay_passed"])

    def test_forbidden_declaration_is_response_contract_failure(self):
        self.set_first_response('{"proof":"by sorry"}')
        self.execute()
        report = self.read("diagnostics/candidate-001.json")
        self.assertEqual(report["kind"], "response")
        self.assertEqual(report["reason"], "declaration_contract_rejected")

    def api_failure(self, raw, kind, reason):
        original = self.harness.advance
        with patch.object(self.harness.models, "query", return_value=raw) as query:
            result = self.execute()
        self.assertEqual(query.call_count, 1)
        self.assertEqual(result["model_requests"], 1)
        self.assertEqual(result["api_calls"], 0)
        self.assertEqual(result["status"], "stopped")
        self.assertTrue(result["replay"]["record_replay_passed"])
        self.assertIs(self.harness.advance, original)
        self.assertEqual(self.read("harness/steps/001/response.json"), raw)
        report = self.read("diagnostics/model-001.json")
        self.assertEqual((report["kind"], report["reason"]), (kind, reason))
        self.assertEqual(report["billing"], "unknown")
        self.assertFalse(report["automatic_retry"])
        self.assertFalse((self.output / "harness/steps/002").exists())
        self.assertTrue(self.read("harness/summary.json")["state"]["unknown_cost"])

    def test_api_timeout_no_retry(self):
        self.api_failure({"transport_error": "TimeoutError", "http_status": None}, "api", "api_response_timeout")

    def test_api_transport_no_retry(self):
        self.api_failure({"transport_error": "URLError", "http_status": None}, "api", "transport_error")

    def test_api_http_no_retry(self):
        self.api_failure({"transport_error": "HTTPError", "http_status": 429}, "api", "http_error")

    def test_invalid_api_envelope_is_response_failure_with_unknown_billing(self):
        self.api_failure({"transport_error": "JSONDecodeError", "http_status": None}, "response", "invalid_api_envelope")

    def test_measurement_missing_report_is_not_proof_or_environment_diagnosis(self):
        self.fault("missing_report")
        result = self.execute()
        self.assertEqual(self.read("diagnostics/candidate-001.json")["kind"], "measurement")
        original = self.read("harness/steps/001/evaluation/result.json")
        self.assertEqual(original["environments"]["fixed"]["error"]["kind"], "environment")
        self.assertEqual(result["model_requests"], 1)  # preserve upstream stopping policy
        self.assertEqual(result["status"], "stopped")
        self.assertTrue(result["replay"]["record_replay_passed"])
        self.assertEqual(self.read("harness/summary.json")["state"]["best"]["sha256"],
                         self.read("harness/initial-state.json")["best"]["sha256"])

    def test_wrapper_compile_failure_is_measurement_failure_after_plain_check(self):
        self.fault("wrapper_error")
        self.execute()
        self.assertEqual(self.read("diagnostics/candidate-001.json")["kind"], "measurement")

    def test_local_timeout_is_not_proof_failure(self):
        self.fault("timeout")
        self.execute()
        report = self.read("diagnostics/candidate-001.json")
        self.assertEqual(report["kind"], "timeout")
        self.assertIn("competition outcome are undetermined", report["guidance"])

    def test_signal_is_unknown(self):
        self.fault("signal")
        self.execute()
        self.assertEqual(self.read("diagnostics/candidate-001.json")["kind"], "unknown")

    def test_ambiguous_output_is_unknown(self):
        self.fault("ambiguous")
        self.execute()
        self.assertEqual(self.read("diagnostics/candidate-001.json")["kind"], "unknown")

    def test_import_failure_after_preflight_is_environment(self):
        self.fault("missing_import")
        self.execute()
        self.assertEqual(self.read("diagnostics/candidate-001.json")["kind"], "environment")

    def test_disallowed_axioms_are_proof_rejection(self):
        self.fault("axioms")
        self.execute()
        self.assertEqual(self.read("diagnostics/candidate-001.json")["reason"], "disallowed_axioms")

    def test_invalid_baseline_stops_before_model(self):
        path = self.input / "examples/first-harness/problem.json"
        problem = json.loads(path.read_bytes())
        problem["reference"] = problem["statement"] + " := by exact False.elim (by assumption)\n"
        path.write_text(json.dumps(problem))
        result = self.execute()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["model_requests"], 0)
        self.assertEqual(result["stage"], "baseline")
        self.assertEqual(result["failure_diagnosis"], "diagnostics/baseline.json")
        self.assertEqual(self.read("diagnostics/baseline.json")["kind"], "proof")

    def test_later_query_exception_does_not_reuse_previous_proof_diagnosis(self):
        query = self.harness.models.query
        def failing_query(body, model, step, fixtures):
            if step == 2:
                raise OSError("injected fixture reader failure")
            return query(body, model, step, fixtures)
        with patch.object(self.harness.models, "query", side_effect=failing_query):
            result = self.execute()
        self.assertEqual(result["stage"], "model")
        self.assertEqual(result["failure_diagnosis"], "diagnostics/failure.json")
        self.assertEqual(self.read("diagnostics/failure.json")["kind"], "unknown")

    def test_failed_final_measurement_is_not_completed(self):
        self.fault("missing_report", stage="harness/final")
        result = self.execute()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(self.read("diagnostics/final.json")["kind"], "measurement")
        self.assertIsNone(self.read("harness/summary.json")["final"])

    def test_context_missing_import_adds_diagnosis_without_overwriting_preflight(self):
        self.template.write_text("import MissingModule\n" + self.template.read_text())
        self.execute()
        self.assertEqual(self.read("preflight.json")["error"]["kind"], "unknown")
        self.assertEqual(self.read("diagnostics/preflight.json")["kind"], "environment")

    def test_replay_offline_after_relocation_and_tampering_rejected(self):
        self.execute()
        relocated = self.root / "relocated"
        shutil.copytree(self.output, relocated)
        with patch.object(self.harness.models, "query", side_effect=AssertionError("model called")), \
                patch.object(self.evaluator, "execute", side_effect=AssertionError("compiler called")):
            self.assertTrue(diagnostics.replay(self.harness, relocated)["record_replay_passed"])
        self.assertTrue(replay.replay(relocated)["record_replay_passed"])
        (relocated / "diagnostics/candidate-001.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "inventory/hash"):
            replay.replay(relocated)

    def test_adapter_restores_hook_when_body_raises(self):
        original = self.harness.advance
        with self.assertRaises(RuntimeError):
            with diagnostics.feedback_adapter(self.harness, self.output):
                raise RuntimeError("injected")
        self.assertIs(self.harness.advance, original)

    def test_original_selection_metrics_match_without_feedback_adapter(self):
        result = self.execute()
        path = self.output / "launch/config.json"
        with patch.object(self.evaluator, "execute", side_effect=self.compiler_execute):
            control = self.harness.run(path, self.root / "control")
        self.assertEqual(result["selected_sha256"], control["state"]["best"]["sha256"])
        self.assertEqual(self.read("harness/summary.json")["final"], control["final"])


if __name__ == "__main__":
    unittest.main()
