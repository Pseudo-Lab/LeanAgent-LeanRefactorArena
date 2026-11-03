"""Legacy trace normalization preserves compiler outputs and existing logs."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from final_cache_traces import invalidate_bad_traces, normalize_cache_traces, trace_outputs


class LegacyTraceTests(unittest.TestCase):
    def test_bad_output_invalidates_only_its_module_metadata_for_official_restoration(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PROJECT_CACHE_DIR')) as folder:
            root = Path(folder)
            build = root / 'build'
            library = build / 'lib/lean'
            library.mkdir(parents=True)
            data = {'outputs': {'o': ['0123456789abcdef.olean', 'fedcba9876543210.olean.server'],
                                'c': '1234567890abcdef.c', 'r': '1234567890abcdef.ir'}}
            bad = library / 'Bad.trace'
            good = library / 'Good.trace'
            for path in [bad, good]:
                path.write_text(json.dumps(data))
            output = library / 'Bad.olean.server'
            output.write_bytes(b'partial compiler output')
            records = trace_outputs([build])
            self.assertIn(str(build / 'ir/Bad.c'), {r['path'] for r in records})
            self.assertIn(str(library / 'Bad.ir'), {r['path'] for r in records})
            original = bad.read_bytes()
            invalid = invalidate_bad_traces(records, {str(output)}, root / 'backups')
            self.assertEqual([r['path'] for r in invalid], [str(bad)])
            self.assertFalse(bad.exists())
            self.assertTrue(good.exists())
            self.assertEqual(output.read_bytes(), b'partial compiler output')
            self.assertEqual((root / 'backups' / (hashlib.sha256(original).hexdigest() + '.json')).read_bytes(), original)

    def test_only_omitted_empty_log_is_normalized_with_reversible_evidence(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PROJECT_CACHE_DIR')) as folder:
            root = Path(folder)
            build = root / 'build'
            build.mkdir()
            trace = build / 'Target.trace'
            original = b'{"schemaVersion":"2025-09-10","depHash":"0123456789abcdef","outputs":{"o":["123.olean"]}}'
            trace.write_bytes(original)
            compiler = build / 'Target.olean'
            compiler.write_bytes(b'original compiler output')
            existing = build / 'Warnings.trace'
            warning = b'{"schemaVersion":"2025-09-10","log":[{"level":"warning","message":"keep"}]}'
            existing.write_bytes(warning)
            legacy = build / 'Old.trace'
            legacy.write_bytes(b'1234')
            records = normalize_cache_traces([build], root / 'backups')
            self.assertEqual(len(records), 1)
            normalized = json.loads(trace.read_bytes())
            self.assertEqual(normalized.pop('log'), [])
            self.assertEqual(normalized, json.loads(original))
            self.assertEqual(compiler.read_bytes(), b'original compiler output')
            self.assertEqual(existing.read_bytes(), warning)
            self.assertEqual(legacy.read_bytes(), b'1234')
            self.assertEqual((root / 'backups' / (hashlib.sha256(original).hexdigest() + '.json')).read_bytes(), original)
            self.assertEqual(normalize_cache_traces([build], root / 'backups'), [])
