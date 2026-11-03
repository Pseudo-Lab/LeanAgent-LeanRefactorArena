#!/usr/bin/env python3
"""Regenerate the source-reviewed observation ledger and mechanism Bank v2.

Review notes/definitions are explicit authored inputs, not automatic semantic
classifications. Hash-checked original/candidate pairs and original diff artifacts
are reused. Recommendations depend only on current input signals, not reviews.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import build_strategy_bank as v1
from lean_agent import strategy_bank as sb
from lean_agent import strategy_signals as signals


def build(benchmark, root=ROOT):
    source = root/'strategy-bank/review-v2'
    notes_bytes = (source/'observations.json').read_bytes()
    defs_bytes = (source/'definitions.json').read_bytes()
    notes = json.loads(notes_bytes)['observations']
    definitions = json.loads(defs_bytes)['definitions']
    if [r['pair'] for r in notes] != list(range(1,81)):
        raise ValueError('Expected one ordered review record for every pair')
    if len({c['id'] for c in definitions}) != len(definitions): raise ValueError('Duplicate mechanism')
    known = {c['id'] for c in definitions}
    generated = v1.build(benchmark, root)
    original_rows = [json.loads(l) for l in Path(benchmark).read_text().splitlines()]
    originals = {p['name']:p for p in original_rows}
    cases = json.loads(generated['evidence.json'])['candidates']
    candidate_rows = list(v1.candidates(root))
    reviewed = []
    for index,(case,note,raw) in enumerate(zip(cases,notes,candidate_rows),1):
        if not isinstance(note['mechanisms'],list) or set(note['mechanisms'])-known or len(set(note['mechanisms']))!=len(note['mechanisms']):
            raise ValueError('Unknown or repeated mechanism')
        before=originals[case['problem']]['src'];after=raw[1]
        clean_before=signals.clean(before);clean_after=signals.clean(after)
        changed=clean_before.split()!=clean_after.split()
        if not changed and note['mechanisms']: raise ValueError('Mechanism assigned to unchanged code')
        reviewed.append({**case,'pair':index,'mechanisms':note['mechanisms'],
                         'observation_ko':note['observation_ko'],
                         'review_status':'source-comparison-no-new-lean-run',
                         'text_changed':before!=after,'code_changed':changed,
                         'whole_candidate_improved':case['paired_ratio_sum']<2,
                         'classification':'authored-source-observation-not-causal-effect',
                         'strategy_candidates':note['mechanisms'],
                         'before_signals':signals.extract(originals[case['problem']]['statement'],before),
                         'after_signals':signals.extract(originals[case['problem']]['statement'],after)})
    bank_cards=[]
    stats=[]
    for definition in definitions:
        all_cases=[r for r in reviewed if definition['id'] in r['mechanisms']]
        supporting=[r for r in all_cases if r['whole_candidate_improved']]
        if not supporting: raise ValueError('No improved candidate observation for '+definition['id'])
        distinct=len({r['problem'] for r in supporting})
        bank_cards.append({**definition,'status':'observed-multiple-problems' if distinct>1 else 'observed-single-problem',
                           'evidence':[{'problem':r['problem'],'candidate_sha256':r['candidate_sha256']} for r in supporting]})
        stats.append({'id':definition['id'],'title_ko':definition['title_ko'],'observed_pairs':len(all_cases),
                      'supporting_improved_pairs':len(supporting),'distinct_supporting_problems':distinct,
                      'non_improving_pairs':[r['pair'] for r in all_cases if not r['whole_candidate_improved']],
                      'pairs':[r['pair'] for r in all_cases]})
    bank={'schema_version':2,'version':'dashboard-mechanisms-v2','scope':'final-adaptation','strategies':bank_cards}
    sb.validate(bank)
    recs=[]
    old_bank=json.loads(generated['bank.json'])
    for i,p in enumerate(original_rows,1):
        problem={'name':p['name'],'statement':p['statement'],'reference':p['src']}
        result=sb.packet(problem,{'bank':bank,'top_k':3})
        old=sb.packet(problem,{'bank':old_bank,'top_k':3})
        recs.append({'id':f'F{i:03}','source':p['source'],'problem':p['name'],
                     'v1_ids':[s['id'] for s in old['strategies']],
                     'v2_ids':[s['id'] for s in result['strategies']],
                     'recommendation':result})
    counts={c['id']:sum(c['id'] in r['v2_ids'] for r in recs) for c in bank_cards}
    summary={'pairs':80,'unique_problems':60,'mechanisms':len(bank_cards),
             'unchanged_code_pairs':[r['pair'] for r in reviewed if not r['code_changed']],
             'changed_unassigned_pairs':[r['pair'] for r in reviewed if r['code_changed'] and not r['mechanisms']],
             'single_problem_mechanisms':[s['id'] for s in stats if s['distinct_supporting_problems']==1],
             'recommendation_counts':counts,'recommended_problems':sum(bool(r['v2_ids']) for r in recs),
             'no_match':[r['id'] for r in recs if not r['v2_ids']], 'strategies':stats,
             'api_calls':0,'lean_runs':0,'meaning':'source review and offline routing, not an efficacy comparison'}
    files={'bank.json':v1.encoded(bank),'observations.json':v1.encoded({'schema_version':2,'cases':reviewed}),
           'summary.json':v1.encoded(summary),'recommendations-60.json':v1.encoded({'scope':'final-adaptation','problems':recs})}
    # Keep independent copies of exact reviewed diffs for the standalone evidence bundle.
    files.update({name:data for name,data in generated.items() if name.startswith('diffs/')})
    lines=['# 80쌍의 실제 변환 검토와 Strategy Bank v2','',
           '모델·Lean 호출 없이 고정된 전후 소스와 기존 측정 근거를 비교한 기록입니다.',
           '에이전트가 전후 코드와 변경 구간을 읽고 분류한 관찰 노트를 입력으로 사용합니다. 새 증명 검증이나 개별 변환 인과 실험은 아닙니다.',
           '전략 수를 정하지 않고 적용 절차·전제·실패 위험이 다른 메커니즘을 묶었습니다. 대안 recipe는 같은 카드 안에 보존했습니다.',
           f'관찰 메커니즘 {len(bank_cards)}개. 코드 동일 {len(summary["unchanged_code_pairs"])}쌍. 변경됐지만 범용 카드 배정을 보류한 쌍: '+str(summary['changed_unassigned_pairs']),
           '', '|전략|관찰 쌍|개선된 전체 후보 쌍|서로 다른 근거 문제|60문제 추천 수|','|---|---:|---:|---:|---:|']
    for s in stats:lines.append(f'|{s["id"]} {s["title_ko"]}|{s["observed_pairs"]}|{s["supporting_improved_pairs"]}|{s["distinct_supporting_problems"]}|{counts[s["id"]]}|')
    lines+=['','단일 문제 카드: '+', '.join(summary['single_problem_mechanisms']),
            '단일 문제 카드는 그 문제를 풀 때 자기 사례가 제외되므로 추천되지 않습니다. 다른 문제 전이는 아직 검증되지 않았습니다.',
            '추천이 없는 문제: '+(', '.join(summary['no_match']) or '없음'),
            'v1과 v2는 전략 내용과 추천 방식이 모두 달라졌습니다. 이 표를 전략 수만의 효과나 성능 비교로 해석하면 안 됩니다.',
            '','## 전체 쌍별 관찰','']
    for r in reviewed:
        lines += [f'### Pair {r["pair"]:03} · F{r["row"]:03} · {r["author"]}',r['problem'],'',
                  r['observation_ko'],'',
                  '메커니즘: '+(', '.join(r['mechanisms']) or '없음/보류')+'; 전체 후보 개선: '+str(r['whole_candidate_improved']),
                  f'[전후 diff]({r["diff"]}) · 원본 SHA `{r["original_sha256"]}` · 후보 SHA `{r["candidate_sha256"]}`','']
    files['REVIEW.md']='\n'.join(lines).encode()
    files['manifest.json']=v1.encoded({'schema_version':2,'dataset_sha256':v1.DATASET,
                                     'authored_inputs':{'strategy-bank/review-v2/observations.json':v1.digest(notes_bytes),
                                                        'strategy-bank/review-v2/definitions.json':v1.digest(defs_bytes)},
                                     'files':{p:v1.digest(b) for p,b in sorted(files.items())}})
    return files


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--benchmark',type=Path,required=True)
    ap.add_argument('--output',type=Path,default=ROOT/'strategy-bank/dashboard-v2')
    ap.add_argument('--check',action='store_true')
    args=ap.parse_args()
    files=build(args.benchmark)
    for name,data in files.items():
        p=args.output/name
        if args.check:
            if not p.is_file() or p.read_bytes()!=data:raise ValueError('Generated v2 evidence differs: '+name)
        else:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    summary=json.loads(files['summary.json'])
    print(json.dumps({k:v for k,v in summary.items() if k!='strategies'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
