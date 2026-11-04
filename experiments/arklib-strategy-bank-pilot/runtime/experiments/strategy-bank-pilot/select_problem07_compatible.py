#!/usr/bin/env python3
"""User-authorized ranked compatibility selection of the new run's recorded candidates. No API calls."""
import ast,csv,difflib,hashlib,html,importlib.util,json,statistics,sys,zipfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO/'src'))
from lean_agent import harness as h,prepared

def read(p):return json.loads(p.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    source=REPO/'work/arklib10/problem07-core-rerun-01';root=REPO/'work/arklib10/problem07-ranked-compatibility-01';out=REPO/'../../outputs/arklib07-ranked-compatibility'
    out=out.resolve()
    if root.exists():raise ValueError('Preserve prior selection audit; use a fresh root')
    root.mkdir(parents=True);out.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('pilot_tools',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    problem=read(source/'inputs/07/problem.json');envs=read(source/'inputs/07/environments.json');summary=read(source/'runs/07/summary.json');cs=summary['state']['exploration']['candidates']
    upstream=ast.parse((REPO/'work/arklib10/upstream-harness-latest.py').read_text());current=ast.parse((REPO/'src/lean_agent/harness.py').read_text())
    for name in ('candidate','ranking'):
        nodes=[next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name) for t in (upstream,current)]
        if ast.dump(nodes[0])!=ast.dump(nodes[1]):raise ValueError('Common ranking differs')
    replay=h.replay(source/'runs/07')
    if not replay['record_replay_passed']:raise ValueError('Recorded generation replay failed')
    m.write(root/'replay.json',replay)
    unique={c['sha256']:(cid,c) for cid,c in cs.items() if c.get('valid')};ranked=sorted(unique.values(),key=lambda x:h.ranking(x[1]))
    baseline=summary['state']['baseline'];ranking=[]
    for n,(cid,c) in enumerate(ranked,1):
        ranking.append({'rank':n,'candidate_id':cid,'sha256':c['sha256'],'tokens':c['tokens'],'screening_hb':c['raw_heartbeats'],'core_ratio_sum':c['tokens']/baseline['tokens']+c['raw_heartbeats']/baseline['raw_heartbeats'],'compatibility_status':'not_checked','checked_versions':{},'selected':False})
    m.write(root/'ranked-candidates.json',ranking)
    guard=prepared.PreparedLeanEvaluator(source/'prepared-v4.31.0.json');guard.verify(full=True);mod=m.pinned_module(source)
    for e in envs:m.check_pin(e)
    ledger_before=(source/'budget.json').read_bytes();core_selected=(source/'runs/07/selected.lean').read_bytes();chosen=None;chosen_checks=None
    for row,(cid,c) in zip(ranking,ranked):
        m.log('candidate_start',rank=row['rank'],candidate_id=cid,tokens=c['tokens'],core_ratio_sum=row['core_ratio_sum'])
        checks={};candidate_ok=True
        # Version order affects CPU work only, never candidate rank or acceptance requirements.
        for e in sorted(envs,key=lambda x:x['id']!='v4.30.0'):
            code=c['code'];cached=None;cache_path=None
            if c['sha256']==sha(core_selected):cache_path=source/'version-checks'/e['id']/'candidate'
            elif cid=='c000':cache_path=source/'version-checks'/e['id']/'baseline'
            if cache_path is not None:cached=m.cached_verification(mod,e,code,problem,cache_path,3)
            if cached is not None:
                r=cached;ref=str(cache_path/'result.json');origin='integrity_checked_same_run_receipt'
            else:
                ev=m.adapter_class(mod,guard)(e);before=ev.fingerprint(e);folder=root/'checks'/cid/e['id']
                r=ev.evaluate(code,problem,[],folder,3);m.write(folder/'result.json',r)
                if ev.fingerprint(e)!=before:raise ValueError('Environment changed')
                ref=str(folder/'result.json');origin='fresh_check_and_three_measurements_if_valid'
            checks[e['id']]=r;row['checked_versions'][e['id']]={'valid':r['valid'],'receipt':ref,'origin':origin}
            if h.environment_failed(r) or any((x.get('error') or {}).get('kind') in ('environment','timeout') for x in r['environments'].values()):raise ValueError('Resource/environment failure; not a proof rejection')
            m.log('version_result',rank=row['rank'],candidate_id=cid,version=e['id'],valid=r['valid'],origin=origin)
            if not r['valid']:
                candidate_ok=False;row['compatibility_status']='rejected';break
        if candidate_ok:
            if set(checks)!={e['id'] for e in envs}:raise ValueError('Missing required version')
            row['compatibility_status']='all_versions_passed';row['selected']=True;chosen=(cid,c);chosen_checks=checks
        m.write(root/'ranked-candidates.json',ranking)
        if chosen:break
    if chosen is None:raise ValueError('No candidate, including original, passed all designated versions')
    guard.verify(full=True)
    if (source/'budget.json').read_bytes()!=ledger_before or (source/'runs/07/selected.lean').read_bytes()!=core_selected:raise ValueError('Original generation evidence changed')
    cid,c=chosen;metrics=[]
    for e in envs:
        bdir=source/'version-checks'/e['id']/'baseline';b=m.cached_verification(mod,e,problem['reference'],problem,bdir,3)
        if b is None or not b['valid']:raise ValueError('Missing validated original baseline')
        def hb(r):return statistics.median(x['measurement']['raw'] for x in r['environments'][e['id']]['runs'] if 'measurement' in x)
        bh,ch=hb(b),hb(chosen_checks[e['id']]);metrics.append({'version':e['id'],'original_tokens':b['tokens'],'selected_tokens':c['tokens'],'original_hb':bh,'selected_hb':ch,'hb_reduction_pct':100*(1-ch/bh),'valid':True})
    length=100*(1-c['tokens']/baseline['tokens']);heartbeat=statistics.mean(x['hb_reduction_pct'] for x in metrics)
    result={'generated_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),'problem':problem['name'],'source_generation':str(source),'selection_policy':'common h.ranking order; first all-designated-version-valid candidate, including original as ranked candidate','policy_authorization':'user requested sequential compatibility rejection and next-ranked selection after the common-core rerun','selected_id':cid,'selected_rank':next(x['rank'] for x in ranking if x['selected']),'selected_sha256':c['sha256'],'generated_primary_valid_unique_candidates':len(ranked)-1,'ranked_candidates_including_original':len(ranked),'checked_candidates':sum(x['compatibility_status']!='not_checked' for x in ranking),'rejected_candidates':sum(x['compatibility_status']=='rejected' for x in ranking),'required_versions':len(envs),'passed_versions':len(envs),'original_tokens':baseline['tokens'],'selected_tokens':c['tokens'],'length_reduction_pct':length,'hb_reduction_pct_mean_within_version':heartbeat,'compatibility_pct':100,'local_combined_score':(length+heartbeat+100)/3,'additional_api_calls':0,'additional_api_cost_usd':'0','source_generation_api_cost_usd':summary['state']['cost_usd'],'version_metrics':metrics,'candidates':ranking,'evidence_unchanged':True,'invoice_verified':False,'official_worker_score':False}
    for target in (root,out):
        m.write(target/'result.json',result);(target/'selected.lean').write_text(c['code'])
    m.write(out/'ranked-candidates.json',ranking)
    with (out/'ranked-candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        columns=['rank','candidate_id','tokens','screening_hb','core_ratio_sum','compatibility_status','selected'];w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(ranking)
    with (out/'metrics-by-version.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(metrics[0]));w.writeheader();w.writerows(metrics)
    (out/'candidate.jsonl').write_text(json.dumps({'name':problem['name'],'proof':c['code']},ensure_ascii=False)+'\n')
    (out/'original-to-selected.patch').write_text(''.join(difflib.unified_diff(problem['reference'].splitlines(True),c['code'].splitlines(True),fromfile='original.lean',tofile='selected.lean')))
    intro='이번 새 실행의 유효 후보를 공통 핵심 순위로 정렬하고, 호환성 실패 시 다음 후보를 검사했습니다. 원본도 순위 목록의 후보로만 처리했습니다. 첫 전체 버전 통과 후보에서 종료하며, 그 아래 후보는 미검사로 표시합니다. 추가 모델 호출은 없습니다.'
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>7번 점수순 호환성 선택</title><style>body{font:16px system-ui;max-width:1100px;margin:32px}pre{white-space:pre-wrap}</style><h1>7번 점수순 호환성 선택</h1><p>'+intro+'</p><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre>')
    (out/'README.txt').write_text(intro+'\n\n생성 실행의 공통 핵심 best와 본 호환성 선택 결과는 별도 보존했습니다. 기존 결과를 덮어쓰지 않았습니다.\n기존 c039 영수증은 전체 소스·로그·명령·계측 해시를 확인해 재사용했고, 나머지는 새로 검사했습니다. 버전 실패 시 불필요한 후속 버전 검사는 생략하되, 채택 후보는 모든 버전 3회 계측을 확인했습니다.\n')
    m.log('complete',selected_id=cid,selected_rank=result['selected_rank'],checked_candidates=result['checked_candidates'],rejected_candidates=result['rejected_candidates'],additional_api_cost_usd='0')
if __name__=='__main__':main()
