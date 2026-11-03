"""Regressions from the published real failures, without model or Lean calls."""
import copy
import json
import tarfile
import unittest

from common import HERE
from native import select_site, patch_site


class ScopeRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        with tarfile.open(HERE/'evaluation/evidence.tar.gz') as archive:
            for name in ('P03-A2-r3-c01', 'P03-A2-r3-c02'):
                prefix = 'run/cases/'+name+'/'
                result = json.load(archive.extractfile(prefix+'result.json'))
                report = next(value for member in sorted(archive.getnames())
                              if member.startswith(prefix+'tape/') and member.endswith('-response.json')
                              if isinstance(value := json.load(archive.extractfile(member)).get('value'), dict)
                              and value.get('kind') == 'proof' and 'tactics' in value)
                cls.cases.append((result['repair']['partial_code'], report))

    def test_real_nested_have_uses_its_residual_goal_and_preserves_outer_proof(self):
        for code, report in self.cases:
            with self.subTest(error=report['errors'][0]['position']):
                block = min((b for b in report['blocks'] if b['start'] <= report['errors'][0]['position'] < b['end']),
                            key=lambda b: b['end']-b['start'])
                site = select_site(report, code)
                self.assertEqual(site['goal']['target'], "ks'.Disjoint (List.map Prod.fst (ks.zip vs))")
                self.assertEqual(site['start'], block['end'])
                self.assertEqual(site['indent'], 4)
                edited, _ = patch_site(code, site, 'by assumption')
                self.assertTrue(edited.encode().startswith(code.encode()[:block['end']]))
                self.assertTrue(edited.encode().endswith(code.encode()[block['end']:]))

    def test_child_ignores_errors_outside_its_region(self):
        code, report = self.cases[0]
        changed = copy.deepcopy(report)
        changed['errors'].insert(0, {'position': 0, 'message': 'unrelated error'})
        self.assertEqual(select_site(changed, code, (765, 805))['start'], 804)

    def test_empty_or_ambiguous_terminal_state_does_not_fall_back_to_intermediate_goal(self):
        code, report = self.cases[0]
        terminal = next(s for s in report['tactics'] if s.get('start') == 772 and s.get('end') == 804
                        and s['syntax_kind'].endswith('.tacticSeq') and s['depth'] == 21)
        empty = copy.deepcopy(report)
        next(s for s in empty['tactics'] if s == terminal)['after'] = []
        self.assertIsNone(select_site(empty, code))
        ambiguous = copy.deepcopy(report)
        extra = copy.deepcopy(terminal)
        extra['after'] = []
        ambiguous['tactics'].append(extra)
        self.assertIsNone(select_site(ambiguous, code))


if __name__ == '__main__':
    unittest.main()
