"""API usage and prepared-library integration. No paid calls or compiler needed."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from lean_agent import accounting, artifacts, harness, models, prepared
from lean_agent.evaluator.lean import execute
import test_runtime_integration as runtime


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.case = runtime.RuntimeTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def live_config(self, costs=("0.01", "0.02", "0.03")):
        case = self.case
        case.config["model"] = {"backend": "openrouter", "id": "test/model", "provider": "test",
            "reasoning_effort": "high", "max_price": {"prompt": 5, "completion": 15},
            "max_tokens": 100, "timeout_seconds": 1}
        def response(body, model, step, fixtures):
            return {"id": f"test-{step}", "model": "test/model", "provider": "test",
                    "choices": [{"message": {"content": 'invalid JSON' if step == 1 else '{"proof":"by rfl"}'}}],
                    "usage": {"cost": costs[step-1], "prompt_tokens": step * 100,
                              "completion_tokens": step * 10,
                              "prompt_tokens_details": {"cached_tokens": step * 50, "cache_write_tokens": 0},
                              "completion_tokens_details": {"reasoning_tokens": step * 5}}}
        return Mock(side_effect=response)

    def run_live(self, query, **kwargs):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            return self.case.execute(query=query, **kwargs)

    def test_usage_records_include_failed_and_duplicate_candidates_and_replay(self):
        self.run_live(self.live_config())
        summary = self.case.read("usage-summary.json")
        self.assertEqual(summary["responses"], 3)
        self.assertEqual(summary["reported_cost_usd"], "0.06")
        self.assertEqual(summary["tokens"]["input_tokens"]["total"], 600)
        self.assertEqual(summary["tokens"]["input_tokens"]["median"], 200)
        self.assertEqual(summary["tokens"]["output_tokens"]["total"], 60)
        self.assertEqual(summary["tokens"]["reasoning_tokens"]["total"], 30)
        self.assertEqual(summary["tokens"]["cached_input_tokens"]["total"], 300)
        with patch.object(models, "query", side_effect=AssertionError("No API in replay")):
            self.assertTrue(harness.replay(self.case.output)["record_replay_passed"])

    def test_resealed_usage_tampering_is_rejected(self):
        self.run_live(self.live_config())
        for name in ("steps/001/usage.json", "usage-summary.json"):
            path = self.case.output / name
            original = path.read_bytes()
            data = artifacts.read(path)
            data["reported_cost_usd"] = "999"
            path.write_text(json.dumps(data))
            (self.case.output / "artifacts.json").unlink()
            harness.seal(self.case.output)
            with self.assertRaisesRegex(ValueError, "Usage"):
                harness.replay(self.case.output)
            path.write_bytes(original)

    def test_threshold_stops_exactly_or_after_crossing_and_call_limit_can_win(self):
        for number, (threshold, max_calls, expected, reason) in enumerate([
                ("0.03", None, 2, "cost_limit"), ("0.025", None, 2, "cost_limit"),
                ("1", 1, 1, "call_limit")]):
            self.case.output = self.case.root / str(number)
            query = self.live_config()
            self.case.config["limits"].update(max_calls=max_calls, cost_stop_usd=threshold)
            result = self.run_live(query)
            self.assertEqual(query.call_count, expected)
            self.assertEqual(result["stop_reason"], reason)
            self.assertTrue(harness.replay(self.case.output)["record_replay_passed"])

    def test_unknown_billing_stops_even_if_tokens_could_be_estimated(self):
        query = self.live_config((None,))
        self.case.config["limits"].update(max_calls=None, cost_stop_usd="1")
        result = self.run_live(query)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(result["stop_reason"], "unknown_cost")
        summary = self.case.read("usage-summary.json")
        self.assertIsNone(summary["reported_cost_usd"])
        self.assertEqual(summary["unknown_cost_responses"], 1)
        self.assertEqual(summary["tokens"]["input_tokens"]["total"], 100)

    def test_malformed_usage_does_not_erase_known_provider_cost(self):
        record = accounting.response_record({"usage": {"cost": "0.2", "prompt_tokens": -1}})
        self.assertEqual(record["reported_cost_usd"], "0.2")
        self.assertIsNone(record["usage"])
        self.assertIsNotNone(record["usage_error"])
        summary = accounting.response_summary([record])
        self.assertIsNone(summary["tokens"]["input_tokens"]["total"])
        self.assertEqual(summary["tokens"]["input_tokens"]["missing_records"], 1)

    def test_dotenv_is_literal_restored_and_never_snapshotted(self):
        query = self.live_config()
        key = 'literal-$(do-not-execute)'
        path = self.case.root / ".env"
        path.write_text("OPENROUTER='" + key + "' # comment\n")
        original = query.side_effect
        def check_key(*args):
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], key)
            return original(*args)
        query.side_effect = check_key
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "prior-key"}):
            self.case.execute(query=query, dotenv=path)
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "prior-key")
        self.assertFalse(any(key.encode() in p.read_bytes() for p in self.case.output.rglob("*") if p.is_file()))
        path.write_text('OPENROUTER=a\nOPENROUTER_API_KEY=b\n')
        with self.assertRaisesRegex(ValueError, "conflicting"):
            models.load_key(path)

    def prepare_libraries(self):
        case = self.case
        libraries = case.root / "lib"
        libraries.mkdir()
        (libraries / "Dependency.olean").write_bytes(b"frozen test dependency")
        manifest = case.root / "libraries.json"
        prepared.freeze([libraries], "test-revision", manifest)
        case.config["lean"]["prepared_environment"] = str(manifest)
        return libraries, manifest

    def test_native_runner_selects_prepared_evaluator_and_archives_manifest(self):
        libraries, manifest = self.prepare_libraries()
        seen = []
        original = self.case.compiler_execute
        def compiled(command, *args, **kwargs):
            seen.append(kwargs["lean_path"])
            return original(command, *args, **kwargs)
        with patch("lean_agent.evaluator.lean.execute", side_effect=compiled):
            self.case.path.write_text(json.dumps(self.case.config))
            result = harness.run(self.case.path, self.case.output)
        self.assertTrue(result["final_valid"])
        self.assertTrue(all(path == str(libraries) for path in seen))
        self.assertEqual((self.case.output / "input/prepared-environment.json").read_bytes(), manifest.read_bytes())
        self.assertEqual(self.case.read("environment.json")["prepared_libraries"]["revision"], "test-revision")
        manifest.unlink()
        self.assertTrue(harness.replay(self.case.output)["record_replay_passed"])

    def test_changed_or_added_dependency_blocks_before_any_model_call(self):
        libraries, manifest = self.prepare_libraries()
        for name in ("Dependency.olean", "Extra.olean"):
            with self.subTest(name=name):
                path = libraries / name
                original = path.read_bytes() if path.exists() else None
                path.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "changed"):
                    prepared.PreparedLeanEvaluator(manifest).verify()
                if original is not None:
                    path.write_bytes(original)
                else:
                    path.unlink()
        (libraries / "Dependency.olean").unlink()
        self.case.path.write_text(json.dumps(self.case.config))
        with patch.object(models, "query") as query:
            with self.assertRaisesRegex(ValueError, "Prepared"):
                harness.run(self.case.path, self.case.output)
        query.assert_not_called()
        self.assertEqual(self.case.read("result.json")["model_requests"], 0)

    def test_prepared_lean_path_does_not_forward_credentials(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret", "LEAN_PATH": "ambient"}):
            result = execute([sys.executable, "-c", "import os; print(os.getenv('LEAN_PATH'), os.getenv('OPENROUTER_API_KEY'))"],
                             self.case.root, 5, lean_path="explicit")
        self.assertEqual(result["output"].strip(), "explicit None")

    def test_missing_optional_usage_is_unknown_instead_of_zero(self):
        a = accounting.response_record({"usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0}})
        b = accounting.response_record({})
        summary = accounting.response_summary([a, b])
        self.assertIsNone(summary["tokens"]["input_tokens"]["total"])
        self.assertEqual(summary["tokens"]["input_tokens"]["known_subtotal"], 5)
        self.assertIsNone(summary["tokens"]["cached_input_tokens"]["total"])


if __name__ == "__main__":
    unittest.main()
