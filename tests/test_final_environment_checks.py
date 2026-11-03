"""Deferred proof checks must retain explicit, limited preparation provenance."""
import importlib.util
from pathlib import Path
import sys
import unittest

directory = Path(__file__).resolve().parents[1] / 'experiments/final-environment'
sys.path.insert(0, str(directory))
spec = importlib.util.spec_from_file_location('final_environment_prepare', directory / 'prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class StandaloneChecksTests(unittest.TestCase):
    def test_simple_headers_share_imports_but_keep_their_options_and_opens_in_separate_sections(self):
        source = prepare.combined_standalone_headers([
            {'header': 'import Mathlib\nopen Set\nset_option maxHeartbeats 0\n'},
            {'header': 'import Mathlib\nimport Aesop\nopen Filter\n'},
        ])
        self.assertEqual(source.count('import Mathlib'), 1)
        self.assertIn('import Aesop', source)
        self.assertIn('section\nopen Set\nset_option maxHeartbeats 0\nend', source)
        self.assertIn('section\nopen Filter\nend', source)
        self.assertIsNone(prepare.combined_standalone_headers([{'header': 'namespace N\n'}]))

    def test_default_checks_the_proof_and_opt_in_deferral_is_marked_as_imports_only(self):
        row = {'header': 'import Mathlib\nopen Set\n',
               'src': 'theorem target : True := by trivial', 'name': 'target'}
        kind, source = prepare.standalone_check(row)
        self.assertEqual(kind, 'canonical_standalone')
        self.assertIn(row['src'], source)
        self.assertIn('#print axioms target', source)
        kind, source = prepare.standalone_check(row, proofs=False)
        self.assertEqual(kind, 'standalone_header_imports')
        self.assertEqual(source, row['header'] + '\n')
