"""Export only an audited completed cohort, without invoking a solver or Lean."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


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
    for name in ['execution-protocol.json', 'cohort.frozen.json', 'dispatch.jsonl']:
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
    lines = ['# P13 프롬프트 개별 효과 실험 결과', '',
             f'이번 표본에서 10회차 평균 비용이 가장 낮은 조건은 **{winner} ({labels[winner]})**였다. '
             f'평균 {winner_cost:.6f}로 A의 {control_cost:.6f}보다 '
             f'{100 * (1 - winner_cost / control_cost):.2f}% 낮았다. '
             '조건당 두 번의 탐색 결과이므로 후속 검증 후보를 고르는 근거로 해석한다.', '',
             'A와 A에 지침 하나씩 추가한 B1~B4를 각각 새 solver 두 개로 실행했다. '
             '동시 solver 상한은 2개이며 10개 실행, 후보 100개를 완료했다. '
             '모든 실행의 예산은 처음부터 10회이고 3·6·10회차의 누적 최선을 관측했다.', '',
             '로컬 비용은 `0.5 × (tokens / 1769 + raw_heartbeats / 115674908)`이며 낮을수록 좋다. '
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
              '한 조건에 추가한 지침이 하나라는 뜻이지, solver의 실제 코드 변경이 한 종류로 제한된다는 뜻은 아니다. '
              '예를 들어 B2-r1의 선택본은 `Fin 4 → Set.Icc B T`로 네 값의 상태를 표현했다. '
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
    lines += ['', 'Lean 4.26.0과 고정 Mathlib, 동일 worker, 원본 기준값을 사용했다. '
              '후보를 일반 컴파일로 먼저 확인하고 통과한 후보는 추가 측정 3회의 중앙값을 사용했다. '
              '최종 선택본도 일반 컴파일 1회와 측정 3회로 별도 재검증했다. '
              '각 invocation의 제한은 420초이며 무효·시간 초과 후보도 예산에 포함했다. '
              '실패에 따라 재시도하거나 조건을 바꾸지 않았다.', '',
              f'전체 {data["trial_count"]}개 기록 replay와 파일 해시 검사를 통과했다. '
              f'공유 런타임 {data["shared_runtime_file_count"]:,}개 파일의 전후 SHA256도 일치했다. '
              '이 검사는 기록의 일관성과 바이트 불변성을 확인하며, OS 수준 격리나 모델 응답의 동일성을 보장하지 않는다.', '',
              '초기 A-r1·B3-r1에서 큰 시계 간격이 관측되었고 원인은 확정하지 못했다. '
              '따라서 실행 경과 시간을 모델·증명 계산 시간으로 해석하지 않는다. '
              '이후 시계 관측 기록을 보존했다. 정확한 모델 ID·샘플링 seed·숨겨진 문맥·내부 호출 수·요금은 통제하거나 관측하지 못했다.', '',
              '기존 제출본의 과거 관측값은 259 tokens / 2,931,231 raw HB이며 공통 분모에서 비용 0.085875다. '
              '이번에 재측정한 실험군은 아니며 solver에 제공하지 않았다.', '',
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
