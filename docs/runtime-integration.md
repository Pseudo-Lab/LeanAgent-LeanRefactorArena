# 환경 점검·오류 피드백·상태 조회의 src 통합

관련 이슈: [#27](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/27).
`experiments/environment-preflight`에서 검증한 기능 1–3을 `src/lean_agent` 공통 패키지에 연결했다.
실행 방법은 [공통 하네스 사용법](first-harness.md)을 참고한다.

## 기준과 적용 범위

기존 `proposal/problem-environment-lock` 브랜치에서 작업했다. 이 브랜치에는 main의 패키지가
없었으므로, main `09ea3c4066569309c971993af32d49200b72d07c`의 패키지·패키징 설정·예제·하네스
회귀 검사를 가져온 뒤 기능을 통합했다. 해당 main의 `src/lean_agent`, 설정·예제·하네스 검사는
실험이 고정했던 `ba593fc4357ee5c429b8f28f1aac512d05bb4355`와 동일함을 비교했다.
초기 통합은 필요한 main 파일만 가져왔다. PR 준비 시 main을 merge하고, 기준 이후 바뀌지 않은
공유 파일 5개는 검증된 통합 버전을 유지해 충돌을 해결했다. 로컬의 별도 작업은 보존했다.

기능 원본은 실험 commit `7c670039ce1b5a571752d3abca35e750dcd8e342`이다.
실험의 기준 코드·설계 lock·검증 결과·실행기는 유지한다. 설치 패키지는 실험 디렉터리나
캐시에 복원한 main, 전역 함수 교체에 의존하지 않는다.

| 기능 | 패키지 연결 | 동작 |
| --- | --- | --- |
| 1. 환경 사전 점검 | `preflight.py`, 평가기 `preflight`, `run`/`check` | 모델 호출 전에 준비된 Lean·버전·prefix·문맥 검사. 실패 시 기록 후 종료 |
| 2. 오류 분류·피드백 | `diagnostics.py`, 평가기와 하네스 | 원문 로그·해시 보존, 실패 종류 분리, 다음 허용 요청에 안내 전달 |
| 3. 실행 상태 조회 | `status.py`, `run`의 단계 기록 | 시작·완료를 영속 기록하고 마지막 검증 후보와 최종 결과를 구분 |
| 공통 기록 | `artifacts.py`, `replay` | JSON·해시 처리 공유, 코드·입력·결과·단계 기록의 일관성 확인 |

기존 후보 점수, 동점 처리, baseline fallback, 호출 제한, 과금 불명 시 중단 정책을 유지했다.
원래 평가기의 환경 실패와 별도로 계측 오류를 진단하므로, 기존 종료 정책도 보존된다.
기존 OpenRouter 연결은 동일하게 사용한다. 새 비용 계산·subagent 과금 모드는 포함하지 않는다.

실험의 hook은 평가기의 executor 주입과 하네스의 명시적 진단 호출로 바꿨다.
사전 점검에서 얻은 fingerprint를 시작 기준으로 사용해 시작 시 중복 fingerprint 호출을 없앴다.
종료 시 환경 불변 확인은 유지한다. 실행 기록은 루트의 `steps/`, `diagnostics/`, `events.jsonl`에
모으고, 기존 `summary.json`에 더해 전체 수명주기를 나타내는 `result.json`을 저장한다.
보관 코드만으로 replay와 status를 사용할 수 있다.

## 검증

구조화된 결과는 [runtime-integration-validation.json](runtime-integration-validation.json)에 기록했다.

- main merge 후 전체 저장소 테스트: 77개 중 73개 통과, 별도 opt-in 실제 Lean 검사 4개 건너뜀.
- Harness CI는 Python 3.10·3.13에서 기존 하네스와 새 runtime 통합 검사를 함께 실행한다.
- 기존 실험 회귀 검사: 68개 모두 통과. 별도 Python 프로세스에서 실행해 패키지 경로를 분리했다.
- 통합 검사: 환경 실패 시 모델 0회, 원문 증명 오류 피드백, Unicode·깊은 JSON 거절,
  API 응답·과금 불명 시 재시도 없음, 계측 실패 분리, Ctrl-C/SystemExit/예외 기록,
  실제 자식 프로세스 SIGKILL, 실행 중 읽기 전용 조회, 이동·변조·replay를 확인했다.
- Python 3.13의 별도 중앙 가상환경에 wheel을 설치하고 저장소 밖에서 실제 Lean 4.26.0으로
  fixture 실행, 상태 조회, 패키지 replay, 보관 코드 replay/status를 확인했다.
  기존 실험과 동일한 2토큰 `by rfl` 후보를 선택했다. heartbeat는 실행별 실제 표본을 기록한다.
- 설치된 패키지에서 누락된 compiler를 지정하면 실패 기록을 남기고 모델 호출 전에 종료한다.

실제 Lean 검사에 사용한 모델 응답은 fixture이며 유료 API 호출은 없다.
실제 OpenRouter 통신, 외부 라이브러리 환경, 자동 설치·복구·재시도·중단 후 재개,
여러 실행기가 공유하는 journal은 이번 통합 검증 범위에 포함하지 않는다.

## 확인할 명령

```sh
lean-agent check --config configs/smoke.json --output runs/manual/check-01
lean-agent run --config configs/smoke.json --output runs/manual/run-01
lean-agent status runs/manual/run-01 --json
lean-agent replay runs/manual/run-01
```

사전 점검 실패는 사람에게 원인과 로그를 남기는 동작이다. 에이전트가 환경을 자동 수정하거나
실패한 실행을 이어서 수행하지 않는다. 원인을 해결한 뒤 새로운 출력 폴더로 실행한다.
