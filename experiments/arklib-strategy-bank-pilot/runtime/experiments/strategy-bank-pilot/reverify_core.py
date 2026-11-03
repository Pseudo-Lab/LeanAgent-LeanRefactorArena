#!/usr/bin/env python3
"""Fresh per-version checks of a recorded common-core winner; never call a model or replace it."""
import argparse, ast, csv, hashlib, html, importlib.util, json, statistics, sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'src'))
from lean_agent import harness,prepared

def read(p):return json.loads(p.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def main(root,dest,output):
    if dest.exists():raise ValueError('Use a fresh output root; preserve old evidence')
    dest.mkdir(parents=True);output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('pilot_tools',Path(__file__).with_name('run.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    run=root/'runs/07';summary=read(run/'summary.json');best=summary['state']['best']
    proof=(run/'selected.lean').read_bytes()
    if sha(proof)!=best['sha256']:raise ValueError('Recorded core selection differs from best')
    ids=[cid for cid,c in summary['state']['exploration']['candidates'].items() if c['sha256']==best['sha256']]
    upstream=REPO/'work/arklib10/upstream-harness-latest.py'
    frozen=run/'code/lean_agent/harness.py'
    trees=[ast.parse(p.read_text()) for p in (upstream,frozen)]
    for name in ('metrics','candidate','ranking'):
        nodes=[next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name) for t in trees]
        if ast.dump(nodes[0])!=ast.dump(nodes[1]):raise ValueError('Selection function changed: '+name)
    replay=harness.replay(run)
    if not replay['record_replay_passed']:raise ValueError('Common replay failed')
    m.write(dest/'replay.json',replay)
    m.write(dest/'policy.json',{'selection':'recorded common-core best, unchanged','upstream_commit':'a517db26b8eee1b58f30810dca5d66000c810748','verified_identical_functions':['metrics','candidate','ranking'],'upstream_harness_sha256':sha(upstream.read_bytes()),'original_run':str(run),'candidate_ids':ids,'candidate_sha256':best['sha256'],'model_called':False,'fresh_lean_checks':True,'fallback_to_original':False})
    problem=read(run/'input/problem.json');envs=read(root/'inputs/07/environments.json')
    guard=prepared.PreparedLeanEvaluator(root/'prepared-v4.31.0.json');guard.verify(full=True)
    mod=m.pinned_module(root);rows=[];cost_before=(root/'budget.json').read_bytes()
    (dest/'selected.lean').write_bytes(proof)
    for e in envs:
        m.check_pin(e);ev=m.adapter_class(mod,guard)(e)
        before=ev.fingerprint(e);m.write(dest/e['id']/'fingerprint-before.json',before)
        row={'version':e['id'],'source_revision':e['sourceRevision']}
        for label,code in [('baseline',problem['reference']),('candidate',proof.decode())]:
            folder=dest/e['id']/label
            print(json.dumps({'event':'fresh_check','version':e['id'],'proof':label}),flush=True)
            value=ev.evaluate(code,problem,[],folder,3);m.write(folder/'result.json',value)
            v=value['environments'][e['id']]
            raw=[r['measurement']['raw'] for r in v['runs'] if 'measurement' in r]
            if v['valid'] and len(raw)!=3:raise ValueError('Missing fresh measurements')
            row[label]={'valid':v['valid'],'tokens':value['tokens'],'raw_hb_median':statistics.median(raw) if raw else None,'raw_samples':raw,'error':v.get('error')}
        after=ev.fingerprint(e)
        if after!=before:raise ValueError('Environment changed')
        m.write(dest/e['id']/'fingerprint-after.json',after);rows.append(row)
    guard.verify(full=True)
    if (root/'budget.json').read_bytes()!=cost_before:raise ValueError('Original cost ledger changed')
    passed=sum(r['candidate']['valid'] for r in rows)
    result={'generated_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),'problem':problem['name'],'candidate_ids':ids,'candidate_sha256':best['sha256'],'selection_policy':'common core best; per-version failures reported without replacement','additional_api_calls':0,'additional_api_cost_usd':'0','historical_problem_api_cost_usd':summary['state']['cost_usd'],'model_called':False,'fresh_lean_called':True,'record_replay_passed':True,'required_versions':len(rows),'passed_versions':passed,'compatibility_pct':100*passed/len(rows),'all_versions_valid':passed==len(rows),'versions':rows,'scope':'Reverification of the existing common-core selection, not regenerated candidates or a new paid run.'}
    m.write(dest/'result.json',result);m.write(output/'result.json',result)
    (output/'selected.lean').write_bytes(proof)
    with (output/'versions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        columns=['version','baseline_tokens','candidate_tokens','baseline_hb','candidate_hb','candidate_valid']
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for r in rows:w.writerow({'version':r['version'],'baseline_tokens':r['baseline']['tokens'],'candidate_tokens':r['candidate']['tokens'],'baseline_hb':r['baseline']['raw_hb_median'],'candidate_hb':r['candidate']['raw_hb_median'],'candidate_valid':r['candidate']['valid']})
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>7번 공통 핵심 하네스 후보 재검증</title><style>body{font:16px system-ui;margin:32px;max-width:1000px}pre{white-space:pre-wrap}</style><h1>7번 공통 핵심 하네스 후보 재검증</h1><p>기존 공통 핵심 하네스의 최고 후보를 유지하고 각 버전의 결과를 새로 검사했습니다. 모델 재생성이나 원본 fallback을 수행하지 않았습니다.</p><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre>')
    print(json.dumps({'event':'complete','passed_versions':passed,'required_versions':len(rows),'additional_api_cost_usd':'0'}),flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--destination',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();main(v.root.resolve(),v.destination.resolve(),v.output.resolve())
