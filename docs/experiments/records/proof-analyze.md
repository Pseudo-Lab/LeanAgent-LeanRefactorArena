# 정적 증명 분석

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

컴파일·모델 없이 블록·토큰·반복·편집 대상을 계산한다.

## 확인된 결과와 해석

warmup15문제의 정적 요약을 생성했다. focus 파일은 자동 생성되는 표시용 소스이며 실행 fixture가 아니다.

## 코드·Lean 보존 결정

도구·JSON·MD 요약 유지. 중복 생성물 P01–P15_focus.lean 15개는 Git에서 제거하고 필요할 때 재생성한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/proof-analyze/README.md` | `로컬 작업본` | `9815e2fcb8b60401471166c54e8b7972adca17cdccf6e49faec94a5d1df4c4c6` |
| `experiments/proof-analyze/results/summary.md` | `로컬 작업본` | `aff9ba209e1ffa1af9d157ef30741a5b3415c6bf11ff5160c8db80eca28ce554` |

## 원문: `experiments/proof-analyze/README.md`

### analyze(proof): LLM에 넘길 증명 분석 도구

에이전트가 증명을 고치기 전에 호출하는 정적 분석 도구임. Lean 컴파일과 모델 호출 없이 증명 하나를 받아 길이, 유형, 블록, 먼저 고칠 대상을 JSON으로 돌려줌. 웜업 블록 전략의 규칙 1–4(블록 분할, 토큰 합, 이름 정규화 해시, 편집 거리)를 그대로 쓰고, 결과를 모델이 바로 쓸 수 있는 형태로 묶음.

#### 목적

- 모델이 증명 전체를 처음부터 다시 쓰지 않고, 줄일 여지가 있는 구간만 고치게 함.
- 같은 정보를 매번 모델에게 다시 찾게 하지 않아 호출 수와 비용을 줄임.
- 유형별로 다른 전략을 고를 수 있게 유형과 힌트를 함께 넘김.

#### 출력

| 필드 | 내용 |
| --- | --- |
| `proof_tokens` | 공식 `proof_length` 규칙으로 센 토큰 수 |
| `type`, `subtype` | 블록 종류별 토큰 비중이 50% 이상인 종류(`case`, `calc`, `have`, 없으면 `mixed`). 25% 이상인 두 번째 종류가 있으면 `subtype` |
| `tags` | 출처, 길이 구간(`short` 300 미만, `medium` 1,500 미만, `long`), 중복 블록 쌍 수, 비슷한 분기 쌍 수 |
| `type_hint` | 유형별 수정 방향 한 문장 |
| `blocks` | 블록 `B1, B2, …`의 src 줄 범위, 종류, 첫 줄, 토큰, 비중 |
| `targets` | 먼저 고칠 대상 `T1, T2, …`. 종류(`repeat` 중복 블록, `case_body` 비슷한 분기, `large` 가장 큰 블록), 줄 범위, 편집 구간 `edit_span`, 서로 다른 토큰 `differs`, 예상 감소량 `est_saving`, 수정 힌트 |
| `needs_compile` | 이 도구로는 알 수 없고 컴파일이 필요한 항목(미사용 `have`, heartbeat, 공리) |

- `est_saving`은 두 블록이 이름만 다르고 완전히 같을 때만 냄. 조금이라도 다르면 `null`로 두고, 다른 토큰을 `differs`에 담아 모델이 인자로 쓸지 판단하게 함.
- 대상 순서는 예상 감소량이 있는 쌍, 크기가 큰 비슷한 쌍, 가장 큰 블록 순.

하네스용 함수 두 개를 함께 둠.

- `focus_view(declaration, edit_span, tag)`: 편집 구간 앞뒤에 `-- EDIT-START T1`, `-- EDIT-END T1` 주석을 넣은 증명을 돌려줌. 모델에게 이 구간만 고치라고 지시할 때 씀.
- `splice(declaration, edit_span, replacement)`: 모델이 돌려준 구간을 원래 자리에 넣음.

15번 1순위 대상 예시:

```json
{"id": "T1", "kind": "repeat", "lines": [[18, 65], [67, 114]], "edit_span": [18, 114],
 "blocks": ["B6", "B7"], "tokens": [812, 812], "similarity": 1.0, "est_saving": 807,
 "differs": [["h₅", "h₆"], ["e", "f"], ["d", "e"], ["d", "e"]]}
```

#### 웜업 15문제 결과

| # | 출처 | 토큰 | 길이 | 유형 | 보조 유형 | 블록 | 대상 | 1순위 대상 | 예상 감소 |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | --- | ---: |
| 1 | strata | 313 | medium | case | - | 10 | 3 | case_body B2,B3 | 17 |
| 2 | strata | 222 | short | case | - | 7 | 1 | large B3 | - |
| 3 | strata | 224 | short | case | - | 8 | 1 | large B8 | - |
| 4 | physlib | 851 | medium | have | - | 27 | 1 | large B10 | - |
| 5 | physlib | 1,372 | medium | calc | - | 12 | 1 | large B12 | - |
| 6 | physlib | 1,217 | medium | calc | - | 24 | 4 | repeat B9 | - |
| 7 | cslib | 408 | medium | case | - | 13 | 9 | case_body B8,B9 | - |
| 8 | cslib | 407 | medium | case | - | 7 | 8 | case_body B5,B6 | 11 |
| 9 | cslib | 251 | short | case | - | 8 | 4 | repeat B7,B8 | - |
| 10 | arklib | 1,463 | medium | have | - | 23 | 1 | large B11 | - |
| 11 | arklib | 1,906 | long | have | calc | 25 | 5 | repeat B15,B16 | - |
| 12 | arklib | 1,353 | medium | have | - | 33 | 2 | repeat B30 | - |
| 13 | putnambench | 1,769 | long | have | - | 3 | 9 | repeat B2 | - |
| 14 | putnambench | 1,754 | long | have | - | 5 | 4 | repeat B2 | 43 |
| 15 | putnambench | 4,085 | long | have | - | 14 | 3 | repeat B6,B7 | 807 |

- 15문제 모두 `proof_tokens`가 공식 `proof_length`와 같음.
- 15문제 전체 실행 시간 0.74초.
- 모든 대상의 `edit_span`에 원래 구간을 다시 넣으면 원본과 바이트 단위로 같음(56개 대상 확인).
- 블록 전략에서 컴파일로 확인한 감소량과 비교하면 1번은 예상 17, 실제 18이고, 15번은 예상 807, 실제 748임. 15번은 보조정리로 묶을 때 인자 선언이 늘어나 실제 감소가 조금 작음.
- 9번처럼 비슷하지만 다른 분기(`follow_fst`, `follow_snd`)는 예상 감소량을 내지 않음. 처음 버전은 이런 경우에도 감소량을 내서 9번에서 112토큰을 예상했으나, 그대로 합칠 수 없는 쌍이라 고침.

#### 실행

```bash
python analyze.py --jsonl benchmark_data_warmup.jsonl --out results
python analyze.py --decl proof.lean --statement statement.lean
```

`results/`에 문제별 `PNN.json`, 1순위 대상을 표시한 `PNN_focus.lean`, 요약 `summary.md`가 생김. `block_analyzer.py`, `proof_tokens.py`는 블록 전략에서 쓴 파일과 같음.

#### 한계와 다음 단계

- 정적 분석이라 미사용 `have`, heartbeat, 공리는 알 수 없음. 이 항목은 컴파일 단계에서 따로 확인해야 함.
- 블록은 들여쓰기로 나누므로 항 자리의 증명이나 한 줄에 여러 tactic이 있는 증명은 나누지 못함.
- 유형 분류 기준(50%, 25%)과 길이 구간은 웜업 15문제를 보고 정한 값이라 본 벤치마크에서 다시 확인해야 함.
- 다음 단계: 하네스에서 `analyze` → `focus_view`로 모델에 구간 전달 → 모델 응답을 `splice` → 컴파일과 점수 확인 순으로 연결하고, 대상을 고르지 않고 증명 전체를 넘긴 경우와 같은 예산에서 비교함.

## 원문: `experiments/proof-analyze/results/summary.md`

### analyze(proof) 결과

컴파일과 모델 호출 없이 계산함. 예상 감소량은 토큰 수로 낸 추정치이며 컴파일 결과가 아님.

| # | 출처 | 토큰 | 길이 | 유형 | 보조 유형 | 블록 | 대상 | 1순위 대상 | 예상 감소 |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: | --- | ---: |
| 1 | strata | 313 | medium | case | - | 10 | 3 | case_body B2,B3 | 17 |
| 2 | strata | 222 | short | case | - | 7 | 1 | large B3 | - |
| 3 | strata | 224 | short | case | - | 8 | 1 | large B8 | - |
| 4 | physlib | 851 | medium | have | - | 27 | 1 | large B10 | - |
| 5 | physlib | 1,372 | medium | calc | - | 12 | 1 | large B12 | - |
| 6 | physlib | 1,217 | medium | calc | - | 24 | 4 | repeat B9 | - |
| 7 | cslib | 408 | medium | case | - | 13 | 9 | case_body B8,B9 | - |
| 8 | cslib | 407 | medium | case | - | 7 | 8 | case_body B5,B6 | 11 |
| 9 | cslib | 251 | short | case | - | 8 | 4 | repeat B7,B8 | - |
| 10 | arklib | 1,463 | medium | have | - | 23 | 1 | large B11 | - |
| 11 | arklib | 1,906 | long | have | calc | 25 | 5 | repeat B15,B16 | - |
| 12 | arklib | 1,353 | medium | have | - | 33 | 2 | repeat B30 | - |
| 13 | putnambench | 1,769 | long | have | - | 3 | 9 | repeat B2 | - |
| 14 | putnambench | 1,754 | long | have | - | 5 | 4 | repeat B2 | 43 |
| 15 | putnambench | 4,085 | long | have | - | 14 | 3 | repeat B6,B7 | 807 |
