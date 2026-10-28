# 환경 사전 점검·오류 상태 실험

[이슈 #27](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/27)의 기획과 기능 1–3 실험이다.
작성일은 2026-10-27이며, 작업 브랜치는 기존 `proposal/problem-environment-lock`이다.
기획 기준은 커밋 `e872351`, 기능 1은 `35906ca`에 보존했다. 기능 2도 `experiments/`에서 구현하며 `src/` 통합은 마지막 단계다.

## 목적과 결정

모델 호출 전에 발견할 수 있는 환경 문제를 확인하고, 실패한 단계와 근거를 기록한다.
PR #3 전체를 main에 병합하는 대신 현재 main 하네스를 기준으로 부족한 기능만 실험한다.

- 재사용: main의 평가기, 실행 제한, 컴파일러 fingerprint, 토큰·raw heartbeat 기반 선택, 코드·입력 스냅샷과 replay.
- 수정·추가: 실패 기록의 시작 시점, 문맥만 확인하는 사전 검사, API·응답·증명 실패의 구분, 단계별 오류 기록, 로그 연결, 실행 상태 조회.
- 후속으로 분리: 설치·다운로드·자동 복구·재시도·실행 재개, 범용 라이브러리 어댑터, OS 격리, 웜업 CI·게시 작업.

상세 코드 대응과 결정 근거는 [comparison.md](comparison.md)에 있다.

## 기능별 기획 범위

| 기능 | 내용 | 이번 계획에서의 위치 |
| --- | --- | --- |
| 1. 환경 사전 점검 | Lean 실행·버전·기본 문맥을 확인하고, 실패 시 모델 호출 전에 원인·로그를 남김 | 우선 범위 |
| 2. 실패 구분·전달 | API 호출 실패, 응답 형식 오류, 증명 컴파일 오류, 계측 실패를 구분하고 원문 근거를 전달 | 우선 범위. API 사례는 실제 호출 없이 오류 주입으로 확인 |
| 3. 실행 상태 조회 | 각 단계 시작·종료를 기록하여 마지막 완료 단계와 완료가 확인되지 않은 단계를 조회 | 우선 범위. 미완료를 곧바로 실패나 성공으로 판정하지 않음 |
| 4. 중단 후 재개 | 저장된 응답·검증 결과부터 이어 실행 | 포함 여부 추후 결정 |
| 5. API/subagent 비용 관리 | 사용량과 비용 또는 환산 추정액을 분리하여 기록 | 후속 후보. 이번 기획 커밋에는 비용 계산 구현 미포함 |
| 6. 여러 실험 비교 | 같은 문제·환경·예산 조건의 실행 결과 비교 | 후속 후보 |

기능 2의 중심은 실패 원인을 다음 수정에 전달하는 것이다. Lean wall-clock timeout을 대회 실패 판정
기준으로 추가하지 않는다. 기존 스모크 설정의 30초는 비교 기준에 포함된 **로컬 실행 보호 설정**이며,
이를 증명 오류·대회 규정 위반으로 해석하지 않는다. API 응답 timeout은 호출 결과·비용이 미확정일 수
있으므로 별도로 기록하고 자동 재호출하지 않는다.

기능 3은 조회까지다. 시작만 기록된 단계는 `incomplete`로 표시하되 실제 프로세스 종료를 확인했다고
주장하지 않는다. 마지막으로 검증된 후보와 최종 선택·재검증이 완료된 결과도 구분한다.

## 고정한 기준

| 항목 | 고정값 |
| --- | --- |
| PR #3 참고 코드 | `c18ec56682462847e2f4d8b6d60aa79ec071a10b` |
| main 실행 기준 | `ba593fc4357ee5c429b8f28f1aac512d05bb4355` |
| 입력·설정 | main의 `configs/smoke.json`과 `examples/first-harness/` 6개 파일을 원본 bytes 그대로 복사 |
| 문제 | `smoke-nat-add-zero` / `first_harness_identity` |
| Lean | `leanprover/lean4:v4.26.0`, 외부 패키지 없는 단일 환경 |
| 모델 | `fixture`, 유료 API 호출 0회 |
| 제한 | 고정 응답 3개, Lean 실행당 30초, 계측 3회. 나머지는 복사한 설정 그대로 |
| 실험 설계 | [design.json](design.json), 버전 `environment-preflight-v4` |
| 출처·무결성 | [baseline.lock.json](baseline.lock.json)의 commit·Git tree·파일 SHA-256 |

입력 복사본은 [baseline/main/configs/smoke.json](baseline/main/configs/smoke.json)부터 상대 경로로 연결된다.
PR #3의 과거 Strata·PutnamBench 후보와 결과를 이번 스모크 입력에 섞지 않는다.
`baseline/main/`에는 입력·설정만 있다. main 실행 코드는 lock의 정확한 commit에서 별도 복원해야 한다.
이 브랜치의 `refactor_eval`을 main 기준 구현인 것처럼 실행하지 않는다.

이 lock은 **소스·입력·설계의 기준**이다. 실제 실험 코드·Python·Lean과 호스트는 실행별
`run-lock.json`, `compiler-before-check.json`, `environment.json`으로 별도 기록한다.
초기 미실행 v1 기획에서 기능 1–3과 timeout의 역할을 정리해 v2로 갱신했다.
기준 코드·입력·설정 bytes는 동일하며, lock에 이전 설계 해시와 변경 사유를 남긴다.
v3는 subagent 검증에서 발견한 중단 상태·잘못된 Unicode/깊은 JSON·계측 보고서 손상 처리 계약을 추가했다.
v4는 단계 기록과 읽기 전용 상태 조회를 추가한다. 고정 main·기준 입력·선택 규칙은 동일하다.

## 다음 단계의 실행 계약

1. lock의 commit에서 main 실행 코드·테스트를 프로젝트 중앙 캐시의 별도 디렉터리로 복원하고 해시를 확인한다.
   현재 브랜치에 main을 병합하거나 main의 `src/`를 덮어쓰지 않는다.
2. 준비된 Lean 4.26.0과 프로젝트 Python interpreter의 실제 경로·버전·해시를 기록한다.
   누락된 도구를 자동 설치하지 않는다. 특히 `elan` shim이 설치를 시작하지 않도록 준비 여부를 먼저 확인한다.
3. `design.json`의 사례별로 새 입력 복사본을 만든다. 기준 파일은 수정하지 않고,
   적용한 변경과 결과 입력의 SHA-256을 실행 기록에 남긴다.
4. 기준 구현과 실험 구현을 별도 출력 폴더에서 실행한다. 실행 코드 commit과 미커밋 변경 해시,
   전체 실행 코드 snapshot, 설계·입력·설정 해시를 모델/Lean 실행 전에 보관한다.
5. 단계·오류 종류·원문 로그·모델 요청 횟수·실제 API 호출 횟수·추가 컴파일 횟수·시간을 비교한다.
   `fixture` 요청도 호출 루프 진입 여부를 판단하기 위해 센다. API 비용 0이라는 사실만으로 사전 중단을 입증하지 않는다.
6. 기존 평가·선택 정책과 replay 회귀 검사를 통과한 기능만 별도 통합 PR에서 `src/lean_agent`로 옮긴다.

아래 실행기는 기능 1–3의 고정 기준 실험이다. 자동 재개·비용 관리는 포함하지 않는다.
검증된 기능의 공통 패키지 통합은 [src 통합 기록](../../docs/runtime-integration.md)과
[공통 하네스 사용법](../../docs/first-harness.md)을 참고한다. 이 실험의 기준 코드·lock은 유지한다.
기준 또는 설계를 변경하면 새 실험 버전과 lock을 만들고, 과거 run의 lock·입력·로그를 덮어쓰지 않는다.

## 기능 1 구현과 사용법

| 파일 | 역할 |
| --- | --- |
| [baseline.py](baseline.py) | 고정 main 복원·해시 확인·import 및 공통 산출물 해시 수집 |
| [preflight.py](preflight.py) | 준비된 Lean 실행 파일·버전·문맥 검사, 결과·원문 로그 저장 |
| [run.py](run.py) | 입력·코드 snapshot, 사전 점검, 통과한 경우에만 기존 main fixture 실행 |
| [diagnostics.py](diagnostics.py) | 원문 평가 결과를 유지한 실패 진단 및 다음 요청의 오류 피드백 |
| [replay.py](replay.py) | 보관된 코드로 진단 피드백까지 재현하는 외부 호출 없는 replay |
| [test_preflight.py](test_preflight.py) | 실패 시 모델 호출 차단, 정상 선택·replay 유지 등 20개 검사 |
| [test_diagnostics.py](test_diagnostics.py) | API 오류 주입, 계측·증명·응답 구분, 피드백·선택·replay 검사 |
| [test_hardening.py](test_hardening.py) | 중단 신호·응답 경계·계측 보고서 손상의 재현 및 회귀 검사 |
| [status.py](status.py) | 단계 시작·종료 기록과 읽기 전용 상태 조회 CLI |
| [test_status.py](test_status.py) | 실행 중 조회·실제 SIGKILL·최종 결과 구분·기록 손상·이동 검증 |

Python 3.10 이상이 필요하다. 이번 검증은 기존 Python 3.13.11과 설치된 Lean 4.26.0으로 수행했고
환경·의존성을 새로 설치하지 않았다. `python3.13`은 로컬에서 사용한 실행 명령이며 다른 호스트에서는
프로젝트 환경의 Python 3.10 이상 interpreter로 바꾼다. 명령마다 아래의 `env/use.sh` 설정을 먼저 적용한다.

사전 점검만 실행:

```sh
python3.13 experiments/environment-preflight/run.py check \
  --config experiments/environment-preflight/baseline/main/configs/smoke.json \
  --output runs/environment-preflight/my-check
```

점검 통과 후 고정 응답 3개로 기존 하네스와 replay까지 실행:

```sh
python3.13 experiments/environment-preflight/run.py run \
  --config experiments/environment-preflight/baseline/main/configs/smoke.json \
  --output runs/environment-preflight/my-run
```

출력 폴더는 매 실행 새로 지정한다. 설정 오류도 가능한 한 결과 폴더에 기록하고,
출력 폴더 자체를 만들 수 없으면 stderr와 비정상 종료 코드로 알린다.

- `result.json`: 실행 결과, 실패 단계, 모델 요청 수와 API 호출 수.
- `preflight.json`: 사전 점검 결과·오류 사유·각 명령·로그 위치·시간.
- `checks/environment/`: 버전·설치 경로 명령의 원문 로그 및 실행 정보.
- `checks/context/context.lean`, `checks/context/*.log`: 후보를 제외한 문맥과 원문 compiler 진단.
- `run-lock.json`, `code/`, `planning/`, `input/`: compiler 실행 전 코드·설계·입력·Python 고정.
- `compiler-before-check.json`, `environment.json`: 실제 실행 파일 해시와 main 평가기의 fingerprint.
- `artifacts.json`: 실행 산출물 해시 목록.
- `harness/`: 사전 점검을 통과한 `run` 명령에만 생성되는 기존 main 실행 기록.
- `diagnostics/`: 기능 2의 단계별 진단. 원문 오류, 근거 파일의 상대 경로·SHA-256, 오류 발췌와 안내.
- `events.jsonl`: 기능 3의 단계별 시작·종료 및 실행 종료 기록. 쓰기 직후 flush/fsync.

문맥에는 template의 기존 문맥만 사용한다. 증명 후보, 계측용 `import Lean`, 계측 wrapper를 추가하지 않는다.
문맥 컴파일 실패는 `stage=context`, `reason=context_compile_failed`로 차단한다. import 오류와
선언 없는 검사에 맞지 않는 template을 문자열 추측으로 구분하지 않으므로 상세 종류는 `unknown`으로 남기고
원문 로그를 연결한다. 기능 2는 이 원문 결과를 덮어쓰지 않고, 명확한 누락 module 진단이 있는 경우에만
별도 `diagnostics/preflight.json`에서 `environment/missing_import`로 분류한다.

정상 점검 후에는 같은 compiler·설정·template인지 main의 시작 fingerprint에서 다시 비교한다.
기존 평가·토큰·heartbeat·선택 정책과 main 소스 bytes는 바꾸지 않았다.

## 기능 2: 실패 원인과 다음 시도의 피드백

실행 명령은 위와 동일하다. 실패 진단은 `result.json`의 `diagnostics` 목록에서 찾는다.
실행 예외로 중단되면 가능한 경우 `failure_diagnosis`가 해당 진단 파일을 가리킨다.
이는 완료된 검사·오류 기록이며 실행 중인 프로세스의 상태 조회나 재개 기능은 아니다.

| 분류 | 판단 근거 | 처리 |
| --- | --- | --- |
| `api` | 모델 어댑터의 transport error 또는 HTTP 오류 receipt | 호출 결과·청구 미확정 기록, 재호출 없이 기존 unknown-cost 중단 유지 |
| `response` | JSON/응답 envelope 파싱 실패 또는 증명 선언 계약 위반 | 응답 형식 안내. 비용이 알려진 fixture는 다음 시도 진행 |
| `proof` | 원본 문맥의 `check.lean`에서 종료 코드 1과 Lean 오류 진단, 또는 허용되지 않은 공리 | 실패 후보 배제, 실제 오류와 목표를 다음 요청에 전달 |
| `measurement` | 원본 검사는 통과했고 `measure-*` 단계에서 실패 또는 보고서 누락 | 증명이 틀렸다고 안내하지 않음. 원래 평가기의 거절·중단 정책 유지 |
| `environment` | 명시적 환경 점검 실패 또는 누락 module의 compiler 진단 | 원문 오류와 환경 점검 안내 |
| `timeout` | 기존 compiler 실행 기록의 timed_out | 로컬 보호 중단, 증명 오류나 대회 실패로 판정하지 않음 |
| `unknown` | 신호 종료, 근거 부족 또는 서로 다른 실패 원인 | 원인을 추정해 단정하지 않음 |

분류는 기록된 단계·진단에 근거한 실험용 해석이다. 특히 `measurement`는 별도 계측 과정의 실패이며
정확한 근본 원인을 확정하지 않는다. compiler 실행에 추가 재시도를 넣지 않는다.

원래 평가기가 반환한 `valid`, `error`, 측정값은 바꾸지 않는다. main이 계측 보고서 누락을
`environment`로 기록하고 중단하는 것도 유지한다. 추가 진단에서만 `measurement`로 설명한다.
기존 `feedback.status`도 중단 규칙과의 호환성을 위해 유지하고, `feedback.diagnosis`와 `details`에
추가 분류·안내·Lean 로그 발췌를 넣는다. 예를 들어 main의 `proof_rejected` 상태가 로컬 timeout에
대해 남아 있어도, 상세 진단의 `timeout`은 증명 실패 판정이 아니다.

`details`는 기존 `max_feedback_characters` 이내이며 실행 경로를 `<RUN>`으로 바꾼다.
전체 원문은 로그와 진단 파일에 남긴다. 전체 요청 크기 제한·호출 수 제한·토큰/heartbeat 선택 규칙은
고정 main 그대로다. 피드백 변경으로 요청 크기가 달라질 수 있으므로 실시간 모델 성능 개선을 주장하지 않는다.

피드백이 상태와 요청 기록에 포함되므로 기능 2 실행은 **실험용 replay**로 검사한다:

```sh
python3.13 experiments/environment-preflight/replay.py runs/environment-preflight/my-run
```

이 명령은 실행 폴더에 보관된 `code/replay.py`, `code/diagnostics.py`, `code/lean_agent/`를 사용한다.
Git 캐시, Lean, 모델 호출 없이 전체 실행 산출물 해시와 main의 상태 전이를 검사한다.
실행 폴더 전체를 다른 위치로 복사해도 재현된다. 기능 2의 피드백이 추가된 기록을 고정 main의
replay만으로 검사하면 상태 불일치가 발생한다. 과거 기능 1 기록의 replay 방식은 그대로다.

단위 검사는 compiler 출력이나 API receipt를 명시적으로 주입한다. API의 HTTP/transport/timeout 사례는
저장된 main 어댑터가 반환하는 receipt 형식을 대상으로 하며 실제 네트워크·API 통합 검증은 아니다.
fixture 실행에서 발생한 임의의 Python 예외를 API 오류라고 단정하지 않는다.

최초 검증 근거는 [validation-feature2.json](validation-feature2.json)에 정리했다. 이 기록은 설계 v2의
`879af9b` 구현에 대한 것이며 이후 보완 검증은 아래에 별도로 기록한다. 기능 1 검증 파일과 과거 실행
산출물을 수정하지 않는다. 이 최초 검증 기록에는 기능 3 검증이 포함되지 않는다.

2026-10-28 검증 결과:

- 기능 1·2 단위/연결 검사 41개(기존 20개 + 신규 21개), 고정 main 회귀 검사 19개 통과.
- 실제 Lean 정상 실행: 첫 증명 오류와 `⊢ False` 목표가 다음 요청에 포함되고, 3개 fixture 이후
  기존과 같은 2토큰 `by rfl` 선택. 최종 raw heartbeat 중앙값 23,213. 기록 replay 통과.
- 실제 잘못된 기준 증명: `baseline/proof`로 진단하고 모델 요청 0회로 중단.
- 실제 malformed JSON fixture: 첫 응답을 `model/response`로 거절하고 다음 후보 처리 및 replay 통과.
- 실제 누락 import: `context/environment` 진단을 추가하고 모델 요청 0회로 중단.
- API 오류·계측 보고서 누락·timeout·신호 종료는 주입 검사. 유료 API 호출은 모든 사례에서 0회.
- 실제 4개 실행의 산출물 목록·근거 파일 해시 검증, 보관 코드 replay 검증 완료.
  원문은 로컬 `runs/environment-preflight/feature2-20261028-*`에 있으며 Git에는 포함하지 않는다.

### subagent 검증 후 보완 — 설계 v3

세 subagent의 1라운드 검증에서 기존 41개 검사가 놓친 세 가지 경계를 발견했고,
재현 사례를 [test_hardening.py](test_hardening.py)에 추가했다.

- **중단/미처리 예외**: Ctrl-C·SystemExit는 실제 단계를 `interrupted`로 저장한 뒤 다시 전달한다.
  그 밖의 실행 예외는 `failed`로 저장한다. `run` 시작 후 사전 검사 상태인 `ready`가 남지 않으며,
  미완료 실행의 replay는 명시적으로 거절한다. 자동 재개·재시도는 하지 않는다.
- **응답 경계**: JSON 깊이 128을 초과하거나 Unicode scalar가 잘못된 응답은 `response`로 거절한다.
  원문 receipt는 손실 없는 JSON escape로 보존한다. 문자열 안의 괄호와 정상적인 Unicode surrogate
  pair는 허용하며, 후보 파일 작성 전 검사한다. 알려진 비용의 fixture는 다음 시도로 진행한다.
  정상 응답의 직렬화 bytes·선택 기준은 그대로다. 같은 응답 검사를 archived replay에도 적용한다.
- **계측 예외**: 원본 검사가 통과하고 계측 프로세스도 성공했지만 보고서 해석에서
  `KeyError`·`TypeError`·`RecursionError`가 발생하면, 이전에는 반환되지 않던 invalid 평가 결과를
  만들어 예외 종류와 원문을 보존한다. main의 기존 malformed-report 환경 오류 중단 정책에 맞추고,
  별도 진단에서는 `measurement`와 원문 로그·SHA-256을 연결한다. 측정값은 만들어내지 않는다.
  계측 근거가 없는 예외는 `unknown`으로 남긴다. 기준 증명·후보·최종 검증에 동일하게 적용한다.

보완 결과는 [validation-feature2-hardening.json](validation-feature2-hardening.json)에 기록했다.
기존 41개 + 추가 12개, 총 53개 실험 검사와 고정 main 19개 회귀 검사를 통과했다.
실제 Lean 정상/Unicode 오류 fixture 실행은 모두 3개 응답 처리 후 같은 `by rfl`을 선택하고
보관 코드 replay를 통과했다. 깊은 JSON·SIGINT·계측 필드 누락 재현은 compiler 응답 주입으로
별도 보존했다. 총 5개 실행의 코드 snapshot·산출물 목록·진단 근거 해시를 확인했다.
이 변경은 기능 3의 실행 중 상태 조회를 구현한 것이 아니다. SIGKILL·전원 종료처럼 정리 코드를
실행할 수 없는 중단은 여기서 처리하지 않으며, 시작/완료 기록을 통한 미완료 조회는 기능 3의 범위다.

### 구조 정리

보완 구현은 `1b78f0f`에 보존했다. 이후 리팩터링은 설계 v3와 출력 형식을 유지한다.
`execute()`는 입력 고정·사전 검사·결과 기록을 담당하고, 하네스 연결은 `run_harness()`로 분리했다.
단계·호출 수·실패 참조는 `RunProgress`에서 관리하여 중첩 함수의 `nonlocal` 공유를 제거했다.
계측 단계 판별과 실행/replay의 산출물 해시 수집은 각각 공통 함수로 합쳤다.
새 실행 계층이나 의존성을 추가하지 않았으며, 기존 53개 회귀 검사와 실제 Lean 실행·보관 코드
replay로 확인한다. 검증 기록은 [validation-refactor.json](validation-refactor.json)에 남긴다.

## 기능 3: 실행 상태 조회 — 설계 v4

리팩터링은 `a6f5566`에 보존했다. 새 실행은 코드·입력 고정부터 단계별 기록을 남긴다.
실행 방법은 이전과 같고, 조회는 별도 명령이다:

```sh
python3.13 experiments/environment-preflight/status.py runs/environment-preflight/my-run
python3.13 experiments/environment-preflight/status.py runs/environment-preflight/my-run --json
```

조회는 실행 폴더를 읽기만 한다. Lean·모델 호출, 파일 갱신, 재시도·재개, PID 생존 추정을 하지 않는다.
보관된 `code/status.py`로도 조회할 수 있어 폴더를 옮긴 뒤에도 원래 코드로 확인할 수 있다.

| 조회 항목 | 의미 |
| --- | --- |
| `last_completed_stage` | 마지막으로 통과 완료가 기록된 단계 |
| `last_finished_stage` | 실패·중단을 포함해 마지막 종료 기록이 있는 단계 |
| `incomplete_stages` | 시작 기록은 있지만 종료 기록이 없는 단계와 후보 번호 |
| `latest_verified_candidate` | 평가 결과와 근거가 저장된 마지막 유효 후보. 최종 선택과 다를 수 있음 |
| `final_verification` | 최종 검증 단계 자체의 종료 결과 |
| `final_result` | 전체 실행 완료, 최종 검증·replay 성공, 결과·기록 봉인까지 확인된 결과 |
| `diagnostics` | 기능 2의 오류 분류와 원문 근거로 연결되는 진단 파일 |

예를 들어 후보 1 통과 후 후보 2 검증 중 강제 종료되면, 후보 1을 마지막 검증 후보로 보여주고
후보 2는 `incomplete`, 최종 결과는 미확정으로 표시한다. 조회 시 프로세스가 아직 실행 중일 수도
있으므로 `process_state`는 `unknown`이다. Ctrl-C처럼 정리 코드가 실행되면 `interrupted` 종료를 기록한다.
API 오류로 `stopped`가 된 실행은 마지막 증명의 최종 검증을 통과했더라도 완료된 실험 결과로 올리지 않는다.

기록은 단일 writer의 append-only JSONL이다. 시작은 해당 작업 전에, 종료는 근거 파일 저장 후에 남긴다.
계측 결과·응답 파일을 쓰기 전에 종료 기록부터 남기지 않는다. 원본 문맥 검사, 하네스 시작/끝 환경 검사,
기준 증명, 모델 요청, 응답 해석, 각 후보, 최종 검증, replay를 구분한다.
진행 중인 `events.jsonl`은 실행 전 고정 파일 해시에서 제외하고, 실행 종료 시 산출물 목록에 봉인한다.

마지막 줄이 아직 쓰이는 중이면 그 줄을 제외한 완전한 기록까지만 읽는다. 완전한 줄의 형식 오류나
저장된 근거 해시 불일치는 `unknown`과 `record_error`로 알린다. 종료 기록은 있지만 최종 봉인이 없으면
완료 여부는 미확정이다. 단계 기록이 없는 과거 실행은 이력 추정 없이 `unknown`으로 표시한다.
이 조회는 기록 무결성 확인이며 증명 재검증이나 실행 재개 기능이 아니다.

검증은 기존 53개 + 상태 조회 15개, 총 **68개 검사**, 고정 main 회귀 19개를 통과했다.
새 Python subprocess를 후보 2에서 실제 SIGKILL한 검사(compiler는 fixture)와 실행 중 조회,
Ctrl-C·봉인 누락·변조·부분 기록·폴더 이동을 확인했다. 실제 Lean 정상 경로는 기존 선택과 replay를 유지한다.
검증 근거는 [validation-feature3.json](validation-feature3.json)에 정리했다.

현재 지원은 **외부 의존성이 없는 단일 환경 + 직접 실행하는 Lean compiler + fixture**다.
설치된 `elan` shim은 고정 버전의 실제 binary로 해석하여 실행하고, 버전이 없으면 설치 없이 중단한다.
Lake나 사용자 wrapper 명령, 외부 라이브러리 adapter, live API 실행은 이번 실행기에서 지원하지 않는다.
단일 프로세스 실험에서 main의 executor를 잠시 감싸 로그를 수집하므로 같은 프로세스의 여러 thread에서
동시에 사용하지 않는다. src 통합 시 executor를 명시적으로 주입하는 경계로 바꿀 예정이다.

## 기능 1 검증 — 2026-10-27

정리된 실행 근거는 [validation-feature1.json](validation-feature1.json)에 있다.
전체 원문·입력·코드는 로컬 `runs/environment-preflight/feature1-20261027-*`에 보존했다.

| 검사 | 결과 |
| --- | --- |
| 기능 1 단위·연결 검사 | 20개 통과. compiler 응답·측정값을 주입한 검사임을 구분 |
| 고정 main 하네스 회귀 검사 | 19개 통과 |
| 실제 Lean 정상 경로 | 사전 점검 → fixture 3개 → 최종 검증 → replay 통과 |
| 실제 기존 main과 비교 | 같은 2토큰 `by rfl` 후보 선택. 두 실행 모두 최종 raw heartbeat 중앙값 23,213 |
| 도구 누락·toolchain 파일 불일치 | Lean 실행과 모델 요청 전에 중단 |
| 실제 import 오류 | 문맥 단계에서 중단, 원문 compiler 로그 보존, 모델 요청 0회 |
| 보관된 코드의 독립 replay | 다른 작업 폴더에서 모델·Lean 재호출 없이 통과 |
| 추가 점검 비용 | 정상 실험 1회에서 약 2.18초. 버전·설치 경로 확인 2회와 문맥 컴파일 1회 |

고정 응답 요청 3회는 API 호출이 아니다. 모든 검사와 실험의 유료 API 호출은 0회다.
heartbeat 일치는 이번 스모크 관측이며 일반적인 실행 간 완전 일치나 전략 성능 개선을 뜻하지 않는다.
초기 별도 `check` 실행은 약 2.36초였으며 위 2.18초는 정상 연결 실행의 관측값이다.
사전 점검 시간은 호스트·캐시 상태에 따라 달라진다. 라이브러리 전체·공식 worker에 대한 검증은 하지 않았다.

```sh
python3.13 -m unittest discover -s experiments/environment-preflight -p 'test_*.py' -v
```

## 저장 위치와 실행 환경

- 실험 코드·문서·입력: `experiments/environment-preflight/`
- 실행 산출물: `runs/environment-preflight/<run-id>/{baseline,experimental}/`
- 각 run: `run-lock.json`, `cases/`, 진단·원문 로그, 비교 요약. 이름은 다음 단계에서 구현할 계약이다.
- Python 환경: `/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/.venv`
- 검사·복원 캐시: `/Users/jwkweon/00_work/00_project/cache/05_pseudolab/LeanAgent-LeanRefactorArena/`

이 로컬 프로젝트에서 명령 세션마다 다음 설정을 먼저 적용한다. 스크립트는 환경을 자동 활성화하지 않는다.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
```

실험 로그·입력·모델 결과는 캐시로 취급하지 않는다. 비밀값이나 로컬 `.env`는 복사·기록하지 않는다.

## 진행 상태

- [x] PR #3와 main의 환경 검사·오류 기록 대응표 작성
- [x] 재사용·수정·제외 범위 확정
- [x] 기준 commit·입력·설정·실험 설계와 파일 해시 고정
- [x] 기능 1 코드·실행 환경 고정 및 정상·환경 실패 사례 실행
- [x] 기능 1 추가 검사 비용·정상 선택·replay 비교
- [x] 기능 2의 오류 구분·근거 저장·다음 요청 피드백 및 회귀 검사
- [x] 기능 3의 실행 상태 조회·강제 종료·기록 무결성·최종 결과 구분 검증
- [x] 검증 요약을 근거로 src 통합 — [통합 기록](../../docs/runtime-integration.md)
