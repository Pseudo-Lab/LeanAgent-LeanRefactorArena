# #37 설계 기반 생성 루프와 수리 연결

실제 모델을 호출할 수 있는 Planner·Worker transport와 반복 생성 Controller를 구현했다.
현재 요청은 P02에서 수리 모듈을 켠 생성 루프 한 회차의 token·HB·지정 버전 호환성을 확인하는 것이다.
API 상한 USD 2.50 전체를 이 한 회차에 배정한다. 호출 경로는 OpenRouter다.
이전 네 실행 비교 계획과 그 무과금 증거는 과거 revision으로 보존한다.
현재 검증은 고정 응답과 실제 Lean을 사용한다. **유료 API 호출·비용은 0이다.**
이 단계는 구조의 동작을 확인한다. P02의 최종 token/HB 개선을 입증하지 않는다.

2026-11-01에 확인한 [#37 공개 설계](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/37)에는
Planner/Worker가 아직 구현 전이고 선행 수정도 미공유라고 되어 있다.
따라서 여기의 코드는 `issue-37-based-local-implementation`이다.
#37의 비공개 코드와 호환성을 검증하거나 그 이슈를 완료 처리하지 않는다.
Controller만 있는 단일 에이전트와 Planner의 비교는 #37 자체의 별도 질문이다.
이번 단일 실행에는 Planner·Worker·Auto Solver·Recursive Repair를 모두 사용한다.

## 실행 흐름

1. 원본 전체 파일과 고정 환경을 확인한다. 원본 검증 실패 시 모든 조건을 중단한다.
2. Planner가 경로와 교훈을 반환한다. Controller가 경로별 시도 수를 기준으로 후보 생성을 배정한다.
3. Worker가 전체 `by` proof 하나를 반환한다.
4. 같은 후보이면 Lean 평가를 생략하고 중복 사실을 이력에 남긴다.
5. 공통 평가기로 명제·공리·proof token·HB를 검사한다.
6. 수리 조건은 실패 후보에 PR B의 Auto Solver → Recursive Repair를 적용한다.
7. 전체 검증을 통과한 후보를 main의 `harness.candidate()`·`harness.ranking()`으로 비교한다.
8. 정체 3회 또는 같은 실패 종류 2회면 Planner를 다시 호출한다.
9. 종료 후 선택 proof를 새 Lean 프로세스로 검증한다. 이 단계에는 모델 호출이 없다.

Planner는 시작·정체·반복 실패에서만 호출한다. 최대 3회, 한 회차의 누적 예산 USD 0.50다.
Planner 상한은 전체 USD 2.50에 포함한다.
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

| 실행 | 구성 | 회차 | 전체 API 상한 |
| --- | --- | ---: | ---: |
| `repair-r1` | Planner + Worker + Auto Solver → Recursive Repair | 1 | USD 2.50 |

정상 원본, 문맥, OpenRouter 모델 `openai/gpt-6.1-sol`와 표준 `openai` provider, high reasoning,
역할별 지침, 공통 평가기, 경로 배정, 중복 차단을 사용한다.
과거 최선·제출 proof, 별도 전략 prompt와 다른 실행의 이력은 모델 입력에 넣지 않는다.
경로·best·중복 집합은 새로 시작한다. 실행 직전에 다시 검증·측정한 정상 원본을 T0/H0로 쓴다.
과거 보정 결과는 환경과 계측 안정성을 확인하는 기준이며 새 원본 측정값을 덮어쓰지 않는다.
실행 ID는 내부 기록에만 쓰고 모델 입력에서는 제거한다.

Planner·생성 Worker·수리 Worker는 한 회차의 USD 2.50 장부를 함께 사용한다.
reasoning도 output 비용에 포함한다. cache hit을 가정하지 않은 최대 비용을 요청 전에 예약한다.
잔액이 적으면 output 한도를 줄이고, 최소 출력 여유도 없으면 호출하지 않는다.
예약과 요청을 먼저 디스크에 기록한다. receipt가 없거나 예약 상한을 넘으면 모든 후속 호출을 막는다.
자동 재시도와 provider fallback은 없다. 실제 비용은 OpenRouter의 `usage.cost`를 보존한다.
대회 정가 기준을 위해 사용량과 고정 공개 단가로 계산한 금액도 별도로 남긴다.
예산 차감에는 두 금액 중 큰 값을 쓴다. 비용이나 필수 사용량이 없으면 suite를 중단한다.
`prepare`는 공개 endpoint metadata를 동결하고, 유료 `run` 직전에 가격 변경 여부를 확인한다.

실행은 최종 T/H/Q, 원본 대비 절대·백분율 변화, 선택 source, 원본 복귀, 수리 노출·복구,
역할별 호출·비용, 전체 Lean 호출·경과 시간과 중단 이유를 기록한다.
Q = T/T0 + H/H0이며 원본 복귀는 Q=2다.
한 회차에서 도달한 품질을 기록한다. 이번 실행에는 수리 없는 조건 비교나 독립 반복이 없다.
record replay는 저장된 관측으로 Controller 결정을 재생한다.
새 모델 호출의 재현성이나 새 Lean 실행 성공을 의미하지 않는다.

## 공통 하네스의 완료·비용·선택 규약

현재 revision은 `single-repair-4-official-compatibility`다.
생성 실행과 재생은 `generation.py`가 담당하며, 공통 하네스의 상태·비용 조회와 선택 함수를 연결한다.
기존 `lean-agent run/replay` 명령으로 생성 실험을 직접 실행하는 것은 별도 범위다.

- 각 실행의 계산 결과는 `summary.json`에 보존한다. 전체 suite의 기록 replay와 비용 재계산이
  통과한 뒤에만 `result.json`에 replay 확인을 넣고 journal을 종료한다.
  개별 실행의 `artifacts.json`을 먼저 만들고 마지막에 suite 해시 목록을 만든다.
  공통 `status.py`는 이 기록과 최종 소스 해시를 확인해 완료를 표시한다.
  중단·replay 실패는 성공으로 봉인하지 않는다. 비용 미확정 실행은 `stopped`로 남는다.
- `calls/`에는 역할·예약액·요청과 원본 응답을 보존한다. `recorded_usage.py`는 이를 공통
  `accounting.py`로 집계한다. `usage-cost.json`은 실행별·전체·역할별 비용을 제공한다.
  OpenRouter 청구액, 공개 정가 계산액, 예산 차감액과 예약액은 별도 값이다.
  호출마다 장부와 대조하고 replay에서도 다시 계산한다. fixture의 실제 비용은 0으로 표시한다.
- 선택 순서는 `(T × H0 + H × T0, T, 선언 SHA256)`이다. 정수 비교로 미세한 차이와 동점을 처리한다.
  경로별 best와 전체 best에 같은 함수를 쓴다. Q 동점의 후보 교체는 정체를 해소한 것으로 세지 않는다.

이 브랜치의 공통 CLI 또는 동결한 코드의 `lean_agent` 모듈로 조회할 수 있다.

```bash
lean-agent status /path/to/suite/runs/repair-r1 --json
lean-agent usage-cost --mode api --format recorded-run --input /path/to/suite
```

상태 조회는 각 실행 폴더를 사용한다. 비용 조회는 개별 실행과 전체 suite 모두 지원한다.

## 파일과 명령

| 파일 | 역할 |
| --- | --- |
| `controller.py` | 경로·반복 실패·정체·best 관리, PR B 호출, 최종 검증 |
| `generation_transport.py` | Planner/Worker JSON 계약, 과거 direct transport, 고정 응답 transport |
| `openrouter_transport.py` | 현재 유료 호출의 유일한 경로, 공개 가격 검증, 정가/청구액 기록 |
| `generation_runtime.py` | 역할 공통 장부, 실행 시간, 중복 집합, 결정 기록 |
| `generation.py` | 단일 생성 실행의 준비·입력/코드 보존·결과 집계·replay·status |
| `competition.py` | 공식 원본과 지정 버전 고정, 최종 검증에 근거한 호환성 보고 |
| `generation_records.py` | 공통 기록 연결, 비용 대조, replay 검증 후 완료 처리 |
| `src/lean_agent/recorded_usage.py` | 역할별 요청·원본 영수증을 읽는 공통 비용 조회 adapter |
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
유료 `run`은 명시적인 `--allow-paid`가 있어야 한다. 가격과 라이브러리를 확인한 뒤
터미널에서 `OpenRouter API key (hidden input):`을 표시한다. 사용자가 키를 입력하고 Enter를 누른다.
입력 내용은 화면에 표시하지 않는다. 키는 프로세스 메모리에서만 사용한다.
파일·환경 변수·명령 인자로 키를 받지 않으며 `--dotenv` 옵션도 없다.
숨김 입력을 지원하지 않는 비대화형 터미널에서는 호출 전에 중단한다.
일반 inference key를 사용하며, 관리용 key는 요구하지 않는다.

```bash
python3 /path/to/suite/code/repo/experiments/verification-repair-policy/generation.py \
  run --output /path/to/suite --allow-paid
```
OpenRouter에서도 이번 실험 전용 key의 총 credit limit을 USD 2.50, 주기적 reset 없음을 권장한다.
하네스의 사전 비용 예약과 provider의 key 한도는 별도 장치다.
이번 준비에서는 유료 run을 실행하지 않았다. 중단한 suite를 이어서 실행하거나 같은 ID로 재호출하지 않는다.
계측 코드가 바뀌면 calibration을 다시 수행한다. 실행 코드가 바뀌면 새 suite를 준비한다.
이전 기록은 보존된 코드로 replay한다.

이전 revision의 검사와 증거는 [검증 기록](integration/validation.json)에 보존한다.
OpenRouter·USD 2.50 변경의 검사, 입력 동결, 공개 가격 출처는
[OpenRouter 전환 당시 기록](integration/openrouter-readiness.json)에 별도로 보존한다.
완료·비용·선택 규약과 터미널 입력 변경은 [이전 준비 기록](integration/shared-records-readiness.json)에 보존한다.
단일 회차와 지정 환경 계약은 [현재 준비 기록](integration/single-run-readiness.json)에 보존한다.

## 지정 버전 호환성 출력

고정한 warm-up P02의 공식 `version_info`에는 Lean `v4.26.0`과 Strata
`451e5f047bafa010d178856db76c00029bfa4d7f` 한 조합이 있다.
공식 benchmark 파일의 SHA-256과 원본 선언을 대조하고 지정 버전 목록을 입력에 고정한다.
생성 전 환경 fingerprint를 확인하고, 최종 선택 소스를 수정 없이 같은 전체 파일 문맥에서 검증한다.
이 최종 평가를 근거로 `compatibility.json`에 `passed_versions: 1`, `required_versions: 1` 또는
`not_confirmed`를 기록한다. 원본으로 복귀한 경우에도 원본의 호환성을 기록한다.
이 P02에 지정되지 않은 다른 Lean 버전의 통과나 공식 서버 평가 통과를 주장하지 않는다.
필수 버전 목록이 늘어나면 일부 버전만 검사하는 대신 준비 단계에서 중단한다.

## 대회 규칙과 이번 실행의 범위

2026-11-01 [공식 규칙](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/main/app.py)은
폐쇄형 모델 호출 전부를 OpenRouter로 보내고, 문제당 USD 3 안에서 재시도·폐기 후보까지 합산하도록 요구한다.
이번 한 실행의 Planner·생성·수리 비용을 하나의 P02 장부로 합산한다.
기존 공통 guard로 명제 변경·sorry/admit·공리 추가·금지 메타프로그램·HB 조작을 거절한다.
진단/계측용 wrapper는 하네스 내부 코드다. 최종 proof 산출물에는 이를 넣지 않는다.

이번 대상은 이전부터 선택한 warm-up P02의 로컬 단일 실행이다.
최종 대회 데이터셋 제출이나 공식 점수 측정은 수행하지 않는다.
공식 제출 시에는 해당 benchmark ID와 지정 버전, 변경 없는 proof의 버전 호환성,
JSONL·재현 코드·기술 보고서 요구 사항도 별도로 확인한다.
