# #37 설계 기반 생성 루프와 수리 연결

실제 모델을 호출할 수 있는 Planner·Worker transport와 반복 생성 Controller를 구현했다.
사용자 요청으로 새 실행의 상한을 USD 2.50으로 낮추고, 대회용 호출 경로를 OpenRouter로 변경했다.
이전 USD 2.80/OpenAI 직접 호출 계획과 그 무과금 증거는 과거 revision으로 보존한다.
현재 검증은 고정 응답과 실제 Lean을 사용한다. **유료 API 호출·비용은 0이다.**
이 단계는 구조의 동작을 확인한다. P02의 최종 token/HB 개선을 입증하지 않는다.

2026-11-01에 확인한 [#37 공개 설계](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/37)에는
Planner/Worker가 아직 구현 전이고 선행 수정도 미공유라고 되어 있다.
따라서 여기의 코드는 `issue-37-based-local-implementation`이다.
#37의 비공개 코드와 호환성을 검증하거나 그 이슈를 완료 처리하지 않는다.
Controller만 있는 단일 에이전트와 Planner의 비교는 #37 자체의 별도 질문이다.
이번 비교에서는 Planner를 양쪽에 공통으로 둔다.

## 실행 흐름

1. 원본 전체 파일과 고정 환경을 확인한다. 원본 검증 실패 시 모든 조건을 중단한다.
2. Planner가 경로와 교훈을 반환한다. Controller가 경로별 시도 수를 기준으로 후보 생성을 배정한다.
3. Worker가 전체 `by` proof 하나를 반환한다.
4. 같은 후보이면 Lean 평가를 생략하고 중복 사실을 이력에 남긴다.
5. 공통 평가기로 명제·공리·proof token·HB를 검사한다.
6. 수리 조건은 실패 후보에 PR B의 Auto Solver → Recursive Repair를 적용한다.
7. 전체 검증을 통과하고 Q가 개선된 후보만 best로 선택한다.
8. 정체 3회 또는 같은 실패 종류 2회면 Planner를 다시 호출한다.
9. 종료 후 선택 proof를 새 Lean 프로세스로 검증한다. 이 단계에는 모델 호출이 없다.

Planner는 시작·정체·반복 실패에서만 호출한다. 최대 3회, 회당 실행의 누적 예산 USD 0.125다.
경로표에는 경로별 시도 수·최선 proof/T/H/Q·실패 종류·마지막 결과가 있다.
Planner가 예산·호출 한도에 도달하면 기존 경로를 사용한다.
Planner의 JSON이 잘못됐고 기존 경로도 없으면 원본 기반 경로로 계속한다.
API 비용을 알 수 없으면 예외 없이 전체 suite의 후속 호출을 중단한다.

실패 종류는 `missing_alternative`, `unknown_name`, `type_mismatch`, `rewrite`,
`unsolved_goals`, 기타 `proof_error`다. 응답 형식 오류와 중복은 별도로 기록한다.
이 구분은 Planner의 반복 실패 집계용이다. 수리 목표는 native 상태에서 선택한다.
중복 정규화는 CRLF와 파일 끝 공백만 다룬다. 들여쓰기·문자열·주석은 보존한다.
이는 의미적으로 같은 모든 proof를 찾는 기능이 아니다. 중복 생성 자체의 API 비용도 환불되지 않는다.

## 오류 위치와 수리 목표의 대응

기존 선택기는 중첩 `have`의 InfoTree 노드가 없으면 바깥 블록의 잔여 목표를 선택할 수 있었다.
`native.py`는 raw syntax의 가장 작은 `by`/bullet 범위와 오류 위치를 먼저 대응한다.
그 범위 안에서 블록 끝의 가장 바깥 전술 sequence를 사용한다.
한 전술짜리 블록은 끝 전술의 상태를 사용한다. 빈 상태나 서로 다른 상태는 추측해서 대체하지 않는다.
자식 수리에서는 자식 범위 안의 오류를 먼저 고른다. source hash와 UTF-8 byte 경계도 확인한다.

실제 P03 실패 기록 두 건에서 `Disjoint` 목표를 고르는 회귀 검사를 추가했다.
별도의 실제 Lean 검사에서는 `have h : β := by skip`의 바깥 목표가 닫힌 상태에서도
안쪽 `β`만 수리하고 바깥 proof를 보존하는지 확인한다.
지원하지 않는 문법은 계속 `extraction_unavailable`로 반환한다.
이 수정으로 모든 Lean 문법의 목표 대응이 보장되는 것은 아니다.

## P02 시간 한도와 계측

| 항목 | 새 P02 한도 |
| --- | ---: |
| Lean 프로세스 하나 | 60초 |
| 전체 평가 하나: 검증 1회 + HB 3회 | 최대 240초 |
| 후보 하나의 재귀 수리 | 600초 |
| 생성 실행 하나 | 1,800초 |
| 최종 검증 + 원본 복귀용 예약 | 480초 |
| Lean 메모리 | 2,048 MiB |

생성은 실행 시작부터 1,320초까지의 시간을 쓴다. 남은 480초는 최종 검증용이다.
각 하위 프로세스와 API 호출은 실행·수리의 남은 시간을 적용한다.
최종 proof의 증명 오류이면 정상 원본을 다시 검증한다.
timeout·환경 오류는 proof 오류로 바꾸지 않고 미확정으로 남긴다.
기존 소형 fixture의 기본 한도와 과거 C 결과의 한도는 바꾸지 않았다.

`calibrate.py`는 고정 Strata revision과 라이브러리 manifest를 사용하여 정상 원본을 3회 평가한다.
각 회차는 공통 검증 1회와 HB 측정 3회다. 이어 native 진단 1회를 확인한다.
세 회차 통과, HB 중앙값의 1% 이내 일치, 각 프로세스가 제한의 절반 이내인지를 검사한다.
최종 코드의 P02 결과: **T=222, 회차별 H 중앙값=2,695,001 / 2,695,001 / 2,695,003,
최대 프로세스 16.657561초**. HB 중앙값 차이는 2이며, 1% 안정성 기준을 통과했다.
60초 한도의 여유는 약 3.60배다. 다른 호스트에서는 다시 보정해야 한다.

`-T20000`과 공통 evaluator의 heartbeat 계측은 바꾸지 않았다.
HB는 목표 선언 elaboration의 raw heartbeat를 새 프로세스 3회로 측정한 중앙값이다.
진단·자동 전술·재귀 수리는 별도 Lean 호출을 늘린다. 그 호출 수와 전체 경과 시간도 기록한다.
최종 proof의 HB와 전체 실험의 계산량은 같은 지표가 아니다.

## 실행 전 동결하는 USD 2.50 계획

| 순서 | 조건 | 독립 반복 | 전체 API 상한 |
| --- | --- | ---: | ---: |
| 1 | Planner + Worker | 1 | USD 0.625 |
| 2 | Planner + Worker + Auto Solver → Recursive Repair | 1 | USD 0.625 |
| 3 | Planner + Worker + Auto Solver → Recursive Repair | 2 | USD 0.625 |
| 4 | Planner + Worker | 2 | USD 0.625 |

두 조건에 같은 정상 원본, 문맥, OpenRouter 모델 `openai/gpt-6.1-sol`와 표준 `openai` provider, high reasoning,
역할별 지침, 평가기, 경로 배정, 중복 차단을 적용한다.
과거 최선·제출 proof, 별도 전략 prompt와 다른 실행의 이력은 모델 입력에 넣지 않는다.
각 반복의 경로·best·중복 집합은 새로 시작한다. 원본 T0/H0만 공통으로 사용한다.
실행 ID는 내부 기록에만 쓰고 모델 입력에서는 제거한다.

Planner·생성 Worker·수리 Worker는 회당 USD 0.625와 전체 USD 2.50 장부를 함께 사용한다.
reasoning도 output 비용에 포함한다. cache hit을 가정하지 않은 최대 비용을 요청 전에 예약한다.
잔액이 적으면 output 한도를 줄이고, 최소 출력 여유도 없으면 호출하지 않는다.
예약과 요청을 먼저 디스크에 기록한다. receipt가 없거나 예약 상한을 넘으면 모든 후속 호출을 막는다.
자동 재시도와 provider fallback은 없다. 실제 비용은 OpenRouter의 `usage.cost`를 보존한다.
대회 정가 기준을 위해 사용량과 고정 공개 단가로 계산한 금액도 별도로 남긴다.
예산 차감에는 두 금액 중 큰 값을 쓴다. 비용이나 필수 사용량이 없으면 suite를 중단한다.
`prepare`는 공개 endpoint metadata를 동결하고, 유료 `run` 직전에 가격 변경 여부를 확인한다.

각 실행은 최종 T/H/Q, 선택 source, 원본 복귀, 수리 노출·복구,
역할별 호출·비용, 전체 Lean 호출·경과 시간과 중단 이유를 기록한다.
Q = T/T0 + H/H0이며 원본 복귀는 Q=2다.
두 반복의 값과 선택 source 차이는 탐색 변동을 보여 준다. 통계적 우월성을 입증하지 않는다.
record replay는 저장된 관측으로 Controller 결정을 재생한다.
새 모델 호출의 재현성이나 새 Lean 실행 성공을 의미하지 않는다.

## 파일과 명령

| 파일 | 역할 |
| --- | --- |
| `controller.py` | 경로·반복 실패·정체·best 관리, PR B 호출, 최종 검증 |
| `generation_transport.py` | Planner/Worker JSON 계약, 과거 direct transport, 고정 응답 transport |
| `openrouter_transport.py` | 현재 유료 호출의 유일한 경로, 공개 가격 검증, 정가/청구액 기록 |
| `generation_runtime.py` | 역할 공통 장부, 실행 시간, 중복 집합, 결정 기록 |
| `generation.py` | 네 실행의 준비·입력/코드 보존·직렬 실행·결과 집계·replay·status |
| `calibrate.py` | 유료 호출 없는 P02 정상 원본·환경·시간 검사 |

```bash
python3 experiments/verification-repair-policy/calibrate.py \
  --project /path/to/pinned/Strata --lean /path/to/lean-4.26.0/bin/lean \
  --output /path/to/new-calibration
python3 experiments/verification-repair-policy/generation.py prepare \
  --calibration /path/to/new-calibration --output /path/to/new-suite
python3 /path/to/new-suite/code/repo/experiments/verification-repair-policy/generation.py \
  check --output /path/to/new-suite
```

prepare/check/replay/status는 API를 호출하지 않는다.
유료 `run`은 명시적인 `--allow-paid`가 있어야 하며, 그때만 `OPENROUTER_API_KEY` 또는 지정 dotenv를 읽는다.
사용자는 레포 루트의 Git 제외 파일 `.env.repair-openrouter`에 `OPENROUTER_API_KEY=…`를 입력한다.
키 파일을 증거·입력·코드 snapshot에 복사하지 않는다. 일반 inference key를 쓰고, 관리용 key는 요구하지 않는다.
OpenRouter에서도 이번 실험 전용 key의 총 credit limit을 USD 2.50, 주기적 reset 없음을 권장한다.
하네스의 사전 비용 예약과 provider의 key 한도는 별도 장치다.
이번 준비에서는 유료 run을 실행하지 않았다. 중단한 suite를 이어서 실행하거나 같은 ID로 재호출하지 않는다.
계측 코드가 바뀌면 calibration을 다시 수행한다. 실행 코드가 바뀌면 새 suite를 준비한다.
이전 기록은 보존된 코드로 replay한다.

이전 revision의 검사와 증거는 [검증 기록](integration/validation.json)에 보존한다.
OpenRouter·USD 2.50 변경의 검사, 입력 동결, 공개 가격 출처는
[새 준비 기록](integration/openrouter-readiness.json)에 별도로 보존한다.

## 대회 규칙과 이번 실행의 범위

2026-11-01 [공식 규칙](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/main/app.py)은
폐쇄형 모델 호출 전부를 OpenRouter로 보내고, 문제당 USD 3 안에서 재시도·폐기 후보까지 합산하도록 요구한다.
이번 네 실행의 전체 비용을 하나의 P02 장부로 합산한다. 각 실행을 별도 문제로 계산하지 않는다.
기존 공통 guard로 명제 변경·sorry/admit·공리 추가·금지 메타프로그램·HB 조작을 거절한다.
진단/계측용 wrapper는 하네스 내부 코드다. 최종 proof 산출물에는 이를 넣지 않는다.

이번 대상은 이전부터 선택한 warm-up P02의 로컬 비교 실험이다.
최종 대회 데이터셋 제출이나 공식 점수 측정은 수행하지 않는다.
공식 제출 시에는 해당 benchmark ID와 지정 버전, 변경 없는 proof의 버전 호환성,
JSONL·재현 코드·기술 보고서 요구 사항도 별도로 확인한다.
