import json
import argparse
from decimal import Decimal
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser(description='Offline run report: no model or Lean calls')
ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args();ROOT=a.output.resolve()
protocol=json.loads((ROOT/'protocol.json').read_text())
CAP=Decimal(protocol['per_problem_usd'])
DIRECT=protocol.get('backend')=='openai'
COST_BASIS='usage_estimate' if DIRECT else 'provider_reported'
ledger=json.loads((ROOT/'budget.json').read_text())
rows=[];bundle=[]
lines=[f"{'OpenAI 직접 API' if DIRECT else 'OpenRouter'} 실행 보고서, 문제당 ${CAP} 사전 예약 제한",
       f"모델 {protocol['model']}, reasoning high.",
       '원본과 기존 API 문맥에서 시작. 88점 제출본과 이전 실험 후보는 API 입력에 포함하지 않음.',
       'v3 공통 지시 + P02/P04/P05 v3 지시. P01/P03은 기존 문제별 지시.',
       ('OpenAI 비용은 저장된 단가표와 응답 usage로 계산한 추정액이며 청구 영수증이 아님.' if DIRECT else 'OpenRouter 비용은 응답 usage.cost로 정산한 청구액.'),
       '호출 전 최대 비용을 예약. 최대 출력16384, 잔액에 따라 최소4096까지 줄임.',
       '서버 측 달러 잠금이 아니며 입력 byte 상한, 출력 한도, 단가와 여유분을 적용한 로컬 제한.',
       'HB(k)는 3회 측정 중앙값. 선택 기준 T/T0 + rawHB/rawHB0. 공식 Arena 점수 아님.',
       'P03은 Lean4.26 단일 환경. 이전 결과와 비교는 동일 환경의 과거 측정.',
       'API에는 고정 문맥, 자체 시도 이력, 최선과 최근3개 후보, 조건부 자체 프로파일을 제공한다.',
       'Codex 서브 에이전트와 시스템 지시·도구·이력 전달 방식이 달라 순수 모델 비교는 아니다.','']
for pid in protocol['order']:
    folder=ROOT/pid;sf=folder/'summary.json'
    if not sf.exists():continue
    s=json.loads(sf.read_text());entries={k:v for k,v in ledger['attempts'].items() if k.startswith(pid+'/')}
    cost=sum((Decimal(v['cost_usd']) for v in entries.values() if v['cost_usd'] is not None),Decimal(0))
    s['cost_usd']=str(cost)
    s['cost_basis']=COST_BASIS
    verified=all(v['status']=='settled' and Decimal(v['cost_usd'])<=Decimal(v['reserved_usd']) for v in entries.values())
    s['budget_verified']=verified and cost<=CAP
    s['api_calls']=len(entries)
    s['valid_candidates']=sum(x['valid'] for x in s['history'])
    hashes=[x['proof_sha256'] for x in s['history'] if x.get('proof_sha256')]
    s['duplicate_candidates']=len(hashes)-len(set(hashes))
    prefix=[x for x in s['history'][:10] if x['valid']]
    s['best_within_first_ten']=min(prefix,key=lambda x:x['objective']) if prefix else None
    cumulative=Decimal(0);s['last_improvement_cost_usd']='0'
    for item in s['history']:
        cumulative+=Decimal(item['cost_usd'])
        if item['improved']:s['last_improvement_cost_usd']=str(cumulative)
    feedback=[json.loads(f.read_text()) for f in folder.glob('*-feedback.json')]
    s['evaluation_compiles']=sum(x['lean_compiles'] for x in feedback)
    s['evaluation_seconds']=round(sum(x['seconds'] for x in feedback),2)
    profiles=[json.loads(f.read_text()) for f in folder.glob('*-profile/profile.json')]
    s['profile_compiles']=sum(sum(k in p for k in ['profiled','plain']) for p in profiles)
    s['usage']={'prompt_tokens':0,'completion_tokens':0,'reasoning_tokens':0}
    for f in folder.glob('*-response.json'):
        u=json.loads(f.read_text()).get('usage') or {}
        for k in ['prompt_tokens','completion_tokens']:s['usage'][k]+=u.get(k,0) or 0
        s['usage']['reasoning_tokens']+=(u.get('completion_tokens_details') or {}).get('reasoning_tokens',0) or 0
    s['previous_v1']=s['previous_v2']=s['reference88']=None
    for name,run in [('v1','prompt-trial-20261029-sequential'),('v2','prompt-trial-20261029-recompose-v2')]:
        oldpath=REPO/'runs'/run/pid/'summary.json'
        if not oldpath.exists():continue
        old=json.loads(oldpath.read_text())
        s['previous_'+name]={'tokens':old['best']['tokens'],'hb_k':old['best']['hb_k']}
        if name=='v1':s['reference88']={'tokens':old['reference88']['tokens'],'hb_k':old['reference88']['hb_k']}
    rows.append(s)
    inp=json.loads((folder/'input.json').read_text())
    bundle.append({'name':inp['problem']['name'],'proof':s['best']['code']})
    lines += [f"{pid}: {s['status']}; calls={len(entries)}, valid={s['valid_candidates']}, cost=${cost}; budget_ok={s['budget_verified']}",
              f"Original {s['baseline']['tokens']}/{s['baseline']['hb_k']}k → best {s['best']['tokens']}/{s['best']['hb_k']}k ({s['best']['label']}); objective {s['objective_best']:.6f}",
              'attempt      valid  Length  HB(k)    accounted USD  improved']
    for a in s['history']:
        lines.append(f"{a['label']:<12} {str(a['valid']):<6} {str(a['tokens']):>6} {str(a['hb_k']):>7} {a['cost_usd']:>13} {a['improved']}")
    lines += [f"v1: {s['previous_v1']}; v2: {s['previous_v2']}; reference88: {s['reference88']}",
              f"Stop: {s.get('stop_reason','running')}; evaluation compiles={s['evaluation_compiles']}; profiles={s['profile_compiles']}",'']
totals={'cost_basis':COST_BASIS,'calls':sum(x['api_calls'] for x in rows),'valid_candidates':sum(x['valid_candidates'] for x in rows),
        'cost_usd':str(sum((Decimal(x['cost_usd']) for x in rows),Decimal(0))),
        'evaluation_compiles':sum(x['evaluation_compiles'] for x in rows),
        'profile_compiles':sum(x['profile_compiles'] for x in rows),
        'all_receipts_settled':all(x['status']=='settled' for x in ledger['attempts'].values()),
        'all_problem_budgets_verified':all(x['budget_verified'] for x in rows)}
(ROOT/'report.json').write_text(json.dumps({'problems':rows,'totals':totals},ensure_ascii=False,indent=2))
(ROOT/'report.txt').write_text('\n'.join(lines)+'\n'+json.dumps(totals,ensure_ascii=False)+'\n')
(ROOT/'best.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in bundle))
print(json.dumps(totals,ensure_ascii=False))
for s in rows:print(s['problem'],s['status'],s['api_calls'],s['cost_usd'],s['best']['tokens'],s['best']['hb_k'])
