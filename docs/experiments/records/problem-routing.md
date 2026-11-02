# 규칙 기반 문제 라우팅

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

정적 분류 결과로 규칙 적용 순서와 LLM에 넘길 구간을 고른다.

## 확인된 결과와 해석

warmup15문제 계획을 생성했다. 비용0·컴파일 없음의 구조 작업으로 모델 성능 개선 실험은 아니다.

## 코드·Lean 보존 결정

PR #25 반영. 계획 표는 Markdown으로 보존한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/problem-routing/README.md` | `로컬 작업본` | `2116205fbbb749639aa0d497caef74be25eeb11ad0d09e18e43567defce2b0f0` |
| `experiments/problem-routing/plans/summary.md` | `로컬 작업본` | `e71a14079adefd67bdefa7fcc05e70747fcba43427fb1d1b1e6374599e7cfef7` |

## 원문: `experiments/problem-routing/README.md`

### 문제 분류와 규칙 라우팅: 본 벤치마크 적용 구조

웜업 15문제는 최종 점수에 들어가지 않음. 11월 1일 본 벤치마크 50문제가 공개되면 바로 쓸 수 있도록, 문제를 비용 없이 분류하고 분류 결과에 따라 미리 만든 규칙을 먼저 적용하는 구조를 정리함. 이번 PR은 구조 단계이며 LLM 실험은 하지 않음.

#### 지난 발표 질문에서 고친 점

| 질문 | 이번 구조에서 |
| --- | --- |
| 문제 유형 분류에 비용이 얼마나 드나요? | LLM이 아니라 증명 텍스트만 읽어 분류함. 모델 호출과 컴파일이 없어 웜업 15문제 전체가 0.78초 걸림 |
| 분류한 뒤 에이전트가 자동으로 전략을 고를 수 있나요? | `route.py`가 분류 결과로 적용할 규칙 단계와 LLM에 넘길 구간을 순서대로 정함 |
| 분류가 맞는지는 어떻게 아나요? | 유형 이름이 맞는지보다, 고른 규칙이 실제로 토큰을 줄였는지로 확인함. 아래 "블록 전략 실측과 대조" |

#### 흐름

```
문제 → analyze(proof)            비용 0, 컴파일 없음
     → route(분석 결과)          비용 0, 컴파일 없음
     → 규칙 단계                  모델 비용 0, 컴파일만 씀
     → LLM 단계                   규칙이 처리하지 못한 구간만 넘김
```

1. **analyze**: 블록을 나누고 유형(`case` 분기형, `calc` 계산 연쇄형, `have` 중간 명제형)과 고칠 대상을 냄. 도구 설명은 [proof-analyze](proof-analyze.md).
2. **route**: 아래 표의 조건으로 규칙 단계를 고름. 유형만 보지 않고 analyze가 찾은 대상의 모양을 함께 봄.
3. **규칙 단계**: 블록 전략에서 만든 스크립트로 처리함. 컴파일로 확인한 후보만 남음.
4. **LLM 단계**: 규칙이 처리하지 못한 비슷한 쌍과 큰 블록만 넘김. 이 단계 설계는 다음 PR(하네스 실험 설계)에서 다룸.

LLM에게 분류를 맡기는 경우는 analyze가 블록을 나누지 못했거나 유형이 `mixed`일 때뿐임. 웜업 15문제에서는 해당 문제가 없었음.

#### 라우팅 조건

| 규칙 단계 | 조건 | 처리 스크립트 |
| --- | --- | --- |
| 같은 분기 합치기 | 본문이 글자까지 같은 분기 쌍이 **같은 부모 아래 형제**일 때 | `block_dp.py` 규칙 8 |
| 미사용 `have` 제거 | 증명에 `have`가 한 줄이라도 있을 때. 모델 비용이 없고 컴파일만 쓰므로 유형과 관계없이 돌림 | `prune_unused.py` |
| 중복 `have` 묶기 | 이름만 다른 중복 쌍의 머리가 `have 이름 : 명제 := by` 한 줄이고, 서로 다른 토큰이 모두 이름이나 숫자일 때 | `block_dp.py` |
| LLM 구간 수정 | 항상 마지막. 위 조건에 걸리지 않은 비슷한 쌍과 가장 큰 블록 | 하네스(다음 PR) |

#### 웜업 15문제 계획

| # | 출처 | 유형 | 규칙 단계 | LLM 단계 |
| ---: | --- | --- | --- | --- |
| 1 | strata | case | 분기 합치기, 미사용 제거 | 남은 구간 |
| 2 | strata | case | - | 남은 구간 |
| 3 | strata | case | 미사용 제거 | 남은 구간 |
| 4 | physlib | have | 미사용 제거 | 남은 구간 |
| 5 | physlib | calc | 미사용 제거 | 남은 구간 |
| 6 | physlib | calc | 미사용 제거 | 남은 구간 |
| 7 | cslib | case | 미사용 제거 | 남은 구간 |
| 8 | cslib | case | - | 남은 구간 |
| 9 | cslib | case | - | 남은 구간 |
| 10 | arklib | have | 미사용 제거 | 남은 구간 |
| 11 | arklib | have/calc | 미사용 제거 | 남은 구간 |
| 12 | arklib | have | 미사용 제거 | 남은 구간 |
| 13 | putnambench | have | 미사용 제거, 중복 묶기 | 남은 구간 |
| 14 | putnambench | have | 미사용 제거 | 남은 구간 |
| 15 | putnambench | have | 미사용 제거, 중복 묶기 | 남은 구간 |

#### 블록 전략 실측과 대조

지난주 블록 전략에서 컴파일로 토큰을 줄인 규칙은 1번(분기 합치기, 미사용 제거), 13번과 15번(중복 묶기, 미사용 제거), 14번(미사용 제거)임. 위 계획은 이 규칙을 모두 포함함.

처음 계획에서는 세 군데가 어긋나서 조건을 고침.

- 1번: 미사용 `have assoc`가 분기 안에 있어 `have` 비중이 0%였고, 유형으로만 고르면 제거 단계가 빠졌음. 실측에서는 이 제거로 15토큰이 줄었음. 그래서 `have`가 있으면 항상 돌리게 바꿈.
- 8번: `case red_I`와 `case red_K`는 본문이 같지만 서로 다른 상위 분기 아래 있어 합칠 수 없음. 형제 조건을 추가함.
- 13번과 14번: 13번은 `h₄`/`h₅`, `i`/`j`처럼 이름만 달라 실측에서 묶였는데 계획에서 빠졌고, 14번은 `A`/`Aᶜ`가 달라 묶이지 않았는데 계획에 들어갔음. 서로 다른 토큰이 이름이나 숫자인지, 머리가 한 줄 형식인지로 판단하게 바꿈.

**주의**: 이 조건은 같은 15문제의 실측을 보고 고쳤으므로 독립적인 검증이 아님. 수업 자료(What Evolves When We Talk About Harness Evolution?)에서 다룬 것처럼 고친 데이터에서만 맞는 과적합일 수 있음. 본 벤치마크에서 계획과 실측을 다시 대조해야 함.

미사용 제거는 실측에서 1, 13, 14, 15번에서만 효과가 있었고 나머지 8문제에서는 컴파일 시간만 썼음. 모델 비용은 없지만 파일 모드 컴파일이 문제당 몇 분씩 걸리므로, 본 벤치마크에서 시간이 부족하면 순서를 뒤로 미룰 수 있음.

#### 실행

```bash
python route.py --jsonl benchmark_data.jsonl --out plans
```

`plans/`에 문제별 `PNN.json`(규칙 단계, 고른 이유, LLM에 넘길 대상 ID)과 `summary.md`가 생김. `../proof-analyze`의 `analyze.py`를 불러 씀.

#### 다음 PR

하네스 실험 설계: LLM 단계에서 고칠 구간만 넘기는 방식과 증명 전체를 넘기는 방식을 같은 예산으로 비교하는 설계, 조정용 문제와 held-out 문제 분리, 모든 호출을 기록하는 비용 장부.

코드는 Claude와 함께 작성.

## 원문: `experiments/problem-routing/plans/summary.md`

| # | 출처 | 유형 | 규칙 단계 (모델 호출 없음) | LLM 단계 | LLM 분류 필요 |
| ---: | --- | --- | --- | --- | --- |
| 1 | strata | case | merge_same_branches, prune_unused_have | llm_focus | 아니오 |
| 2 | strata | case | - | llm_focus | 아니오 |
| 3 | strata | case | prune_unused_have | llm_focus | 아니오 |
| 4 | physlib | have | prune_unused_have | llm_focus | 아니오 |
| 5 | physlib | calc | prune_unused_have | llm_focus | 아니오 |
| 6 | physlib | calc | prune_unused_have | llm_focus | 아니오 |
| 7 | cslib | case | prune_unused_have | llm_focus | 아니오 |
| 8 | cslib | case | - | llm_focus | 아니오 |
| 9 | cslib | case | - | llm_focus | 아니오 |
| 10 | arklib | have | prune_unused_have | llm_focus | 아니오 |
| 11 | arklib | have/calc | prune_unused_have | llm_focus | 아니오 |
| 12 | arklib | have | prune_unused_have | llm_focus | 아니오 |
| 13 | putnambench | have | prune_unused_have, generalise_repeat | llm_focus | 아니오 |
| 14 | putnambench | have | prune_unused_have | llm_focus | 아니오 |
| 15 | putnambench | have | prune_unused_have, generalise_repeat | llm_focus | 아니오 |
