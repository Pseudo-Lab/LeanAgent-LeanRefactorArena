"""Export only an audited completed cohort, without invoking a solver or Lean."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics


def export(cohort, destination):
    source = cohort / 'cohort-summary.json'
    data = json.loads(source.read_text())
    assert data['all_record_checks_passed'] and data['trial_count'] == 10
    assert data['proposal_count'] == 100
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination / 'results.json')
    proof_dir = destination / 'selected'
    proof_dir.mkdir(exist_ok=True)
    exports = {}
    for row in data['trials']:
        proof = cohort / row['trial_id'] / 'selected.lean'
        digest = hashlib.sha256(proof.read_bytes()).hexdigest()
        assert digest == row['selected']['sha256']
        target = proof_dir / (row['trial_id'] + '.lean')
        shutil.copyfile(proof, target)
        exports[str(target.relative_to(destination))] = digest
    exports['results.json'] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ['execution-protocol.json', 'cohort.frozen.json', 'dispatch.jsonl', 'operator-incidents.jsonl']:
        shutil.copyfile(cohort / name, destination / name)
        exports[name] = hashlib.sha256((destination / name).read_bytes()).hexdigest()
    inventories = {}
    for phase in ['before', 'after']:
        inventory_path = cohort / f'runtime-inventory.{phase}.json'
        inventory = json.loads(inventory_path.read_text())
        inventories[phase] = {key: value for key, value in inventory.items() if key != 'files_sha256'}
        inventories[phase]['full_inventory_sha256'] = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    (destination / 'runtime-inventory-check.json').write_text(json.dumps(inventories, indent=2) + '\n')
    exports['runtime-inventory-check.json'] = hashlib.sha256((destination / 'runtime-inventory-check.json').read_bytes()).hexdigest()
    readiness = {}
    for i in [1, 2]:
        folder = cohort / f'calibration-{i}'
        result = json.loads((folder / 'original/result.json').read_text())
        summary = json.loads((folder / 'summary.json').read_text())
        samples = [run['measurement']['raw'] for run in result['environments']['fixed']['runs']
                   if 'measurement' in run]
        readiness[str(i)] = {'tokens': result['tokens'], 'raw_samples': samples,
                             'median_raw_heartbeats': statistics.median(samples),
                             'valid': result['valid'], 'environment_unchanged': summary['environment_unchanged'],
                             'summary_sha256': hashlib.sha256((folder / 'summary.json').read_bytes()).hexdigest(),
                             'diagnostic_correction': summary['diagnostic_correction']}
    readiness['baseline_policy'] = 'These fresh observations were kept separate; every solver request used the same archived original denominator.'
    (destination / 'readiness-observations.json').write_text(json.dumps(readiness, indent=2) + '\n')
    exports['readiness-observations.json'] = hashlib.sha256((destination / 'readiness-observations.json').read_bytes()).hexdigest()
    previous = destination.parents[1] / 'prompt-ablation-v1/results/results.json'
    previous_data = json.loads(previous.read_text())
    comparison_rows = {}
    for condition in ['A', 'B1', 'B2', 'B3', 'B4']:
        comparison_rows[condition] = {
            problem: 100 * (cohort_data['aggregate'][condition]['checkpoints']['10']['mean_cost'] /
                            cohort_data['aggregate']['A']['checkpoints']['10']['mean_cost'] - 1)
            for problem, cohort_data in [('P01', data), ('P13', previous_data)]}
    comparison_data = {'metric': '100 * (mean cost of condition / mean cost of A - 1); negative favors condition',
                       'checkpoint': 10, 'repetitions_per_condition': 2,
                       'P13_results_sha256': hashlib.sha256(previous.read_bytes()).hexdigest(),
                       'P01_results_sha256': exports['results.json'], 'relative_cost_change_pct': comparison_rows,
                       'caution': 'Exploratory, not a held-out generalization test; P01 informed some prompt hypotheses.'}
    (destination / 'cross-problem-comparison.json').write_text(json.dumps(comparison_data, indent=2) + '\n')
    exports['cross-problem-comparison.json'] = hashlib.sha256((destination / 'cross-problem-comparison.json').read_bytes()).hexdigest()
    (destination / 'export-provenance.json').write_text(json.dumps({
        'raw_cohort': str(cohort), 'audited_summary_sha256': exports['results.json'],
        'files_sha256': exports,
        'selected_proof_context': '../input/context.lean.in; declarations are not standalone projects',
        'model_calls_and_cost': 'unobservable; null, not zero',
    }, ensure_ascii=False, indent=2) + '\n')

    labels = {'A': '기존 naive', 'B1': '증명 구조 대안', 'B2': '목표 중심 simplification',
              'B3': '구조 변경 후 1회 후속 개선', 'B4': '목표에서 lemma 역방향 적용'}
    winner = min(labels, key=lambda c: data['aggregate'][c]['checkpoints']['10']['mean_cost'])
    winner_cost = data['aggregate'][winner]['checkpoints']['10']['mean_cost']
    control_cost = data['aggregate']['A']['checkpoints']['10']['mean_cost']
    comparison = (f'A의 {control_cost:.6f}보다 {100 * (1 - winner_cost / control_cost):.2f}% 낮았다.'
                  if winner != 'A' else '추가 지침 조건들은 10회차 평균에서 A를 넘지 못했다.')
    lines = ['# P01 프롬프트 개별 효과 실험 결과', '',
             f'이번 표본에서 10회차 평균 비용이 가장 낮은 조건은 **{winner} ({labels[winner]})**였다. '
             f'평균 비용은 {winner_cost:.6f}이다. {comparison} '
             '조건당 두 번의 탐색 결과이므로 후속 검증 후보를 고르는 근거로 해석한다.', '',
             'A와 A에 지침 하나씩 추가한 B1~B4를 각각 새 solver 두 개로 실행했다. '
             '동시 solver 상한은 2개이며 10개 실행, 후보 100개를 완료했다. '
             '모든 실행의 예산은 처음부터 10회이고 3·6·10회차의 누적 최선을 관측했다.', '',
             '로컬 비용은 `0.5 × (tokens / 313 + raw_heartbeats / 5173306)`이며 낮을수록 좋다. '
             '아래는 탐색 중 관측값이다. 최종 선택본은 별도 검증했다.', '',
             '| 조건 | 추가 지침 | 3회 평균 | 6회 평균 | 10회 평균 | 10회 B−A | 최종 검증 |',
             '|---|---|---:|---:|---:|---:|---:|']
    for condition, label in labels.items():
        aggregate = data['aggregate'][condition]
        values = [aggregate['checkpoints'][str(k)]['mean_cost'] for k in [3, 6, 10]]
        delta = aggregate['checkpoints']['10']['difference_from_A']
        lines.append(f'| {condition} | {label} | {values[0]:.6f} | {values[1]:.6f} | '
                     f'{values[2]:.6f} | {delta:+.6f} | {aggregate["final_valid_count"]}/2 |')
    lines += ['', '![회차별 평균 로컬 비용](results.png)', '',
              'B−A가 음수이면 해당 회차에서 B의 평균 비용이 더 낮다. '
              '반복이 두 번뿐이므로 통계적 우위나 다른 문제로의 일반화를 주장할 수 없다. '
              '누적 최선은 구조상 나빠지지 않으므로 3→10회 개선 자체가 프롬프트 효과의 증거는 아니다.', '',
              f'B2의 10회차 평균 비용은 P13에서 A 대비 {comparison_rows["B2"]["P13"]:+.2f}%, '
              f'P01에서는 {comparison_rows["B2"]["P01"]:+.2f}%였다. '
              'P13에서 관측한 개선이 P01에서 그대로 재현되지는 않았다. '
              '[두 문제의 A 대비 비교](cross-problem-comparison.json)를 별도로 보존했다.', '',
              '한 조건에 추가한 지침이 하나라는 뜻이지, solver의 실제 코드 변경이 한 종류로 제한된다는 뜻은 아니다. '
              '따라서 조건 간 차이는 지침을 받은 탐색의 결과이며 특정 tactic 하나의 순수 실행 비용 차이가 아니다.', '',
              '| 실행 | 3회 비용 | 6회 비용 | 10회 비용 | 유효/10 | 선택 토큰 | 선택 raw HB | 최종 검증 |',
              '|---|---:|---:|---:|---:|---:|---:|---|']
    for row in sorted(data['trials'], key=lambda r: (r['condition'], r['repetition'])):
        values = [row['checkpoints'][str(k)]['local_cost'] for k in [3, 6, 10]]
        selected = row['selected']
        lines.append(f'| [{row["trial_id"]}](selected/{row["trial_id"]}.lean) | '
                     f'{values[0]:.6f} | {values[1]:.6f} | {values[2]:.6f} | '
                     f'{row["verified_proposals"]}/10 | {selected["tokens"]} | '
                     f'{selected["raw_heartbeats"]:,} | {"통과" if row["final_valid"] else "실패"} |')
    lines += ['', '| 조건 | 3회 범위 | 6회 범위 | 10회 범위 | 후보 오류 종류·횟수 |',
              '|---|---|---|---|---|']
    for condition in labels:
        ranges = [data['aggregate'][condition]['checkpoints'][str(k)] for k in [3, 6, 10]]
        errors = {}
        for row in data['trials']:
            if row['condition'] == condition:
                for key, count in row['proposal_error_counts'].items():
                    errors[key] = errors.get(key, 0) + count
        lines.append(f'| {condition} | ' + ' | '.join(
            f'{r["min_cost"]:.6f}–{r["max_cost"]:.6f}' for r in ranges) +
            f' | {json.dumps(errors, ensure_ascii=False)} |')
    lines += ['', 'Lean 4.26.0과 고정 Strata 라이브러리, 동일 worker, 원본 기준값을 사용했다. '
              '후보를 일반 컴파일로 먼저 확인하고 통과한 후보는 추가 측정 3회의 중앙값을 사용했다. '
              '최종 선택본도 일반 컴파일 1회와 측정 3회로 별도 재검증했다. '
              '각 invocation의 제한은 420초이며 무효·시간 초과 후보도 예산에 포함했다. '
              '후보 검증 실패에 따라 재시도하거나 조건을 바꾸지 않았다.', '',
              f'전체 {data["trial_count"]}개 기록 replay와 파일 해시 검사를 통과했다. '
              f'공유 런타임 {data["shared_runtime_file_count"]:,}개 파일의 전후 SHA256도 일치했다. '
              '이 검사는 기록의 일관성과 바이트 불변성을 확인하며, OS 수준 격리나 모델 응답의 동일성을 보장하지 않는다.', '',
              '실행 전부터 시계 관측 기록을 보존했다. 벽시계 경과 시간을 모델·증명 계산 시간으로 해석하지 않는다. '
              '정확한 모델 ID·샘플링 seed·숨겨진 문맥·내부 호출 수·요금은 통제하거나 관측하지 못했다.', '',
              'P01은 일부 지침 도출에 사용했던 개발 문제다. 이번 비교는 해당 문제의 독립 solver 반복이며 새로운 문제로의 일반화 검증이 아니다. '
              'solver에는 이전 증명이나 결과를 제공하지 않았다.', '',
              '운영 오류 1건: B3-r2의 4번 후보 제출 명령에서 응답 경로 오타가 보고됐다. '
              '응답을 읽기 전 실패였으며 같은 응답 파일로 경로만 수정했다. '
              '추가 후보나 완료된 검증의 재시도는 없었다. [운영 오류 기록](operator-incidents.jsonl)을 별도로 보존했다.', '',
              '[감사된 전체 결과](results.json), [export 해시](export-provenance.json), '
              '[사전 설계](../design.json), [실행 프로토콜](execution-protocol.json), '
              '[실제 배정 순서](dispatch.jsonl), [각 프롬프트](../prompts/). '
              f'원문 실행 기록: `{cohort}`.', '']
    (destination / 'README.md').write_text('\n'.join(lines))
    print(json.dumps({'exported': str(destination), 'trials': len(data['trials'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    export(args.cohort.resolve(), args.destination.resolve())
