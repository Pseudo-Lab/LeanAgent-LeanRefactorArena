# 비용 가설을 사용하는 Lean 리팩터 파이프라인

브랜치 `exp/cost-hypothesis-pipeline`. 첫 하네스가 보존된
`exp/feedback-followup-20261025`의 `93cc6bb`에서 별도 worktree로 시작했다.
기존 첫 하네스와 다른 작업의 미추적 파일을 수정하지 않는다.

## 현재 실행 상태

2026-10-27 상태 조회 기준 48개 후보 중 41개 평가 기록이 있으며, 독립 실행 8개 중 6개가 완료됐다.
P01-A-r2는 5/6, P13-B-r2는 평가 완료 기록이 0/6이다. pending 표시는 현재 프로세스 생존을 보장하지 않는다.
이전에는 31개 평가 후 디스크 사전 검사에서 중단됐으나, 공간 확보 후 저장된 후보부터 재개했다.
[실행 현황](PROGRESS.ko.md), [인사이트 초안](INSIGHTS.ko.md),
[기록을 보존한 재개 절차](STORAGE_RECOVERY.ko.md)를 참고한다. 전체 비교 결과는 아직 확정하지 않았다.

기존 연구와 공개 산식을 연결한 [94점 목표 전략](STRATEGY_94.ko.md)에 길이·HB별 병목,
측정 착시 확인 항목, 검색 기능과 구간 진단을 분리한 다음 실험안을 정리했다.
이는 새 Lean 실험 결과가 아니라 2026-10-27의 전략 분석이다.

## 실험 질문

원본과 최선·직전 후보만 제공하는 자유 탐색에 비해, **없앨 증명 작업에 대한 가설,
단계별 탐색 지침, 분기별 부모와 Pareto 대안**을 함께 제공하면 같은 후보 예산에서
더 좋은 검증된 증명을 얻는가?

이번 비교는 프롬프트와 상태 관리의 묶음이다. 개별 문장이나 개별 기능의 효과를
분리하는 ablation은 아니다. P01·P13은 개발에 사용한 문제이므로 일반화 평가가 아니다.

## 바꾼 구조

```text
원래 전체 소스와 runtime 고정
  → 원본 plain compile와 fresh measurement 3회
  → 문제별 공통 baseline 고정
  → 독립 solver에 원본과 요청만 제공
  → 후보 제안
      A: proof
      B: proof + 부모 + 변경 위치 + 변경 종류 + 줄어들 작업의 가설
  → 원문 검증 + fresh measurement 3회 + target 공리 검사
  → 전체 후보 기록 / 종합점수 best / 분기별 부모 / Pareto 갱신
  → 실패 진단 또는 다음 단계 요청
  → 6개 후보 예산 종료
  → 선택본 재검증 / 기록 replay / 결과 집계
```

B 요청은 초반 구조 변경, 중반 불필요한 추론·반복 제거, 후반 정리·압축을 제시한다.
실패 시에는 수리 또는 가설 포기를 제시한다. 이는 강제 tactic 순서가 아니라
현재 상태에 따른 탐색 지침이며, 실제 선택한 family와 parent를 기록한다.
명제에 맞는 정리, 더 적절한 귀납, 기존 증거·witness·instance의 직접 전달을 우선한다.
`clear`, `simp only`, 공유, 명시적 term을 보편적인 개선 규칙으로 취급하지 않는다.

syntax inventory는 원문 구문 횟수일 뿐 profiler가 아니다. 실제 구간 프로파일링과
라이브러리 검색 도구는 이번 파일 기반 solver 인터페이스에 추가하지 않았다.
정확한 원인 분해가 필요한 후보는 후속 진단 대상으로 남긴다.

## 공통 평가와 선택

두 조건은 같은 원문·baseline·검증기·오류 피드백·6개 후보 예산을 사용한다.
선택은 `tokens × baseline_raw + raw × baseline_tokens` 최소화로 하고,
동점은 토큰과 선언 SHA256으로 결정한다. 원본이 유효한 fallback이다.
후보가 짧아져도 HB가 늘면 종합 목적함수로 판단한다.

실패와 중복 제출도 예산을 소비한다. 같은 선언을 다시 측정한 값으로 등록 지표를
덮어쓰지 않아, 반복 측정의 작은 변동으로 best가 개선되는 것을 막는다.
증명 항이 같아도 소스가 다른 후보는 서로 보존한다.
두 조건의 컴파일 통과 후보에 모두 3회 계측을 적용해 측정 절차를 맞췄다.
실제 총 평가 작업 수·시간은 성공과 실패에 따라 달라진다. 공유 머신의 부하를 통제하지 않아 실행 초는 조건별 속도의 인과 비교로 해석하지 않는다.
최종 재검증이나 환경 동일성 검사가 실패하면 집계기는 비교 점수 표를 발행하지 않는다.
요약에 기록된 baseline·선택본·유효 후보 수도 재생된 상태와 대조한다.

B는 유효한 후보 전체를 registry에 남기고, family별 종합점수 최선과 Pareto 대안을
다음 요청에서 제한된 수만 노출한다. 실패 카드와 실제 피드백도 기록한다.
가설 설명은 짧은 공개 실험 메모이며 모델의 내부 추론 추적을 요구하지 않는다.

## 고정 실험 조건

- P01·P13 × A/B × 조건별 두 반복 = 독립 실행 8개, 후보 48개.
- 관측 회차 2·4·6. 문제별 최종 local cost와 유효 후보 수, HB·길이 및 반복 편차를 보고한다.
- solver 최대 2개, Lean 평가 최대 1개. 코호트 공통 파일 잠금으로 직렬화한다.
- 각 solver는 `fork_turns=none`으로 시작하며 자기 입력·요청·피드백만 읽는다.
- 과거 해답과 이 대화의 증명 코드는 solver 입력에 넣지 않는다.
- 기존 원본 입력과 runtime 연결만 재사용하며 원본 성능은 새로 측정한다.
- 컴파일러·라이브러리는 읽기 전용으로 사용하고 실행 전후 파일 SHA256을 비교한다.
- 모델 backend는 Codex 서브에이전트이며 정확한 모델 ID·seed·내부 호출량·청구 비용은 관측할 수 없다.
- OpenRouter나 별도 유료 API를 호출하지 않는다. Codex 사용 비용을 0달러라고 기록하지 않는다.
- 파일 접근은 지시로 제한하며 OS 수준 격리를 주장하지 않는다.
- 각 solver는 자기 대화·요청·응답 이력을 유지한다. A도 과거 후보를 기억하거나 다시 읽을 수 있으므로 B의 명시적 registry만이 기억의 유일한 출처는 아니다.
- 주 환경 Lean 4.26만 비교하며 결과를 공식 LB 점수로 보고하지 않는다.

## 실행과 재현

저장소 루트에서 실행한다. 기존 환경이 준비되어 있어야 한다.

```sh
python3 -B experiments/cost-hypothesis-pipeline/prepare.py \
  --output runs/cost-hypothesis-pipeline/new-cohort \
  --legacy-runs /absolute/path/to/original-repo/runs/first-harness-jwkweon
```

독립 solver는 할당된 trial의 `requests/001.json`과 `input/source.lean`을 읽고
`responses/001.json`에 정확한 응답 JSON을 저장한다. 그다음 스냅샷 코드를 실행한다.

```sh
python3 -B <trial>/code/worker.py submit <trial> --response <trial>/responses/001.json
# 다음 requests/002.json을 읽고 같은 절차로 고정 예산까지 진행
python3 -B <trial>/code/worker.py finish <trial>
python3 -B <trial>/code/worker.py replay <trial>
```

replay는 저장된 요청·응답·평가로 상태와 선택을 재계산하며 모델이나 Lean을 호출하지 않는다.
실행 기록은 덮어쓰지 않는다. 모든 작업에는 새 output 경로를 사용한다.

이 버전의 모델 실행은 수동 Codex 서브에이전트 bridge다. `prepare.py` 자체가 모델을
호출하지는 않는다. coordinator가 `design.frozen.json` 순서로 `fork_turns=none`의
새 agent를 배정하고, 최대 두 개의 solver를 유지한다. `SOLVER_DISPATCH.txt`의 경로를
치환해 동일한 운영 지시를 전달한다. 조건별 전략은 trial의 고정된 prompt에만 들어 있다.
coordinator는 코호트의 `dispatch.jsonl`에 `dispatched`/`completed`, `trial_id`,
`agent`, `observed_at`을 기록하며 dispatched에는 `fork_turns: "none"`을 포함한다.
처음 pilot의 두 agent는 초기화 완료를 제한된 시간 동안 기다린 뒤 동일 절차를 시작했다.

공유 runtime의 전후 inventory는 readiness 폴더별로 기록한다. 모든 trial 완료 후
집계기는 입력·코드·평가 로그·공리·fresh nonce·replay·dispatch·runtime을 검사한다.

```sh
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P01 before
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P13 before
# 위 before는 solver 시작 전, 아래 after는 모든 Lean 실행이 끝난 뒤 실행한다.
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P01 after
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P13 after
python3 -B experiments/cost-hypothesis-pipeline/report.py <cohort> --output <new-results-directory>
```

결과를 해석하는 기준과 후속 검증 방향은 [분석 계획](ANALYSIS_PLAN.ko.md)에 적었다.

첫 pilot에서는 JSON 저장 전후 부모 순서가 달라지는 replay 결함을 발견해 수정했다.
원래 측정 기록과 기존 요청 20개를 보존·대조한 절차 및 해당 코호트 전용 실행 경로는
[정렬 수정 이력](ORDERING_FIX.ko.md)에 있다. 새 코호트에는 수정된 정책이 바로 적용된다.

## 코드와 검증

| 파일 | 책임 |
|---|---|
| `policy.py` | 응답 카드 검증, registry·분기 부모·Pareto, 단계별 요청과 순수 상태 전이 |
| `worker.py` | immutable 기록, Lean 직렬 평가, 최종 검증과 replay |
| `prepare.py` | 원본 입력·실행 코드 스냅샷, 원본 재측정, 독립 trial 준비 |
| `prompts/` | A 자유 탐색과 B 비용 가설 프롬프트 |
| `error_feedback.py` | 이전 피드백 실험의 structured_v1 formatter를 두 조건 공통으로 재사용 |
| `test_policy.py` | 무효 후보 배제, 길이/HB 교환, 분기 보존, 중복 측정, 요청 정책 검증 |
| `report.py`, `test_report.py` | 결과·탐색 비용 집계와 증거 불일치/변조 거절 검증 |
| `status.py` | 모델·Lean 호출 없이 현재 진행 상태 조회 |

원래 검증기·토큰 계산·공리 허용 목록은 `first-harness-jwkweon`에서 그대로 복사해 실행한다.
검증기의 공리 검사는 target을 계측하는 명령에서 수행한다. 원문 전체 plain compile는 별도다.
기존 연구의 별도 importer 공리 감사와 동일하다고 표현하지 않는다.

```sh
python3 -B -m unittest discover -s experiments/cost-hypothesis-pipeline -p 'test_*.py' -v
python3 -B -m unittest discover -s experiments/first-harness-jwkweon -p 'test_*.py' -v
```

공식 문서의 명확한 입력·출력 계약과 실제 workload 검증 원칙을 참고했다.
실험은 API tool calling을 추가하는 대신 기존 manual bridge를 유지한다.
[OpenAI prompting guidance](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra#prompting-best-practices)
