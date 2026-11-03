import json
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from export_final_results import audit_result, digest, score

class EvidenceTests(unittest.TestCase):
    def fixture(self, root):
        folder = root / 'env'; folder.mkdir()
        code = 'theorem example : True := by trivial\n'
        runs = []
        for i, name in enumerate(['check', 'measure-1', 'measure-2', 'measure-3']):
            source, log = folder / (name + '.lean'), folder / (name + '.log')
            source.write_text(code); log.write_text('')
            runs.append({'source': source.name, 'source_sha256': digest(source), 'log': log.name,
                         'log_sha256': digest(log), 'returncode': 0, 'timed_out': False,
                         **({'measurement': {'raw': 10}} if i else {})})
        result = {'valid': True, 'tokens': 4, 'environments': {'env': {'valid': True, 'runs': runs, 'median_raw_heartbeats': 10}}}
        path = root / 'result.json'; path.write_text(json.dumps(result))
        return path, code, result

    def test_rejects_tampering_and_cached_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path, code, result = self.fixture(root)
            metrics = {'tokens': 4, 'raw_heartbeats': 10, 'raw_samples': [10,10,10]}
            audit_result(path, code, ['env'], metrics)
            (root / 'env/check.lean').write_text(code + '-- modified')
            with self.assertRaisesRegex(ValueError, 'hash'): audit_result(path, code, ['env'], metrics)
            (root / 'env/check.lean').write_text(code)
            result['environments']['env']['cache'] = {'hit': True}; path.write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError, 'Fresh'): audit_result(path, code, ['env'], metrics)

    def test_score_uses_own_paired_baseline(self):
        self.assertEqual(score({'baseline': {'tokens': 100, 'raw_heartbeats': 100},
                                'final': {'tokens': 50, 'raw_heartbeats': 50}}), Fraction(200, 3))

if __name__ == '__main__': unittest.main()
