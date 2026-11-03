import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from export_final20_trajectories import export_problem, score


class TrajectoriesTest(unittest.TestCase):
    def test_published_attempts_and_html_agree(self):
        folder = Path(__file__).resolve().parents[1] / 'public/reports'
        data = json.loads((folder / 'final20-attempts.json').read_text())
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
        self.assertIn(payload, (folder / 'final20-attempts.html').read_text())
        self.assertEqual(data['problemCount'], 20)
        self.assertEqual(sum(p['calls'] for p in data['problems']), 2141)
        self.assertEqual(data['totalCostUsd'], '55.7459113')
        for problem in data['problems']:
            points = problem['points']
            self.assertEqual([p['step'] for p in points], list(range(problem['calls'] + 1)))
            self.assertEqual(len(problem['final']['raw_samples']), 3)
            self.assertAlmostEqual(score(problem['final'], problem['baseline']), problem['finalScore'])
            self.assertTrue(all(a['best'] <= b['best'] + 1e-10 for a, b in zip(points, points[1:])))
            self.assertTrue(all(a['cost'] <= b['cost'] for a, b in zip(points, points[1:])))
            for point in points[1:]:
                self.assertEqual(point['candidate'] is not None, point['outcome'] == 'valid')

    def test_failed_and_lookup_attempts_preserve_incumbent_and_spend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'problems/F001'
            folder.mkdir(parents=True)
            def save(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))
            def candidate(code, valid, tokens, hb, rank):
                return dict(code=code, sha256=hashlib.sha256(code.encode()).hexdigest(),
                            valid=valid, tokens=tokens, raw_heartbeats=hb, rank_numerator=rank)
            base = candidate('original', True, 100, 100, 200)
            improved = candidate('better', True, 50, 50, 100)
            failed = candidate('invalid', False, 1, None, None)
            history = [dict(step=1, candidate_id='c001', cost_usd_after='0.1'),
                       dict(step=2, candidate_id='c002', cost_usd_after='0.2'),
                       dict(step=3, cost_usd_after='0.3')]
            state = dict(baseline=dict(tokens=100, raw_heartbeats=100), calls=3, cost_usd='0.3',
                         exploration=dict(candidates=dict(c000=base, c001=improved, c002=failed), history=history))
            summary = dict(status='completed', all_versions_valid=True, name='fixture', cost_usd='0.3',
                           final=dict(tokens=50, raw_heartbeats=51, raw_samples=[50, 51, 51]),
                           selected=dict(sha256=improved['sha256']))
            save(folder / 'state.json', state)
            save(folder / 'summary.json', summary)
            attempts = {}
            for step, action in enumerate(['candidate', 'candidate', 'search'], 1):
                attempts[step] = dict(status='settled', cost_usd='0.1')
                save(folder / 'steps' / f'{step:04}' / 'event.json',
                     dict(step=step, cost_usd_after=f'0.{step}', best_sha256=improved['sha256'],
                          action=dict(action=action)))
            result = export_problem(root, 1, attempts)
            self.assertEqual([p['outcome'] for p in result['points']], ['baseline', 'valid', 'invalid', 'lookup'])
            self.assertIsNone(result['points'][2]['candidate'])
            self.assertIsNone(result['points'][3]['candidate'])
            self.assertEqual(result['points'][1]['best'], result['points'][3]['best'])
            self.assertNotEqual(result['finalScore'], result['points'][3]['best'])
            attempts[3]['cost_usd'] = '0.2'
            with self.assertRaisesRegex(ValueError, 'cost differs'):
                export_problem(root, 1, attempts)
            attempts[3]['cost_usd'] = '0.1'
            attempts[2]['status'] = 'dispatched'
            with self.assertRaisesRegex(ValueError, 'Unsettled'):
                export_problem(root, 1, attempts)


if __name__ == '__main__':
    unittest.main()
