# 구조화 v6 API 15문제

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

공통 구조 지침과 상태 장부로 원본에서 API 탐색 후 전체 golf를 수행한다.

## 확인된 결과와 해석

710고유 응답·$20.8474525,14문제40평가·P06은36평가. golf4689변형 중P03만84→80토큰. 평균O0.523951,사후88참조0.357309;2문제 개선·13악화.

## 코드·Lean 보존 결정

15 primary final 성공과 전체 지정 버전 성공을 구분한다. 성능 우월성 근거로 삼지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/structured-openai-20261031/README.md` | `로컬 작업본` | `5a20e57162df373555ebe9051f3a204d20dccc2e97051c85b6834584bcc9ae6d` |
| `runs/structured-openai-20261031/report.md` | `로컬 작업본` | `6ac94a946c1c32d8e36ea325f7a186e81541c2550093eb6b919599b47b3e9d84` |
| `runs/structured-openai-20261031/reference-88-comparison.md` | `로컬 작업본` | `86b6988b6973853b0a120ced8b1201b2cfb477aaa93d57b69ba623c30337f9ad` |

## 원문: `experiments/structured-openai-20261031/README.md`

### Structured v6 · OpenAI · P01–P15

Run requested on 2026-10-31: OpenAI API, current harness, at most **$2.70 per problem**, followed by deterministic golf and independent Lean verification. Total ceiling $40.50. Model `gpt-6.1-sol`, high reasoning, default service tier, explicit 30-minute prompt caching. Existing reference submissions and previous candidates are excluded from solver inputs.

`pipeline.py` imports the existing `structured-reasoning-20261030/controller.py` without editing it. The common strategy, evidence quotations, claim DAG, parent constraints, repairs, two-failure quarantine, duplicate rejection, best and Pareto retention remain the same. API transport replaces local agent execution. The forty-evaluation target is subordinate to the monetary ceiling; every API response, including rejected plans or incomplete outputs, consumes its case budget. API cases run independently in parallel, with three Lean compiler slots.

The stateless API receives the fixed original/context, all route definitions and evaluation metrics, current best proof, latest feedback and the last three full candidates/results. Earlier proof files remain in the controller ledger but are not all repeated in every API input. The API has no filesystem/library inspection tools. These transport constraints are recorded rather than treated as an exact reproduction of a local tool-using agent.

Inputs match full theorem names to the benchmark's original proofs. P01–P05 reuse the approved original/API context packets. The remaining cases expose preceding declarations and definitions while removing preceding theorem proof bodies. Each original is independently checked and measured three times in the same pinned local environment used for its candidates. Original T/H normalizers remain fixed throughout the case.

Two uniform compatibility repairs are recorded: qualify `Lean.Name.toString` in the measurement wrapper and allow `#(term)` cardinality through an old guard that rejected every `#`. Commands such as `#eval`, executable constructs, added options and axioms remain rejected. Actual Lean compilation and token counting always use the unmodified candidate bytes.

`adapter.py` reserves a conservative dollar ceiling before sending each request, has no automatic HTTP retry, and reconciles detailed cache/read/write/output usage. An unknown response keeps its full reservation charged and stops paid calls for that problem. An interrupted reserved call cannot be resubmitted automatically. A case worker lock prevents concurrent spend for the same problem. API keys are loaded in memory from the existing `.env`, never stored in requests or passed to Lean processes.

Golf uses the unchanged, hashed source from `runs/common-v5-golf-20261030/golf-source.py`: shorter source variants, greedy T+H/(H0/T0), up to forty rounds, dollar rewrites enabled, margin 0.3. Each final seed and changed candidate receives a fresh check and three measurements. Only a valid, lower-objective final candidate is adopted. Golf makes no model calls.

After the API phase and all fifteen independent finalizations completed, golf was checkpointed and resumed using the existing `Golf.load` cache support in `resume_golf.py`. Two case jobs now run in increasing initial-pool size order; the three compiler slots and two screen workers per case are unchanged. This avoids fifteen postprocessing jobs competing for the compiler queue. The transition records original state/API ledger hashes, and the report verifies they remain identical. Completed screening results are preserved and reused; interrupted directories are retained outside the cache scan. The frozen golf algorithm and API experiment source remain unchanged. The resumed driver never loads an API key and forbids model calls.

Commands, with the project's central environment configuration sourced first:

```sh
python -B experiments/structured-openai-20261031/pipeline.py prepare
python -B experiments/structured-openai-20261031/pipeline.py pilot --problems P01
python -B experiments/structured-openai-20261031/pipeline.py run
python -B experiments/structured-openai-20261031/verify_versions.py
python -B experiments/structured-openai-20261031/compare_88.py
python -B experiments/structured-openai-20261031/report.py
```

Results are in `runs/structured-openai-20261031/`; isolated model receipts and Lean artifacts are in `runs/structured-openai-private-20261031/`. `report.py` independently reconciles API receipts and controller/proof hashes. `verify_versions.py` checks additional prepared local versions and explicitly records missing versions. This experiment does not claim an official leaderboard score or a submission.

Completed: 710 unique API responses, usage estimate $20.8474525, maximum case $2.3628738. Fourteen cases completed forty Lean evaluations, P06 thirty-six because the next conservative reservation could not fit its remaining cap. All fifteen golf results passed independent primary checks and three measurements. Golf screened 4,689 new variants and improved P03 (84 to 80 proof tokens). Final mean O is 0.5239510246086615. Fresh archived 88-line comparison: two better (P03/P15), thirteen worse; reference mean O 0.3573090561511962.

P07–P09 additionally pass Cslib v4.31.0. Two historical additional-version templates omitted preceding definitions/theorems. `repair_additional.py` restores only surrounding source verified byte-for-byte against the official pinned GitHub commit and Git blob hash. The original failed artifacts and repair provenance are preserved; both unchanged original and selected golf proofs pass repaired contexts. Other absent required environments remain explicitly unverified, so this is not full benchmark version-matrix coverage. Final receipt/directory/unique-ID, frozen-source, budget, selected-proof and actual Lean source/log audits pass.

`compare_88.py` runs only after every golf summary exists. It verifies the archived 88-line input hashes and freshly checks/measures them using the same current primary contexts and fixed normalizers. Reference snapshots were retrieved only after the paid API search closed; they were never supplied to the solver or used as golf seeds. This comparison makes no model calls.

## 원문: `runs/structured-openai-20261031/report.md`

### OpenAI v6 · P01–P15

Model: `gpt-6.1-sol`, high reasoning. Current v6 common strategy; no case-specific hints. API cap $2.70 per case, $40.50 total.

Golf complete: 15/15. API calls: 710. Lean evaluations: 596. Usage estimate: $20.8474525; accounting including unresolved ceilings: $20.8474525.

| Problem | Stage | API / Lean | Valid / invalid | USD | Search T / H | Golf T / H | Golf O | Stop |
|---|---|---:|---:|---:|---:|---:|---:|---|
| P01 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P01/golf-best.lean`, 원래 실행 자료) | golf_complete | 46 / 40 | 28 / 12 | 0.8646970 | 40 / 1,679,470 | 40 / 1,679,460 | 0.452435 | forty_evaluations |
| P02 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P02/golf-best.lean`, 원래 실행 자료) | golf_complete | 49 / 40 | 29 / 11 | 0.8802883 | 54 / 388,027 | 54 / 388,027 | 0.387223 | forty_evaluations |
| P03 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P03/golf-best.lean`, 원래 실행 자료) | golf_complete | 59 / 40 | 34 / 6 | 1.3148648 | 84 / 181,319 | 80 / 180,910 | 0.395868 | forty_evaluations |
| P04 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P04/golf-best.lean`, 원래 실행 자료) | golf_complete | 40 / 40 | 30 / 10 | 1.0468388 | 193 / 2,054,125 | 193 / 2,054,125 | 0.398779 | forty_evaluations |
| P05 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P05/golf-best.lean`, 원래 실행 자료) | golf_complete | 41 / 40 | 28 / 12 | 1.7019093 | 556 / 7,958,750 | 556 / 7,958,750 | 0.700208 | forty_evaluations |
| P06 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P06/golf-best.lean`, 원래 실행 자료) | golf_complete | 51 / 36 | 25 / 11 | 2.3628738 | 496 / 15,405,346 | 496 / 15,405,346 | 0.774103 | budget_reservation |
| P07 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P07/golf-best.lean`, 원래 실행 자료) | golf_complete | 61 / 40 | 31 / 9 | 2.1811003 | 360 / 12,566,043 | 360 / 12,566,024 | 1.085208 | forty_evaluations |
| P08 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P08/golf-best.lean`, 원래 실행 자료) | golf_complete | 54 / 40 | 26 / 14 | 1.2925794 | 224 / 474,686 | 224 / 474,686 | 0.894233 | forty_evaluations |
| P09 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P09/golf-best.lean`, 원래 실행 자료) | golf_complete | 46 / 40 | 29 / 11 | 0.9068198 | 112 / 440,474 | 112 / 440,474 | 0.560504 | forty_evaluations |
| P10 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P10/golf-best.lean`, 원래 실행 자료) | golf_complete | 40 / 40 | 27 / 13 | 1.5497828 | 457 / 4,653,652 | 457 / 4,653,652 | 0.604901 | forty_evaluations |
| P11 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P11/golf-best.lean`, 원래 실행 자료) | golf_complete | 43 / 40 | 27 / 13 | 1.8513564 | 501 / 11,488,620 | 501 / 11,488,620 | 0.515154 | forty_evaluations |
| P12 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P12/golf-best.lean`, 원래 실행 자료) | golf_complete | 47 / 40 | 29 / 11 | 1.4055472 | 341 / 3,067,147 | 341 / 3,067,147 | 0.585430 | forty_evaluations |
| P13 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P13/golf-best.lean`, 원래 실행 자료) | golf_complete | 41 / 40 | 29 / 11 | 1.1242598 | 304 / 1,743,013 | 304 / 1,743,014 | 0.201111 | forty_evaluations |
| P14 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P14/golf-best.lean`, 원래 실행 자료) | golf_complete | 44 / 40 | 27 / 13 | 1.0439956 | 154 / 870,514 | 154 / 870,514 | 0.098421 | forty_evaluations |
| P15 (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/P15/golf-best.lean`, 원래 실행 자료) | golf_complete | 48 / 40 | 28 / 12 | 1.3205392 | 283 / 1,660,146 | 283 / 1,660,146 | 0.205688 | forty_evaluations |

| Problem | Required versions | Verified versions | Unavailable / failed |
|---|---|---|---|
| P01 | v4.26.0 | v4.26.0 |  |
| P02 | v4.26.0 | v4.26.0 |  |
| P03 | v4.29.1, v4.27.0, v4.26.0 | v4.26.0 | v4.29.1: unavailable, v4.27.0: unavailable |
| P04 | v4.32.0 | v4.32.0 |  |
| P05 | v4.32.0 | v4.32.0 |  |
| P06 | v4.32.0 | v4.32.0 |  |
| P07 | v4.33.0-rc2, v4.32.0, v4.31.0 | v4.32.0, v4.31.0 | v4.33.0-rc2: unavailable |
| P08 | v4.33.0-rc2, v4.32.0, v4.31.0, v4.30.0 | v4.32.0, v4.31.0 | v4.33.0-rc2: unavailable, v4.30.0: unavailable |
| P09 | v4.33.0-rc2, v4.32.0, v4.31.0 | v4.32.0, v4.31.0 | v4.33.0-rc2: unavailable |
| P10 | v4.31.0, v4.30.0, v4.29.0, v4.28.0 | v4.31.0 | v4.30.0: unavailable, v4.29.0: unavailable, v4.28.0: unavailable |
| P11 | v4.31.0, v4.30.0, v4.29.0 | v4.31.0 | v4.30.0: unavailable, v4.29.0: unavailable |
| P12 | v4.31.0, v4.30.0, v4.29.0 | v4.31.0 | v4.30.0: unavailable, v4.29.0: unavailable |
| P13 | v4.25.0, v4.26.0, v4.27.0 | v4.26.0 | v4.25.0: unavailable, v4.27.0: unavailable |
| P14 | v4.25.0, v4.26.0 | v4.26.0 | v4.25.0: unavailable |
| P15 | v4.25.0, v4.26.0, v4.27.0 | v4.26.0 | v4.25.0: unavailable, v4.27.0: unavailable |

O=T/T0+H/H0; lower is better. Fixed original normalizers, check plus three measurements for every valid candidate and final selection. Forty evaluations is a target subordinate to the dollar cap. Failed Lean evaluations count; rejected plans still consume API budget.

Golf uses the frozen existing local rewrite/screening algorithm, with no additional model calls. It adopts only a valid candidate with a lower independently remeasured objective.

Verification covers the frozen local primary environment per problem. Available additional versions are reported separately; absent versions are not claimed as verified. These local metrics are not an official leaderboard score.

API request/response receipts and Lean logs remain under `runs/structured-openai-private-20261031/`; the key is never persisted in requests. The audit reconciles received usage, reserved ceilings, request hashes, controller ledger and selected proof hashes.

API cost by response outcome: lean=$17.3901652, preflight=$3.4572873.
Preflight rejection reasons: {"Evidence quotation missing from the named source (min 8 characters)": 67, "Duplicate/comment-only candidate; not a new evaluation": 47}.
API token usage (including hidden reasoning in output): {"input_tokens": 9905519, "output_tokens": 1156719, "cached_tokens": 5571370, "cache_write_tokens": 109655, "reasoning_tokens": 612412}. These API tokens differ from Lean proof-source T.

88-line fresh same-environment comparison (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/structured-openai-20261031/reference-88-comparison.md`, 원래 실행 자료): better 2, tie 0, worse 13; reference valid 15/15. Mean local O: reference 0.3573090561511962, current 0.5239510246086615.

## 원문: `runs/structured-openai-20261031/reference-88-comparison.md`

### 보관된 88점 라인과 동일 환경 비교

API 탐색이 모두 종료된 후에만 88 입력 스냅샷을 읽었다. 풀이 입력·프롬프트·후처리에는 참조 증명을 제공하지 않았다.
각 참조 증명을 이번 실행의 동일한 고정 주환경에서 새로 검사하고 3회 측정했다. O=T/T0+H/H0이며 낮을수록 좋다. 공식 제출 점수와 구분한 로컬 비교다.

참조 검증 통과 15/15. 이번 결과가 더 낮음 2, 동률 0, 더 높음 13.

| 문제 | 88 입력 T / H | 88 O | 이번 golf T / H | 이번 O | 판정 |
|---|---:|---:|---:|---:|---|
| P01 | 32 / 1320580 | 0.357505 | 40 / 1679460 | 0.452435 | worse |
| P02 | 19 / 326116 | 0.206593 | 54 / 388027 | 0.387223 | worse |
| P03 | 78 / 230112 | 0.397471 | 80 / 180910 | 0.395868 | better |
| P04 | 123 / 1406313 | 0.262283 | 193 / 2054125 | 0.398779 | worse |
| P05 | 427 / 5484136 | 0.514473 | 556 / 7958750 | 0.700208 | worse |
| P06 | 422 / 11133579 | 0.611658 | 496 / 15405346 | 0.774103 | worse |
| P07 | 101 / 7934820 | 0.375642 | 360 / 12566024 | 1.085208 | worse |
| P08 | 185 / 382913 | 0.731929 | 224 / 474686 | 0.894233 | worse |
| P09 | 79 / 512881 | 0.447817 | 112 / 440474 | 0.560504 | worse |
| P10 | 257 / 3165262 | 0.374635 | 457 / 4653652 | 0.604901 | worse |
| P11 | 248 / 6215475 | 0.266612 | 501 / 11488620 | 0.515154 | worse |
| P12 | 156 / 2277845 | 0.362900 | 341 / 3067147 | 0.585430 | worse |
| P13 | 259 / 2606427 | 0.190168 | 304 / 1743014 | 0.201111 | worse |
| P14 | 55 / 821228 | 0.041377 | 154 / 870514 | 0.098421 | worse |
| P15 | 281 / 1822909 | 0.218572 | 283 / 1660146 | 0.205688 | better |

동일 비교 사례 평균 O: 88 입력 0.3573090561511962, 이번 golf 0.5239510246086615.
지원 버전 전체의 검증 여부는 본 실행 report.md의 버전 표를 참조한다.
