#!/usr/bin/env python3
"""Build a standalone pilot report from settled receipts and full-version verification."""
import argparse,csv,hashlib,html,json,statistics,difflib
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

def read(p):return json.loads(p.read_text())
def hb(r):return {k:statistics.median(x['measurement']['raw'] for x in v['runs'] if 'measurement' in x) if v['valid'] else None for k,v in r['environments'].items()}
def build(root,out,dataset):
    out.mkdir(parents=True,exist_ok=True)
    plan=read(root/'plan.json');results=read(root/'results.json') if (root/'results.json').exists() else []
    ledger=read(root/'budget.json') if (root/'budget.json').exists() else {'calls':[]}
    if hashlib.sha256(dataset.read_bytes()).hexdigest()!=plan['dataset_sha256']:raise ValueError('Dataset changed')
    rows=[];jsonl=[];version_rows=[];originals={r['name']:r for r in map(json.loads,dataset.read_text().splitlines())}
    for item in plan['problems']:
        result=next((r for r in results if r['name']==item['name']),None)
        spent=str(sum((Decimal(c.get('charged_usd') or '0') for c in ledger['calls'] if c['problem']==item['name']),Decimal('0')))
        row={'index':item['index'],'name':item['name'],'cost_usd':spent,'status':'not_started'}
        actual_problem=root/'runs'/f"{item['index']:02}"/'input/problem.json'
        observed_problem=read(actual_problem) if actual_problem.exists() else read(Path(item['input'])/'problem.json')
        row['input_policy']='single_reference_with_version_info_v2' if 'original' not in observed_problem and 'version_info' in observed_problem else 'legacy_duplicate_reference_v1'
        events=sorted((root/'runs'/f"{item['index']:02}"/'steps').glob('*/event.json'))
        if events and not result:
            state=read(events[-1])['state_after']
            row.update(status='screening_or_final_verification',completed_steps=len(events),
                       screening_best_tokens=state['best']['tokens'],screening_raw_heartbeats=state['best']['raw_heartbeats'],
                       screening_version='v4.31.0',all_versions_valid=None)
        initial_request=root/'runs'/f"{item['index']:02}"/'steps/001/request.json'
        if initial_request.exists():
            packet=json.loads(read(initial_request)['messages'][1]['content'])
            row['initial_recommended_ids']=[c['id'] for c in packet.get('strategy_bank',{}).get('strategies',[])]
            declared=set();recommended=set()
            for event in events:
                declared.update((read(event).get('action') or {}).get('strategy_ids',[]))
                request_packet=json.loads(read(event.parent/'request.json')['messages'][1]['content'])
                recommended.update(c['id'] for c in request_packet.get('strategy_bank',{}).get('strategies',[]))
            row['declared_selected_ids']=sorted(declared)
            row['ever_recommended_ids']=sorted(recommended)
        review_path=root/'reviews'/f"{item['index']:02}.json"
        if review_path.exists():
            row['source_review']=read(review_path)
            row['observed_bank_ids']=[x['strategy_id'] for x in row['source_review']['observed_bank_mechanisms']]
        if result:
            archive=read(root/'runs'/f"{item['index']:02}"/'summary.json')['state']['exploration']['candidates']
            final_id='c000' if result['selection']=='baseline' else result['selection']
            row['final_declared_strategy_ids']=archive[final_id].get('strategy_ids',[])
            pending=[final_id];seen=set();lineage_ids=set()
            while pending:
                cid=pending.pop()
                if cid in seen:continue
                seen.add(cid);candidate=archive[cid]
                lineage_ids.update(candidate.get('strategy_ids',[]))
                if candidate.get('parent_id'):pending.append(candidate['parent_id'])
                pending.extend(candidate.get('source_candidate_ids',[]))
            row['lineage_declared_strategy_ids']=sorted(lineage_ids)
            baseline=read(root/'verification'/f"{item['index']:02}"/'baseline/result.json')
            selected=read(root/'verification'/f"{item['index']:02}"/result['selection']/'result.json') if result['selection']!='baseline' else baseline
            row.update(result,status='completed',baseline_hb=hb(baseline),selected_hb=hb(selected),token_reduction_pct=100*(1-selected['tokens']/baseline['tokens']))
            src=(root/'selected'/f"{item['index']:02}.lean").read_text()
            if hashlib.sha256(src.encode()).hexdigest()!=result['selected_sha256']:raise ValueError('Selected proof hash changed')
            (out/'diffs').mkdir(exist_ok=True)
            (out/'diffs'/f"{item['index']:02}.patch").write_text(''.join(difflib.unified_diff(originals[item['name']]['src'].splitlines(True),src.splitlines(True),fromfile='original.lean',tofile='selected.lean')))
            for version,b in hb(baseline).items():
                c=hb(selected)[version]
                version_rows.append({'index':item['index'],'name':item['name'],'version':version,'original_tokens':baseline['tokens'],'selected_tokens':selected['tokens'],'original_raw_hb':b,'selected_raw_hb':c,'hb_reduction_pct':100*(1-c/b) if b and c is not None else None,'valid':selected['environments'][version]['valid']})
            (out/'proofs').mkdir(exist_ok=True);(out/'proofs'/f"{item['index']:02}.lean").write_text(src)
            obj=dict(originals[item['name']]);obj['src']=src
            # Keep original proof_length metadata in source dataset; measured token counts live in result records.
            jsonl.append({'name':obj['name'],'proof':src})
        rows.append(row)
    value={'generated_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),'scope':'ArkLib 10, 20-card Bank top-1 contextual retrieval; single-arm pilot',
           'model':'gpt-6.1-sol','provider':'OpenAI direct','reasoning_effort':'high','total_cap_usd':'25.00','per_problem_cap_usd':'2.50',
           'charged_usd':str(sum((Decimal(c.get('charged_usd') or '0') for c in ledger['calls']),Decimal('0'))),
           'input_adapter_correction':read(root/'input-policy-update.json') if (root/'input-policy-update.json').exists() else None,
           'billing_basis':'provider token usage times frozen public list prices; not invoice verified',
           'prior_unknown_reservation_usd':ledger.get('prior_unsettled_reservation_usd','0'),
           'calls':len(ledger['calls']),'unsettled_calls':[c['key'] for c in ledger['calls'] if c['status']!='settled'],
           'completed_problems':len(results),'problems':rows,
           'interpretation':'Observed candidates and joint effects; no baseline arm, causal strategy effect or holdout-generalization claim.'}
    (out/'results.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
    (out/'candidates.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in jsonl))
    (out/'budget.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    with (out/'metrics-by-version.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['index','name','version','original_tokens','selected_tokens','original_raw_hb','selected_raw_hb','hb_reduction_pct','valid']);w.writeheader();w.writerows(version_rows)
    with (out/'strategy-alignment.csv').open('w',encoding='utf-8-sig',newline='') as f:
        columns=['index','name','initial_recommended_ids','ever_recommended_ids','declared_selected_ids','final_declared_strategy_ids','lineage_declared_strategy_ids','observed_bank_ids','status']
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
    headers=['index','name','input_policy','status','selection','cost_usd','baseline_tokens','selected_tokens','token_reduction_pct','all_versions_valid','stop_reason']
    with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers,extrasaction='ignore');w.writeheader();w.writerows(rows)
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(k,'')))+'</td>' for k in headers)+'</tr>' for r in rows)
    panels=[]
    for r in rows:
        proof=''
        if r['status']=='completed':
            index=f"{r['index']:02}"
            proof=('<details><summary>원본 → 최종 채택 diff</summary><pre>'+html.escape((out/'diffs'/(index+'.patch')).read_text())+'</pre></details>'
                   '<details><summary>전체 버전 검증을 마친 채택 증명</summary><pre>'+html.escape((out/'proofs'/(index+'.lean')).read_text())+'</pre></details>')
        panels.append('<details><summary>'+html.escape(r['name'])+'</summary><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre>'+proof+'</details>')
    details=''.join(panels)
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>ArkLib Strategy Bank pilot</title><style>body{font:15px system-ui;margin:32px;max-width:1400px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px}pre{white-space:pre-wrap;max-height:65vh;overflow:auto;padding:12px;background:#f6f8fa}details{margin:16px 0}</style><h1>ArkLib 10문제 Strategy Bank 실측</h1><p>갱신: '+html.escape(value['generated_at'])+' (한국 시간)</p><p>새 20개 Bank·contextual retriever·top-1, GPT-6.1 Sol high / OpenAI 직접 API. 비용은 제공 토큰 사용량과 고정 공개 단가로 계산하며 청구서 확인액이 아닙니다. 탐색적 단일 조건 파일럿이며 5개/20개 비교실험은 아닙니다. 미시작 8–10번 입력에는 중복 원본 제거·공식 version_info 보강을 적용했고 이전 결과는 보존했습니다. 전략 ID는 모델의 선택 선언이고 실제 적용·인과 효과는 별도 검토 대상입니다.</p><p>완료 '+str(len(results))+'/10 · API 비용 $'+str(value['charged_usd'])+' / $25 상한</p><p>탐색은 Lean 4.31.0에서 1회 계측, 최종 비교는 모든 지정 버전에서 원본과 후보를 새로 컴파일·3회 계측합니다. 공식 worker 점수나 대회 누적비용 인증은 아닙니다.</p><table><tr>'+''.join('<th>'+k+'</th>' for k in headers)+'</tr>'+table+'</table>'+details)
    return value
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--dataset',type=Path,required=True);args=ap.parse_args();v=build(args.root,args.output,args.dataset);print(json.dumps({k:v[k] for k in ('completed_problems','charged_usd','calls','unsettled_calls')}))
