"""Export audited feedback ablation results and a standard ReportLab chart."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(base, destination):
    data = json.loads((base/'cohort-summary.json').read_text())
    assert data['all_record_checks_passed'] and data['trial_count']==8 and data['proposal_count']==80
    destination.mkdir(parents=True,exist_ok=True)
    for name in ['cohort-summary.json','design.frozen.json','execution-protocol.json','cohort.frozen.json',
                 'dispatch.jsonl','offline-formatter-check.json']:
        shutil.copyfile(base/name,destination/('results.json' if name=='cohort-summary.json' else name))
    if (base/'operator-incidents.jsonl').exists():
        shutil.copyfile(base/'operator-incidents.jsonl',destination/'operator-incidents.jsonl')
    (destination/'selected').mkdir(exist_ok=True)
    for row in data['trials']:
        source=base/row['trial_id']/'selected.lean'
        assert sha(source)==row['selected']['sha256']
        shutil.copyfile(source,destination/'selected'/f'{row["trial_id"]}.lean')
    runtime={}
    for pid in ['P01','P13']:
        runtime[pid]={}
        for phase in ['before','after']:
            path=base/'readiness'/pid/f'runtime-inventory.{phase}.json'
            value=json.loads(path.read_text())
            runtime[pid][phase]={k:v for k,v in value.items() if k!='files_sha256'}
            runtime[pid][phase]['full_inventory_sha256']=sha(path)
    (destination/'runtime-checks.json').write_text(json.dumps(runtime,indent=2)+'\n')
    lines=['# 오류 피드백 구조화: P01·P13 A/B 결과','',
        '독립변수는 실패한 Lean 컴파일의 오류 선택·구조화 정책이다. L은 기존 피드백, S는 첫 오류와 목표·주변 가정을 구조화한 피드백이다. '
        '두 조건 모두 details 상한은 1,600자이며 같은 naive 프롬프트를 사용했다. JSON 표기만의 효과를 분리한 실험은 아니다.','',
        '문제별·조건별 새 solver 2개, 실행당 후보 10개로 총 8개 실행·80개 후보를 평가했다. 최대 2개 solver를 동시 실행했다. '
        '첫 요청은 같은 문제의 네 실행에서 바이트 단위로 동일했다. 추가 검증·라이브러리 검색·전략 지침을 주지 않았고 성공 피드백은 기존과 같다.','',
        '주 관측값은 3회차에 원본보다 낮은 비용을 찾은 실행 수다. 비용은 `0.5 × (tokens/원본tokens + rawHB/원본rawHB)`이며 낮을수록 좋다. '
        '모든 실행은 처음부터 10회 예산을 알고 있었고 3·6회는 중간 관측이다.','',
        '| 문제 | 조건 | 3회차 개선 실행 | 초반 유효 후보 평균/3 | 3회 비용 | 6회 비용 | 10회 비용 | 최종 검증 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for pid in ['P01','P13']:
        for condition in ['L','S']:
            a=data['aggregate'][pid][condition];c=a['checkpoints']
            lines.append(f'| {pid} | {condition} | {a["improved_at3_count"]}/2 | {a["valid_first3_mean"]:.2f} | '
                f'{c["3"]["mean_cost"]:.6f} | {c["6"]["mean_cost"]:.6f} | {c["10"]["mean_cost"]:.6f} | {a["final_valid_count"]}/2 |')
    p01_change=(data['aggregate']['P01']['S']['checkpoints']['10']['mean_cost']/data['aggregate']['P01']['L']['checkpoints']['10']['mean_cost']-1)*100
    p13_change=(data['aggregate']['P13']['S']['checkpoints']['10']['mean_cost']/data['aggregate']['P13']['L']['checkpoints']['10']['mean_cost']-1)*100
    lines+=['',f'이번 표본에서 구조화 조건의 10회차 평균 비용 변화는 기존 대비 P01 {p01_change:+.2f}%, P13 {p13_change:+.2f}%였다. '
        'P01의 3회차 개선은 0/2에서 1/2로 늘었지만 초반 유효 후보 수는 두 조건 모두 평균 1.5/3으로 같았다. '
        '구조화 피드백의 일관된 성능 향상을 확인한 결과는 아니다.','',
        'P01의 3회차 정체 실행들은 모두 그때까지 유효한 후보를 만들었다. '
        '예를 들어 S-r1의 3회차는 33토큰이지만 12,283,267 raw HB여서 원본보다 종합 비용이 높았다. '
        '오류 전달 개선만으로 높은 검증 비용까지 해결되지는 않았다. '
        'P13의 L 두 실행은 3회차 전에 오류 피드백을 받지 않았고 S 두 실행은 각각 한 번 받았다. '
        '첫 요청은 같아도 첫 응답부터 탐색 경로가 달랐으므로 이 초기 차이를 피드백의 인과효과로 단정할 수 없다.','',
        '![회차별 평균 비용](results.png)','',
        '| 실행 | 첫 유효 후보 | 첫 비용 개선 | 초반 유효/3 | 3회차 전 오류 노출 | 3회 비용 | 6회 비용 | 10회 비용 | 최종 검증 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in sorted(data['trials'],key=lambda x:(x['problem_id'],x['condition'],x['repetition'])):
        c=r['checkpoints'];valid=r['first_valid_proposal'];improve=r['first_improvement_proposal']
        lines.append(f'| [{r["trial_id"]}](selected/{r["trial_id"]}.lean) | {valid if valid is not None else ">10"} | '
            f'{improve if improve is not None else ">10"} | {r["valid_first3"]}/3 | {r["early_error_feedback_exposures"]} | '
            f'{c["3"]["local_cost"]:.6f} | {c["6"]["local_cost"]:.6f} | {c["10"]["local_cost"]:.6f} | {"통과" if r["final_valid"] else "실패"} |')
    lines+=['','오류 피드백을 받은 적 없는 실행에서는 해당 시점까지 독립변수에 실제 노출되지 않았다. '
        '오류가 발생한 후의 다음 후보 성공률은 서로 다른 탐색 경로에서 생긴 관측이므로 오류별 인과효과로 해석하지 않는다. '
        '처음 3회에 개선하지 못한 실행도 유효한 증명은 만들었을 수 있다.','',
        'P01-L-r1과 P13-S-r1은 계정 사용량 제한으로 중단됐다가 사용자의 재개 지시에 따라 같은 solver 문맥에서 이어갔다. '
        '진행 중인 검증은 없었고 완료 후보를 재시도하거나 예산을 추가하지 않았다. 이 운영 중단은 결과 해석의 한계로 남는다.','',
        '| 문제 | 조건 | 3회 비용 범위 | 6회 비용 범위 | 10회 비용 범위 |',
        '|---|---|---|---|---|']
    for pid in ['P01','P13']:
        for condition in ['L','S']:
            a=data['aggregate'][pid][condition]
            lines.append(f'| {pid} | {condition} | '+' | '.join(f'{a["checkpoints"][str(k)]["min_cost"]:.6f}–{a["checkpoints"][str(k)]["max_cost"]:.6f}' for k in [3,6,10])+' |')
    lines+=['','[동일한 과거 로그의 형식 비교](offline-formatter-check.json)는 정보 보존을 확인하는 검사이며 solver 성능 자료가 아니다. '
        '현재 후보는 일반 컴파일 1회와 측정 3회의 중앙값으로 평가하고 최종 선택본도 별도 재검증했다. '
        'Lean·문맥·공통 기준값·worker·420초 invocation 제한·예산·선택 규칙은 조건 간 동일하다.','',
        '조건당 두 번의 탐색은 통계적 우위를 입증하지 않는다. 두 문제 모두 개발에 사용한 문제다. '
        '정확한 모델 ID·sampling seed·숨겨진 문맥·내부 호출 수·요금은 관측하거나 고정하지 못했다. '
        '라이브러리는 정책상 읽기 전용 공유이며 OS 격리는 없다. 기록 replay는 모델 재생성이 아니다.','',
        f'최종 검증 {sum(r["final_valid"] for r in data["trials"])}/8, 기록 감사 통과. 운영 사건 {len(data["operational_incidents"])}건. '
        '사건의 상세 내용은 전체 결과 JSON에 보존했다. 원본 로그는 아래 로컬 원문 경로에 있다.','',
        '[전체 결과](results.json) · [실행 프로토콜](execution-protocol.json) · [전후 런타임 해시](runtime-checks.json) · '
        '[사전 설계](design.frozen.json) · [실제 배정 순서](dispatch.jsonl)','',f'원문: `{base}`','']
    (destination/'README.md').write_text('\n'.join(lines))
    plot(data,destination/'results.svg')
    exported={str(p.relative_to(destination)):sha(p) for p in destination.rglob('*') if p.is_file() and p.name!='export-provenance.json'}
    (destination/'export-provenance.json').write_text(json.dumps({'raw_cohort':str(base),
        'audited_summary_sha256':sha(base/'cohort-summary.json'),'files_sha256':exported,
        'selected_proof_context':'../inputs/PROBLEM/context.lean.in; declarations require the frozen context.'},indent=2)+'\n')
    print(json.dumps({'exported':str(destination),'trial_count':8}))


def plot(data,path):
    from reportlab.graphics.shapes import Drawing,String,Line,Rect
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.widgets.markers import makeMarker
    from reportlab.graphics import renderSVG
    from reportlab.lib import colors
    drawing=Drawing(940,385);drawing.add(Rect(0,0,940,385,fillColor=colors.white,strokeColor=None))
    drawing.add(String(28,355,'Error feedback policy: legacy vs structured',fontName='Helvetica-Bold',fontSize=17))
    drawing.add(String(28,335,'Same naive prompt, 1600-character details cap, 10 proposals. Means of two fresh runs; lower cost is better.',fontSize=10,fillColor=colors.HexColor('#4b5563')))
    for n,pid in enumerate(['P01','P13']):
        x=55+n*455
        chart=LinePlot();chart.x=x;chart.y=95;chart.width=380;chart.height=175
        chart.data=[[(k,data['aggregate'][pid][c]['checkpoints'][str(k)]['mean_cost']) for k in [3,6,10]] for c in ['L','S']]
        chart.xValueAxis.valueMin=3;chart.xValueAxis.valueMax=10;chart.xValueAxis.valueSteps=[3,6,10]
        chart.yValueAxis.valueMin=0;chart.yValueAxis.labelTextFormat='%.2f';chart.yValueAxis.visibleGrid=True;chart.yValueAxis.gridStrokeColor=colors.HexColor('#e5e7eb')
        for i,color in enumerate(['#374151','#0f977b']):
            chart.lines[i].strokeColor=colors.HexColor(color);chart.lines[i].strokeWidth=2
            chart.lines[i].symbol=makeMarker('FilledCircle');chart.lines[i].symbol.size=5
        drawing.add(chart);drawing.add(String(x,296,pid,fontName='Helvetica-Bold',fontSize=13))
        drawing.add(String(x+85,67,'Completed proposals: 3 / 6 / 10',fontSize=9))
        for i,(c,label,color) in enumerate([('L','Legacy','#374151'),('S','Structured','#0f977b')]):
            a=data['aggregate'][pid][c]
            values=' / '.join(f'{a["checkpoints"][str(k)]["mean_cost"]:.4f}' for k in [3,6,10])
            drawing.add(String(x,44-i*14,f'{label}: {values}; improved at 3: {a["improved_at3_count"]}/2',fontSize=9,fillColor=colors.HexColor(color)))
    drawing.add(String(28,9,'Search-time cost. Final revalidation, feedback exposure and per-run ranges are reported separately. Exploratory n=2.',fontSize=8,fillColor=colors.HexColor('#4b5563')))
    renderSVG.drawToFile(drawing,str(path))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('cohort',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();export(args.cohort.resolve(),args.destination.resolve())
