# 준비된 환경의 반복 해시 검사 비용

관련 이슈: [#32](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/32).

`PreparedLeanEvaluator`는 준비된 라이브러리를 공유하되, 후보마다 새 Lean 프로세스로
검증·계측한다. 이 실험은 Python 환경 검사기의 반복 파일 읽기 비용만 줄이는
`stat-cache` 정책과 main `84412c8576a58110abeeaf9ec4a74a0055db554b`를 비교한다.
증명 결과, compiler 프로세스, heartbeat 표본은 재사용하지 않는다.

## 방법

- 이미 준비된 P02 / Strata revision `451e5f047bafa010d178856db76c00029bfa4d7f`,
  Lean 4.26.0, 동일한 후보·문맥·compiler 옵션·sandbox를 사용한다.
- main의 `prepared.py`를 Git에서 읽어 별도 모듈로 실행한다. 나머지 평가기 코드는
  main과 같으므로 비교 대상은 환경 검사 정책뿐이다.
- 두 evaluator의 시작 fingerprint를 수행한 뒤 정책별로 5회 후보를 평가한다.
  실행 순서는 회차마다 뒤집는다. 한 평가마다 plain compile 1회와 계측 3회를 새 프로세스로 실행한다.
- 매 회차 별도의 환경 검사 시간과 후보 평가 전체 시간을 측정한다. `Path.read_bytes()`를
  계측해 Python 해시 검사기가 읽은 라이브러리 파일 수·바이트를 기록한다.
- 종료 fingerprint는 전체 내용을 다시 읽는다. 시작·종료 환경 일치, 유효성,
  proof-token 일치, 실제 compiler 프로세스 수를 확인한다. heartbeat는 실제 표본을 보존한다.

바이트 수는 해시 계산을 위한 **논리적 내용 읽기**다. OS page cache가 활성화되어 있으므로
물리 디스크 I/O나 Lean 프로세스 자체의 라이브러리 읽기를 뜻하지 않는다. 측정값은 이 로컬
환경의 관찰이며, 전체 에이전트 실행이나 다른 문제의 동일한 속도 향상을 보장하지 않는다.
모델 호출·네트워크·라이브러리 설치·빌드는 하지 않는다.

## 측정 결과 · 2026-10-28

macOS 26.6.2 / arm64 / Python 3.13.11에서 라이브러리 11,311개 파일,
2,498,475,791바이트와 동일한 43 proof-token 후보로 측정했다.
아래 시간은 정책별 5회 중앙값이며 시작·종료 fingerprint는 후보 평가 시간에서 제외한다.

| 항목 | main `84412c8` | `stat-cache` | 관찰한 개선 |
| --- | ---: | ---: | --- |
| 단독 반복 환경 검사 | 3.447710초 | 0.132489초 | 26.02배 빠름 |
| 후보 평가 전체: compile 1회 + 계측 3회 | 57.517717초 | 40.550945초 | 29.50% 시간 단축, 1.42배 빠름 |
| 후보당 해시 검사의 내용 읽기 횟수 | 45,244회 | 0회 | 캐시 준비 후 중복 내용 읽기 제거 |
| 후보당 해시 검사의 논리적 읽기 바이트 | 9,993,903,164 | 0 | Lean 자체 읽기는 별도 |

양쪽 10회 평가 모두 유효했고, 매번 4개의 새 compiler 프로세스가 실행됐다.
proof-token은 모두 43이며 raw heartbeat 전체 표본의 중앙값은 양쪽 모두 2,497,328이었다.
개별 heartbeat 표본은 미세하게 달랐으므로 완전히 동일하다고 판정하지 않았다.
시작·종료 환경 fingerprint도 양쪽 모두 일치했다. 캐시 사용 시에도 시작과 종료에 각각
2,498,475,791바이트를 실제로 읽었다. main은 fingerprint 내부의 compiler 호출에서도
전체 검사를 반복해 각 경계에서 3회분인 7,495,427,373바이트를 읽었다.

전체 회차별 시간·내용 읽기 계수·heartbeat·코드 해시는
[results-20261028.json](results-20261028.json)에 보존한다.
추가 검증 기록은 [validation-20261028.json](validation-20261028.json)에 있다.

- Python 3.13에서 공통 하네스·runtime·API·회계·캐시 검사 76개 통과. 캐시 관련 12개 포함.
- API 비교 실험 13개, usage-cost 호환 검사 19개 통과. 합계 108개.
- 실제 Lean 4.26.0과 같은 라이브러리 manifest의 `stat-cache` 정책으로 스모크 실행.
  고정 응답 3회, 실패 피드백과 후보 갱신을 거쳐 `by rfl` / 2 proof-token을 선택했다.
  최종 검증·상태 조회·패키지 replay·실행에 보관한 코드의 replay 모두 통과했다.
- CLI의 명시적 `stat-cache`와 기본 `full` manifest 생성도 확인했다.
  실제 모델 API 호출과 과금은 없다. CI에는 Python 3.10·3.13의 캐시 회귀 검사를 추가했다.

## 재현

Python 3.10 이상과 해당 문제의 준비된 라이브러리·native harness 설정이 필요하다.
현재 작업 공간에서는 중앙 환경의 Python 3.13을 사용했다. 저장소 루트에서 실행한다.

```sh
PYTHONPATH="$PWD/src" python experiments/environment-verification/benchmark.py \
  --config /ABSOLUTE/PREPARED/P02/config.json \
  --candidate /ABSOLUTE/P02/candidate.lean \
  --baseline-ref 84412c8576a58110abeeaf9ec4a74a0055db554b \
  --trials 5 \
  --output runs/environment-verification/p02-main-v-cache
```

`--candidate`를 생략하면 문제의 원본 증명을 사용한다. `--baseline-ref`의 Python 코드를
실행하므로 신뢰하는 로컬 Git revision만 지정한다. 기존 실행 폴더를 재사용하지 않는다.
입력 설정과 manifest는 수정하지 않고 정책별 복사본을 실행 폴더에 남긴다.
원문 로그·후보·fingerprint·전체 보고서는 로컬 `runs/environment-verification/`에 보존하며
이 디렉터리는 Git에서 제외한다. 공유할 측정 집계는 이 실험 디렉터리에 별도로 보존한다.

## 활성화 및 한계

```sh
python -m lean_agent freeze-environment \
  --library-path /ABSOLUTE/PREPARED/LIB/lean \
  --revision PINNED_LIBRARY_COMMIT \
  --verification stat-cache \
  --output configs/libraries.local.json
```

생성한 manifest를 `lean.prepared_environment`로 지정한다. 기본 `full`과 기존 manifest의
동작은 유지한다. 캐시는 evaluator별 메모리에만 있으며 파일 목록과 metadata를 매 호출
재검사한다. 시작·종료 fingerprint와 명시적 `verify()`는 실제 전체 바이트를 읽는다.
파일 metadata를 신뢰할 수 없는 환경, 악의적 동시 변경에 대한 OS 격리나 변경 차단은
제공하지 않는다. 그런 환경에서는 기본 `full` 검사와 별도의 실행 격리를 유지한다.
