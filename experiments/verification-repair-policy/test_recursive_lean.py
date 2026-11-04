"""Actual Lean checks. Opt in with REPAIR_RUN_LEAN_TESTS=1; never call model APIs."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from common import HERE, Limits, read, sha
from lean_agent import status
import run


@unittest.skipUnless(os.environ.get('REPAIR_RUN_LEAN_TESTS') == '1', 'Opt-in actual Lean 4.26 check')
class RealLean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['id']:c for c in read(HERE/'fixtures/cases.json')}
        evidence = os.environ.get('REPAIR_EVIDENCE_DIR')
        cls.temp = None if evidence else tempfile.TemporaryDirectory(prefix='recursive-repair-tests-')
        cls.root = Path(evidence or cls.temp.name).resolve()
        cls.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls.temp:
            cls.temp.cleanup()

    def execute(self, case_id, arm='recursive-repair-v1', limits=None, case=None, suffix=''):
        folder = self.root/(self._testMethodName+'-'+case_id+'-'+arm+suffix)
        run.prepare(folder, case or self.cases[case_id], arm, limits=limits)
        # Use the archived exact revision: editing working files during a long
        # test does not change code in an already prepared run.
        script = folder/'code/repo/experiments/verification-repair-policy/run.py'
        command_log=folder.parent/(folder.name+'.command.log')
        with command_log.open('w') as log:
            process = subprocess.run([sys.executable,str(script),'run','--output',str(folder)],stdout=log,stderr=subprocess.STDOUT)
        self.assertEqual(process.returncode,0,command_log.read_text()[-5000:])
        with patch('subprocess.Popen', side_effect=AssertionError('Replay tried a process')):
            replay = run.replay(folder)
        self.assertTrue(replay['record_replay_passed'])
        result = read(folder/'result.json')
        self.assertEqual(result['actual_api_calls'],0)
        self.assertEqual(result['actual_api_cost_usd'],'0')
        observation=status.inspect(folder)
        self.assertIsNone(observation['record_error'])
        self.assertTrue(observation['sealed'])
        self.assertEqual(observation['status'],result['status'])
        if result['status']=='completed':
            self.assertEqual(observation['final_result']['sha256'],result['selected_sha256'])
        return result, folder

    def test_all_three_conditions_and_recursive_grandchild(self):
        results, root_requests = {}, []
        for arm in ('planner-worker-v1','auto-solver-v1','recursive-repair-v1'):
            results[arm], folder = self.execute('F04',arm)
            root_requests.append(next(read(p)['input'] for p in sorted((folder/'tape').glob('*-request.json'))
                                 if read(p)['kind']=='worker' and read(p)['input']['role']=='root'))
        self.assertEqual(root_requests[0],root_requests[1])
        self.assertEqual(root_requests[1],root_requests[2])
        self.assertIsNone(results['planner-worker-v1']['repair'])
        self.assertEqual(results['auto-solver-v1']['repair']['reason'],'auto_solver_exhausted')
        repaired=results['recursive-repair-v1']['repair']
        self.assertEqual(repaired['status'],'verified')
        self.assertEqual(repaired['remaining_goals'],[])
        self.assertEqual([n['depth'] for n in repaired['nodes']],[1,2])
        self.assertEqual(repaired['nodes'][1]['parent_id'],repaired['nodes'][0]['node_id'])
        self.assertEqual(repaired['nodes'][1]['solved_by'],'auto_solver')
        self.assertTrue(all(n['status']=='solved' for n in repaired['nodes']))
        self.assertEqual(results['recursive-repair-v1']['repair_dispatches'],1)

    def test_valid_candidate_and_auto_only_repair(self):
        valid,_=self.execute('F01')
        self.assertIsNone(valid['repair'])
        result,_=self.execute('F02')
        self.assertEqual(result['repair']['status'],'verified')
        self.assertEqual(result['repair_dispatches'],0)

    def test_worker_direct_completion_and_multiple_goals(self):
        direct,_=self.execute('F03')
        self.assertEqual(direct['repair']['status'],'verified')
        self.assertEqual(len(direct['repair']['nodes']),1)
        multiple,_=self.execute('F05')
        self.assertEqual(multiple['repair']['status'],'verified')
        nodes=multiple['repair']['nodes']
        self.assertEqual([n['site']['goal']['target'] for n in nodes],['P','Q'])
        self.assertEqual([n['depth'] for n in nodes],[1,1])
        self.assertEqual(multiple['repair_dispatches'],0)

    def test_cycle_and_depth_limit_preserve_best(self):
        cycle,_=self.execute('F06')
        self.assertEqual(cycle['repair']['reason'],'cycle')
        self.assertEqual(cycle['repair']['remaining_goals'][0]['target'],'False')
        self.assertEqual(cycle['repair']['observation_source_sha256'],sha(cycle['repair']['partial_code']))
        self.assertEqual(cycle['selected_origin'],'baseline')
        depth,_=self.execute('F09',limits=replace(Limits(),depth=1))
        self.assertEqual(depth['repair']['reason'],'depth_limit')
        self.assertIsNotNone(depth['repair']['next_site'])
        self.assertEqual(depth['selected_origin'],'baseline')

    def test_last_allowed_worker_call_is_verified_and_selected(self):
        case=deepcopy(self.cases['F03'])
        case['responses'].insert(0,{'proof':'by sorry'})
        result,_=self.execute('F03',case=case,limits=replace(Limits(),run_calls=3,repair_calls=2))
        self.assertEqual(result['repair']['status'],'verified')
        self.assertEqual(result['repair_dispatches'],2)
        self.assertEqual(result['dispatches'],3)
        self.assertTrue(result['final_valid'])

    def test_syntax_sorry_and_uncertain_receipt(self):
        for case_id in ('F07','F08','F10','F10-indirect','F12'):
            result,_=self.execute(case_id)
            self.assertEqual(result['selected_origin'],'baseline')
            self.assertEqual(result['final_q'],2)
            if case_id=='F12':
                self.assertTrue(result['unknown_cost'])
                self.assertEqual(result['dispatches'],1)
            if case_id=='F10':
                self.assertEqual(result['stop_reason'],'response_rejected')

    def test_nested_have_unicode_and_incorrect_tactic(self):
        statement='theorem fixture_nested (α β : Prop) (hα : α) (hβ : β) : α ∧ β'
        case={'id':'nested','problem':{'name':'fixture_nested','statement':statement,
              'reference':statement+' := by exact ⟨hα, hβ⟩\n'},
              'candidate':'by\n  have h : β := by\n    exact False.elim\n  exact ⟨hα, h⟩'}
        result,folder=self.execute('F05',case=case,suffix='-nested')
        self.assertEqual(result['repair']['status'],'verified')
        self.assertIn('exact ⟨hα, h⟩',result['repair']['code'])
        node=result['repair']['nodes'][0]
        self.assertEqual(node['site']['goal']['target'],'β')
        self.assertIn('hβ',[l['name'] for l in node['site']['goal']['local_context']])
        # Integrity rejects tampering, including saved native reports.
        with tempfile.TemporaryDirectory() as temporary:
            copy=Path(temporary)/'tampered'
            shutil.copytree(folder,copy)
            request=next((copy/'tape').glob('*-request.json'))
            request.write_text('{}\n')
            with self.assertRaises(ValueError):
                run.replay(copy)

    def test_nested_have_unsolved_after_outer_goal_closes(self):
        statement='theorem fixture_unsolved (α β : Prop) (hα : α) (hβ : β) : α ∧ β'
        case={'id':'nested-unsolved','problem':{'name':'fixture_unsolved','statement':statement,
              'reference':statement+' := by exact ⟨hα, hβ⟩\n'},
              'candidate':'by\n  have h : β := by\n    skip\n  exact ⟨hα, h⟩'}
        result,_=self.execute('F05',case=case)
        self.assertEqual(result['repair']['status'],'verified')
        site=result['repair']['nodes'][0]['site']
        self.assertEqual(site['goal']['target'],'β')
        self.assertEqual(site['indent'],4)
        self.assertIn('exact ⟨hα, h⟩',result['repair']['code'])


if __name__=='__main__':
    unittest.main()
