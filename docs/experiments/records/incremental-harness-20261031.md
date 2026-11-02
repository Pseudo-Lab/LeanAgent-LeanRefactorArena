# v10 증분 하네스

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

소스 구간 golf·LSP 실패 선별·문맥 유지·FIFO 및 fresh 병렬 측정을 연결한다.

## 확인된 결과와 해석

3문제 유료 실행105호출·77평가·$5.8509499. v9 대비 조건부 평균69.212969→86.077089, 경과2.754배 비율. 후보·작업량이 다른 과거 대조이며 모두40회 이전 예산 예약 중단이다.

## 코드·Lean 보존 결정

실험 구현과 검증 근거를 보존. LSP의 warm HB로 최종 순위를 정하지 않는다. 공통 기본 경로의 후속 통합 대상이다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/incremental-harness-20261031/README.md` | `로컬 작업본` | `c1535aa79edaa473308a5eac7e87e3b1b7ba83ab29a61539d85a8c237ba6fade` |
| `runs/incremental-v10-threecase-20261031/comparison.md` | `로컬 작업본` | `379cc537d24601fecc137d34a3e75d133a3e4da435e678f8acd918bcb89d0452` |
| `runs/incremental-v10-threecase-20261031/budget-reservation-analysis.md` | `로컬 작업본` | `68209d3b59c66800e431342c4629ce3e40d5174173a713a5b9b6b218f14cef75` |
| `runs/incremental-v10-worker-validation-20261031/REPORT.md` | `로컬 작업본` | `2bd00e86c2c8225273840f8c2b491250b8770ff699ca12948e82e3b6b0a9b472` |
| `runs/incremental-v10-fresh-parallel-validation-20261031/comparison.md` | `로컬 작업본` | `cff11d0cc8b6ede1c37793a80929952eea06f6555052239d4dc2bad9cac0271d` |

## 원문: `experiments/incremental-harness-20261031/README.md`

### Incremental v10 harness

Recommended next-run entrypoint: `fast_runner.py prepare` followed by
`fast_runner.py run`. Its default root is a new `incremental-parallel-v10-20261031`
run; it records both the entrypoint and parallel evaluator in the protocol. The
completed paid v10 trial keeps its original serial measurement policy and files.
The new entrypoint passed all three original baselines with three fresh samples
each, source freezing and workflow auditing, using no additional API calls.
Final combined regression suite:97tests passed (87original v10,8parallel,2entrypoint).

The completed Sol-plus-golf trial used105calls,$5.8509499 and77actual search
evaluations(P01 25,P10 17,P14 35). Preparation plus batch execution took
4597.397772seconds versus12659.550287seconds previously (2.754× elapsed ratio).
Three-case conditional mean score rose69.212969→86.077089. P01 total time grew
while doing more evaluations; P10 and P14 total time fell. See
`runs/incremental-v10-threecase-20261031/comparison.md` and `final-audit.json`.

All cases stopped before40because conservative next-call reservations exceeded
remaining budgets; the actual charges did not exhaust$2.70. The budget diagnosis
records that byte-based input bounds were3.1–3.4× the last observed token counts.
This is a remaining planner limitation, not evidence of40completed attempts.

After the paid process exited, identical final proofs were verified with four
fresh processes in both serial and parallel modes. P01 took41.69→22.23seconds,
P10 33.20→19.56seconds, P14 7.80→2.72seconds. Validity/token counts agreed; median
raw heartbeat differences were−60,0,+13. These are single paired observations
with alternating case order, not guaranteed speedups. The parallel path still
performs an unchanged-context check first and three independent fresh processes;
the shared FIFO remains the global capacity limit. See
`runs/incremental-v10-fresh-parallel-validation-20261031/summary.json`.

Astra implementation was reviewed and integrated by the parent agent before the
new GPT-6.1 Sol experiment. Historical v9 sources and paid runs remain frozen.

`v10_trial.py prepare` prepares P01/P10/P14 from the original benchmark packets.
`v10_trial.py run` uses the same common instructions, high reasoning, a $2.70
ceiling per problem, a target of 40 actual Lean evaluations, and full golf.
The budget takes precedence over the target. Only `run` loads the existing key.
Preparation, status, validation and auditing do not call a model API.

The implementation changes four things:

1. Golf edits source spans. Unchanged bytes, line layout, literals and comments
   survive reconstruction. All original generic operator families and greedy
   tiers remain; there is no screen-count or elapsed-time cap. The original
   forty-round limit and minimum objective improvement remain unchanged.
2. Golf's negative prefilter uses persistent Lean LSP document snapshots. Each
   edit replaces the target command and suffix from the same immutable prefix.
   Exact-version completion, diagnostics and nonce checks prevent stale results.
   Only completed failures skip a fresh process; pass/unknown always receives a
   fresh CLI screen. Warm heartbeats never rank candidates. Search evaluations
   and final selection still use the original unchanged-context check plus
   three fresh measurements.
3. Model requests retain every unique retrieved native fact and the active and
   most recent failed proof with diagnostics. Fact provenance is losslessly
   compacted rather than capped. Identical immutable native queries can reuse
   their result. Diagnostic-address and parent-citation annotations are warnings;
   source access, same-route parent checks and Lean proof guards stay enforced.
4. A shared FIFO queue admits up to three active compiler jobs. Each case has
   three golf workers and may use idle slots. Kernel owner locks recover crashed
   tickets without expiring a slow live compiler. Idle LSP servers hold no slot.

The v9 transactional request lifecycle is retained: dispatch intent is committed
before network access, unknown responses retain their full reserved charge, and
unknown paid requests are never automatically retried. Fresh sources, model,
instructions, compiler and runtime fingerprints are recorded in the protocol.

Parent verification before the paid experiment: 87 unit/regression tests passed;
an actual three-job queue/prefilter/fresh-CLI integration test passed with
valid/invalid/valid outcomes. Astra's fixed-source corpus agreed with the CLI on
15/15 decisions; prefix clock witnesses demonstrated actual snapshot reuse and
absence of a previous candidate's theorem on Lean 4.26, 4.31 and 4.32.

See `runs/incremental-v10-worker-validation-20261031/REPORT.md` for matched
timings, including expensive cold startup and the slower short-batch results.
Only a completed new trial can establish end-to-end elapsed time and score;
changing candidate choices prevents attributing every wall-time difference to
the worker. Required-version coverage is reported separately from primary pins.

## 원문: `runs/incremental-v10-threecase-20261031/comparison.md`

### v10 검증 시간·점수 비교

상태: complete. 공통 프롬프트, GPT-6.1 Sol high, 문제당 최대 $2.70, 목표 40회 평가, 전체 golf.

| 문제 | v9 평가 → v10 평가 | v9 실행 → v10 실행 | v9 golf → v10 golf | v9 점수 → v10 점수 | v10 사용액 |
|---|---:|---:|---:|---:|---:|
| P01 | 11 → 25 | 35분 58초 → 52분 32초 | 22분 25초 → 18분 57초 | 75.944 → 81.441 | $1.9055988 |
| P10 | 2 → 17 | 3시간 27분 40초 → 1시간 14분 12초 | 3시간 17분 43초 → 20분 22초 | 33.333 → 78.213 | $1.8778431 |
| P14 | 24 → 35 | 38분 18초 → 21분 9초 | 1분 35초 → 1분 30초 | 98.362 → 98.577 | $2.0675080 |

세 문제 평균 점수: 69.213 → 86.077.
동일 세 문제의 이전 v6 평균은 87.158, 88라인 참조 평균은 91.405이다.
배치 실행: 1시간 14분 12초. 준비 포함 합계: 1시간 16분 37초.

점수는 공통 원본 정규화값으로 계산한 3문제 조건부 로컬 점수다. 필수 버전 전체 호환을 가정하며, 공식 제출 점수나 15문제 평균이 아니다.
실행 시간에는 큐 대기, 상주 검증기 첫 기동, API, 새 프로세스 측정, 전체 golf가 포함된다. 생성된 증명과 평가 횟수가 달라 전체 시간 차이를 검증기만의 인과 효과로 볼 수 없다.
동일 후보를 대조한 검증 시간은 ../incremental-v10-worker-validation-20261031/REPORT.md를 참고한다. 짧은 묶음에서는 첫 기동 비용 때문에 더 느린 결과도 포함한다.

## 원문: `runs/incremental-v10-threecase-20261031/budget-reservation-analysis.md`

### Why the paid search stopped before 40 evaluations

All three cases stopped at `budget_reservation`, not because their $2.70 caps were fully spent. The exact frozen planner was replayed offline against the closed search state; no request was reserved or sent.

| Case | Evaluations | Settled cost | Unused budget | Next input bound | Minimum next reservation | Shortfall |
|---|---:|---:|---:|---:|---:|---:|
| P01 | 25/40 | $1.9055988 | $0.7944012 | 158,662 | $0.841830 | $0.0474288 |
| P10 | 17/40 | $1.8778431 | $0.8221569 | 161,345 | $0.855245 | $0.0330881 |
| P14 | 35/40 | $2.0675080 | $0.6324920 | 123,360 | $0.665320 | $0.0328280 |

The planner counts the serialized UTF-8 request bytes, adds 4,096, and prices that entire bound as input tokens at **$5 per million**: the maximum frozen input/cache price, covering a 12-hour cache write even though the request asks for 30 minutes. It also reserves **4,352 output tokens** (minimum 4,096 plus 256 padding) at $10 per million and adds $0.005. Thus the minimum is `bound × $0.000005 + $0.04352 + $0.005`.

The computed affordable output limits were P01: -647, P10: 787, P14: 813. Each is below the required 4,096; the negative P01 value means its input ceiling and safety margin alone exceed the remaining budget. All input bounds remain below the separate 200,000 cutoff.

#### Last sent request versus reconstructed next request

The following provider counts are **observed for the last sent request**. They are not exact counts for the unsubmitted next packet.

| Case | Last provider input tokens | Last planner byte bound | Bound / actual tokens | Last max output tokens | Last settled cost |
|---|---:|---:|---:|---:|---:|
| P01 | 46,306 | 158,733 | 3.428× | 7,399 | $0.0808172 |
| P10 | 51,012 | 159,337 | 3.124× | 9,294 | $0.0750307 |
| P14 | 36,668 | 122,022 | 3.328× | 8,500 | $0.0701838 |

The byte bound was roughly 3.1–3.4 times the last actual input count, before the additional conservatism from worst-case input pricing. Reservations are released down to settled receipt costs after each call, but the resulting remainder must still cover the next full conservative reservation. Unused money therefore does not imply that the current policy could safely send another call.

#### Reconstructed context size

Values below are canonical JSON bytes for each component; request JSON escaping, field names and schema add overhead. The JSON report also provides exact wire contributions and nested breakdowns. No facts were dropped or capped.

| Case | Experience | Persistent working memory | Workflow memory | Routes | Observation metadata | Full wire request |
|---|---:|---:|---:|---:|---:|---:|
| P01 | 42,641 | 52,845 | 10,235 | 1,917 | 1,567 | 154,566 |
| P10 | 31,287 | 47,655 | 6,886 | 4,718 | 3,100 | 157,249 |
| P14 | 44,768 | 37,099 | 4,894 | 1,107 | 2,899 | 119,264 |

Working memory retains all unique native facts plus the full active/latest failed candidates. Experience includes attempt edges, failure diagnostics, valid Pareto source and patch summaries. Some evidence/diagnostics occur in multiple views, so further **lossless** sharing could reduce size in a future protocol; arbitrary fact truncation is not recommended.

#### Method and limits

The analysis read a single SQLite `mode=ro` snapshot and immutable same-case inputs/source files. It called the frozen `dynamic`, `Workflow.memory`, `payload` and `plan` functions with in-memory snapshots, without constructing a database-writing Workflow object or configuring/running the pipeline. It reproduced the exact extra fields assigned by `Driver.search_step`. The search attempts match the workflow ledger; later finalization/golf fields do not affect these request fields. Frozen hashes still match.

The next request was rejected before persistence, so its original bytes do not exist for direct comparison. The JSON report records the deterministically reconstructed body/static/dynamic hashes. It separately records the last actually sent request, its provider usage, and its reserved/settled cost.

For a future reviewed protocol, the [documented exact-input-count endpoint](https://developers.openai.com/api/docs/guides/token-counting) may allow a tighter reservation for the assembled request. Its existence was verified by the parent; this analysis did not call it, and its pricing has not been verified—there is no claim that it is free. Any change to cache-rate assumptions requires verified provider guarantees. This trial remains closed to additional API spending; no resume or live changes were performed.

## 원문: `runs/incremental-v10-worker-validation-20261031/REPORT.md`

### Persistent Lean worker offline validation

15/15 fixed candidates matched fresh CLI classification; 0 false rejections. No paid API calls.

| Case | Compiler | Warm worker median | Matched fresh median | Cold worker | Five-candidate fresh total | Negative-prefilter modeled total |
|---|---|---:|---:|---:|---:|---:|
| P01 | v4.26.0 | 2.915s | 16.017s | 32.099s | 79.854s | 89.454s |
| P10 | v4.31.0 | 2.592s | 40.882s | 60.674s | 204.186s | 189.347s |
| P14 | v4.26.0 | 0.218s | 1.679s | 10.235s | 7.523s | 15.715s |

Each case used the same five persisted candidate sources in valid→invalid→valid→invalid→valid order. Worker and fresh order alternated. Fresh CLI retained the original command, template, compiler options, sandbox, and measurement wrapper. The worker disabled automatic Lake setup so pinned LEAN_PATH remains authoritative.

Warm processing is substantially faster, but cold startup is expensive. The conservative negative-prefilter policy still runs a fresh screen for every valid/unknown worker result. On this tiny corpus its modeled total improved only P10; P01 and P14 were slower. Three worker instances per case multiply cold startup and retained memory; benefits require sufficient invalid candidates per warmed instance. These are local wall times, not statistical performance guarantees.

The prefix-reuse witness used a clock-valued diagnostic before the target. Its exact stamp remained unchanged across three different target proofs on Lean 4.26, 4.31, and 4.32, then changed after a forced restart. A self-reference proof failed between two valid proofs, demonstrating no previous target theorem leaked. See reuse-witness/summary.json.

Safety: exact-version diagnostics plus the versioned waitForDiagnostics completion barrier; random per-request report nonce; serial fixed-URI edits beginning before the target; compiler/environment/template/options fingerprint with restart on guard changes. Timeout, crash, stale/missing diagnostics, prefix error, or resource exhaustion returns unknown. No warmed heartbeat value is returned for ranking. Ten protocol tests pass.

Only confidently complete invalid results may skip the fresh screen. Existing fresh CLI and three fresh heartbeat measurements remain necessary for validity/ranking. Dependencies are expected to remain frozen; guard checks compiler, environment configuration, and declared manifest/fingerprint files, not every imported artifact recursively.

Source provenance: the benchmark executed the exact archived benchmarked-worker-source.py. Final code differs in compact progress logging and candidate-literal-preserving one-pass rendering. All 15 complete rendered candidate sources were byte-identical between archived and final renderers. Exact hashes and per-case manifest clarification are in source-provenance.json.

## 원문: `runs/incremental-v10-fresh-parallel-validation-20261031/comparison.md`

### 동일 증명: 새 측정 3회 병렬화

Sol+golf 최종 증명과 동일한 고정 환경을 두 방식에서 사용했다. 매번 원문 검사 1회와 독립된 새 측정 3회, 총 새 프로세스 4개를 실행했다. 추가 API 호출은 0회다.

| 문제 | 순차(초) | 병렬(초) | 비율 | 토큰 수 | 중앙값 HB 차이 |
|---|---:|---:|---:|---:|---:|
| P01 | 41.69 | 22.23 | 1.88× | 62 | -60 |
| P10 | 33.20 | 19.56 | 1.70× | 477 | +0 |
| P14 | 7.80 | 2.72 | 2.87× | 33 | +13 |

세 문제 검증 시간 합계: 82.69초 → 44.51초 (1.86×).

각 문제 한 번의 짝지은 관측이며 실행 순서를 문제별로 바꿨다. OS 캐시·기계 부하가 달라질 수 있어 이 비율을 모든 실행의 보장값으로 해석할 수 없다. Heartbeat는 상주 검증기에서 가져오지 않았다.

검사기는 parallel_evaluator.py, 연결된 새 진입점은 fast_runner.py다. 완료된 유료 v10 실험의 실행 시간을 이 병렬 검사 결과로 소급 변경하지 않았다.
