# Final 환경 준비 현황

기준: 2026-11-02T07:20:09.450676+00:00

Final 60문제는 출처·revision·Lean 버전 조합 17개와 compiler 버전 8개, 문제·버전 조합 127개를 사용한다. 기존 환경을 읽기 전용으로 재사용해 F001을 먼저 측정했다. 이 세 환경의 현재 봉인 범위는 F001이며 전체 Strata 10문제 준비 완료를 뜻하지 않는다.

현재 디스크 여유: 6.30 GiB. 기존 `prepare.py`의 새 빌드 최소 여유 기준은 15 GiB다. 이 기준을 낮추거나 원본 증거·다른 작업의 환경을 삭제하지 않았다.

| 환경 | 전체 대상 문제 수 | 재사용해 봉인된 문제 | 현재 상태 |
| --- | ---: | --- | --- |
| arklib-v4.30.0 | 10 | 없음 | 준비 대기 |
| arklib-v4.31.0 | 10 | 없음 | 준비 대기 |
| arklib-v4.33.1 | 3 | 없음 | 준비 대기 |
| arklib-v4.34.0 | 2 | 없음 | 준비 대기 |
| cslib-v4.30.0 | 1 | 없음 | 준비 대기 |
| cslib-v4.31.0 | 3 | 없음 | 준비 대기 |
| cslib-v4.33.1 | 10 | 없음 | 준비 대기 |
| cslib-v4.34.1 | 8 | 없음 | 준비 대기 |
| leanpool-v4.34.0 | 10 | 없음 | 준비 대기 |
| leanpool-v4.35.0-rc3 | 10 | 없음 | 준비 대기 |
| physlib-v4.34.0 | 10 | 없음 | 준비 대기 |
| physlib-v4.34.1 | 10 | 없음 | 준비 대기 |
| putnambench-v4.26.0 | 10 | 없음 | 준비 대기 |
| putnambench-v4.27.0 | 9 | 없음 | 준비 대기 |
| strata-v4.26.0 | 1 | F001 | F001 문맥 재사용 |
| strata-v4.27.0 | 10 | F001 | F001 문맥 재사용 |
| strata-v4.31.0 | 10 | F001 | F001 문맥 재사용 |

## 다음 처리

1. 필요한 디스크 여유를 확보한다. 신규 compiler가 없는 버전은 4.30.0·4.34.0·4.34.1·4.35.0-rc3이다.
2. 실행 중인 다른 작업의 봉인된 라이브러리를 변경하지 않는 별도 빌드 경로에서, 부족한 환경·모듈만 준비한다. compiler는 중앙 env, 빌드·다운로드 캐시는 중앙 cache 경로를 사용한다.
3. 전체 환경을 봉인한 뒤 F002부터 순서대로 측정한다. 재빌드로 F001의 봉인 환경이 바뀌면 과거 결과를 새 환경 결과로 재사용하지 않고 재측정한다.
4. 신규 문제는 각 지정 버전에서 HB 1회만 측정한다. 대표 HB는 첫 지정 버전의 값이며, 완료된 F001은 실제 3회 표본과 중앙값을 그대로 유지한다.

## 실행과 재개

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/.worktrees/arena-final60-baselines
BASELINE_PYTHON=/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/integration-py313/bin/python3.13
"$BASELINE_PYTHON" -B scripts/measure_final_baselines.py \
  --output runs/manual/final60-baselines-once-20261102 \
  --carry-forward runs/manual/final60-baselines-20261102 \
  --compiler-lock /Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final-f001-20/runs/manual/final-f001-subagent-20/compiler.lock
```

동일 소스·환경·측정 코드의 완료 결과만 유지하며 다음 문제로 넘어간다. 환경이 없으면 exit 2로 대기 상태를 기록한다. 프로토콜이나 봉인 환경이 달라지면 새 실행 폴더를 사용해야 한다. 모델 API는 호출하지 않는다.

사용자 요청으로 후속 측정 횟수를 버전별 1회로 줄였다. 기존 3회 실행의 protocol·결과·표본은 수정하지 않고 새 실행 폴더에서 검증 후 계승한다. 반복 측정은 불일치 조사나 중요한 후보의 최종 확인 시 별도로 수행한다.
