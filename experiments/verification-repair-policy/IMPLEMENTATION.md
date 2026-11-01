# PR B: 수리 정책 구현과 무과금 검증

이 구현은 [PR A의 설계](README.md)를 고정 응답으로 검사한다. 모델 API 호출은 0회다.
모델의 전략 선택 능력이나 두 정책의 성능 우열을 측정하지 않는다.

## 구현 범위

| 파일 | 책임 |
| --- | --- |
| [policy.py](policy.py) | 진단을 분류하고 다음 행동을 선택한다. 수리 이력과 중복 후보를 추적한다. |
| [prompts.py](prompts.py), [prompt/](prompt/) | v4의 공통 편집, 행동 지시, 변경 diff와 해시를 고정한다. |
| [adapter.py](adapter.py) | 기존 예산 실행기에 정책을 연결한다. 결정·관측 기록, 최종 검증, 기록 재생을 수행한다. |
| [run.py](run.py) | fixture 전용 prepare/check/run/replay/status 명령을 제공한다. |
| [fixtures/responses.json](fixtures/responses.json) | 미완성 → 타입 오류 → 유효 후보 → 응답 거절 → 유효 후보의 고정 응답이다. |

기존 `experiments/openrouter-budget-trial/run.py`에 선택적인 실험 인자를 추가했다.
후보 생성 루프, `LeanEvaluator`, proof 파서, 비용 영수증 파서와 호출 전 예약 계산을 재사용한다.
실험 인자를 주지 않는 기존 실행 경로는 유지한다. `src/`의 공통 정책이나 `status.py`는 변경하지 않는다.

## 상태와 행동

| 관측 | uniform-repair-v1 | state-aware-v1 |
| --- | --- | --- |
| 유효 후보 | best 갱신 후 개선 계속 | 동일 |
| 구체적인 Lean 오류 | 현재 실패 후보 수리 | 동일 |
| 명시적인 unsolved-goals 진단만 있음 | 현재 실패 후보 수리 | best에서 재탐색 |
| 응답 형식 거절 | best에서 출력 계약을 지켜 다시 요청 | 동일 |
| 중복 실패 후보 또는 후속 수리 2회 소진 | best에서 재탐색 | 동일 |
| 환경·계측·timeout·API·원인 불명 | 추가 요청 중단 | 동일 |

실제 우선순위는 [설계의 행동 표](README.md#행동과-우선순위)를 따른다.
검증기의 원래 결과를 보존하고 전체 진단에서 정책 상태를 계산한다. 모델에 보낼 진단의 길이는 그다음에 제한한다.
구체적인 오류와 남은 목표가 함께 있으면 `proof_error`다. native goals/local context는 수집하지 않으므로 null이다.
중복 판정은 공통 proof 파서가 조립한 동일 선언의 바이트 해시를 사용한다. 추가 평가 캐시는 없다.

첫 실패를 만든 생성 호출은 수리 횟수에서 제외한다. `repair_current` 이후의 호출은 응답 거절도 수리 횟수에 포함한다.
완료된 유효 후보를 먼저 best에 반영하고 다음 호출의 예산·상한을 확인한다.
최종 선택은 새 Lean 프로세스로 재검증한다. 구체적인 증명/계약 실패이면 원본을 다시 검증한다.
원본 복귀의 개선량은 0이다. 최종 timeout·환경·계측 오류 또는 원본 재검증 실패는 미확정(null)으로 남긴다.

## 준비 환경

- Python 3.10 이상. 하네스 실행에 외부 Python 패키지는 필요하지 않다.
- 실제 Lean 검사에는 미리 설치된 `leanprover/lean4:v4.26.0`과 PATH의 `lean`이 필요하다.
- 기본 문제는 `n + 0 = n`이다. GPU나 Mathlib 다운로드가 필요하지 않다.
- 누락된 toolchain을 자동 설치하지 않는다. 문제별 라이브러리가 필요한 입력은 사용자가 준비한 환경으로 한정한다.

일반 단위 검사는 Lean 없이 실행한다. 실제 Lean 검사는 별도로 선택한다.
현재 로컬 검증은 Python 3.12.13으로 수행했다. 실행할 Python의 버전은 `python3 --version`으로 확인한다.

## 실행

저장소 루트에서 실행한다. 모든 실행은 새 출력 폴더를 사용한다. 재개와 자동 재시도는 지원하지 않는다.

```sh
python3 experiments/verification-repair-policy/run.py prepare \
  --output runs/manual/repair-uniform-01 --policy uniform-repair-v1
python3 experiments/verification-repair-policy/run.py check \
  --output runs/manual/repair-uniform-01
python3 experiments/verification-repair-policy/run.py run \
  --output runs/manual/repair-uniform-01
python3 experiments/verification-repair-policy/run.py status \
  --output runs/manual/repair-uniform-01
python3 experiments/verification-repair-policy/run.py replay \
  --output runs/manual/repair-uniform-01
```

두 번째 조건은 새 폴더와 `--policy state-aware-v1`로 prepare한 뒤 실행한다.
`check`는 고정 입력·코드 해시를 확인한다. `run`은 실제 Lean 사전 점검, 원본 검증, 고정 응답 루프를 수행한다.
`replay`는 저장된 관측으로 결정·요청·모의 비용·종료·선택을 다시 계산한다. 모델과 Lean을 호출하지 않는다.

기본 fixture의 `usage.cost`는 호출당 `0.01`인 **모의 값**이다. `--simulated-budget-usd`도 예약기 검사에만 쓰는 가상 금액이다.
프로토콜과 최종 결과는 실제 API 비용 0과 모의 비용을 구분한다. 가격 snapshot은 과거 공개 응답이며 현재 요금표가 아니다.
이 CLI는 유료 backend, API key, dotenv 인자를 제공하지 않는다. 실행 중 기존 API·endpoint 조회 함수가 호출되면 검사를 실패시킨다.

기존 문제 입력을 확인하려면 prepare에 `--input-root 경로 --problem P01`을 지정할 수 있다.
각 문제 폴더에는 `agent-input.json`, `original.lean`, 기계별 `environment.json`이 있어야 한다.
한 개의 고정 Lean 환경을 지원한다. 최상위 `strategy_prompt`, `instructions`, `attempt_cap`, `output_protocol`은 모델 입력에서 제외한다.
`problem`의 name/statement/original과 `context`만 유지한다. context 내부의 설명까지 자동으로 전략 문장과 구별하지는 않으므로 실제 문제 비교 전에는 문맥 내용을 검토해야 한다.

## 산출물과 재현

| 경로 | 내용 |
| --- | --- |
| `protocol.json`, `frozen-inputs.json` | 정책·분류기 버전, 입력·코드 해시, 호출 한도, 모의 예산, 실행 기준 |
| `common-prompt.txt`, `common-prompt.diff`, `actions.json`, `prompt-manifest.json` | 검토한 공통 프롬프트와 편집·행동 지시 해시 |
| `문제/attempt-NNN-decision.json` | 호출 전 상태, 행동, 기준 후보·요청 해시, 예약액, 수리 묶음·종료 이유 |
| `문제/attempt-NNN-observation.json` | 정책 상태, 원래 진단과 근거 해시, 후보 코드, goal 수집 여부 |
| `문제/attempt-NNN-{request,response,result}.json` | 실제 fixture 요청·응답과 평가 결과 |
| `문제/stop-decision.json` | 마지막 상태와 추가 호출을 하지 않은 이유 |
| `문제/summary.json`, `문제/result.json` | 최종 검증, 선택 출처, 모의/실제 비용 구분, replay 결과 |
| `문제/events.jsonl`, `문제/artifacts.json` | 기존 상태 조회기가 읽는 단계 이력과 완료 기록 |
| `code/repo/`, `artifacts.json` | 보관 실행 코드와 전체 산출물 해시 |

결정 기록은 기존 atomic 저장 함수를 통해 fsync한 뒤 fixture를 읽는다.
소스가 바뀌면 새 실행을 준비한다. 이전 기록은 보관 코드를 사용한다.

```sh
python3 -B runs/manual/repair-uniform-01/code/repo/experiments/verification-repair-policy/run.py \
  replay --output runs/manual/repair-uniform-01
```

산출물 폴더를 이동해도 재생할 수 있다. 재생은 기록 무결성 검사이며 증명을 새로 검증하는 작업은 아니다.
이 fixture 실행에서 `selected_origin=generated`는 고정 응답의 후보를 선택했다는 뜻이다. 실제 모델을 호출했다는 뜻이 아니다.

## 검증 명령

```sh
PYTHONPATH=src python3 -m unittest discover \
  -s experiments/verification-repair-policy -p 'test_*.py' -v
PYTHONPATH=src REPAIR_POLICY_LEAN_TESTS=1 python3 -m unittest discover \
  -s experiments/verification-repair-policy -p 'test_lean.py' -v
```

단위 검사에서는 컴파일러 결과를 모의한다. 분기·수리 0/1/2회·중복·마지막 개선·예산 부족·미확정 영수증·최종 원본 복귀·미확정 결과를 확인한다.
입력 힌트 제거, 같은 상태에서의 첫 요청 동일성, 변조 탐지, 폴더 이동 후 보관 코드 재생도 검사한다.
실제 Lean 검사에서는 두 정책의 5회 루프, 미완성/타입 오류/혼합 오류/금지 공리 판정, 최종 선택과 상태 조회를 확인한다.
CI에는 무과금 단위 검사만 추가했다. CI가 Lean을 자동 설치하거나 모델 API를 호출하지 않는다.

2026-11-01 로컬 검증에서 새 단위 검사 27개, 실제 Lean 검사 2개, 기존 하네스 22개, 기존 예산·API 어댑터 24개로 **총 75개가 통과**했다.
기본 단위 검사 명령에서는 실제 Lean 검사 2개를 건너뛰며, 별도 명령으로 해당 검사를 실행했다.
[검증 기록](validation.json)에 실행 명령·환경·소스 해시·실제 Lean 관측과 로컬 증거 경로를 보관했다.
전체 로그는 `runs/manual/` 아래에 있으며 Git에 포함하지 않는다. 실제 API 호출과 비용은 0이다.

## 해석과 후속 작업

고정 응답은 정책의 요청 내용을 보고 생성되지 않는다. 따라서 이 결과로 수리·재탐색의 우열이나 모델의 지시 준수를 주장할 수 없다.
동일한 baseline·상태를 넣은 요청의 동일성은 검사했지만, 독립된 실제 Lean 실행은 heartbeat와 실행 시간 측정값이 달라질 수 있다.
유료 비교를 설계할 때는 공통 baseline snapshot과 모델 입력에 포함할 측정값을 함께 고정해야 한다.
fixture 검사에서는 두 조건 모두 HB profiler를 끈다. 실제 비교에서 profiler를 사용할지는 같은 설정으로 다시 고정한다.

P01–P05의 전체 실행 환경 준비, 현재 모델·가격 확인, 실제 API dispatch 연결 및 성능 비교는 보류한다.
유료 실행을 검토할 때는 현재 main·관련 PR 변경도 다시 확인한다. PR B는 무과금 구현 검증으로 완료한다.
