"""Prepare a fixed, source-only cohort from original inputs, never old solutions."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'first-harness-jwkweon'
sys.path.insert(0,str(OLD))
import harness as h
sys.path.insert(0,str(HERE))
import worker

CODE={name:OLD/name for name in ['harness.py','models.py','evaluator/__init__.py','evaluator/lean.py','evaluator/tokens.py','evaluator/provenance.json']}
CODE.update({name:HERE/name for name in ['worker.py','policy.py','error_feedback.py']})


def setup(root,pid,mode,rep,origin):
    root.mkdir()
    for d in ['input','project','home','tmp','responses']:(root/d).mkdir()
    for filename in ['problem.json','source.lean','context.lean.in','environment.lock.json']:
        shutil.copyfile(OLD/'feedback-ablation-v1/inputs'/pid/filename,root/'input'/filename)
    shutil.copyfile(HERE/'prompts'/('control.txt' if mode=='A' else 'treatment.txt'),root/'input/prompt.txt')
    shutil.copyfile(origin/'lean_runner.py',root/'lean_runner.py')
    runtime=h.read(origin/'runtime.json');runtime.update(home=str(root/'home'),tmp=str(root/'tmp'))
    h.write(root/'runtime.json',runtime)
    (root/'project/lean-toolchain').write_text('leanprover/lean4:v4.26.0\n')
    for name,source in CODE.items():
        dest=root/'code'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    return {'trial_id':root.name,'problem_id':pid,'condition':mode,'repetition':rep,
        'max_proposals':6,'toolchain':'leanprover/lean4:v4.26.0'}


def freeze(root,config):
    h.write(root/'trial.json',config)
    files={str(p.relative_to(root)):h.digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    h.write(root/'manifest.json',{'files':files,'created_at':worker.now()})


def main(base,legacy):
    base.mkdir(parents=True,exist_ok=False)
    origins={'P01':legacy/'p01-p13-subagents-20261024/P01-r1','P13':legacy/'p13-budget10-subagents-20261024/P13-10-r1'}
    order=[('P01','A',1),('P13','B',1),('P01','B',1),('P13','A',1),('P01','B',2),('P13','A',2),('P01','A',2),('P13','B',2)]
    design={'created_at':worker.now(),'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=HERE,text=True).strip(),
        'conditions':{'A':'naive prompt + best/latest','B':'cost-hypothesis prompt + staged requests + family parents + Pareto memory'},
        'independent_variable':'Bundled prompt and state policy, not a single-factor prompt ablation',
        'constants':['original full source','fresh common baseline','same ranking','structured error feedback 1600 chars','six proposals including failures and duplicates','plain plus three fresh measurements per valid candidate','final verification','no old solutions or parent-chat context supplied'],
        'scope':'P01/P13 development pilot, not held-out generalization or official all-pin score',
        'proposal_budget':6,'checkpoints':[2,4,6],'max_solver_parallelism':2,'max_lean_parallelism':1,
        'planned_trials':[{'id':f'{p}-{m}-r{r}','problem':p,'condition':m,'repetition':r} for p,m,r in order],
        'model':'inherited fresh Codex subagents; exact backend ID, internal calls, sampling seed and cost unobservable',
        'api_calls':0,'os_isolation':False,'prompt_sha256':{m:h.digest((HERE/'prompts'/f).read_bytes()) for m,f in [('A','control.txt'),('B','treatment.txt')]},
        'code_sha256':{n:h.digest(p.read_bytes()) for n,p in CODE.items()}}
    h.write(base/'design.frozen.json',design)
    for pid,origin in origins.items():
        root=base/f'readiness-{pid}'
        config=setup(root,pid,'A',0,origin)
        # The readiness job has no solver and measures the original afresh.
        freeze(root,config)
        before=worker.load(root)[2]
        fp=worker.LeanEvaluator().fingerprint(before)
        problem=h.read(root/'input/problem.json')
        result=worker.evaluate(root,problem['reference'],root/'baseline')
        assert result['valid'],f'{pid} original failed: {result}'
        h.write(root/'readiness.json',{'valid':True,'metrics':h.metrics(result),'fingerprint':fp})
        print(json.dumps({'ready':pid,'metrics':h.metrics(result)}),flush=True)
    for pid,mode,rep in order:
        root=base/f'{pid}-{mode}-r{rep}';config=setup(root,pid,mode,rep,origins[pid])
        shutil.copytree(base/f'readiness-{pid}'/'baseline',root/'baseline')
        config['baseline_sha256']=h.digest((root/'baseline/result.json').read_bytes())
        freeze(root,config)
        subprocess.run([sys.executable,'-B',str(root/'code/worker.py'),'init',str(root)],check=True)
    print(json.dumps({'prepared':True,'trials':len(order),'proposals':6*len(order)}))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--legacy-runs',type=Path,required=True)
    a=ap.parse_args();main(a.output.resolve(),a.legacy_runs.resolve())
