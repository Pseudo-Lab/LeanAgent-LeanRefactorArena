"""Export only fully audited structured-versus-semantic feedback results."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(base, destination):
    data = json.loads((base / 'cohort-summary.json').read_text())
    assert data['all_record_checks_passed'] and data['summary_compliance_checked']
    assert data['trial_count'] == 8 and data['proposal_count'] == 80
    destination.mkdir(parents=True, exist_ok=True)
    names = ['cohort-summary.json', 'design.frozen.json', 'execution-protocol.json',
             'cohort.frozen.json', 'dispatch.jsonl', 'summary-dispatch.jsonl',
             'operator-incidents.jsonl', 'host-clock-observations.jsonl',
             'execution-context.json', 'semantic-review.json']
    for name in names:
        source = base / name
        if source.exists():
            shutil.copyfile(source, destination / ('results.json' if name == 'cohort-summary.json' else name))
    runtime = {}
    for pid in ['P01', 'P13']:
        runtime[pid] = {}
        for phase in ['before', 'after']:
            path = base / 'readiness' / pid / f'runtime-inventory.{phase}.json'
            runtime[pid][phase] = {k: v for k, v in json.loads(path.read_text()).items() if k != 'files_sha256'}
            runtime[pid][phase]['full_inventory_sha256'] = sha(path)
    (destination / 'runtime-checks.json').write_text(json.dumps(runtime, indent=2) + '\n')
    selected = destination / 'selected'
    selected.mkdir(exist_ok=True)
    lines = ['# 구조화 추출 vs 의미 보존 요약 결과', '',
        '동일한 naive A 프롬프트·첫 오류 추출기·1,600자 상한에서 S(기존 structured_v1)와 M(독립 모델 요약)을 비교했다. '
        'M에는 메시지 요약과 goal·context의 원문 선택을 요청하고 수리 전략 생성을 금지했다. '
        '문제별·조건별 두 독립 solver, 실행당 10후보, 총 8실행·80후보다.', '',
        '주 관측값은 3회차에 원본보다 낮은 비용을 찾은 실행 수다. 로컬 실험 비용은 '
        '`0.5 × (tokens/원본tokens + rawHB/원본rawHB)`이며 낮을수록 좋다. '
        '3·6회는 처음부터 고지된 10회 예산 내 중간 관측이다.', '',
        '| 문제 | 조건 | 3회차 개선 | 초반 유효 평균/3 | 3회 비용 | 6회 비용 | 10회 비용 | 최종 검증 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for pid in ['P01', 'P13']:
        for condition in ['S', 'M']:
            a = data['aggregate'][pid][condition]
            costs = ' | '.join(
                f'{a["checkpoints"][str(k)]["mean_cost"]:.6f} '
                f'[{a["checkpoints"][str(k)]["min_cost"]:.6f}, '
                f'{a["checkpoints"][str(k)]["max_cost"]:.6f}]' for k in [3, 6, 10])
            lines.append(f'| {pid} | {condition} | {a["improved_at3_count"]}/2 | {a["valid_first3_mean"]:.2f} | {costs} | {a["final_valid_count"]}/2 |')
    lines += ['', '비용 셀은 평균 [두 실행의 최솟값, 최댓값]이다. 최종 검증은 탐색 중 비용과 구분한다.', '']
    for pid in ['P01', 'P13']:
        control, model = [data['aggregate'][pid][c] for c in ['S', 'M']]
        relative = 100 * (model['checkpoints']['10']['mean_cost'] /
                          control['checkpoints']['10']['mean_cost'] - 1)
        lines += [f'{pid}의 주 관측값(3회차 개선)은 S {control["improved_at3_count"]}/2, '
                  f'M {model["improved_at3_count"]}/2다. 10회차 평균 비용의 M 대 S 상대 차이는 '
                  f'{relative:+.2f}%다. 이는 두 실행씩의 관측 차이이며 인과 효과 추정치가 아니다.', '']
    lines += [
                 '| 실행 | 첫 유효 | 첫 개선 | 3회 전 오류 노출 | 요약 jobs | fallback | 최종 검증 |',
                 '|---|---:|---:|---:|---:|---:|---|']
    for row in data['trials']:
        source = base / row['trial_id'] / 'selected.lean'
        assert sha(source) == row['selected']['sha256']
        shutil.copyfile(source, selected / source.with_name(row['trial_id'] + '.lean').name)
        first_valid = row['first_valid_proposal'] if row['first_valid_proposal'] is not None else '>10'
        first_improvement = row['first_improvement_proposal'] if row['first_improvement_proposal'] is not None else '>10'
        lines.append(f'| {row["trial_id"]} | {first_valid} | {first_improvement} | {row["early_error_feedback_exposures"]} | '
                     f'{row["summarizer_job_count"]} | {row["summary_fallback_count"]} | {"통과" if row["final_valid"] else "실패"} |')
    lines += ['', f'요약 요청 {data["summary_request_count"]}건, 관측 가능한 독립 요약 job {data["summarizer_job_count"]}개, '
              f'fallback {data["summary_fallback_count"]}건이다. 요약 원문 입출력·응답 해시·대기시간·목표/가정 보존 길이는 results.json에 보존했다. '
              '정확한 모델 ID·내부 호출 수·요금은 unknown이다.', '',
              '초기 요청 동일성·80후보 기록/replay·최종 상태·전체 공유 런타임 전후 SHA256·요약 스키마/원문 선택 검사를 통과했다. '
              '의미 보존과 전략 비포함은 기계 검사만으로 완전히 입증할 수 없다. 실제 오류 노출과 fallback을 함께 해석해야 한다.', '',
              '조건당 두 번과 개발에 사용한 두 문제의 탐색 결과이며 통계적 우위나 일반화를 입증하지 않는다. '
              '오류 이후 후보 유효성은 서로 다른 탐색 경로의 관측이다. 기록 replay는 모델 재생성이 아니다. '
              '실행 안의 solver 대화는 유지되므로 매 회차 API 문맥이 완전히 통제된 실험은 아니다. '
              '라이브러리는 정책상 공유 읽기 전용이며 OS 격리는 없다.', '',
              '[전체 결과](results.json) · [사전 설계](design.frozen.json) · [전후 런타임 검사](runtime-checks.json) · '
              '[실행 프로토콜](execution-protocol.json)', '', f'원문 실행: `{base}`', '']
    summaries = [s for r in data['trials'] for s in r['summaries']]
    counts = data['compiler_invocations']
    lines += [f'이번 실행의 Lean 컴파일 호출: 후보 검증 {counts["candidates"]}회, 최종 검증 {counts["final_validation"]}회, '
              f'원본·imports 사전 검증 {counts["readiness_including_imports"]}회다. '
              '`--version`/`--print-prefix` 조회와 재사용한 과거 baseline의 컴파일은 제외했다. '
              '컴파일 횟수·증명 후보 수·요약 job 수·관측 불가능한 내부 모델 호출 수는 서로 다르다.', '']
    changed = sum(s['changed_payload_from_structured'] for s in summaries)
    shorter = sum(s['delivered_characters'] < s['same_error_structured_characters'] for s in summaries)
    lines += [f'동일 오류를 S로 포맷한 출력과 실제 전달 내용이 달랐던 것은 {changed}/{len(summaries)}건이고, '
              f'더 짧게 전달된 것은 {shorter}/{len(summaries)}건이다. '
              '이는 같은 저장 로그를 다시 포맷한 조작 확인이며 추가 solver·Lean 실험이 아니다.', '']
    lines += [f'추출 원문 대비 오류 설명 문장을 바꾼 경우 {sum(s["message_rewritten_from_source"] for s in summaries)}건, '
              f'동일 오류의 S 출력 대비 목표 선택이 달랐던 경우 {sum(s["goal_differs_from_structured"] for s in summaries)}건, '
              f'가정 선택이 달랐던 경우 {sum(s["context_differs_from_structured"] for s in summaries)}건이다. '
              '이 범주는 중복될 수 있으며, 모델 호출 자체와 실제 문장 요약·정보 선택의 발생을 구분한다.', '']
    lines += [f'사후 입력·출력 검토에서 의미 보존 우려 {data["semantic_fidelity_concern_count"]}건, '
              f'추가 수리 전략 관측 {data["added_repair_strategy_observed_count"]}건을 기록했다. '
              '이 검토는 형식 검사와 별개이며 solver 피드백을 수정하지 않았다. '
              '[사례별 품질 검토](semantic-review.json)에서 근거를 확인할 수 있다.', '']
    lines += [f'원문 컴파일러의 제안을 그대로 남긴 경우는 {data["compiler_advice_retained_count"]}건이며, '
              f'엄격한 제안 비포함 조건에 대한 우려는 {data["advice_free_output_concern_count"]}건이다. '
              '모델이 새로 추가한 수리 전략과 원문 제안의 잔존을 각각 기록했다.', '']
    for pid in ['P01', 'P13']:
        runs = [r for r in data['trials'] if r['problem_id'] == pid and r['condition'] == 'M']
        lines += [f'{pid} M 실행별 실제 변경 피드백 노출(3회차 이전/전체): ' +
                  ', '.join(f'{r["trial_id"]} {r["early_changed_feedback_exposures"]}/{r["changed_feedback_exposures"]}' for r in runs) +
                  '. 오류 노출이 있어도 S와 동일한 내용이면 변경된 정보에 대한 노출로 세지 않았다.', '']
        if not any(r['changed_feedback_exposures'] for r in runs):
            lines += [f'{pid}에서는 M이 solver에게 전달한 오류 내용이 모두 같은 오류의 S 출력과 같았다. '
                      '따라서 조건 간 성능 차이로 요약 내용 변경의 효과를 식별할 수 없다.', '']
    plot_receipt = destination / 'plots-provenance.json'
    if plot_receipt.exists():
        plots = json.loads(plot_receipt.read_text())
        assert plots['source_summary_sha256'] == sha(base / 'cohort-summary.json')
        for name, digest in plots['files_sha256'].items():
            assert sha(destination / name) == digest
        lines += ['![P01 평균과 실행 간 범위](P01-cost-ranges.svg)', '',
                  '![P13 평균과 실행 간 범위](P13-cost-ranges.svg)', '']
    (destination / 'README.md').write_text('\n'.join(lines))
    with (destination / 'trial-results.csv').open('w', newline='') as stream:
        fields = ['trial_id', 'problem_id', 'condition', 'repetition', 'valid_first3', 'improved_at3',
                  'first_valid_proposal', 'first_improvement_proposal', 'summarizer_job_count', 'summary_fallback_count', 'final_valid',
                  'changed_feedback_exposures', 'early_changed_feedback_exposures',
                  'cost_at3', 'cost_at6', 'cost_at10']
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for row in data['trials']:
            values = {key: row[key] for key in fields if not key.startswith('cost_at')}
            values.update({f'cost_at{k}': row['checkpoints'][str(k)]['local_cost'] for k in [3, 6, 10]})
            writer.writerow(values)
    manifest = {str(path.relative_to(destination)): sha(path) for path in destination.rglob('*')
                if path.is_file() and path.name != 'export-provenance.json'}
    (destination / 'export-provenance.json').write_text(json.dumps({'raw_cohort': str(base),
        'audited_summary_sha256': sha(base / 'cohort-summary.json'), 'files_sha256': manifest}, indent=2) + '\n')
    print(json.dumps({'exported': str(destination), 'trial_count': 8, 'proposal_count': 80}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    export(args.cohort.resolve(), args.destination.resolve())
