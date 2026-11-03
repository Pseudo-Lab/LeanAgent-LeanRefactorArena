#!/usr/bin/env python3
"""Export a completed single-problem common-core run; never infer all-version acceptance."""
import argparse,csv,difflib,hashlib,html,importlib.util,json,statistics,sys,zipfile
from decimal import Decimal
from pathlib import Path
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO/'src'))
from lean_agent import harness,budgeting,openai_direct,models

def read(p):return json.loads(p.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2))
def main(root,out):
    result=read(root/'result.json');out.mkdir(parents=True,exist_ok=True);run=root/'runs/07';ledger=read(root/'budget.json')
    spent=Decimal(0);seen=set()
    for c in ledger['calls']:
        if c['status']!='settled' or c['key'] in seen:raise ValueError('Unsettled or duplicate request')
        seen.add(c['key']);folder=run/'steps'/f"{c['step']:03}"
        request=read(folder/'request.json');bound=Decimal(budgeting.request_cost(request)['reserved_usd'])
        raw=read(root/'provider-responses'/c['problem']/(str(c['step'])+'.json'))
        cost=Decimal(openai_direct.compute_cost(raw)['cost_usd'])
        if cost!=Decimal(c['charged_usd']) or bound!=Decimal(c['reserved_usd']):raise ValueError('Cost mismatch')
        if cost>bound or spent+bound>Decimal('2.50'):raise ValueError('Budget exceeded')
        if openai_direct.normalize(raw)!=read(folder/'response.json'):raise ValueError('Receipt mismatch')
        spent+=cost
    if spent!=Decimal(result['cost_usd']):raise ValueError('Total cost mismatch')
    replay=harness.replay(run)
    if not replay['record_replay_passed']:raise ValueError('Replay failed')
    proof=(run/'selected.lean').read_bytes();summary=read(run/'summary.json')
    if sha(proof)!=result['selected_sha256'] or sha(proof)!=summary['state']['best']['sha256']:raise ValueError('Selected proof differs from core best')
    policy=read(root/'selection-policy.json')
    if sha((REPO/'src/lean_agent/harness.py').read_bytes())!=policy['core_file_sha256']:raise ValueError('Core changed')
    problem=read(run/'input/problem.json');dataset=Path('<LOCAL_HOME>/_feynlang/temp3/benchmark_data_final.jsonl')
    original=next(x for x in map(json.loads,dataset.read_text().splitlines()) if x['name']==problem['name'])
    if original['src']!=problem['reference'] or original['statement']!=problem['statement']:raise ValueError('Official input mismatch')
    rows=[]
    for v in result['versions']:
        row={'version':v['version'],'baseline_tokens':v['baseline']['tokens'],'candidate_tokens':v['candidate']['tokens']}
        for label in ('baseline','candidate'):
            r=v[label];e=r['environments'][v['version']];samples=[x['measurement']['raw'] for x in e['runs'] if 'measurement' in x]
            if e['valid'] and len(samples)!=3:raise ValueError('Missing samples')
            row[label+'_valid']=e['valid'];row[label+'_hb']=statistics.median(samples) if samples else None
        row['hb_reduction_pct']=100*(1-row['candidate_hb']/row['baseline_hb']) if row['candidate_valid'] and row['baseline_hb'] else None
        rows.append(row)
    result['version_metrics']=rows;result['compatibility_pct']=100*result['passed_versions']/result['required_versions']
    result['length_reduction_pct']=100*(1-result['tokens']/result['baseline_tokens'])
    result['historical_plus_new_problem_cost_usd']=str(spent+Decimal(result['historical_problem_cost_usd']))
    result['all_version_mean_hb_score']=statistics.mean(x['hb_reduction_pct'] for x in rows) if all(x['hb_reduction_pct'] is not None for x in rows) else None
    write(out/'result.json',result);write(out/'budget.json',ledger);write(out/'selection-policy.json',policy)
    audit={'passed':True,'all_calls_settled':True,'calculated_cost_usd':str(spent),'new_budget_usd':'2.50','calls':len(seen),'duplicates':False,'pre_dispatch_reservations_within_cap':True,'raw_provider_cost_reconciled':True,'record_replay_passed':True,'selected_matches_core_best':True,'core_source_unchanged':True,'postchecks_did_not_replace_selection':True,'invoice_verified':False}
    write(out/'audit.json',audit);write(out/'replay.json',replay)
    (out/'selected.lean').write_bytes(proof);(out/'original-to-selected.patch').write_text(''.join(difflib.unified_diff(problem['reference'].splitlines(True),proof.decode().splitlines(True),fromfile='original.lean',tofile='selected.lean')))
    (out/'candidate.jsonl').write_text(json.dumps({'name':problem['name'],'proof':proof.decode()},ensure_ascii=False)+'\n')
    with (out/'versions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    history=[];last=read(run/'initial-state.json')['best']['sha256']
    for event in sorted((run/'steps').glob('*/event.json')):
        e=read(event);state=e['state_after'];a=e.get('action') or {};best=state['best'];ids=[k for k,c in state['exploration']['candidates'].items() if c['sha256']==best['sha256']]
        history.append({'step':int(event.parent.name),'action':a.get('action'),'parent_id':a.get('parent_id'),'feedback_status':(state.get('latest') or {}).get('feedback',{}).get('status'),'best_updated':best['sha256']!=last,'best_candidate_ids':','.join(ids),'best_tokens':best['tokens'],'best_raw_hb':best['raw_heartbeats'],'best_sha256':best['sha256']});last=best['sha256']
    with (out/'selection-history.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(history[0]));w.writeheader();w.writerows(history)
    intro='7번만 원본에서 새로 생성한 독립 $2.50 실행입니다. 공통 h.run의 best 갱신·최종 선택을 그대로 사용했습니다. 버전별 사후 검사는 선택된 증명을 교체하지 않습니다. API 비용은 토큰 사용량과 고정 단가의 계산액이며 청구서 확인액이 아닙니다.'
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>ArkLib 7번 공통 하네스 단독 재실행</title><style>body{font:16px system-ui;max-width:1100px;margin:32px}pre{white-space:pre-wrap}</style><h1>ArkLib 7번 공통 하네스 단독 재실행</h1><p>'+intro+'</p><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre>')
    (out/'README.txt').write_text(intro+'\n\n'+json.dumps(audit,ensure_ascii=False,indent=2)+'\n\n과거 실행과 이번 실행은 분리했습니다. 이번 selected.lean은 공통 핵심 하네스의 출력 그대로입니다. 실패한 버전의 HB는 미측정이며 0으로 바꾸지 않습니다. 일부 버전 실패 시 전체 버전 평균 HB 점수는 산출하지 않습니다.\n')
    key=models.load_key(Path('<LOCAL_HOME>/Documents/Codex/2026-11-03/x20/work/openai.env'),names=('OPENAI_API_KEY','OPENROUTER_API_KEY')).encode()
    scan=[p for base in (root,out) for p in base.rglob('*') if p.is_file() and p.suffix!='.zip']
    if any(p.name.endswith('.env') or key in p.read_bytes() for p in scan):raise ValueError('Credential content found; refuse archive')
    audit['credential_scan_passed']=True;write(out/'audit.json',audit)
    with zipfile.ZipFile(out/'implementation-evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix not in ('.lock','.pyc') and '__pycache__' not in p.parts:z.write(p,'evidence/'+str(p.relative_to(root)))
        for name in ('rerun_problem07.py','report_problem07_rerun.py'):z.write(Path(__file__).with_name(name),'implementation/'+name)
        for p in sorted(out.iterdir()):
            if p.is_file() and p.suffix!='.zip':z.write(p,'report/'+p.name)
    with zipfile.ZipFile(out/'implementation-evidence.zip') as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
    print(json.dumps({'cost_usd':str(spent),'api_calls':len(seen),'tokens':result['tokens'],'passed_versions':result['passed_versions'],'required_versions':result['required_versions'],'audit_passed':True}))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();main(v.root.resolve(),v.output.resolve())
