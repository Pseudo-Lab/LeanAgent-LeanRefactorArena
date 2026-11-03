"""Source-pin regression fixtures; Git commands only read the existing repo."""
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from baseline_snapshot import UPSTREAM_DIRECTORIES, verify_baseline_snapshot
import run_experiment as experiment

REPO = Path(__file__).resolve().parents[2]
BASE = experiment.BASE


class BaselineSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        data = subprocess.run(['git', '--no-replace-objects', '-C', str(REPO), 'archive',
                               '--format=tar', BASE, '--', *UPSTREAM_DIRECTORIES],
                              check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if not member.isfile():
                    continue
                target = self.root / member.name
                self.assertTrue(target.resolve().is_relative_to(self.root.resolve()))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())

    def test_same_inventory_and_contents_pass_while_pycache_is_excluded(self):
        cache = self.root/'src/__pycache__'
        cache.mkdir(); (cache/'ignored.pyc').write_bytes(b'ignored local bytecode')
        receipt = verify_baseline_snapshot(REPO, BASE, source_root=self.root)
        self.assertTrue(receipt['verified_against_local_git'])
        self.assertEqual(receipt['baseline_commit'], BASE)
        self.assertGreater(receipt['file_count'], 0)
        self.assertFalse(any('__pycache__' in path for path in receipt['files_sha256']))

    def test_modified_source_fails_and_prepare_guard_precedes_run_directory(self):
        path = self.root/'experiments/final-batch-next/driver.py'
        path.write_bytes(path.read_bytes()+b'\n# unreviewed upstream change\n')
        with self.assertRaisesRegex(ValueError, 'content differs'):
            verify_baseline_snapshot(REPO, BASE, source_root=self.root)
        destination = self.root/'new-run'
        with patch('baseline_snapshot.verify_baseline_snapshot', side_effect=ValueError('Use a pinned checkout')):
            with self.assertRaisesRegex(ValueError, 'pinned checkout'):
                experiment.prepare(destination, self.root/'env', self.root/'slots')
        self.assertFalse(destination.exists())

    def test_untracked_executable_is_an_inventory_error(self):
        extra = self.root/'src/untracked-runner'
        extra.write_text('#!/bin/sh\nexit 0\n'); extra.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'inventory differs.*untracked-runner'):
            verify_baseline_snapshot(REPO, BASE, source_root=self.root)


if __name__ == '__main__':
    unittest.main()
