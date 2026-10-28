# 검증 기록 — 2026-10-18 KST

평가 모듈 v0.1.0을 macOS/arm64, Lean 4.26.0에서 실행했다.
새로운 모델 호출·리팩터링 탐색은 하지 않았다. 예제와 기존 후보를 이용해 평가/선택 동작을 검사했다.
수치와 코드·설정 해시는 [validation-results.json](validation-results.json)에 저장했다.

## 테스트

```sh
REFACTOR_EVAL_LEAN_TESTS=1 python3 -m unittest discover -s tests -v
```

**30/30 통과.** 그중 실제 Lean을 실행하는 4개 테스트는 다음을 검사했다.

- 실패 후보의 오류 피드백 → 수정 후보 → 원본과 모든 후보의 최종 재평가 → 최고점 선택.
- `module` 문맥에서 선언 측정과 대상 공리 확인.
- 후보가 문맥 속 `sorry` 증명에 의존하면 거절.
- 계측을 위해 추가한 `import Lean`으로만 통과하는 코드는 원래 문맥 검사에서 거절.

나머지는 최고점/동점/원본 유지, 중간 채택 후 최종 실패, 다중 환경 자격, 점수 상충,
비증가 정책, 후보 변경 탐지, 환경 변경, 중단 복구, 동시 쓰기 차단,
잘못된 수치 및 설정, timeout과 agent JSON 프로토콜을 검사했다.
skill 형식 검사도 통과했다.

## 실제 자동 루프

```sh
python3 -m refactor_eval run \
  --problem examples/basic/problem.json \
  --run-dir runs/validated-demo \
  --max-attempts 3 \
  -- python3 examples/replay_agent.py
```

| 후보 | 최종 검증 | 증명 토큰 | heartbeat 중앙값 | 점수 | 결과 |
| --- | --- | ---: | ---: | ---: | --- |
| baseline | 통과 | 14 | 47 | 0 | 보존 |
| candidate-0001 | 컴파일 실패 | 3 | 측정 불가 | 없음 | 제외 |
| candidate-0002 | 통과 | 2 | 24 | 67.325228 | 최종 선택 |

최종값은 각각 3개의 독립 Lean compiler process에서 측정했다.
별도로 원래 문맥에서 계측 없이 컴파일하는 검사도 수행했다.
선택된 코드는 `runs/validated-demo/selections/final-001/selected.lean`이다.

## 기존 Strata 문제와 전체 파일 문맥

대상은 `CallElimCorrect.substOldPostSubset`,
[Strata 커밋 451e5f047baf](https://github.com/strata-org/Strata/tree/451e5f047bafa010d178856db76c00029bfa4d7f)의
`Strata/Transform/CallElimCorrect.lean`이다. 기존 로컬 LEArN의 `refactored.lean` 후보를 입력으로 사용했다.
원래 전체 파일에서 대상 선언만 교체했으며 이후 선언까지 컴파일했다.
Lean 4.26.0, `-Dexperimental.module=true`, 기본 50:50 가중치로 평가했다.

| 후보 | 최종 검증 | 증명 토큰 | heartbeat 중앙값 | 점수 | 결과 |
| --- | --- | ---: | ---: | ---: | --- |
| baseline | 통과 | 313 | 5,173 | 0 | 최종 선택 |
| 기존 리팩터링 후보 | 통과 | 35 | 11,716 | -18.832887 | 개선 부족으로 제외 |

이 사례는 토큰 감소만으로 좋은 후보라고 판단하지 않고, 기록된 종합 점수에 따라 원본을 유지하는지 검증한다.
최종 heartbeat는 원본·후보 각각 3회 측정했다. 후보 생성 성능이나 공식 Arena 점수를 검증한 결과는 아니다.
로컬 실행 기록은 `runs/strata-validated/`에 있다.

## 토큰 계산 보정 검사

공개 워밍업 스냅샷의 15개 원본 `proof_length`와 **15/15 일치**했다.
입력 JSONL 해시와 문제별 결과는 [token-calibration.json](token-calibration.json)에 기록했다.
사용한 데이터는 [공개 Arena의 고정 스냅샷](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/tree/ca9547e925db345a919d50f4294df078a1bb036e)의
`benchmark_data_warmup.jsonl` 로컬 사본이다. 데이터 자체는 이 저장소에 재배포하지 않는다.

```sh
python3 scripts/check_token_counts.py /path/to/benchmark_data_warmup.jsonl \
  --output token-calibration.json
```

원본 15개의 길이 일치는 모든 새 구문에서 공식 tokenizer와 동일하다는 보장이 아니다.
중첩 주석, 문자열 내 주석 기호, 명제 내부의 `:=`, 공백을 다루는 방법을 명시한 로컬 metric을 사용한다.

## 확인 범위

실제 Lean 통합 검증은 4.26.0에서 수행했다. 다중 환경에 대한 필수 통과/재선택 로직은 제어된
측정값을 사용하는 테스트로 확인했으며, 전체 Arena의 모든 지정 버전을 실행하지 않았다.
유료 API와 실제 생성 agent의 연결도 이번 검증 범위에 포함하지 않았다.

`runs/`의 후보·전체 compiler 입력·원시 로그는 로컬에 보존하고 Git에서는 제외했다.
평가 방법·코드·Lean 버전·문맥이 달라지면 새 run으로 다시 측정해야 한다.
