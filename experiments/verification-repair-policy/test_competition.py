"""Exact official-version coverage and unchanged final source; no external calls."""
from copy import deepcopy
import unittest

from common import canonical, sha
from competition import contract, report
from test_contracts import evaluation, protocol


class Compatibility(unittest.TestCase):
    def setUp(self):
        self.p = protocol()
        self.p['environment']['toolchain'] = 'leanprover/lean4:v4.26.0'
        self.p['condition_order'] = [('repair-r1', 'recursive-repair-v1')]
        self.ready = {'problem': self.p['problem'], 'environment': self.p['environment'],
                      'fingerprint': {'git': {'head': 'pinned-revision'}}}
        self.meta = {'name': self.p['problem']['name'], 'src': self.p['problem']['reference'],
                     'statement': self.p['problem']['statement'], 'file_path': 'Fixture.lean',
                     'url': 'fixture-repository', 'version_info': [{'v4.26.0': 'pinned-revision'}]}
        self.snapshot = {'arena_revision': 'fixture-snapshot', 'files': {'benchmark_data_warmup.jsonl':
                         {'sha256': sha(canonical(self.meta).encode()), 'url': 'fixture-snapshot-source'}}}

    def contract(self):
        return contract(canonical(self.meta).encode(), self.snapshot, self.ready)

    def test_requires_exact_snapshot_problem_and_complete_version_matrix(self):
        spec = self.contract()
        self.assertEqual(spec['required_environments'], [{'lean_version': 'v4.26.0',
                         'library_revision': 'pinned-revision', 'environment_id': 'fixed'}])
        with self.assertRaisesRegex(ValueError, 'checksum'):
            contract(b'changed', self.snapshot, self.ready)
        changed = deepcopy(self.ready)
        changed['problem']['reference'] += 'changed'
        with self.assertRaisesRegex(ValueError, 'official original'):
            contract(canonical(self.meta).encode(), self.snapshot, changed)
        self.meta['version_info'].append({'v4.27.0': 'another-revision'})
        self.snapshot['files']['benchmark_data_warmup.jsonl']['sha256'] = sha(canonical(self.meta).encode())
        with self.assertRaisesRegex(ValueError, 'every official environment'):
            self.contract()

    def test_only_same_selected_source_verified_at_required_pin_passes(self):
        self.p['compatibility'] = self.contract()
        code = self.p['problem']['reference']
        row = {'selected_code': code, 'selected_sha256': sha(code), 'final_valid': True,
               'final_evaluation': evaluation()}
        reference = {'status': 'completed', 'fingerprint': self.ready['fingerprint']}
        value = report(self.p, reference, [row])
        self.assertEqual((value['passed_versions'], value['required_versions']), (1, 1))
        self.assertEqual(value['status'], 'passed')
        self.assertFalse(value['official_evaluation'])
        for changed in ({**row, 'selected_code': code+' '}, {**row, 'final_valid': None},
                        {**row, 'final_evaluation': evaluation(False)}):
            self.assertEqual(report(self.p, reference, [changed])['status'], 'not_confirmed')
        reference['fingerprint'] = {'git': {'head': 'wrong-revision'}}
        self.assertEqual(report(self.p, reference, [row])['passed_versions'], 0)

    def test_fixture_never_claims_official_compatibility(self):
        self.p['compatibility'] = None
        self.assertEqual(report(self.p, {}, [])['status'], 'fixture_only')


if __name__ == '__main__':
    unittest.main()
