import json
from pathlib import Path
import tempfile
import unittest
from export_final_baselines import supplemental_root, digest


class SupplementalEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.result = self.root / 'problems/F022/baseline/result.json'
        self.input = self.root / 'problems/F022/input/problem.json'
        for p in [self.result, self.input]:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}\n')
        self.receipt = self.root / 'groups/cslib-v4.34.1.json'
        self.receipt.parent.mkdir()
        self.group = {'boundary_verified': True, 'initial_fingerprints': {'env': 'hash'},
                      'final_fingerprints': {'env': 'hash'}, 'rows': [
                          {'row': 22, 'valid': True, 'result_sha256': digest(self.result),
                           'input_sha256': digest(self.input)}]}

    def select(self):
        return supplemental_root([self.root], 'F022', 'cslib-v4.34.1', 22)

    def save(self):
        self.receipt.write_text(json.dumps(self.group))

    def test_in_progress_or_failed_boundary_never_publishes_measurements(self):
        self.assertIsNone(self.select())
        self.group['boundary_verified'] = False
        self.save()
        self.assertIsNone(self.select())

    def test_verified_group_and_exact_input_result_hashes_are_required(self):
        self.save()
        self.assertEqual(self.select(), self.root)
        self.result.write_text('{"valid":false}')
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            self.select()

    def test_mismatched_final_fingerprint_is_rejected(self):
        self.group['final_fingerprints'] = {'env': 'changed'}
        self.save()
        with self.assertRaisesRegex(ValueError, 'boundary mismatch'):
            self.select()

    def test_failed_problem_remains_missing_in_successful_group(self):
        self.group['rows'][0]['valid'] = False
        self.save()
        self.assertIsNone(self.select())


if __name__ == '__main__':
    unittest.main()
