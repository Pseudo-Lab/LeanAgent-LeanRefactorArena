# Final 환경 준비 현황

갱신: 2026-11-02 (환경 추가 준비 중)

환경은 출처·revision·Lean 버전 조합 17개, compiler 버전 8개다. 문제·버전 조합은 127개다. 버전이 다른 빌드 산출물은 공유하지 않는다.

Strata 4.31·4.27은 기존 소스와 빌드의 APFS copy-on-write 복제본에서 필요한 전체 10문제 모듈을 증분 빌드하고 별도 manifest로 봉인했다. 원래 F001 환경·빌드·측정 표본은 유지한다. 고정한 환경을 재사용해 F002부터 한 문제씩 처리한다.

| 환경 | 전체 대상 문제 수 | 봉인된 문제 수 | 상태 |
| --- | ---: | ---: | --- |
| arklib-v4.30.0 | 10 | 0 | 준비 대기 |
| arklib-v4.31.0 | 10 | 0 | 준비 대기 |
| arklib-v4.33.1 | 3 | 3 | 준비됨 |
| arklib-v4.34.0 | 2 | 2 | 준비됨 |
| cslib-v4.30.0 | 1 | 1 | 준비됨 |
| cslib-v4.31.0 | 3 | 3 | 준비됨 |
| cslib-v4.33.1 | 10 | 10 | 준비됨 |
| cslib-v4.34.1 | 8 | 8 | 준비됨 |
| leanpool-v4.34.0 | 10 | 0 | 준비 대기 |
| leanpool-v4.35.0-rc3 | 10 | 0 | 준비 대기 |
| physlib-v4.34.0 | 10 | 10 | 준비됨 |
| physlib-v4.34.1 | 10 | 10 | 준비됨 |
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
- PhysLib 4.34.1의 전체 10문제 문맥도 빌드·봉인했다. 4.34.0의 전체 10문제 문맥도 빌드·봉인했으며, F011 이후 두 버전의 HB를 한 문제씩 순서대로 측정한다.

## 재사용 가능한 환경 준비

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/.worktrees/arena-final60-baselines
BASELINE_PYTHON=/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/integration-py313/bin/python3.13
"$BASELINE_PYTHON" -B scripts/prepare_final_cached.py \
  --environment strata-v4.31.0 --environment strata-v4.27.0 \
  --compiler-lock /Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final-f001-20/runs/manual/final-f001-subagent-20/compiler.lock
```

이미 전체 문맥을 봉인한 환경은 검증 후 재사용하며 빌드를 반복하지 않는다.

## F031부터 순차 측정·재개

```sh
"$BASELINE_PYTHON" -B scripts/measure_final_baselines.py --start 31 \
  --output runs/manual/final60-baselines-final-20261102 \
  --history-root runs/manual/final60-baselines-20261102 \
  --history-root runs/manual/final60-baselines-expanded-20261102 \
  --history-root runs/manual/final60-baselines-cached-20261102 \
  --history-root runs/manual/final60-baselines-cslib-20261102 \
  --history-root runs/manual/final60-baselines-cslib-hygiene-20261102 \
  --history-root runs/manual/final60-baselines-cslib-final-20261102 \
  --evaluation-cache runs/manual/final60-evaluation-cache \
  --wait-for-environments \
  --compiler-lock /Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final-f001-20/runs/manual/final-f001-subagent-20/compiler.lock
```

실행 중인 protocol과 구현은 변경하지 않는다. 동일 소스·환경·구현의 완료 결과만 유지하고 다음 문제로 넘어간다. 환경이 없으면 exit 2, 실제 측정이 실패하면 exit 1로 상태를 저장한다. 모델 API는 호출하지 않는다.

## PhysLib 이후 환경과 캐시

`prepare_final_environment.py`는 lock의 정확한 source revision·의존성·compiler를 설치하고 필요한 전체 문제 문맥을 한 번 빌드한다. 이후 봉인된 라이브러리와 setup을 읽기 전용 측정에 재사용한다. 새 환경 준비 전 15 GiB, 빌드 중 5 GiB 여유를 확인한다. compiler 단독 설치는 공식 배포 파일 SHA256과 실제 압축 해제 크기를 확인하고 8 GiB 여유를 유지한다.

중앙 `.lake/build`와 Mathlib 다운로드 캐시는 유지한다. Lake의 별도 artifact 복제 저장소만 중복 생성을 끄며(`LAKE_ARTIFACT_CACHE=false`), 이미 생성된 이 워크트리 소유 복제본은 봉인된 실제 라이브러리 경로와 무관함을 확인한 뒤 제거했다. 원본 소스와 필요한 빌드 산출물은 유지한다.

APFS 파일시스템 압축은 파일 내용·권한·심볼릭 링크를 전후 대조해 동일한 경우에만 교체한다. 증거는 `runs/manual/final60-environment-prep-20261102/`의 compression 및 artifact-store-cleanup JSON에 보관한다.

새 측정 실행은 시작·종료 시 라이브러리 전체 bytes를 검사하고, 문제 사이에는 stat-cache와 소스·문맥·setup 검사를 유지한다. 동일 원본·환경·평가기·표본 수의 측정 캐시가 있으면 증거 해시를 검증해 재사용한다. 재사용은 새 표본이나 새 compiler 실행으로 집계하지 않는다.

F002~F010 원래 실행기의 정확한 구현은 commit `582bb71`에 보존했다. 이후 구현으로 과거 protocol 폴더를 덮어쓰지 않는다. 새 실행기는 구현 소스도 실행 폴더 안에 복사한다.

## 원본 계측의 중복 컴파일 제거

F021 이후 새 실행기는 `reference_single_pass`를 사용한다. 기존 HB wrapper는 `elabCommand`로 원문을 실제 컴파일한 뒤 대상 정리의 존재와 공리 집합을 확인한다. 원본은 dataset과 정확히 같은 bytes인 경우에만 이 모드를 허용하며, 같은 컴파일을 별도 사전 프로세스에서 반복하지 않는다. 계측 wrapper·counter·표본 수는 바꾸지 않았다. 공리 frontier 추가 검사가 필요한 버전은 해당 검사를 계속 수행한다.

후보 평가의 기본 경로는 유지한다. 원본의 이전 별도 컴파일 결과도 원래 실행 폴더와 구현 snapshot에 보존한다. 새 모드는 protocol과 결과에 기록하고 평가 캐시 식별자에 포함한다. `--separate-reference-check`로 이전 방식의 새 실행을 선택할 수 있다.

## 추가 환경의 캐시 격리와 준비 예산

`--namespace arklib` 같은 출처별 공간에서 동일 revision의 기존 소스·빌드를 APFS copy-on-write로 복제한 뒤 필요한 모듈을 추가한다. 이전에 봉인한 의존성 파일 목록을 다른 출처의 빌드가 늘리지 않도록 한다. 복제본의 절대 경로가 들어 있는 compiler setup은 Lake의 `query +Module:setup`으로 다시 생성한다. 실제 import·plugin·dynlib 파일이 봉인한 manifest에 포함되는지 준비기와 평가기가 확인한다.

이미 full compiler가 있는 작은 증분 준비는 `--incremental-budget-gib N`을 사용할 수 있다. 시작 시 5+N GiB 여유를 요구하고, 준비 중 전체 디스크 여유 감소가 N GiB를 넘거나 5 GiB 여유를 침범하면 중단한다. 실패한 산출물은 봉인하지 않고 재개용으로 보존한다. compiler를 이 경로에서 새로 내려받지 않으며, 기본 일괄 준비의 15 GiB 조건은 유지한다.

`--wait-for-environments`는 미봉인 환경을 기다리면서 하나의 평가기 세션을 유지한다. 환경이 준비될 때마다 전체 파일을 처음 검증하고, 그 이후에는 stat-cache를 재사용한다. 마지막 전체 bytes 검사 전의 새 결과는 잠정값이다. 역사적 실행은 완료된 환경 종료 검사와 증거 해시를 확인해 유지한다. 중첩된 library root가 같은 파일을 가리키는 경우 전체 해시는 파일별 한 번만 계산하며 manifest의 파일 목록·해시와 검증 범위는 동일하다.

## Strata setup 경로 감사

초기 Strata 확장 캐시의 setup 일부는 복제 전 seed의 절대 경로를 유지했다. 실제 참조한 4.31 파일 261개·4.27 파일 249개를 복제본의 봉인 해시와 대조했으며 불일치·누락이 없었다. 모든 파일의 ctime도 F002 측정 시작 이전이어서 측정 구간 중 원본 파일 변경이 없음을 확인했다. 따라서 기존 HB 표본은 추가 계측 없이 유지한다.

원래 setup 파일은 SHA256별로 보존했고, 현재 복제본의 setup은 Lake로 다시 생성해 실제 참조 파일이 복제본 manifest에 들어 있음을 확인했다. 원본 라이브러리와 기존 측정 로그는 유지한다. 감사와 경로 재생성 증거는 `runs/manual/final60-strata-import-audit-20261102/receipt.json`, `relocated-setups.json`, `legacy-setups/`에 있다. 이후 평가기는 compiler setup이 봉인하지 않은 파일을 참조하면 실행·캐시 재사용을 거부한다.
