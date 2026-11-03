# final60 runbook

One autonomous, resumable run over all 60 final problems through OpenRouter only.
Entry point: `python -m lean_agent.final60 {plan,run,row,status,assemble}` from the repository
root with `PYTHONPATH=src`. Paths below are placeholders (`$REPO`, `$RUN`, `$KEY`, `$PY`); nothing
machine-specific is tracked. Linux uses the bwrap sandbox and macOS uses sandbox-exec, both unchanged.

## What runs

- `<run-dir>/rows/F0NN` is a normal `experiments/final-batch-next` root holding exactly one row.
  A stop marker, a bad receipt or an audit failure affects that row only.
- Each row: route (routing component, or a stub) -> `input/route.json` + `input/final60.json`
  -> `driver.prepare_inputs` (cold start, strict cap) and `seal_inputs` -> `preflight`
  -> `driver.run_problem` (scouts a/b/c, merger until budget) -> golf + `select_final`
  (golf component, when installed) -> `report.build_report` -> `published.json`.
- Money: every request is reserved in the row's `ledger.json` (the audited truth) with
  `spent + open reservations + worst-case bound <= 2.99 - declared prior`, then sent by
  `money.dispatch_guarded`, which mirrors every HTTP sub-attempt in `<run-dir>/final60.sqlite`.
  One settled `ledger.json` attempt per driver step; a lost response is one unevaluated call
  charged at its exact generation cost or its bound. A possibly billed request is never re-sent.
- Exploration ends cleanly (row still selects and publishes) on: `skip_llm` rows, the row
  exploration clock (75 min default), the global soft stop, `api-disabled.json` (401/402),
  a row API freeze (bound violation or accounting mismatch), salvage after 3 crashes, or a
  ledger `BudgetExceeded`.
- `submission.jsonl` always has 60 rows: a row's proof is used only when its `published.json`
  matches `selected.lean` and `report.json` by hash, its audit passed, its root is an OpenRouter
  (non-dry-run) root, its recorded spend is at most 2.99, and both PR #64/#70 checkers accept it.
  Every other row is the dataset original (33.33, never 0).

## 0. One-time setup (before launch)

1. Production runs from a dedicated worktree at a tagged commit that no agent edits (critic A6).
   Every row root freezes `experiments/final-batch-next/*.py`, the `lean_agent` harness files and
   `src/lean_agent/final60/{contracts,catalog,transport,ledger,money}.py`; editing any of them in
   that worktree stops **every** row at its next request. Only routing/golf/select/orchestrator
   modules may be hot-fixed there, followed by a supervisor restart.

   ```bash
   git -C "$REPO" worktree add "$PROD" <tagged-commit>
   ln -sfn "<shared sources folder>" "$PROD/sources"
   cp "<registry>" "$PROD/configs/final-environments.local.json"            # untracked
   mkdir -p "$PROD/benchmarks/arena/final-d53690b057f9"
   cp "<final jsonl>" "$PROD/benchmarks/arena/final-d53690b057f9/"           # SHA-256 is checked
   ```
2. The key file is a dotenv with `OPENROUTER_API_KEY=...`. Only the transport reads it
   (`--key-file`); never print or copy it.
3. Python 3.12 virtualenv; run every command from `$PROD` with `PYTHONPATH=src`.

## 1. Plan (no API, no Lean)

```bash
PYTHONPATH=src $PY -m lean_agent.final60 plan --run-dir "$RUN" \
    [--prepared-repo "<checkout with the newest registry>"] \
    --non-openrouter "<codex/team run trees>" ...
```

`--prepared-repo` names the checkout whose `configs/final-environments.local.json` registry is
newest (the environment stage updates its own checkout); readiness is read from it, while Lean
always runs from this checkout's `sources/`. Pass the same `--prepared-repo` to `run`.
Row workers prepend `<repo>/sources/final/bin` (the shipped bwrap) to `PATH` when it exists.

Writes `plan.json` (coverage per row, routes, priority order), `non-openrouter.jsonl` (every
known non-OpenRouter proof, flattened from nested dashboard JSON, `.lean` files and run states;
critic A3) and an all-original `submission.jsonl` with both checks. `same_sources: false` in the
output means the prepared repo and this checkout see different `sources/` folders: fix that first.

## 2. Dry run (no network, no spend)

Use a separate run dir; dry-run roots are sealed with `dry_run: true`, answered by the transport's
`MockOpenRouter` and never submitted.

```bash
PYTHONPATH=src $PY -m lean_agent.final60 run --run-dir "$RUN-dry" --dry-run --rows 11,12 --max-rows 2
```

## 3. Smoke (paid, small)

Run Smoke inside the final rows' own roots with the production code (critic A11), e.g.
`--rows 16 --max-rows 1 --exploration-minutes 5`, so the full run resumes those roots and every
call stays in their `ledger.json`. If any spend for a row happened outside its root, declare it:
`--prior-costs priors.json` with `{"F016": "0.12"}`; it is sealed into `final60.json`, lowers that
row's cap to `2.99 - prior`, and assembly passes it to the PR #70 checker as `prior_cost_usd`.

## 4. Launch

```bash
nohup setsid scripts/final60_supervise.sh "$RUN" --key-file "$KEY" --rows 1-60 \
    --max-rows 8 --compiler-slots 6 --deadline 2026-11-04T20:59:59+09:00 --soft-stop-min 100 \
    > "$RUN.watchdog.out" 2>&1 < /dev/null &
```

Set `FINAL60_PYTHON` to the virtualenv's python. The watchdog restarts the supervisor every 30 s
until it exits 0. Only one supervisor can hold `supervisor/supervisor.lock` (a second exits 3).
Row workers run in their own sessions and keep running if the supervisor dies; a restarted
supervisor adopts them through `rows/F0NN/worker.lock` and never starts a duplicate.

Defaults (all flags): `--max-rows 8`, `--compiler-slots 6` (2..8), `--mem-start-gib 10`
(new worker only above this MemAvailable), `--mem-reserve-gib 6` + `--gib-per-compile 3.5`
(absolute compile admission), `--exploration-minutes 75`, `--soft-stop-min 100`.
Exploration screens compile once (`screening: single-pass`, critic A7); preflight, all-version
compatibility and the fresh 3x final measurement keep full checks.

## 5. Monitor

```bash
PYTHONPATH=src $PY -m lean_agent.final60 status --run-dir "$RUN"      # frozen-code check first
tail -f "$RUN/supervisor/events.jsonl"; cat "$RUN/supervisor/status.json"
less "$RUN/supervisor/logs/F0NN.log"
```

Per row: `supervisor/rows/F0NN.json` (RowState), `supervisor/rows/F0NN.supervisor.json`
(crashes by phase, backoff), `rows/F0NN/worker-state.json`, `rows/F0NN/published.json`.
Crashes back off 60/180/600 s; 3 crashes while exploring switch the row to salvage (no API);
3 while preparing or in preflight publish the original; 8 in total publish the original.
A compiler-capacity or memory wait timeout exits 75 and is not counted as a crash.

## 6. Deadline

- deadline - 100 min: `<run-dir>/stop-exploration.json` (no new paid requests in any row).
- deadline - 60 min: final assembly every 10 min; no new rows are prepared.
- deadline - 20 min: last assembly, `SUBMIT-READY.txt`, no new workers.
- The user uploads `submission.jsonl` **once**, by 20:45 KST. The leaderboard keeps only the
  latest submission, so never upload an interim file after a better one (critic A18).

Manual assembly at any time (no Lean, no API): `... assemble --run-dir "$RUN" --final`.
Stop everything gracefully: `touch "$RUN/supervisor/STOP"` (workers finish their current step).

## 7. Outputs

`submission.jsonl`, `provenance-benchmark.jsonl` (name, statement, `reference=src`, required by
PR #70 for originals), `checks/rules.json`, `checks/provenance.json`, `report.json` / `report.md`
(per row origin, score estimate, calls, spend, served providers; totals, mean and max spend per
problem, models), `SUBMIT-READY.txt` (final only, last-validated time per row).
Scores in reports are local estimates, not official worker scores.

## Round 2 additions (see `docs/final-run.md` for the operator checklist)

- Assembly runs a third checker on every improved row: the verbatim Space intake filter
  (`rules.official_rejection`) plus `rules.check_static` from the golf component; a hit reverts
  the row to its original. The intake filter also runs over all 60 originals
  (`checks/official.json`); a rejected original marks `SUBMIT-READY.txt` as `DO NOT UPLOAD`.
- Routes assert that the primary (first listed) toolchain is the newest listed one; a failing row
  keeps its original and `plan.json` names the reason under `missing`.
- The row worker sets `ARENA_LEAN_MEMORY_MIB` per row (16384 for Mathlib-based sources, else 4096;
  `--lean-memory-mib` / `FINAL60_LEAN_MEMORY_MIB` override) and the evaluator passes it to Lean as
  `-M`. Lean aborts (exit -6, or 134 under bwrap) are diagnosed as the allocator limit, and such a
  failed preflight is set aside and retried.
- The supervisor sizes `--compiler-slots` down to what MemTotal holds (reserve + per-compile
  budget), logs lean RSS and MemAvailable to `supervisor/memory.jsonl` every
  `--memory-log-seconds` (30 s) and reports peaks in `status.json`.
- `<sources>/final/bin` (this checkout's and `--prepared-repo`'s) is prepended to `PATH` for the
  supervisor's children and in every row worker, so `shutil.which("bwrap")` finds the shipped sandbox.
- `--transport NAME` is passed through to row workers (`FINAL60_TRANSPORT` and `--transport`).
- `python -m lean_agent.final60 package --out code.zip [--repo R]` builds the code ZIP from tracked
  files and asserts that no `declaration-indexes`, `quarantine` or competitor artifact is packed.

## Component dependencies

- transport (`catalog`, `transport`, `ledger`, `money`, `experiments/final-batch-next/openrouter_transport.py`)
  is required to seal or run any row; without it only `plan`, `status` and `assemble` work.
  The driver uses: `catalog.spec_for_model(model)`, `ledger.CostLedger(path, cap_usd=)`
  (`open_attempts(run_root=)`, `recover(id, step_dir=, key=)`, `attempts(problem)`),
  `ledger.BudgetExceeded`, `money.dispatch_guarded(...)` returning `.normalized`, `.receipt`,
  `.http_calls` (optional `.sub_attempts`), `money.ApiDisabled` (optional `RowApiDisabled`,
  `RowApiFrozen`), `transport.MockOpenRouter(responder)` where the responder maps a request body
  to the assistant content string, and the adapter's `ENDPOINT`, `PRICING`, `payload`,
  `request_cost`, `load_key`, `audit_step`.
  `normalized["usage"]["cost"]` must equal the step's total charge; a mismatch freezes the row's API.
  A recovered lost step is saved as `response.json` `{"id": "lost-F0NN-SSSS", "final60_lost": true,
  "choices": [], "usage": {"cost": total}, "_cost_receipt": {...}}`; `audit_step` must accept it.
- routing: `route`, `route_json`, `prompt_addendum`, `schedule`, `default_route` (stub otherwise).
- golf: `evaladapter.EvalAdapter`, `golf.improve`, `select.candidates_from_run`, `select_final`,
  `write_selection` (otherwise the driver's own selection is kept). Golf screens may pass
  `screen_single_pass=True` to `FinalEvaluator.evaluate` for primary-only screens.
