# 환경 사전 점검·오류 상태 실험

[이슈 #27](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/27)의 기획과 기능 1 실험이다.
작성일은 2026-10-27이며, 작업 브랜치는 기존 `proposal/problem-environment-lock`이다.
기획 기준은 커밋 `e872351`에 보존했다. 기능 1을 `experiments/`에서 구현·검증했으며 `src/` 통합은 아직 하지 않았다.

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
| 실험 설계 | [design.json](design.json), 버전 `environment-preflight-v2` |
| 출처·무결성 | [baseline.lock.json](baseline.lock.json)의 commit·Git tree·파일 SHA-256 |

입력 복사본은 [baseline/main/configs/smoke.json](baseline/main/configs/smoke.json)부터 상대 경로로 연결된다.
PR #3의 과거 Strata·PutnamBench 후보와 결과를 이번 스모크 입력에 섞지 않는다.
`baseline/main/`에는 입력·설정만 있다. main 실행 코드는 lock의 정확한 commit에서 별도 복원해야 한다.
이 브랜치의 `refactor_eval`을 main 기준 구현인 것처럼 실행하지 않는다.

이 lock은 **소스·입력·설계의 기준**이다. 실제 실험 코드·Python·Lean과 호스트는 실행별
`run-lock.json`, `compiler-before-check.json`, `environment.json`으로 별도 기록한다.
초기 미실행 v1 기획에서 기능 1–3과 timeout의 역할을 정리해 v2로 갱신했다.
기준 코드·입력·설정 bytes는 동일하며, lock에 이전 설계 해시와 변경 사유를 남긴다.

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

아래 실행기는 기능 1만 구현한다. 전체 `design.json`의 기능 2·3 사례 실행기는 후속 범위다.
기준 또는 설계를 변경하면 새 실험 버전과 lock을 만들고, 과거 run의 lock·입력·로그를 덮어쓰지 않는다.

## 기능 1 구현과 사용법

| 파일 | 역할 |
| --- | --- |
| [baseline.py](baseline.py) | 고정 main을 중앙 캐시에 복원하고 파일 해시를 확인한 뒤 import |
| [preflight.py](preflight.py) | 준비된 Lean 실행 파일·버전·문맥 검사, 결과·원문 로그 저장 |
| [run.py](run.py) | 입력·코드 snapshot, 사전 점검, 통과한 경우에만 기존 main fixture 실행 |
| [test_preflight.py](test_preflight.py) | 실패 시 모델 호출 차단, 정상 선택·replay 유지 등 20개 검사 |

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

문맥에는 template의 기존 문맥만 사용한다. 증명 후보, 계측용 `import Lean`, 계측 wrapper를 추가하지 않는다.
문맥 컴파일 실패는 `stage=context`, `reason=context_compile_failed`로 차단한다. import 오류와
선언 없는 검사에 맞지 않는 template을 문자열 추측으로 구분하지 않으므로 상세 종류는 `unknown`으로 남기고
원문 로그를 연결한다. 이는 기능 2의 세부 오류 분류 완료를 주장하지 않기 위한 경계다.

정상 점검 후에는 같은 compiler·설정·template인지 main의 시작 fingerprint에서 다시 비교한다.
기존 평가·토큰·heartbeat·선택 정책과 main 소스 bytes는 바꾸지 않았다.

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
- [ ] 기능 2·3의 오류 분류·실행 상태 조회 구현 및 전체 사례 실행
- [ ] 검증 요약을 근거로 src 통합
