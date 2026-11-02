# 캐시된 Lean 검증

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

준비된 라이브러리를 재사용하는 지속 worker와 전체 모듈·공리 검사를 시험한다.

## 확인된 결과와 해석

P01·P02·P04·P05·P06 검증 범위의 로컬 구현이다. stat-cache와 지속 worker는 다른 기능이며 이 결과로 HB 개선을 주장하지 않는다.

## 코드·Lean 보존 결정

stat-cache는 PR #33에 반영. 실험 지속 worker는 공통 기본 경로에 통합하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/cached-verification/README.md` | `로컬 작업본` | `c28dcdf3098e6d378761f300eed6efe38ef0210d80e902363ef838e7804884da` |

## 원문: `experiments/cached-verification/README.md`

### 작은 장비에서 재사용하는 Lean 검증 환경

공식 Discord의 운영진 설명(사용자가 제공한 인용)에 따르면, Arena는 REPL을 사용하지 않는다.
15개 checkout과 10개 toolchain, 약 126GB의 환경을 미리 빌드하고 원본 파일에 증명을 교체한 뒤
`lake env lean <file>`을 실행한다. 약 500GB RAM의 파일 캐시와 병렬 실행을 사용하며 검사에
약 2초가 걸린다는 설명이다. 이 수치는 운영진 장비의 관찰값이고 이 실험의 목표 시간 보장은 아니다.
[공개 UI 코드](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/main/app.py)에서도
별도 평가 worker가 컴파일과 채점을 수행함을 확인할 수 있다. 비공개 worker의 구현을 복제한 것은 아니다.

이 실험은 기존 빌드 산출물을 공유하고 검사 때마다 새 Lean 프로세스를 실행한다.
작업 머신은 RAM 16GB이며 시작 시 디스크 여유가 약 2.5GiB였다. 새로운 Mathlib 복사본이나
toolchain 다운로드 없이 Strata와 Physlib의 기존 캐시를 연결했다. 추가 환경 메타데이터·원본 소스는
약 10MB이며, 원래 캐시를 지우면 연결도 사용할 수 없게 된다.

#### 현재 로컬 구성

| 문제 | 환경 | 등록 범위 |
| --- | --- | --- |
| P01, P02 | Strata `451e5f0`, Lean 4.26.0 | 공식 지정 버전 전체 |
| P04, P05, P06 | Physlib `c484336`, Lean 4.32.0 | 공식 지정 버전 전체 |
| P03 | Strata `451e5f0`, Lean 4.26.0 | 등록만 완료. 4.27.0·4.29.1은 미등록 |

Strata는 기존 `sources/strata/.lake`의 빌드를, Physlib는 이전 검증에서 구성한
`cache/05_pseudolab/LeanAgent-LeanRefactorArena/warmup-team-results/remaining-dependencies/physlib/c48433678e8fb6306ebcd48453300c8e16058a62/lib`
연결 모음을 사용한다. Physlib 연결 모음은 약 3.1GB의 기존 파일을 가리키며 새 복사본이 아니다.
다른 프로젝트가 공유 중인 원본 캐시는 이 실험에서 이동·정리하지 않는다.
실제 새 검사 결과는 local-results.json (`experiments/cached-verification/local-results.json`, 원래 실행 자료)에 기록한다.

5문제 batch에서 모두 통과했으며 후보별 컴파일·공리 확인은 P01 13.1초, P02 10.1초,
P04 9.2초, P05 10.0초, P06 5.2초였다. 환경 시작·종료의 전체 해시 검사는 이 시간에 포함하지 않는다.
별도 `serve` 요청의 P06도 통과했으며 16.3초가 걸렸다. 장비 상태에 따른 변동이 있으므로
이를 일정한 처리 시간이나 캐시 최적화 전후의 속도 향상 비율로 해석하지 않는다.
단위·연결 검사는 121개 통과, 선택적 Lean 검사 4개 skip이었다.

#### 바로 사용하기

저장소 루트에서 실행한다. 이 장비의 `.venv`는 Python 3.9이므로, 이미 존재하는 Python 3.13 환경을
명시한다. `PYTHONPATH=src`는 이번 저장소의 코드를 사용하게 한다. 모델 호출은 없다.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
ARENA_PY="$PROJECT_ENV_DIR/integration-py313/bin/python"
REGISTRY="$PROJECT_ENV_DIR/cached-verifier/local-five/registry.json"

PYTHONPATH=src "$ARENA_PY" experiments/cached-verification/worker.py status --registry "$REGISTRY"

PYTHONPATH=src "$ARENA_PY" experiments/cached-verification/worker.py batch \
  --registry "$REGISTRY" --candidate-dir submissions/warmup/best \
  --problems P01 P02 P04 P05 P06 --output runs/cached-verification/my-five
```

출력 디렉터리는 매번 새 경로를 사용한다. 후보 디렉터리에는 `P01.lean`처럼 정리 선언 전체를 담는다.
`batch`는 한 프로세스 안에서 환경별 검증기를 유지하고 같은 환경의 파일 해시를 재사용한다.
현재 장비에서는 한 번에 하나의 Lean 프로세스만 실행한다. 각 검사 결과와 원본 전체 모듈·로그는
문제별 폴더에 남고 종료 시 `summary.json`에 모인다.

후보를 반복 생성하는 agent는 `serve`를 실행해 표준 입력으로 요청을 전달할 수 있다.

```sh
PYTHONPATH=src "$ARENA_PY" experiments/cached-verification/worker.py serve \
  --registry "$REGISTRY" --output runs/cached-verification/my-session
```

입력은 한 줄에 JSON 하나다. 예: `{"problem":"P01","proof":"정리 선언 전체"}`.
복수 버전을 등록했다면 `"version":"v4.26.0"`도 명시한다. 출력도 요청별 JSON 한 줄이다.
입력을 닫으면 전체 환경 해시를 다시 검사하고 summary를 저장한다. 프로세스를 강제 종료한 경우
개별 검증 로그는 남아도 최종 환경 불변 검사가 완료됐다고 볼 수 없다.
동일한 증명을 보내도 Lean 검사는 다시 실행한다. 성공 결과를 답으로 재사용하지 않는다.

#### 검사 범위와 확장

`prepare`는 benchmark의 source·version·commit과 Git checkout, toolchain을 대조한다.
원본 소스를 별도로 고정하며, 실제 검사에서는 원본 선언 한 곳만 바꾼 전체 파일을 새 scratch에 쓴다.
`--root`와 원래 상대 모듈 경로를 보존하고 빌드된 라이브러리 검색 경로를 명시한다.
공유 checkout의 파일을 덮어쓰지 않으므로 요청 간 증명 교체 충돌이 없다.

전체 파일을 컴파일한 뒤 내장 `#print axioms`로 대상 정리를 검사한다. 명제 변경과 금지된 선언은
공통 선언 검사기로 거절하며, 허용 공리는 `propext`, `Classical.choice`, `Quot.sound`다.
이 경로는 **빠른 컴파일·공리 확인**이며 heartbeat 측정·공식 점수 계산을 하지 않는다.
후보 순위 비교와 제출 전 최종 계측은 기존 공통 하네스를 사용한다.
공식 실행기와 동일한 `lake env` 호출을 재현한 것은 아니며, Lake의 환경·옵션을 spec에 명시해서
직접 compiler를 호출한다. 모듈 옵션이나 native plugin이 다른 라이브러리를 연결할 때는 실제 검사가 필요하다.

추가 문제는 코드에 번호를 넣지 않고 환경 항목을 등록해 확장한다.
같은 source·Lean 버전·commit의 문제들은 한 manifest를 공유한다. 다른 pin이나 플랫폼의 빌드는 섞지 않는다.
라이브러리 준비가 끝나면 spec.example.json (`experiments/cached-verification/spec.example.json`, 원래 실행 자료)의 경로를 채우고 새 registry를 만든다.
경로는 spec 파일 기준으로 해석되므로 복사할 때 상대 경로도 조정한다.

```sh
PYTHONPATH=src "$ARENA_PY" experiments/cached-verification/worker.py prepare \
  --spec configs/cached-verification.local.json \
  --output "$PROJECT_ENV_DIR/cached-verifier/my-environments"
```

현재 머신의 로컬 spec은 `configs/cached-verification.local.json`에 있다. example에는 절대 경로
자리표시자가 있으므로 그대로 실행할 수 없다. 등록되지 않은 버전은 다른 버전으로 대체하지 않고 거절한다.
새 의존성을 내려받아야 한다면 먼저 디스크 공간을 확보하고 중앙 env/cache 규칙에 맞춰 별도로 빌드한다.
필요한 모듈의 import 의존성만 준비하는 방식으로 확장할 수 있으며, 전체 Mathlib를 문제마다 복제할 필요는 없다.
`prepare` 성공은 빌드 산출물의 모든 provenance나 모든 문제의 통과를 보장하지 않는다. 실제 후보 검사로 확인한다.

#### 해시 검증 캐시

기존 `PreparedLeanEvaluator`는 compiler 호출마다 라이브러리 전체 bytes를 다시 읽었다.
P02의 11,311개 파일 약 2.5GB를 읽는 데 이 장비에서 3.4~4.3초가 관측됐다.
새 `stat-cache` 정책은 프로세스 안에서 검증된 해시와 파일의 inode·size·mtime·ctime·mode를 보관한다.
각 호출에서 파일 목록과 metadata를 검사하고 변경된 파일만 다시 읽는다.
시작·종료 fingerprint에서는 캐시를 사용하지 않고 실제 bytes 전체를 읽는다.

이것은 로컬 파일시스템 metadata를 신뢰하는 선택 모드다. 악의적인 호스트나 metadata를 신뢰할 수 없는
파일시스템에 대한 동등한 보안 보장은 아니다. 기본 정책과 기존 manifest는 매번 전체 내용을 검사한다.
macOS 설정은 Lean 프로세스의 파일 쓰기·네트워크를 차단하지만, 다른 호스트 프로세스의 변경까지 막지 않는다.

공통 하네스에서도 이미 빌드된 경로를 다음과 같이 고정하면 같은 최적화를 사용할 수 있다.

```sh
PYTHONPATH=src "$ARENA_PY" -m lean_agent freeze-environment \
  --library-path /ABSOLUTE/PREPARED/lib/lean --revision PINNED_COMMIT \
  --verification stat-cache --sandbox macos-readonly \
  --output configs/my-cached-environment.local.json
```

`lean.prepared_environment`에 이 manifest 경로를 지정한다. 컴파일 횟수·명제·공리 검사·heartbeat
계측 조건은 바뀌지 않는다. `benchmark.py`로 같은 후보의 full/stat-cache 정책을 비교할 수 있다.
페이지 캐시를 강제로 비우지 않으며 OS 캐시·메모리 압력 때문에 전체 wall time은 달라질 수 있다.
라이브러리 해시 비용 감소와 Lean 자체의 실행 시간 감소를 구분해야 한다.
