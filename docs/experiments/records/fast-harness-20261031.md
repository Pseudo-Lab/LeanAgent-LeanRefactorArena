# v8 빠른 실험 모드

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

API 탐색과 golf 큐를 분리하고 중간 측정·golf 검사량을 제한한다.

## 확인된 결과와 해석

P10 40회+제한 golf: 37분29초, 비용 추정 $2.0348133. 조건부 점수 79.84→78.09로 악화. 동등 품질의 속도 개선 실험이 아니다.

## 코드·Lean 보존 결정

속도·품질 절충의 부정 결과로 보존. 공통 기본 모드로 자동 채택하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/fast-harness-20261031/README.md` | `로컬 작업본` | `b60d0335093a11a54589b202b4e783e19fcaa441374ea78e9cf6a2c39edd3054` |
| `runs/fast-p10-timing-20261031/comparison.md` | `로컬 작업본` | `7179d444a60b53884379c19d1b84358f858cba818eca0e6e1744b5c318dfc4bb` |

## 원문: `experiments/fast-harness-20261031/README.md`

### V8 fast experiment profile

Status: a workload/quality tradeoff experiment, not demonstrated equal-quality
acceleration. The new common strategy is [v9](research-harness-20261031.md),
which restores three measurements and full golf while improving compiler context
and within-run evidence reuse. V8 source and historical results remain preserved.

Adds a faster fresh-run profile on top of v7 state/recovery, without changing
completed v6/v7 source or results. Initial implementation used no paid model calls.
A subsequent authorized P10 pilot completed forty evaluations and bounded golf:
37m29s execution, 56s preparation, $2.0348133 usage estimate, 45 API responses.
The historical P10 fifteen-case-batch wall was 4h26m including queueing/resumption;
this is not a matched speed benchmark. Search/golf compiler counts were 121/516
historically and 65/18 in the pilot. The conditional common-normalizer score fell
from 79.84 to 78.09. Full fifteen-case fast timing and repeated quality trials remain
unmeasured. See `runs/fast-p10-timing-20261031/comparison.md` and its receipt audit.

#### Why the previous run took hours

The preserved request/response files show API start at 01:46:19 KST and final
golf at 07:02:45 KST on 2026-10-31: 5h16m for that core interval. This excludes
earlier preparation/operator work and later version checks/analysis, so it does
not account for the user's entire approximately nine-hour wait.

| Work | Recorded invocations | Sum of process wall hours |
|---|---:|---:|
| Search candidate compilation | 1,877 | 5.46 |
| Golf screening, including seeds | 4,704 | 9.72 |

These process-hours overlap across three compiler slots; they are **not** elapsed
machine hours and must not be added to API wait as sequential durations. API
responses span 2h08m and overlap compiler work. Intermediate proofs were checked
once and measured three times; 427 valid/169 invalid evaluations required 1,877
compiler invocations. Golf's 4,689 new variants improved one case and added about
0.04 points to the conditional local fifteen-case score.

`profile_run.py` reproduces the accounting without API or compiler calls and
writes `runs/fast-harness-analysis-20261031/timing.json`.

#### Fast profile

| Setting | Default | Effect |
|---|---:|---|
| Search case workers | 15 | Overlap API waits across problems. This replaces v7's two workers for the entire problem lifecycle. |
| Native Lean slots | 3 | Retain the tested concurrency for this 16GB machine. |
| Intermediate measurements | 1 | Still run the unchanged-context compilation, then one heartbeat/axiom measurement. |
| Baseline/final measurements | 3 | Preserve the original check plus three independent measurements. |
| Golf case workers | 2 | Separate bounded postprocessing queue after all selected searches settle. |
| Golf screen workers/case | 2 | Share the same three native slots. |
| New golf screens/case | 40 | Lifetime cap, including interrupted reservations. |
| Golf screening wall budget/case | 180s | Stop launching new batches after the budget; active compiles and independent seed/final checks are additional. |

The API cap remains $2.70/problem and the target remains forty completed Lean
evaluations. Budget priority and unknown-response blocking are unchanged. Only
the sampling repeats and postprocessing breadth change. Full original-context
compilation, statement preservation, axioms and final independent checks remain.

For exactly the historical candidates, intermediate invocations would drop from
1,877 to 1,023; golf gets at most 600 new screens across fifteen problems. The
candidate compilation workload estimate is 6,581 → 1,623, about **75% fewer**,
excluding baseline/final checks. Future candidates, API latency, memory pressure
and validation failures can change actual wall time. A 2–3 hour core-run target
is a planning estimate, not a measured benchmark or guarantee.

Reduced measurement sampling can change the order of candidates with very close
HB values. Bounded golf can miss improvements found by exhaustive screening.
Every adopted golf result must still pass a fresh unchanged-context check plus
three measurements and improve on its independently checked seed.

#### State and instrumentation

`FastDriver` settles all selected searches with fifteen workers, leaving finalized
cases in `golfing`. The second stage runs two golf jobs, with model transport
disabled. API waiting no longer shares a two-worker limit with postprocessing,
and golf cannot occupy a remaining search's compiler queue.

Golf reuses the frozen variant generator, lexical guard, screen compiler and
axiom checker. It selects variants by a deterministic round-robin over edit
families, prioritizing token savings within each family. A measured improvement
is applied promptly. Reservations persist before native submission, so restart
cannot reset the forty-screen cap. Completed screens and the current best path
are reused; interrupted artifacts are retained separately.

`timings.jsonl` separates API waits, compiler execution and queue wait estimates.
Telemetry errors never prevent a received API response from reaching the durable
workflow ledger. State, uncertainty, explicit resume and receipt reconciliation
retain v7 behavior. Existing prepared context packets are reused; the separate
context extraction/API-discovery issues are not repaired by this speed profile.

#### Run

Use the project's central venv Python after sourcing the environment. `prepare`
runs local baseline checks; only `run` can load an API key and spend money.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
python -B experiments/fast-harness-20261031/runner.py prepare
python -B experiments/fast-harness-20261031/runner.py run
python -B experiments/fast-harness-20261031/runner.py status
python -B experiments/fast-harness-20261031/runner.py audit
```

Default output is `runs/fast-openai-v8-20261031/`. Use `--root` for a fresh direct
child of `runs/`, and `--problems P01` to prepare a fixed subset. Optional frozen
flags include `--search-workers`, `--golf-workers`, `--compiler-slots`,
`--search-measurements` (1 or 3), `--golf-screens` and `--golf-seconds`.
Existing runs load their recorded flags automatically. Changing one requires a
fresh run. `pause`, `resume` and `reconcile` match the v7 control commands and
never launch paid work.

#### Verification

```sh
python -B -m unittest discover -s experiments/fast-harness-20261031 -p 'test_*.py'
python -B experiments/fast-harness-20261031/profile_run.py
python -B experiments/fast-harness-20261031/native_probe.py
```

Tests cover lifetime caps, interruption/resume, the soft wall budget, preserving
an already selected improvement after expiry, cached results, deterministic edit
family diversity, API/golf scheduling barriers, blocked cases, telemetry failure
and intermediate/final sampling separation. The native probe uses a previously
selected P01 proof solely to validate two versus four actual compiler invocations;
it is not a new solver result. Full v7 recovery tests remain separate and unchanged.

## 원문: `runs/fast-p10-timing-20261031/comparison.md`

### P10 fast-profile trial

One isolated v8 trial versus a historical v6 fifteen-case batch. Different solver candidates, memory/prompt and machine contention; not a controlled causal speedup estimate. Scores assume 100% compatibility; only primary pin is verified here.

| Metric | Historical v6 | New v8 |
|---|---:|---:|
| Run wall time (historical includes batch queue/resume) | 266.22 min | 37.48 min |
| Search + final wall | 122.58 min | 33.72 min |
| Golf stage wall | 143.64 min | 3.76 min |
| Search compiler processes | 121 | 65 |
| Golf screening processes | 516 | 18 |
| API calls | 40 | 45 |
| Usage estimate USD | 1.5497828 | 2.0348133 |
| Proof T / H | 457 / 4,653,652 | 540 / 4,582,678 |
| Conditional score (common normalizers, compatibility=100%) | 79.8366 | 78.0943 |

Preparation: 0.93 min. Completed evaluations: 40; stop: forty_evaluations. Primary final proof independently checked plus three measurements.

Final declaration: /Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/fast-p10-trial-20261031/P10/golf-best.lean (`/Users/jwkweon/00_work/00_project/05_pseudolab/LeanAgent-LeanRefactorArena/runs/fast-p10-trial-20261031/P10/golf-best.lean`, 원래 실행 자료). Receipt, request isolation, source, ledger, budget and proof audits passed.
