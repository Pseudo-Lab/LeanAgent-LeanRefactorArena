# PR #3와 main: 환경 검사·오류 기록 대응표

이 문서는 코드 정적 검토 결과다. 기능의 존재와 한계를 확인했으며 런타임 성공을 새로 측정하지 않았다.
기준은 [PR #3 c18ec566](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/tree/c18ec56682462847e2f4d8b6d60aa79ec071a10b)와
[main ba593fc](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/tree/ba593fc4357ee5c429b8f28f1aac512d05bb4355)다.
아래 경로·함수는 각각 이 commit의 파일을 가리킨다. 이동하는 `main` 브랜치 최신 내용과 혼용하지 않는다.

## 핵심 차이

main의 `src/lean_agent/evaluator/lean.py`는 PR #3의 `refactor_eval/lean.py`와 비교하면
자식 프로세스 환경변수 허용 목록, `--print-prefix`를 통한 실제 compiler 경로와 바이너리 SHA-256 검사를 추가했다.
컴파일·공리·heartbeat 검사 흐름은 대부분 같다. 옛 평가기를 복사하면 main의 보강을 잃는다.

큰 차이는 실행 제어에 있다. #3는 변경 가능한 Session manifest와 checkpoint·recover를 사용하고,
main은 요청·응답·상태 전이를 기록하여 재생하는 단일 모델 하네스다.
환경 검사 아이디어는 가져오되 Session 저장 형식과 점수 정책은 이식하지 않는다.

## 기능별 대응과 결정

| 기능 | PR #3 코드·동작 | main 코드·동작 | 이번 결정 |
| --- | --- | --- | --- |
| 설정·입력 검사 | `refactor_eval/session.py:load_config()`가 선언·template·여러 환경·선택 정책 검사 | `harness.py:load_config()`가 설정·fixture·template 검사. 외부 의존성 있는 project 거절 | **main 재사용.** 기존 검사 결과에 단계·근거를 연결. 초기 파일 읽기·설정 실패도 기록 |
| Lean 버전 확인 | `refactor_eval/lean.py:LeanEvaluator.fingerprint()`에서 toolchain 파일과 실제 `--version` 대조 | `evaluator/lean.py:fingerprint()`에서 같은 검사 및 compiler 실체·해시 추가 | **main 재사용.** 없거나 잘못된 도구의 결과를 사전 점검 기록으로 보완 |
| 환경 파일 fingerprint | toolchain·Lake 설정·선택 파일·template·Git HEAD/diff 기록 | 같은 기능. 단 실행 하네스는 별도 snapshot project를 사용 | **main 재사용.** 현재 fingerprint는 모든 라이브러리 산출물의 완전한 lock이 아님을 명시 |
| 의존성·빌드 산출물 검사 | `scripts/validate_environment_pilot.py:check_checkout/resolve_environment/inventory()`가 기존 checkout·의존성 commit 및 compiler/library 전체 파일 확인 | 공통 하네스는 외부 의존성 없는 프로젝트만 지원. 전체 라이브러리 inventory 없음 | **이번 실험에서 제외.** 고정 입력·실행 파일 hash 원칙만 참고. 라이브러리 어댑터는 후속 |
| 부모 환경변수 처리 | 일반 `execute()`는 부모 환경 상속. 파일럿 `clean_environment()`만 compiler·LEAN_PATH를 직접 구성 | `evaluator/lean.py:execute()`가 명시된 환경변수만 전달 | **main 재사용.** 파일럿의 macOS 실행기를 이식하지 않음 |
| template 문법 검사 | `validate_template()`가 필수 marker의 수·순서·독립 줄 확인 | 동일 | **재사용.** 이 검사는 import가 실제로 가능한지 증명하지 않음 |
| 문맥의 실제 컴파일 | `evaluate()`가 원문 문맥과 후보를 함께 컴파일 | 동일. 기준 증명도 모델 호출 전에 검증 | **추가.** 후보를 넣기 전 허용 문맥만 확인하는 단계. 기존 baseline 검사와 목적·비용을 구분 |
| 실행 제한·로그 | `execute()`가 프로세스 그룹 종료, timeout·returncode·seconds·출력 제공. 평가 단계가 로그·source hash 저장 | 같은 동작 및 환경변수 제한 | **재사용·보완.** fingerprint 실행의 원문 출력도 별도 보존. subprocess 시작 실패도 진단으로 기록 |
| 기본 오류 종류 | 평가기는 `validation/environment/timeout/compile/axioms`; Session은 예외를 `evaluation_error`로 묶음 | 평가기 종류는 같음. `feedback()`은 `response_rejected/environment_failed/proof_rejected/verified`로 전달 | **수정.** 기존 원본 결과를 보존하며 실패 단계와 진단 종류를 별도 기록 |
| API·응답 오류 | `cli.py`의 외부 agent subprocess와 JSON 프로토콜. API별 진단은 없음 | `models.py:query()`는 transport 오류·HTTP 상태를 반환하고 자동 재시도하지 않음. `parse_proof()`는 응답 형식을 검사 | **main 재사용·보완.** API 실패와 응답 파싱 실패를 증명 오류와 구분. 실제 호출 없이 fixture·오류 주입으로 검증 |
| 원인 오분류 가능성 | 누락된 측정 report 등의 `ValueError`도 평가기에서 `environment` 처리 | 같은 넓은 예외 분류. `compile`만으로 import 실패와 proof 실패를 구분하지 못함 | **보완.** 문맥 점검 근거 및 측정 프로토콜 실패를 구분. 로그 문자열만으로 원인을 확정하지 않음 |
| 초기 실패 기록 | `Session.initialize()`는 fingerprint 후 run directory 생성. 그 이전 실패는 manifest 없음 | `run()`의 설정·일부 준비가 `try` 바깥. `try` 내 예외의 `failure.json`은 상태·예외 타입만 저장 | **추가.** 유효한 출력 위치 확보 후 초기 단계부터 기록. 출력 위치 자체를 만들 수 없으면 stderr·종료 코드 사용 |
| 환경 변경 검사 | `Session._check_environment()`가 checkpoint 전·측정 후·최종 선택 전에 fingerprint 비교 | `run()`의 시작과 최종 검증 후 fingerprint 비교 | **실험 대상으로 보완.** 후보 실행 경계의 경량 검사와 기존 전체 fingerprint를 구분하고 추가 비용 측정 |
| 실행 중 상태 | `Session._measure()`가 측정 전 `pending` 저장, 종료 후 해제 | 모델 호출 전 request 저장, 응답·평가 후 event 저장. Lean 단계 pending 기록은 없음 | **원칙만 재사용.** 단계 시작·완료·실패 기록 추가. 끊긴 실행은 미완료로 표시하며 자동 재개하지 않음 |
| 코드·입력 무결성 | manifest가 구현·설정·후보 hash 검사. 코드 전체 복사 방식은 아님 | `snapshot/CODE_FILES/seal/check_artifacts/replay()`가 코드·입력 보관과 상태 전이 검증 | **main 재사용.** 향후 추가 모듈·설정·진단 기록도 보관·무결성 검증에 포함 |
| 모델 호출 전 중단 | `run_search()` 전에 Session 초기화·baseline 확인 | fingerprint·baseline 성공 후 요청 시작. 환경 실패·비용 미확정 시 중단 기능 존재 | **기존 동작 유지·검증.** 새 기여는 사전 중단 자체의 발명이 아니라 원인·단계·근거의 명확화 |
| 후보 평가·선택 | `assess()`는 scaled heartbeat와 설정 가능한 가중치, 동점은 이전 후보 우선 | `candidate/ranking()`은 raw heartbeat 비율의 정수 분자, 동점은 토큰·SHA256 | **main 유지.** #3의 선택 함수를 가져오면 비교 조건이 달라짐 |
| 복구·동시 실행·여러 버전 | Session의 `recover()`·fcntl 잠금·다중 환경 finalization | 단일 환경·신규 run, replay는 외부 호출 없이 기록 재계산 | **제외.** 상태 진단과 유료 실행 재개를 분리 |

`harness.py`는 main의 `src/lean_agent/harness.py`, `evaluator/`는 `src/lean_agent/evaluator/`의 축약이다.

## 실험에서 추가할 최소 계약

이는 새 API의 구현 완료를 뜻하지 않는 실험 설계다.

- 단계: `config`, `environment`, `context`, `baseline`, `model`, `candidate`, `final`.
- 단계 상태: `started`, `passed`, `failed`; 종료 기록 없이 끊긴 단계는 분석 시 `incomplete`.
- 실패 종류: `configuration`, `environment`, `api`, `response`, `proof`, `timeout`, `measurement`, `unknown`.
- 근거: 원래 error kind/message, exception type, command, returncode, timed_out, 로그 상대 경로와 해시,
  입력·후보·환경 식별값, 단계 시간. 적용되지 않는 값은 `null`로 두고 추정하지 않는다.
- 기존 evaluator 결과를 새 분류로 덮어쓰지 않는다. 파생 진단과 원본을 함께 보관한다.
- 시간 초과는 발생 단계와 관측 사실을 남긴다. 자원 부족·증명 난이도 중 무엇이 원인인지 자동 단정하지 않는다.
- Lean timeout은 기존 로컬 보호 설정의 관측값이며 이번 핵심 기능이나 대회 실패 판정 기준이 아니다.
  API 응답 timeout은 호출 결과·비용 미확정과 함께 기록하고 자동 재호출하지 않는다.
- 문맥 점검 통과는 후보 증명의 유효성을 보장하지 않으며 이후 환경 변화를 배제하지도 않는다.
  근거가 부족한 compile 실패는 `unknown`으로 남길 수 있어야 한다.
- 잘못된 기준 증명도 `baseline` 단계 실패다. 이를 곧바로 설치 문제로 분류하지 않는다.
- 출력 폴더 생성 실패 시 로그 파일이 생겼다고 보고하지 않는다. 기존 run은 덮어쓰지 않는다.

문맥 점검은 template의 기존 import·선행 문맥·닫는 구문을 보존한 파일을 compiler로 확인하는 방식부터 실험한다.
선언 없이 컴파일할 수 없는 template은 환경 실패로 단정하지 않고 지원 제한으로 기록한다.
계측용 import를 추가하여 원래 import 실패를 가리지 않으며, 기준 증명 컴파일은 계속 별도 수행한다.
이 추가 컴파일 비용은 main보다 늘어나는 비용으로 명시적으로 측정한다.

## 재사용할 검증 근거와 새 사례

| 기존 검증 코드 | 확인하는 내용 | 활용 |
| --- | --- | --- |
| #3 `tests/test_evaluation.py:test_environment_change_blocks_comparison` | 환경 변경을 감지하면 비교 차단 | 새 검사 위치의 회귀 사례 참고 |
| #3 `tests/test_lean_integration.py:test_timeout_keeps_partial_diagnostics` | timeout에서 부분 진단 보존 | 단계별 timeout 기록 설계 참고 |
| #3 `test_interrupted_checkpoint_requires_recovery_and_is_never_a_score` | 끊긴 측정을 성공 점수로 처리하지 않음 | 미완료 상태 의미만 참고. recover는 이식하지 않음 |
| main `tests/test_harness.py:test_environment_failure_stops_without_charging_another_call` | 환경 실패 후 다음 모델 호출 차단 | 유지할 동작 |
| main `test_baseline_failure_is_incomplete_not_a_new_trial` | baseline 실패 처리 | 실패 기록을 보강해도 기존 무효 처리 유지 |
| main `test_invalid_candidate_never_wins_and_replay_uses_no_external_calls` | 무효 후보 배제·외부 호출 없는 replay | 유지할 동작 |
| main `test_archived_package_replays_from_another_working_directory` | 보관된 코드의 독립 replay | 새 파일도 snapshot에 포함하는지 확인 |

이번 문서 작업에서 위 테스트를 새로 실행한 것은 아니다. 다음 실험에서는 정상·도구 누락·버전 불일치·
import 실패·기준 증명 오류·후보 오류·API/응답 오류·측정 근거 누락·미완료 상태 조회를 `design.json`에 따라 비교한다.
Lean 단계별 timeout은 선택적 로컬 보호 회귀 검사로 분리한다.
오류 주입으로 얻은 진단 결과와 실제 Lean 실행 결과는 분리한다.

## src 통합 판단 기준

1. 같은 고정 응답·입력과 같은 저장 측정값을 사용했을 때 기존 후보 선택과 replay가 유지된다.
   실제 Lean 반복의 raw heartbeat가 비트 단위로 같아야 한다는 조건은 두지 않는다.
2. 사전 점검에서 실패한 실행은 fixture 요청과 실제 API 호출 모두 0회다.
3. 환경 오류·증명 실패·timeout·측정 실패·미확정을 구분한 근거가 남는다.
4. 검사 자체의 시간·컴파일 횟수를 보고하고, 누락·실패를 전략 성능 수치에 섞지 않는다.
5. 새 실행 코드·입력·설정·진단이 snapshot과 replay 계약에 들어간다.

판단 대상은 환경 사전 점검과 진단 기록에 한정한다. 전략 성능 개선, 라이브러리 전반 지원,
공식 worker 동등성, 복구·재개 기능의 완료를 주장하지 않는다.
