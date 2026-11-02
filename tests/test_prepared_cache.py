"""Cached-library invalidation and full-verification boundaries; no compiler required."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import artifacts, prepared
from lean_agent import harness
import test_runtime_integration as runtime


class PreparedCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("PROJECT_CACHE_DIR"))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.lib = self.root / "lib"
        self.lib.mkdir()
        self.file = self.lib / "Dependency.olean"
        self.file.write_bytes(b"original")

    def evaluator(self, policy="stat-cache"):
        manifest = self.root / (policy + ".json")
        prepared.freeze([self.lib], "pinned-revision", manifest, verification=policy)
        return prepared.PreparedLeanEvaluator(manifest)

    def test_reuses_bytes_only_after_successful_full_check(self):
        evaluator = self.evaluator()
        evaluator.verify()
        original = Path.read_bytes
        with patch.object(Path, "read_bytes", autospec=True, side_effect=original) as read:
            evaluator.verify(full=False)
            read.assert_not_called()
            evaluator.verify()
            self.assertEqual(read.call_count, 1)

    def test_nested_roots_hash_each_pinned_file_once_without_changing_inventory(self):
        root = self.root / 'compiled'
        leaf = root / 'lean'
        leaf.mkdir(parents=True)
        artifact = leaf / 'Dependency.olean'
        artifact.write_bytes(b'pinned')
        for policy in ['full', 'stat-cache']:
            manifest = self.root / ('nested-' + policy + '.json')
            prepared.freeze([root, leaf], 'fixed', manifest, verification=policy)
            evaluator = prepared.PreparedLeanEvaluator(manifest)
            original = Path.read_bytes
            with patch.object(Path, 'read_bytes', autospec=True, side_effect=original) as read:
                evaluator.verify(full=True)
                self.assertEqual(read.call_count, 1)
            self.assertEqual(set(evaluator.settings['files']), {str(artifact)})

    def test_cache_is_local_to_each_evaluator(self):
        evaluator = self.evaluator()
        evaluator.verify()
        other = prepared.PreparedLeanEvaluator(self.root / "stat-cache.json")
        original = Path.read_bytes
        with patch.object(Path, "read_bytes", autospec=True, side_effect=original) as read:
            other.verify(full=False)
            self.assertEqual(read.call_count, 1)

    def test_unchanged_content_with_new_metadata_is_rehashed_once(self):
        evaluator = self.evaluator()
        evaluator.verify()
        before = self.file.stat()
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        original = Path.read_bytes
        with patch.object(Path, "read_bytes", autospec=True, side_effect=original) as read:
            evaluator.verify(full=False)
            evaluator.verify(full=False)
            self.assertEqual(read.call_count, 1)

    def test_file_changing_during_content_read_cannot_seed_cache(self):
        evaluator = self.evaluator()
        original = Path.read_bytes

        def changing_read(path):
            data = original(path)
            if path == self.file:
                path.write_bytes(b"tampered")
            return data

        with patch.object(Path, "read_bytes", changing_read):
            with self.assertRaisesRegex(ValueError, "during verification"):
                evaluator.verify(full=False)
        self.assertFalse(evaluator._verified_files)
        with self.assertRaisesRegex(ValueError, "files changed"):
            evaluator.verify(full=False)

    def test_unknown_policy_is_rejected_and_default_manifest_stays_compatible(self):
        manifest = self.root / "invalid.json"
        with self.assertRaisesRegex(ValueError, "verification policy"):
            prepared.freeze([self.lib], "revision", manifest, verification="disabled")
        self.assertFalse(manifest.exists())
        prepared.freeze([self.lib], "revision", manifest)
        data = artifacts.read(manifest)
        self.assertNotIn("verification", data)
        data["verification"] = "disabled"
        manifest.write_text(artifacts.canonical(data))
        with self.assertRaisesRegex(ValueError, "Invalid prepared environment manifest"):
            prepared.PreparedLeanEvaluator(manifest)

    def test_first_cached_invocation_reads_bytes_and_old_manifests_stay_strict(self):
        original = Path.read_bytes
        for policy in ("full", "stat-cache"):
            evaluator = self.evaluator(policy)
            if policy == "full":
                self.assertNotIn("verification", evaluator.settings)
            with patch.object(Path, "read_bytes", autospec=True, side_effect=original) as read:
                evaluator.verify(full=False)
                evaluator.verify(full=False)
                self.assertEqual(read.call_count, 2 if policy == "full" else 1)

    def test_same_size_edit_with_restored_mtime_is_rejected(self):
        evaluator = self.evaluator()
        evaluator.verify()
        before = self.file.stat()
        self.file.write_bytes(b"tampered")
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "files changed"):
            evaluator.verify(full=False)

    def test_added_deleted_and_replaced_library_is_rejected(self):
        evaluator = self.evaluator()
        evaluator.verify()
        extra = self.lib / "Extra.olean"
        extra.write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "files changed"):
            evaluator.verify(full=False)
        extra.unlink()
        evaluator.verify()
        self.file.unlink()
        with self.assertRaisesRegex(ValueError, "files changed"):
            evaluator.verify(full=False)
        self.file.write_bytes(b"original")
        evaluator.verify()
        replacement = self.root / "replacement"
        replacement.write_bytes(b"tampered")
        replacement.replace(self.file)
        with self.assertRaisesRegex(ValueError, "files changed"):
            evaluator.verify(full=False)

    def test_full_check_ignores_cached_metadata_and_detects_in_memory_manifest_edit(self):
        evaluator = self.evaluator()
        evaluator.verify()
        stamp = evaluator._stamp(self.file)
        self.file.write_bytes(b"tampered")
        # Even if a filesystem reports stale metadata, a boundary check reads bytes.
        with patch.object(evaluator, "_stamp", return_value=stamp):
            with self.assertRaisesRegex(ValueError, "files changed"):
                evaluator.verify()
        evaluator.settings["files"][str(self.file)] = artifacts.sha(b"tampered")
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            evaluator.verify(full=False)

    def test_failure_blocks_compiler_and_does_not_seed_cache(self):
        evaluator = self.evaluator()
        evaluator.verify()
        self.file.write_bytes(b"tampered")
        with patch("lean_agent.evaluator.lean.execute") as compiler:
            with self.assertRaisesRegex(ValueError, "files changed"):
                evaluator.execute(["lean"], self.root, 5)
            compiler.assert_not_called()
        self.assertFalse(evaluator._verified_files)
        self.file.write_bytes(b"original")
        evaluator.verify(full=False)

    def test_symlink_retarget_is_rejected(self):
        target = self.root / "target"
        target.write_bytes(b"original")
        self.file.unlink()
        self.file.symlink_to(target)
        evaluator = self.evaluator()
        evaluator.verify()
        other = self.root / "other"
        other.write_bytes(b"tampered")
        self.file.unlink()
        self.file.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "files changed"):
            evaluator.verify(full=False)

    def test_native_runner_keeps_full_boundaries_and_replay_with_cached_manifest(self):
        case = runtime.RuntimeTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        manifest = self.root / "native.json"
        prepared.freeze([self.lib], "pinned-revision", manifest, verification="stat-cache")
        case.config["lean"]["prepared_environment"] = str(manifest)
        case.path.write_text(artifacts.canonical(case.config))
        checks = []
        verify = prepared.PreparedLeanEvaluator.verify
        def record(evaluator, *, full=True):
            checks.append(full)
            return verify(evaluator, full=full)
        with patch.object(prepared.PreparedLeanEvaluator, "verify", record), \
                patch("lean_agent.evaluator.lean.execute", side_effect=case.compiler_execute):
            result = harness.run(case.path, case.output)
        self.assertTrue(result["final_valid"])
        self.assertEqual(sum(checks), 2)  # start and final environment fingerprints
        self.assertGreater(checks.count(False), 2)
        self.assertEqual(artifacts.read(case.output / "input/prepared-environment.json")["verification"], "stat-cache")
        self.assertTrue(harness.replay(case.output)["record_replay_passed"])


if __name__ == "__main__":
    unittest.main()
