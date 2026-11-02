"""A disk-reserve abort must retain the cache and release its partial copy."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class CompressionFailureTests(unittest.TestCase):
    def test_reserve_abort_preserves_original_and_removes_staging_after_copier_exits(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PROJECT_CACHE_DIR')) as folder:
            root = Path(folder)
            with patch.dict(os.environ, PROJECT_CACHE_DIR=str(root / 'cache'), PROJECT_ENV_DIR=str(root / 'env')):
                spec = importlib.util.spec_from_file_location('final_compressor', Path(__file__).resolve().parents[1] / 'scripts/compress_final_cache.py')
                compressor = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(compressor)
            compressor.CACHE.mkdir()
            compressor.ALLOWED = [root]
            original = root / 'original'
            original.mkdir()
            (original / 'proof.olean').write_bytes(b'verified compiler output')
            before = compressor.inventory(original)

            class Copier:
                pid = 123456
                returncode = None
                def __init__(self, command, **kwargs):
                    shutil.copytree(command[-2], command[-1])
                def poll(self):
                    return self.returncode
                def wait(self):
                    self.returncode = 0
                    return 0

            with patch.object(compressor.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')), \
                 patch.object(compressor.subprocess, 'Popen', Copier), \
                 patch.object(compressor.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
                 patch.object(compressor.os, 'killpg') as terminate:
                with self.assertRaisesRegex(RuntimeError, 'disk reserve'):
                    compressor.compress(original)
                terminate.assert_called_once()
            self.assertEqual(compressor.inventory(original), before)
            self.assertEqual(list((compressor.CACHE / 'compression-staging').iterdir()), [])
            self.assertEqual(list((compressor.CACHE / 'compression-backups').iterdir()), [])
