# 환경 사전 점검·오류 상태 실험

[이슈 #27](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/27)의 1단계 정리다.
작성일은 2026-10-27이며, 작업 브랜치는 기존 `proposal/problem-environment-lock`이다.
이번 변경은 비교·범위 결정·기준 고정까지다. 실험 실행과 `src/` 통합은 아직 하지 않았다.

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

이 lock은 **소스·입력·설계의 기준**이다. 앞으로 작성할 실험 코드와 실제 Python·Lean 실행 파일,
호스트 상태가 이미 고정·검증되었다는 뜻은 아니다. 현재 실행 결과와 성능 수치는 없다.
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

실험 구현·실행기는 다음 단계에서 작성한다. 이 문서의 사례와 산출물 이름은 실행 계약이며 기존 CLI 옵션이 아니다.
기준 또는 설계를 변경하면 새 실험 버전과 lock을 만들고, 과거 run의 lock·입력·로그를 덮어쓰지 않는다.

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
- [ ] 실험 코드와 실행 환경을 run 단위로 고정하고 사례 실행
- [ ] 실패 분류·비용·정상 경로·replay 비교
- [ ] 검증 요약을 근거로 src 통합
