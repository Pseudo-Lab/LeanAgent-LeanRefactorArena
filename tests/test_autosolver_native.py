"""Opt-in real pinned Lean execution; no model API or external dependencies."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from lean_agent import artifacts as a, harness as h
ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('AUTOSOLVER_LEAN'), 'Set AUTOSOLVER_LEAN to a pinned compiler')
class NativeAutoSolverTests(unittest.TestCase):
    def run_native(self,statement,reference,proof):
        temp=tempfile.TemporaryDirectory(dir=os.environ.get('PROJECT_CACHE_DIR'));self.addCleanup(temp.cleanup)
        root=Path(temp.name).resolve();project=root/'project';project.mkdir()
        compiler=Path(os.environ['AUTOSOLVER_LEAN']).resolve()
        version=os.environ['AUTOSOLVER_LEAN_VERSION']
        (project/'lean-toolchain').write_text('leanprover/lean4:'+version+'\n')
        name=statement.split()[1]
        a.write(root/'problem.json',{'id':'native-test','name':name,'statement':statement,'reference':reference})
        a.write(root/'corpus.json',{'schema_version':1,'entries':[]})
        a.write(root/'responses.json',[a.canonical({'action':'propose','parent_id':'c000','strategy':'native fixture','proof':proof})])
        (root/'context.lean.in').write_text('{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n{{DECLARATION}}\n')
        config={'schema_version':1,'problem':str(root/'problem.json'),'template':str(root/'context.lean.in'),
                'project':str(project),'prompt':str(ROOT/'examples/actions/prompt.txt'),
                'agent':{'mode':'actions-v1','corpus':str(root/'corpus.json'),
                         'autosolver':{'tactics':['rfl'],'max_attempts':4,'inspection_seconds':30,'search_seconds':120}},
                'lean':{'toolchain':'leanprover/lean4:'+version,'command':[str(compiler),'-j1','-M2048'],
                        'timeout_seconds':60,'repetitions':1},
                'limits':{'max_calls':1,'max_proof_characters':4000,'max_feedback_characters':4000,'max_request_characters':40000},
                'model':{'backend':'fixture','responses':str(root/'responses.json')}}
        a.write(root/'config.json',config)
        result=h.run(root/'config.json',root/'run')
        self.assertTrue(result['state']['exploration']['candidates']['c001-auto']['valid'])
        self.assertEqual(result['state']['calls'],1)
        self.assertEqual(result['autosolver']['model_calls'],0)
        self.assertTrue(result['final_valid'])
        self.assertTrue(h.replay(root/'run')['record_replay_passed'])
        evidence=os.environ.get('AUTOSOLVER_EVIDENCE')
        if evidence:
            destination=Path(evidence)/version/self._testMethodName
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(root/'run',destination)
        return result
    def test_real_compiler_closes_failed_candidate_and_replays(self):
        statement='theorem native_identity (n : Nat) : n + 0 = n'
        self.run_native(statement,statement+' := by\n have h : n + 0 = n := Nat.add_zero n\n exact h\n',
                        'by exact missing_native_proof')
    def test_multiple_scoped_goals_and_unicode_offsets(self):
        statement='theorem native_σ (n : Nat) : n = n ∧ n = n'
        result=self.run_native(statement,statement+' := by constructor <;> rfl\n',
            'by\n constructor\n · exact missing_left\n · exact missing_right')
        self.assertEqual(result['autosolver']['verified_candidates'],1)
        self.assertEqual(result['state']['latest']['feedback']['autosolver']['sites_closed'],2)


if __name__=='__main__':unittest.main()
