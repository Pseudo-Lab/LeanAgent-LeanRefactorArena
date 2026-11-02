# v7 상태·복구

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

SQLite 트랜잭션으로 dispatch intent·예약·영수증·복구·실패 기억을 관리한다.

## 확인된 결과와 해석

recovery/replay 및 로컬 검증이며 v7만의 새 유료 최적화·점수 개선 결과는 없다. unknown 유료 요청은 자동 재호출하지 않는다.

## 코드·Lean 보존 결정

상태 계약 연구로 보존. 전체 v7 실행기를 PR #46에 복사하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/stateful-harness-20261031/README.md` | `로컬 작업본` | `5549203f25fd1cea572f7f2c8f14fe99a74ab2322ed4b330a92376ad6a9b0a5a` |

## 원문: `experiments/stateful-harness-20261031/README.md`

### Stateful v7 harness

Fresh-run orchestration around the existing frozen v6 controller, OpenAI adapter,
Lean evaluator and deterministic golf algorithm. Historical v6 source, prepared
inputs and completed results remain unchanged. This change has not been tested
with a new paid optimization run and makes no score-improvement claim.

#### State and recovery

`src/lean_agent/workflow.py` stores each case, API call, completed Lean observation,
failure memory and hash-linked event in one SQLite transaction. SQLite uses FULL
synchronization; USD values use Decimal strings, never SQL floating-point sums.
The database is a run artifact. A nonblocking per-case worker lock excludes
concurrent workers. The existing controller retains ownership of Lean proof
admission, its immutable attempt ledger and the Pareto/best policy.

| Scope | Flow | Recovery rule |
|---|---|---|
| Problem | prepared → searching → finalizing → golfing → complete | Finalizing needs a stop reason and no unresolved call; golfing/completion require valid proof evidence. |
| Interruption | prepared/searching/finalizing/golfing → paused → original phase | STOP/PAUSE pauses at a work boundary, preserving its stage. It never implicitly finalizes a search. |
| Unknown API outcome | searching → blocked | Keep the full dollar reservation. Require the original response receipt before explicit resume. |
| API call | reserved → dispatching → responded → received → staged → evaluating → evaluated/rejected | Persist request and dispatch intent before HTTP; persist raw response before pricing; settle the receipt before candidate evaluation. |
| Lean interruption | evaluating with existing controller reservation | Recover the same attempt slot, without another API request. |
| Cross-ledger interruption | Lean result committed, API call still evaluating | Match expected attempt label and proof hash, then finish the call exactly once. |
| Golf interruption | golfing | Reuse the unchanged Golf.load/run cache and repeat independent final checks. |

An unsent reservation can dispatch after restart. A request interrupted after
dispatch intent cannot be automatically resent, even if the process might have
stopped just before HTTP. This is conservative recovery, not an exactly-once
guarantee from the external provider. Unknown usage remains reserved and blocks
further spend. Receipt IDs are unique across cases, and a saved response cannot be
replaced. The audit checks the event chain, committed projections, indexed fields
and all case caps. State changes and external HTTP/compiler work never share an
open database transaction.

Derived best/status files are rebuilt from the controller ledger before the next
stage. A matching orphan proof written before an interrupted controller reservation
is preserved before recovery. Infrastructure failures remain resumable; they are
not silently counted as preflight rejections or successful completion.

#### Persistent search memory

Every failed attempt remains in the database. Normalized diagnostics group fresh
metavariable IDs while retaining constants, argument types and failing expression
text. The next API input includes up to eight recurrent/recent failure groups,
their exact diagnostic excerpts and source lines, plus up to eight successful
repair summaries. This memory survives route changes and the old last-three full
candidate window; the complete observations are never evicted from disk.

Material stagnation uses a cumulative 0.5% objective improvement threshold.
Tiny heartbeat changes do not reset the counter. After six evaluations without
material gain, the common search state asks for a different induction target,
reusable interface or shared case handling. It does not equate a new route ID
with a new proof decomposition, and it does not add case-specific hints or reject
all local refinements automatically.

#### Commands

Source the project environment and use its central venv Python. Only `run` loads
an API key or can spend money. `prepare` runs local original-proof checks.
Preparation also resumes interrupted baseline work, preserving incomplete outputs
and skipping completed case checks. `prepare --problems P01` prepares a subset;
that run's problem selection stays fixed. Default selection is all fifteen.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
python -B experiments/stateful-harness-20261031/runner.py prepare
python -B experiments/stateful-harness-20261031/runner.py status --problems P02
python -B experiments/stateful-harness-20261031/runner.py run --problems P02
python -B experiments/stateful-harness-20261031/runner.py pause --problems P02
python -B experiments/stateful-harness-20261031/runner.py resume --problems P02
python -B experiments/stateful-harness-20261031/runner.py audit
python -B experiments/stateful-harness-20261031/runner.py reconcile --problems P02 --call call-001 --response /path/to/original-response.json
```

Default fresh output: `runs/stateful-openai-v7-20261031/`; use `--root` to select
another direct child of `runs/`. Historical runs are rejected. A pause command
sets a per-case request observed at the next work boundary; an active HTTP, Lean
evaluation or golf operation can finish first. Explicit resume changes state and
does not launch paid work. Run-wide `STOP` must be removed before resuming.
`reconcile` attaches a receipt to the original uncertain call; it never sends a
replacement request. Two case workers share the original three compiler slots.
Status reports outstanding reservations as accounted USD, including unsent or
unknown calls, rather than presenting them as confirmed usage charges.

Existing prepared input packets are reused. The previously identified theorem
signature extraction defect and import-level API discovery remain separate work;
this version changes state/orchestration and memory rather than repairing those
inputs or modifying the old frozen experiment.

#### Verification

```sh
python -B -m unittest discover -s experiments/stateful-harness-20261031 -p 'test_*.py' -v
python -B experiments/stateful-harness-20261031/replay.py
```

Tests inject interruptions before dispatch, after dispatch, after response saving,
during Lean, after Lean commit, after preflight rejection and before controller
reservation. They also cover exact dollar caps, concurrent reservations, duplicate
response IDs, phase guards, pause behavior, stale best files, golf-stage resumption,
persistent failure groups and material stagnation. Transport and Lean measurements
are synthetic; controller admission and ledger code are real.

Validation on 2026-10-31: 28 new state/driver tests and 22 existing controller/API
tests passed. A separate P01 native smoke run passed the original check plus three
measurements under the frozen primary compiler; repeated preparation reused that
completed state. No new paid search was launched. This validates recovery and
integration, not an improvement over the previous 82.53-point conditional estimate.

`replay.py` reads all 596 historical attempts into a **separate inspection database**
without API/compiler calls. It verifies that P02's repeated `bad rfl` errors stay
available after many subsequent attempts, audits all fifteen case projections and
verifies the historical files remain byte-identical. The replay is not a new
optimization result or a resumable paid run.
