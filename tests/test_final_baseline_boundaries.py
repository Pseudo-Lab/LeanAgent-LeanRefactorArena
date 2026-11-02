"""Environment-boundary checks must also run on early exits and failures."""
from contextlib import nullcontext
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "final_baseline_runner", Path(__file__).resolve().parents[1] / "scripts/measure_final_baselines.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ["PROJECT_CACHE_DIR"])
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.output = self.repo / "output"
        self.output.mkdir()
        self.manifest = self.repo / "manifest.json"
        self.manifest.write_text("{}\n")
        self.state = {"prepared_environment": "manifest.json",
                      "prepared_manifest_sha256": runner.sha(self.manifest.read_bytes())}
        self.state_file = self.repo / "environments/env/environment.json"
        self.state_file.parent.mkdir(parents=True)
        self.state_file.write_text(json.dumps(self.state))
        self.prepared = Mock()
        self.prepared.verify.return_value = "verified-byte-inventory"
        self.evaluator = Mock(repo=self.repo, root=self.repo)
        self.evaluator._states = {"env": self.state}
        self.evaluator._prepared = {"env": self.prepared}
        self.evaluator._compiler_lock.side_effect = lambda: nullcontext()
        self.report = patch.object(runner, "report").start()
        self.addCleanup(patch.stopall)

    def session(self):
        return runner.verification_session(self.evaluator, self.output, self.repo / "report.md", "run")

    def test_full_verification_runs_even_when_queue_returns_early(self):
        def queue():
            with self.session():
                return "missing next environment"
        self.assertEqual(queue(), "missing next environment")
        self.prepared.verify.assert_called_once_with(full=True)
        receipt = json.loads((self.output / "environment-verification.json").read_text())
        self.assertEqual(receipt["status"], "passed")

    def test_native_error_is_preserved_after_full_verification(self):
        with self.assertRaisesRegex(RuntimeError, "native failure"):
            with self.session():
                raise RuntimeError("native failure")
        self.prepared.verify.assert_called_once_with(full=True)

    def test_library_byte_failure_marks_run_failed(self):
        self.prepared.verify.side_effect = ValueError("library changed")
        with self.assertRaisesRegex(ValueError, "library changed"):
            with self.session():
                pass
        receipt = json.loads((self.output / "environment-verification.json").read_text())
        progress = json.loads((self.output / "progress.json").read_text())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(progress["status"], "failed_environment_boundary")

    def test_metadata_change_is_not_hidden_by_unchanged_libraries(self):
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            with self.session():
                self.state_file.write_text(json.dumps({**self.state, "revision": "different"}))
        self.prepared.verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
