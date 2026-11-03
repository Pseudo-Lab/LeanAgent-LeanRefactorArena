#!/usr/bin/env python3
"""New $2.50 problem07 generation through common h.run; postchecks never select or replace."""
import ast,hashlib,importlib.util,json,shutil,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO/'src'))
from lean_agent import harness as h,prepared

def main():
    old=REPO/'work/arklib10/pilot-openai-01';root=REPO/'work/arklib10/problem07-core-rerun-01'
    if root.exists():raise ValueError('Never automatically rerun a paid root')
    # Check before preparing any paid request.
    upstream=REPO/'work/arklib10/upstream-harness-latest.py';current=REPO/'src/lean_agent/harness.py'
    trees=[ast.parse(p.read_text()) for p in (upstream,current)]
    names=('metrics','candidate','ranking','initial_state','advance')
    for name in names:
        nodes=[next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name) for t in trees]
        if ast.dump(nodes[0])!=ast.dump(nodes[1]):raise ValueError('Core selection differs: '+name)
    def selected_write(tree):
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        return [ast.dump(n) for n in ast.walk(run) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id=='selected' and n.value.func.attr=='write_text']
    if selected_write(trees[0])!=selected_write(trees[1]):raise ValueError('Core final selection differs')
    core_hash=hashlib.sha256(current.read_bytes()).hexdigest()
    spec=importlib.util.spec_from_file_location('pilot_tools',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root.mkdir(parents=True);dest=root/'inputs/07';dest.mkdir(parents=True)
    oldinput=old/'inputs/07'
    for name in ('problem.json','environments.json','context.lean.in','prompt.txt','corpus.json'):shutil.copy2(oldinput/name,dest/name)
    shutil.copy2(old/'prepared-v4.31.0.json',root/'prepared-v4.31.0.json')
    config=m.read(oldinput/'config.json')
    for key,name in [('problem','problem.json'),('template','context.lean.in'),('prompt','prompt.txt')]:config[key]=str(dest/name)
    config['agent']['corpus']=str(dest/'corpus.json');config['lean']['prepared_environment']=str(root/'prepared-v4.31.0.json')
    m.write(dest/'config.json',config);envs=m.read(dest/'environments.json');problem=m.read(dest/'problem.json');primary=next(e for e in envs if e['id']=='v4.31.0')
    m.write(root/'budget.json',{'total_cap_usd':'2.50','problem_cap_usd':'2.50','calls':[],'budget_scope':'new independent problem07 rerun authorized by user; previous $1.6265804 is separate'})
    m.write(root/'plan.json',{'source':'arklib','problems':[{'index':7,'name':problem['name'],'input':str(dest),'required_versions':[e['id'] for e in envs]}],'model':config['model'],'total_cap_usd':'2.50','problem_cap_usd':'2.50','dataset_sha256':m.EXPECTED,'selection_policy':'unmodified common-core h.run; postchecks never replace selected proof','generation_start':'original reference; no historical generated candidate injected','max_calls':config['limits']['max_calls']})
    m.write(root/'selection-policy.json',{'upstream_commit':'a517db26b8eee1b58f30810dca5d66000c810748','identical_functions':list(names),'identical_final_selected_write':True,'core_file_sha256':core_hash,'version_checks_role':'diagnostic only; no reranking or fallback','new_budget_usd':'2.50'})
    mod=m.pinned_module(root);guard=prepared.PreparedLeanEvaluator(root/'prepared-v4.31.0.json');guard.verify(full=True)
    for e in envs:m.check_pin(e)
    run=root/'runs/07';m.log('new_run_start',problem=problem['name'],budget_usd='2.50',selection='common h.run unchanged')
    summary=h.run(dest/'config.json',run,evaluator=m.adapter_class(mod,guard)(primary),query=m.Ledger(root).query(problem['name'],run),dotenv=m.ENVFILE)
    if hashlib.sha256(current.read_bytes()).hexdigest()!=core_hash:raise ValueError('Core code changed during run')
    selected=(run/'selected.lean').read_bytes();best=summary['state']['best']
    if hashlib.sha256(selected).hexdigest()!=best['sha256']:raise ValueError('Core selected proof differs from state best')
    m.log('core_generation_complete',cost_usd=summary['state']['cost_usd'],tokens=best['tokens'],candidate_sha256=best['sha256'])
    rows=[]
    for e in envs:
        ev=m.adapter_class(mod,guard)(e);before=ev.fingerprint(e);row={'version':e['id'],'source_revision':e['sourceRevision']}
        for label,code in [('baseline',problem['reference']),('candidate',selected.decode())]:
            folder=root/'version-checks'/e['id']/label;m.log('diagnostic_version_check',version=e['id'],proof=label)
            result=ev.evaluate(code,problem,[],folder,3);m.write(folder/'result.json',result);row[label]=result
        if ev.fingerprint(e)!=before:raise ValueError('Environment changed')
        rows.append(row)
    guard.verify(full=True)
    if (run/'selected.lean').read_bytes()!=selected:raise ValueError('Postchecks modified common selection')
    ids=[k for k,c in summary['state']['exploration']['candidates'].items() if c['sha256']==best['sha256']]
    result={'generated_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),'problem':problem['name'],'run_status':summary['status'],'stop_reason':summary['stop_reason'],'selection_policy':'common core h.run, unchanged','selected_candidate_ids':ids,'selected_sha256':best['sha256'],'tokens':best['tokens'],'baseline_tokens':summary['state']['baseline']['tokens'],'cost_usd':summary['state']['cost_usd'],'cost_basis':'provider token usage times frozen prices, not invoice verified','api_calls':summary['state']['calls'],'new_budget_usd':'2.50','historical_problem_cost_usd':'1.6265804','versions':rows,'passed_versions':sum(row['candidate']['valid'] for row in rows),'required_versions':len(rows),'version_checks_change_selection':False,'model':'gpt-6.1-sol','reasoning_effort':'high','provider':'OpenAI direct','bank':'20 contextual top-1'}
    m.write(root/'result.json',result);m.log('run_complete',api_calls=result['api_calls'],cost_usd=result['cost_usd'],passed_versions=result['passed_versions'],required_versions=result['required_versions'])
if __name__=='__main__':main()
