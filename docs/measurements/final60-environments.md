# Final 환경 준비 현황

갱신: 2026-11-02T07:48:17.082418+00:00

환경은 출처·revision·Lean 버전 조합 17개, compiler 버전 8개다. 문제·버전 조합은 127개다. 버전이 다른 빌드 산출물은 공유하지 않는다.

Strata 4.31·4.27은 기존 소스와 빌드의 APFS copy-on-write 복제본에서 필요한 전체 10문제 모듈을 증분 빌드하고 별도 manifest로 봉인했다. 원래 F001 환경·빌드·측정 표본은 유지한다. 고정한 환경을 재사용해 F002부터 한 문제씩 처리한다.

| 환경 | 전체 대상 문제 수 | 봉인된 문제 수 | 상태 |
| --- | ---: | ---: | --- |
| arklib-v4.30.0 | 10 | 0 | 준비 대기 |
| arklib-v4.31.0 | 10 | 0 | 준비 대기 |
| arklib-v4.33.1 | 3 | 0 | 준비 대기 |
| arklib-v4.34.0 | 2 | 0 | 준비 대기 |
| cslib-v4.30.0 | 1 | 0 | 준비 대기 |
| cslib-v4.31.0 | 3 | 0 | 준비 대기 |
| cslib-v4.33.1 | 10 | 0 | 준비 대기 |
| cslib-v4.34.1 | 8 | 0 | 준비 대기 |
| leanpool-v4.34.0 | 10 | 0 | 준비 대기 |
| leanpool-v4.35.0-rc3 | 10 | 0 | 준비 대기 |
| physlib-v4.34.0 | 10 | 0 | 준비 대기 |
| physlib-v4.34.1 | 10 | 0 | 준비 대기 |
| putnambench-v4.26.0 | 10 | 0 | 준비 대기 |
| putnambench-v4.27.0 | 9 | 0 | 준비 대기 |
| strata-v4.26.0 | 1 | 1 | 준비됨 |
| strata-v4.27.0 | 10 | 10 | 준비됨 |
| strata-v4.31.0 | 10 | 10 | 준비됨 |

## 저장과 자원 제한

- 소스 snapshot은 `sources/final-expanded/checkouts/`에 두고, `.lake/build`는 이 워크트리의 중앙 `$PROJECT_CACHE_DIR/lean-build/`를 가리킨다.
- 기존 소스의 compiler·라이브러리 bytes를 변경하지 않는다. 소스 revision·manifest·추적 파일 무변경을 확인하고 `prepared-expanded.json`으로 봉인한다.
- 이번 로컬 증분 경로는 compiler 설치·다운로드 없이 기존 캐시만 사용한다. 처음 4 GiB 이상, 실행 중 3 GiB 여유와 최대 2 GiB 추가 사용 제한을 적용한다. 전체 17환경 신규 설치기의 15 GiB 기준은 변경하지 않았다.
- 빌드와 측정은 같은 compiler lock을 사용한다. 측정은 원문 컴파일·공리 확인 후 버전별 fresh HB 1회다.
- F001의 과거 세 표본과 그 중앙값은 원래 환경 기준의 역사적 증거로 표시한다. 새 확장 환경에서 다시 측정한 것처럼 취급하지 않는다.
- 마지막 확인 디스크 여유: 14.59 GiB. 새 compiler 네 버전과 다른 출처 환경의 준비는 별도 공간 검토가 필요하다.

## 재사용 가능한 환경 준비

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/.worktrees/arena-final60-baselines
BASELINE_PYTHON=/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/integration-py313/bin/python3.13
"$BASELINE_PYTHON" -B scripts/prepare_final_cached.py \
  --environment strata-v4.31.0 --environment strata-v4.27.0 \
  --compiler-lock /Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final-f001-20/runs/manual/final-f001-subagent-20/compiler.lock
```

이미 전체 문맥을 봉인한 환경은 검증 후 재사용하며 빌드를 반복하지 않는다.

## F002부터 순차 측정·재개

```sh
"$BASELINE_PYTHON" -B scripts/measure_final_baselines.py --start 2 \
  --output runs/manual/final60-baselines-expanded-20261102 \
  --history-root runs/manual/final60-baselines-20261102 \
  --compiler-lock /Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final-f001-20/runs/manual/final-f001-subagent-20/compiler.lock
```

실행 중인 protocol과 구현은 변경하지 않는다. 동일 소스·환경·구현의 완료 결과만 유지하고 다음 문제로 넘어간다. 환경이 없으면 exit 2, 실제 측정이 실패하면 exit 1로 상태를 저장한다. 모델 API는 호출하지 않는다.
