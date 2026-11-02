# Final 환경 준비

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

compiler·source revision·문맥·검사 결과를 고정해 배치 입력을 준비한다.

## 확인된 결과와 해석

환경 준비 코드·lock·snapshot은 실행 기반이며 그 자체로 모든 Final 문제의 성공 결과가 아니다.

## 코드·Lean 보존 결정

PR #46 runtime이 사용하는 adapter를 유지한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/final-environment/README.md` | `3ee67de` | `3e598596fc1ff1cdf64c266d365816ceb05c5e0f9f8b6bb0fd0bcd5c7663db40` |

## 원문: `experiments/final-environment/README.md`

### 최종 60문제의 고정 실행 환경

사용자가 제공한 `benchmark_data_final.jsonl`의 SHA-256은
`d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`이다.
원본 사본과 정적 점검은 [benchmark snapshot](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/benchmarks/arena/final-d53690b057f9/snapshot.json)에 있다.
공식 원격 revision을 추측하지 않고 이 파일의 실제 bytes를 입력으로 고정한다.

대회 저장소 안에서 macOS arm64용 환경을 구성한다. 소스·의존성·compiler의 지정 버전을
준비하고 대상 원본 모듈과 정리 타입을 컴파일한다. 모델 호출, 후보 생성, heartbeat 측정,
공식 제출은 하지 않는다. 문제별 전체 axiom-policy 검사는 별도 평가 단계다.

#### 위치와 고정 기준

- [configs/final-environments.lock.json](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/configs/final-environments.lock.json): 60문제,
  17개 출처·버전 환경, 127개 문제·버전 조합의 revision과 연결.
- `sources/final/checkouts/<version>/<owner>--<repo>--<SHA>/`: 정확한 Git checkout.
- `sources/final/toolchains/<version>/`: 지정 compiler. 이미 설치된 동일 버전은 연결하고,
  없는 버전은 이 경로에 공식 배포본을 설치한다. native 빌드용 `libLean.a`도 확인한다.
- `sources/final/environments/<id>/`: 빌드·원본 검사 로그, 입력, manifest.
- `sources/final/problems/F001.json` … `F060.json`: 최종 dataset SHA가 들어간 별도 문제 ID.
  warmup의 번호·기준값을 재사용하지 않는다.
- `configs/final-environments.local.json`: 준비된 환경을 가리키는 로컬 registry.
- [preparation-results.json](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/final-environment/preparation-results.json): 모든 환경 준비와 봉인이 끝나면 생성하는 요약.

큰 runtime과 캐시는 `/sources/` 아래에 있고 Git에서 제외된다. 코드와 pin lock은 검토 가능한
작은 파일이다. 전역 기본 Lean 버전은 바꾸지 않는다. 원본 저장소의 추적 소스와
`lake-manifest.json`도 바꾸지 않는다. 같은 compiler 버전·동일 revision인 의존성만 공유한다.
Lean 버전이 다르면 `.olean`을 공유하지 않는다.

#### 처음부터 구성

저장소 루트에서 실행한다. Python 3.12 이상, Git, zstd와 공개 GitHub/Mathlib cache 접근이
필요하다. archive 안전 추출에는 `tarfile` data filter를 사용하며,
이번 준비에는 Python 3.13을 사용했다. dataset 원본은 위 snapshot 경로에 있어야 한다.

```sh
PYTHONPATH=src python3 -B experiments/final-environment/setup.py
```

단계를 나눠 실행할 수도 있다.

```sh
python3 -B experiments/final-environment/bootstrap.py fetch
python3 -B experiments/final-environment/toolchains.py
PYTHONPATH=src python3 -B experiments/final-environment/resolve.py
PYTHONPATH=src python3 -B experiments/final-environment/prepare.py
PYTHONPATH=src python3 -B experiments/final-environment/finalize.py
```

`bootstrap.py`는 manifest에 있는 전체 SHA를 사용한다. branch/tag의 최신 값을 dependency
revision으로 대체하지 않는다. ProofWidgets cloud release 조회에 필요한 실제 태그만
해당 SHA와 대조해 추가한다. `source-lock.json`에 transitive checkout과 manifest hash를 보관한다.
macOS의 시스템 Git이 Xcode license 상태에 묶일 수 있어, 빌드에는 실행한 Git의 실제 경로를
명시적으로 제공한다. 라이선스 동의나 시스템 설정 변경은 수행하지 않는다.

`prepare.py`는 필요한 소스 import를 따라 Mathlib cache의 범위를 구한다. 원래 header가
`import Mathlib`을 요구하는 Putnam 등은 전체 cache가 필요하다. source library는 대상 모듈만
빌드한다. 각 Lake 프로세스의 thread pool은 `LEAN_NUM_THREADS=2`로 제한한다.
메모리가 제한된 머신에서는 `ARENA_BUILD_THREADS=1`을 앞에 붙여 한 thread로 준비할 수 있다.
설정 의미는 [Lean Tasks and Threads](https://lean-lang.org/doc/reference/latest/IO/Tasks-and-Threads/)를 참고한다.

#### 상태 조회와 사용

```sh
PYTHONPATH=src python3 -B experiments/final-environment/env.py
PYTHONPATH=src python3 -B experiments/final-environment/env.py strata-v4.31.0 -- lean --version
PYTHONPATH=src python3 -B experiments/final-environment/env.py cslib-v4.34.1 -- lake lean /ABSOLUTE/FILE.lean
```

wrapper는 지정된 source HEAD와 compiler 버전을 확인하고, 해당 project 안에서 명시한
compiler의 `bin`을 사용한다. 프로젝트별 옵션을 보존하려면 `lake lean`/`lake build`를 사용한다.
`module`/`import all`을 쓰는 검사용 파일은 원래 `lean_lib` 범위에 두어 package 접근 조건도 보존한다.
Python 하네스도 저장소 내부 `.venv`에 설치된다. `.venv/bin/lean-agent --help`로 확인할 수 있다.
환경 하나만 준비하거나 재시도하려면:

```sh
PYTHONPATH=src python3 -B experiments/final-environment/prepare.py --only strata-v4.31.0
```

이미 `ready`인 환경은 빌드를 반복하지 않는다. 라이브러리를 추가 빌드하거나 파일을 바꾼 뒤에는
기존 hash manifest를 그대로 사용하지 말고 다시 `finalize.py`로 봉인한다.

#### 검증 범위

127개 조합 중 project source는 원본 본문 107개가 byte 단위로 일치하고, 한 개는 공백만
다르다. 공백 차이도 정확한 선언 범위를 확인해 dataset bytes를 원본 전체 파일에 삽입한
복사본으로 추가 컴파일한다. 나머지 19개 Putnam 조합은 제공된 header와 src를 그대로 컴파일한다.
모듈 비공개 선언은 원래 library 범위에서 `module`/`import all`로 읽어 타입을 확인한다.
실제 source 파일과 고정 dependency manifest는 수정하지 않는다.

검사용 임시 모듈은 입력 증거를 별도로 보관한 뒤 source tree에서 치워, 원래 library의
전체 build 대상에 끼어들지 않게 한다. `finalize.py`는 모든 checkout의 HEAD·추적 변경·manifest를
대조한 뒤 공통 하네스와 호환되는 `prepared-environment.json`을 만든다. 파일 내용 hash에는
Lean library와 native 공유 라이브러리를 포함한다. 파일 경로는 로컬 절대 경로이므로 다른
머신에서는 같은 pin을 준비하고 manifest를 새로 만든다.

이 준비는 공식 Linux worker와 동일한 실행 결과나 점수를 보장하는 검증이 아니다.
현재 하네스의 보수적 후보 문자열 검사에 걸리는 원본 4개와 로컬 토큰 계산 차이 2개는
[dataset audit](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/benchmarks/arena/final-d53690b057f9/audit.json)에 별도 기록돼 있다.
환경 준비를 위해 후보 검사 규칙이나 dataset의 길이 값을 완화·수정하지 않는다.
