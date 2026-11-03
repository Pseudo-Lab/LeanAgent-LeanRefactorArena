"""Inventory reuse must detect library edits without compiler/API calls."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent.prepared import freeze
from fast_prepared import FastPreparedLeanEvaluator


class FastInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.lib = self.root / "lib"
        self.lib.mkdir()
        self.file = self.lib / "A.olean"
        self.file.write_bytes(b"pinned compiled library")
        self.manifest = self.root / "prepared.json"
        freeze([self.lib], "fixture", self.manifest, verification="stat-cache")
        self.ev = FastPreparedLeanEvaluator(self.manifest)
        self.digest = self.ev.verify(full=True)

    def test_hot_verification_does_not_walk_or_read_library_bytes(self):
        with patch("os.walk", side_effect=AssertionError("recursive scan")), \
             patch.object(Path, "rglob", side_effect=AssertionError("recursive scan")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("library read")):
            self.assertEqual(self.ev.verify(full=False), self.digest)
        self.assertEqual(self.ev.last_verification["mode"], "inventory-stat")

    def assert_changed(self):
        with self.assertRaises((ValueError, OSError)):
            self.ev.verify(full=False)
        self.assertIsNone(self.ev._fast_files)

    def test_in_place_content_edit_is_rejected(self):
        self.file.write_bytes(b"different compiled bytes")
        self.assert_changed()

    def test_same_size_edit_with_restored_mtime_is_rejected(self):
        before = self.file.stat()
        self.file.write_bytes(b"X" * before.st_size)
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assert_changed()

    def test_added_library_file_is_rejected(self):
        (self.lib / "B.olean").write_bytes(b"unexpected")
        self.assert_changed()

    def test_removed_library_file_is_rejected(self):
        self.file.unlink()
        self.assert_changed()

    def test_added_nested_library_file_is_rejected(self):
        (self.lib / "new").mkdir()
        (self.lib / "new/B.olean").write_bytes(b"unexpected")
        self.assert_changed()

    def test_empty_directory_layout_change_is_rejected(self):
        nested = self.lib / "new"
        nested.mkdir()
        self.assert_changed()

    def test_restart_layout_identity_changes_when_empty_directory_is_added(self):
        before = self.ev.layout_sha256
        (self.lib / "new").mkdir()
        restarted = FastPreparedLeanEvaluator(self.manifest)
        restarted.verify()
        self.assertNotEqual(before, restarted.layout_sha256)

    def test_added_nonregular_file_is_rejected_without_opening_it(self):
        os.mkfifo(self.lib / "unexpected.olean")
        self.assert_changed()

    def test_regular_file_replaced_by_fifo_is_rejected_without_opening_it(self):
        self.file.unlink()
        os.mkfifo(self.file)
        self.assert_changed()

    def test_touch_of_unchanged_bytes_requires_full_reverification(self):
        info = self.file.stat()
        os.utime(self.file, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
        self.assertEqual(self.ev.verify(full=False), self.digest)
        self.assertEqual(self.ev.last_verification["mode"], "full-after-file-change")
        self.assertEqual(self.ev.verify(full=False), self.digest)
        self.assertEqual(self.ev.last_verification["mode"], "inventory-stat")

    def test_manifest_mutation_is_rejected(self):
        self.ev.settings["revision"] = "edited"
        self.assert_changed()

    def test_full_boundary_always_reads_actual_bytes(self):
        original = Path.read_bytes
        reads = []
        def recorded(path):
            reads.append(path)
            return original(path)
        with patch.object(Path, "read_bytes", recorded):
            self.ev.verify(full=True)
        self.assertIn(self.file, reads)

    def test_directory_link_insertion_is_rejected(self):
        other = self.root / "other"
        other.mkdir()
        (self.lib / "alias").symlink_to(other, target_is_directory=True)
        self.assert_changed()

    def test_file_added_during_stat_gate_is_detected_by_second_directory_pass(self):
        original = os.stat
        changed = False
        def racing(path, *args, **kwargs):
            nonlocal changed
            result = original(path, *args, **kwargs)
            if str(path) == str(self.file) and not changed:
                changed = True
                (self.lib / "racing.olean").write_bytes(b"unexpected")
            return result
        with patch("os.stat", racing):
            self.assert_changed()

    def test_file_added_during_full_scan_is_detected(self):
        original = Path.read_bytes
        changed = False
        def racing(path):
            nonlocal changed
            result = original(path)
            if path == self.file and not changed:
                changed = True
                (self.lib / "racing.olean").write_bytes(b"unexpected")
            return result
        with patch.object(Path, "read_bytes", racing):
            with self.assertRaises(ValueError):
                self.ev.verify(full=True)
        self.assertIsNone(self.ev._fast_files)

    def test_file_link_retargeting_is_rejected(self):
        original = self.file.read_bytes()
        first, second = self.root / "first", self.root / "second"
        first.write_bytes(original)
        second.write_bytes(b"different bytes")
        self.file.unlink()
        self.file.symlink_to(first)
        self.ev.verify(full=False)
        self.file.unlink()
        self.file.symlink_to(second)
        self.assert_changed()

    def test_overlapping_roots_are_deduplicated_in_hot_inventory(self):
        sub = self.lib / "Sub"
        sub.mkdir()
        (sub / "B.olean").write_bytes(b"second module")
        self.manifest.unlink()
        freeze([self.lib, sub], "fixture", self.manifest, verification="stat-cache")
        ev = FastPreparedLeanEvaluator(self.manifest)
        ev.verify()
        self.assertEqual(len(ev._fast_files), 2)
        self.assertEqual(len(ev._fast_directories), 2)
        ev.verify(full=False)


if __name__ == "__main__":
    unittest.main()
