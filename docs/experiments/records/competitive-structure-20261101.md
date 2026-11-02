# incumbent 출발 구조 탐색

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

P06·P13·P14·P15의 과거 후보에서 출발해 고정 공개 분모와 환율 피드백으로 각40회 평가한다.

## 확인된 결과와 해석

160평가 중 120유효·40실패, 독립 final4개. 최종 길이는 409/187/31/181토큰. 원본 출발 fresh40과 달리 incumbent-seeded이며 full header·추가 버전은 미검증이다.

## 코드·Lean 보존 결정

고정 환율·잔여 비율·다음 접근 정책을 PR #46 공통 경로로 옮겼다. 예전 r/4 노이즈 규칙은 옮기지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/competitive-structure-20261101/README.md` | `로컬 작업본` | `1ed5211745a3bc7f78a3f598ddf709eb8c357942bac1afe23c74efc36b7f696b` |
| `results/competitive-structure-20261101/analysis.md` | `로컬 작업본` | `e461cafbd5a40babe7ae1a1360ce368b8e47c7fef15e79ce58c5cf41bd60f8a3` |
| `results/competitive-structure-20261101/comparison.md` | `로컬 작업본` | `9a296e3988f4c91e32bad41285b94fd268ea486b997311333cbab417a8694c92` |
| `results/competitive-structure-20261101/report.md` | `로컬 작업본` | `6fd674bb8b9235397f98a5f956a5577b80b8691ccc6445b807f37bcb7972e9f0` |
| `results/competitive-structure-20261101/review.md` | `로컬 작업본` | `0d4e94cfa6515b68f7df78c1bd5818dd860f956dc47442d08683d68c973ae40f` |

## 원문: `experiments/competitive-structure-20261101/README.md`

### Competitive structural search

P06, P13, P14 and P15 receive 40 new candidate evaluations each, starting from the best archived candidate under the published competition normalizers. These runs continue from incumbents; they are not independent original-start trials. Previous experiments remain unchanged.

The controller refreshes current-candidate competition every four evaluations, records recent valid statistics, and ranks exact rational cost `T/T0 + floor(rawHB/1000)/published_H0`. A relative cost of 50 is an aspiration. All candidates and repairs consume credits; duplicate bytes do not. Each selected final proof receives a fresh check and three HB measurements.

Initial archived seeds: P06 422 tokens / 11,133,579 raw HB; P13 211 / 4,156,941; P14 55 / 821,228; P15 244 / 1,366,707. Fresh preparation measurements are authoritative for run baselines. The per-case 88-point submission reference is a different object from an assumed literal score of 88.

`protocol.json`, `instructions.txt` and `structure-design.md` describe scoring, solver scope and source-backed structural hypotheses. Inputs live in `runs/competitive-structure-inputs-20261101`; public results in `runs/competitive-structure-20261101`; native evidence in `runs/competitive-structure-private-20261101`.

Only the supplied primary local compiler is verified: Lean 4.32 for P06 and 4.26 for the other cases. Putnam imports are narrowed. Conditional score deltas assume unchanged compatibility and are not a measured full submission score.

All native work uses the shared old/new experiment lock. Root limits child contexts to two and reduces dispatch when host resources require it. External jobs that do not use this lock are outside that concurrency guarantee.

Completed: 160 candidate evaluations, 120 valid, four independent final checks. See `results/competitive-structure-20261101/analysis.md`, `comparison.md` and `review.md`. `compare_results.py --write` performs the final offline evidence audit and creates the exact-score comparison, separately recording official axis rounding.

## 원문: `results/competitive-structure-20261101/analysis.md`

### 구조 탐색 결과

네 문제 모두 기존 최선보다 낮은 대회 비용의 증명을 확보했다. gpt-6.1-sol / high가 문제당 40개씩 새 후보를 평가했고, 총 160개 중 120개가 유효했다. 각 최종 증명은 별도 컴파일 및 HB 3회 측정을 통과했다.

이번 출발점은 원본 증명이 아니라 공개 대회 분모로 재정렬한 기존 후보군의 최선이었다. P06/P14는 88점 제출본, P13은 이전 40회 실험의 attempt-39, P15는 이전 실험 최종 후보에서 시작했다. 따라서 원본부터 출발한 이전 독립 실험과 구분해야 한다.

| 문제 | Length 변화 | raw HB 변화 | 출발점 대비 비용 감소 | 문제 점수 개선 |
| --- | ---: | ---: | ---: | ---: |
| P06 | 422 → 409 | 11,133,579 → 11,003,038 | 2.25% | +0.458692 |
| P13 | 211 → 187 | 4,156,941 → 2,559,918 | 17.82% | +0.929765 |
| P14 | 55 → 31 | 821,229 → 969,083 | 33.59% | +0.419421 |
| P15 | 244 → 181 | 1,366,707 → 1,171,287 | 18.68% | +0.974090 |

비용은 `T/T0 + floor(rawHB/1000)/published_H0`이며 낮을수록 좋다. 같은 호환율을 가정한 반올림 전 15문제 평균 개선량은 이번 출발 후보군 대비 **+0.185464**, 88점 제출본 대비 **+0.306707**이다. 대회 화면의 축 반올림을 적용하고 최종 전체 반올림 전까지 계산하면 각각 +0.185556, +0.306667이다. 이는 새로운 전체 제출본의 실측 점수가 아니다. 나머지 11문제가 같다는 조건의 변화량이며, 정확한 전체 표시 점수에는 전체 반올림 위치가 영향을 준다.

#### 실제로 이긴 구조

- **P06:** 쌍선형 함수의 기저 비교와 공통 인수분해라는 기존 수학적 구조를 유지했다. 두 특수화된 식의 정리를 한 번에 공유하고, 존재 증명의 구성자 안에서 중간 인수를 추론하게 해 반복 처리와 타입 추론 비용을 줄였다. span 귀납, 자유대수 인수분해, Wick 출력 공간에서의 직접 비교도 실제로 검증했지만 비용상 이기지 못했다. 여기서는 큰 수학적 구조 변경이 성공했다고 해석하면 안 된다.
- **P13:** 충돌한 두 상태의 순서를 처음부터 정해 양방향 주기 분기를 없앴다. 강한 귀납을 짧은 증명항으로 표현하고, 귀납 내부에 필요 없는 순서 가정만 지워 `omega`의 불필요한 계산을 줄였다. 주기의 양수성도 직접 정리로 증명했다. 네 항 상태 창의 successor 전파, 유한 상태 표현 변경, 실수 상태의 전이 함수 및 iterate 경로도 검증했지만 더 길고 비쌌다.
- **P14:** 이미 강력했던 최대 교차집합 정리를 유지하면서 두 조건의 정규화를 공유하고, 최소한의 `grind`로 연결했다. 거듭제곱 등식의 방향을 바꿔 곱셈 교환 단계도 삭제했다. HB는 늘었지만 24토큰 절약의 가치가 더 커 총비용은 33.59% 줄었다. 27토큰 후보는 HB가 약 989만이라 탈락했다.
- **P15:** 설치된 소스에서 찾은 `Finset.sum_erase_eq_sub`가 전환점이었다. 교체한 한 항의 합을 `bᵢw + (D - aᵢw)`로 표현해, 기존의 항별 합 비교와 별도 덧셈 정리를 단일 `simpa`로 대체했다. 마지막에는 서로소 거듭제곱의 지수를 추론하게 해 5토큰을 절약하고 약 7천 HB 증가만 받아들였다. 단순히 HB가 가장 낮은 타입 명시를 고르는 것보다 대회 비용이 낮았다.

#### 탐색 방식과 해석

후보 평가는 현재 최선, Pareto 후보, 최근 유효 8개의 평균·중앙값을 제공했다. 비교 기준은 4회마다 갱신했고, 현재 비용의 50% 목표는 유효성 조건이 아닌 탐색 목표로 사용했다. 후보별 가설과 부모, 실패 및 수정도 기록했다. 실패한 후보 역시 40회 예산에 포함했다.

결과는 현재 후보군에서 추가 개선을 찾았다는 증거다. 경쟁형 프롬프트 자체의 인과 효과를 분리한 대조 실험은 아니므로, 개선 전체를 프롬프트 변화만의 효과라고 주장하지 않는다. 사례별로 의미 있는 후보 구조를 실제로 바꾸고 측정한 결과다.

실행 중 활성 서브 에이전트는 최대 2개, 이 실험의 native 작업은 공유 잠금 아래 1개로 제한했다. 마지막에는 탐색 에이전트 하나만 유지했다. 자원 점검에서 메모리 압력은 정상(1)이었고, 이번 실험에서 native 중단·동일 크레딧 복구는 없었다. 공유 잠금을 쓰지 않는 외부 작업은 이 동시성 보장의 대상이 아니다.

검증 범위는 P06 Lean 4.32.0, P13/P14/P15 Lean 4.26.0의 고정된 로컬 환경이다. Putnam 문제는 축소 imports를 사용했다. 전체 공식 header와 나머지 Lean 버전의 호환성은 이번 실험에서 검증하지 않았다.

#### 증거

- 정확한 점수 비교 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/results/competitive-structure-20261101/comparison.md`, 원래 실행 자료), 계산 데이터 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/results/competitive-structure-20261101/comparison.json`, 원래 실행 자료), 독립 검토 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/results/competitive-structure-20261101/review.md`, 원래 실행 자료)
- P06 최종 증명 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P06/final.lean`, 원래 실행 자료), 탐색 보고서 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P06/solver-report.md`, 원래 실행 자료)
- P13 최종 증명 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P13/final.lean`, 원래 실행 자료), 탐색 보고서 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P13/solver-report.md`, 원래 실행 자료)
- P14 최종 증명 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P14/final.lean`, 원래 실행 자료), 탐색 보고서 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P14/solver-report.md`, 원래 실행 자료)
- P15 최종 증명 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P15/final.lean`, 원래 실행 자료), 탐색 보고서 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P15/solver-report.md`, 원래 실행 자료)

## 원문: `results/competitive-structure-20261101/comparison.md`

### Structural search: final comparison

Incumbent-seeded continuation, 40 new candidates per case. Exact supplied primary local environments only; Putnam narrowed imports. Full official headers and additional versions unverified.

Compatibility unchanged and other 11 tasks unchanged. These are conditional score deltas, not a measured full submission score.

Exact unrounded objective and conditional score for search/comparison. Secondary display rounds each axis with Python round to 2 decimals, then rounds the problem mean to 2. Overall leaderboard averages rounded axes before its final 2-decimal rounding.

Fresh independent final raw-HB median is authoritative; search selection measurement is retained separately.

| Case | Incumbent T / raw HB | Final T / raw HB | Cost reduction | Problem score gain vs incumbent | Gain vs 88 seed |
| --- | ---: | ---: | ---: | ---: | ---: |
| P06 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P06/final.lean`, 원래 실행 자료) | 422 / 11,133,579 | 409 / 11,003,038 | 2.2543% | +0.458692 | +0.458692 |
| P13 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P13/final.lean`, 원래 실행 자료) | 211 / 4,156,941 | 187 / 2,559,918 | 17.8164% | +0.929765 | +1.370753 |
| P14 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P14/final.lean`, 원래 실행 자료) | 55 / 821,229 | 31 / 969,083 | 33.5886% | +0.419421 | +0.419421 |
| P15 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/competitive-structure-20261101/P15/final.lean`, 원래 실행 자료) | 244 / 1,366,707 | 181 / 1,171,287 | 18.6841% | +0.974090 | +2.351733 |

15-task mean change versus strongest starting incumbents: **+0.185464**.

15-task mean change versus the archived 88-point submission: **+0.306707**.

With the official axis rounding, these deltas before the final overall rounding are +0.185556 and +0.306667, respectively. A change in the final rounded full-submission display also depends on the unchanged other 11 tasks; no exact displayed total or measured leaderboard score is asserted.

Completed 160 candidate evaluations (120 valid, 40 invalid), four fresh baselines and four independent final checks. Offline evidence audits passed for all four cases.

[Official competition formula](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/main/leaderboard.py), observed last-file commit `88057731673d44e231788e3e87a9c797d585042a`. The original independent40 experiment remains a separate historical comparison.

## 원문: `results/competitive-structure-20261101/report.md`

### Continuous structure search

One continuous 40-candidate search per supplied local primary environment; C=100 conditional scores.

Scores use fixed published denominators and floor(raw heartbeats / 1000).

| Case | Complete | Done | Valid | Champion | T | Raw HB | Conditional score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P06 | True | 40 | 23 | attempt-25 | 409 | 11003038 | 80.11158220194504567310771893277574341134 |
| P13 | True | 40 | 35 | attempt-40 | 187 | 2559919 | 95.71116486246053207169295378240154414869 |
| P14 | True | 40 | 29 | attempt-30 | 31 | 969137 | 99.17071990709590843329274773106831880325 |
| P15 | True | 40 | 33 | attempt-39 | 181 | 1171287 | 95.76060784295041987859426211639139158649 |

## 원문: `results/competitive-structure-20261101/review.md`

### Independent review — complete

**Pass.** All four cases and the generated comparison outputs pass this offline review. No blocking issue remains. No native Lean, model, network or installation calls were made by this reviewer. The central account check exited 0; Git configuration was unchanged. This review file is the reviewer's only written artifact.

The unchanged offline `audit_case` passed P06, P13, P14 and P15 after finalization. Each has exactly 40 reservations, 40 measurement starts, 40 completed evaluations, no inflight credit, one fresh baseline and one independent final check. Across the experiment there are **160 candidates: 120 valid, 40 invalid**, plus four baselines and four independent finals. Frozen inputs/runtime/compiler fingerprints, hash-chain replay, immutable candidate/final sources, raw source/log inventories, rendered contexts, prescribed compiler commands, plain checks, three heartbeat samples, medians, allowed axioms and proof-token replay passed. Independent rational arithmetic selected the same four winners.

| Case | Valid / invalid | Winner | Final T / raw HB | Cost reduction vs fresh incumbent | Unrounded conditional problem gain |
| --- | ---: | --- | ---: | ---: | ---: |
| P06 | 23 / 17 | attempt-25 | 409 / 11,003,038 | 2.254333% | +0.4586916583 |
| P13 | 35 / 5 | attempt-40 | 187 / 2,559,918 | 17.816363% | +0.9297646856 |
| P14 | 29 / 11 | attempt-30 | 31 / 969,083 | 33.588583% | +0.4194210111 |
| P15 | 33 / 7 | attempt-39 | 181 / 1,171,287 | 18.684058% | +0.9740900417 |

P15 final SHA256 is `ac5b1fadac0923a96cbce17eefa0d38625f3b35490b190e27821d7ec27277325`; its fresh samples are `[1171287, 1171281, 1171308]`. Its exact final cost is `1468213/11544210`.

All four published normalizer pairs match the pinned benchmark metadata at `56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c`; every snapshot-file hash matches. The complete frozen input manifest also matches. Archived reference88 sources and metrics for all four cases, and the distinct P13/P15 incumbent sources and metrics, match their cited archived source digests and evaluation records. P06/P14 start from reference88; P13/P15 start from stronger prior-search incumbents. These are incumbent-seeded continuations, not independent original starts. The archived reference88 same-case gains are respectively +0.4586916583, +1.3707525470, +0.4194210111 and +2.3517330333.

All 160 charged sources remain distinct after removing comments and whitespace. Every attempt has route, hypothesis, parent and expected-tradeoff metadata. Source and metadata samples support meaningful exploration: P06 span/list/output-map/free-algebra/pair-difference alternatives; P13 scalar/window/finite-range/real-transition alternatives; P14 explicit adapter/extension/division/direct-theorem alternatives; P15 sum decomposition/reverse-kernel/quotient-witness/modular-omega/factored-row/erase-subtraction alternatives. Repairs and normalization/tactic ablations have concrete recorded hypotheses. No padding evidence was found. P06's selected gain is an elaboration refinement of the incumbent structure, not a newly superior mathematical route. P15's winning erase-subtraction identity materially shortens the coordinate replacement argument.

Reviewed the unfrozen `compare_results.py` without editing it. Independent arithmetic checks every per-case cost, exact score, delta, reduction, selected rank, final digest, raw samples and rounded display in `comparison.json`, and checks completion/count/final evidence fields in `report.json`. Offline helper reproduction matches both JSON outputs and `comparison.md`; the Markdown numbers were also inspected. The `report.md` champion table retains search measurements (P13 raw HB 2,559,919; P14 969,137); `comparison.md/json` correctly report the authoritative fresh finals (2,559,918; 969,083). These measurements remain separately identified.

The helper uses exact rational `T/T0 + floor(rawHB/1000)/published_H0` ranking. Independently recomputed aggregate unrounded conditional 15-task mean gains are **+0.185464493111957** versus fresh incumbents and **+0.306706549980739** versus archived reference88. The corresponding rounded-axis contributions before final overall rounding are exactly **167/900 = +0.185555555555556** and **23/75 = +0.306666666666667**. Secondary displays use Python rounding of the two reduction axes followed by problem-score rounding; the aggregate uses rounded axes before final full-score rounding. The root inspected the official formula page and reported last-file commit `88057731673d44e231788e3e87a9c797d585042a`; this reviewer did not independently fetch that page.

All score gains are conditional on unchanged compatibility and unchanged other 11 cases. The full displayed two-decimal score change depends on the unchanged aggregate's rounding phase. The exact supplied local primary compiler/context is the verification scope; Putnam imports are narrowed, and additional versions/full official headers remain unverified. No measured full-submission score or exact displayed full total is claimed. The final comparison states these limitations accurately.
