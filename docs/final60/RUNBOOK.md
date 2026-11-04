# final60 runbook

One autonomous, resumable run over all 60 final problems through OpenRouter only.
Entry point: `python -m lean_agent.final60 {plan,run,row,status,assemble,package,regolf}` from the repository
root with `PYTHONPATH=src`. Paths below are placeholders (`$REPO`, `$RUN`, `$KEY`, `$PY`); the harness
reads no machine-specific path (historical record files under `experiments/` keep the paths of the
machines that produced them). Linux uses the bwrap sandbox and macOS uses sandbox-exec, both unchanged.

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

1. Production runs from a dedicated worktree at a tagged commit that no agent edits (critic A6); the
   production tag is `final60-rc4` (see the hot-fix track section below).
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
nohup scripts/final60_supervise.sh "$RUN" --key-file "$KEY" --rows 1-60 \
    --max-rows 8 --compiler-slots 6 --deadline 2026-11-04T20:59:59+09:00 --soft-stop-min 100 \
    --lean-memory-mib 16384 \
    > "$RUN.watchdog.out" 2>&1 < /dev/null &     # Linux: setsid optional; macOS has none
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
- Uploads follow `docs/final-run.md` section 4 (interim, final, at most one later upload, none
  after 20:45 KST). The leaderboard keeps only the latest submission, so never upload an interim
  file after a better one (critic A18).

Manual assembly at any time (no Lean, no API): `... assemble --run-dir "$RUN" --final`.
Stop everything gracefully: `touch "$RUN/supervisor/STOP"` (workers finish their current step).

### Second golf pass over published rows (`regolf`, hot-fix track)

```bash
PYTHONPATH=src $PY -m lean_agent.final60 regolf --run-dir "$RUN" --rows 11-30 --report-only   # eligibility only
PYTHONPATH=src $PY -m lean_agent.final60 regolf --run-dir "$RUN" --rows 11-30 [--compiles 24] [--margin 0.25]
```

No API call, no transport import. Only terminal rows whose `published.json` is a model-produced
publication (`origin: openrouter-run` of a submittable OpenRouter root) are considered; a row whose
worker holds `worker.lock` is skipped. Under the lock the pass checks the frozen code, golfs the
incumbent `selected.lean` with the normal passes (`--compiles` screens, cached by content), runs
`select_final` over incumbent + winners (all versions, fresh 3x) and only when the validated estimate
beats the published one by `--margin` points writes `selected.lean`/`final/`/`summary.json`, rebuilds
`report.json` and rewrites `published.json` last (rolled back the same way if the rebuilt audit
disagrees). Records: `rows/F0NN/regolf/*.json`, the `regolf` list in `worker-state.json`, the usual
`golf/` evidence, and `published.json` `regolf` (previous sha and estimate). `--allow-dev-roots`
(mock/OpenAI-direct roots) is for testing on copies only. Run it from the hot-fix worktree while idle
compile slots exist. Operator rules (from the rc3 verification findings, 2026-11-04):

- Run it only after the rows it targets (and their neighbours) are terminal: its `--compiles` screens
  (24 per row) compete for the shared 8-slot pool with live rows whose validations are deadline-bounded.
  While more than 8 rows are live, use `--compiler-slots 2` to `4` (or `--compiles 8` to `12`). Regolf
  holds the row's `worker.lock`, so the supervisor counts one row slot as live while it runs and logs a
  `worker_exit` with code None (no alert) when the lock is released; both are expected.
- Do not start regolf rows after 19:30 KST: its own guard stops at deadline - 28 min, but the top
  validation always completes, so a late row can write during the last assembly.
- Never kill a regolf process (`idle.sh` lists it as BUSY; let it finish the row). A kill between
  `write_selection` and `published.json` leaves `selected.lean` != `published.json`; the assembler then
  reports `changed after publication` and carries the ORIGINAL for that row. The next regolf pass on that
  row repairs this first (restores the published proof from its kept `final-prev-<sha12>-*` evidence,
  rebuilds `report.json`, rewrites `published.json`; record action `repaired`). After any crash or reboot:
  `regolf --rows 1-60 --report-only` (such rows show `interrupted: true` and `repairable`), then
  `regolf --rows <those> --repair-only` (no golf, no Lean beyond the kept evidence), then grep
  `report.json` for `changed after publication` before any upload.
- The rolling assembly re-runs only when the SET of published rows changes, so a regolf publication is
  not in `submission.jsonl` / `SUBMIT-READY.txt` until the next assembly. After regolf finishes, run
  `python -m lean_agent.final60 assemble --run-dir "$RUN" --final` (then the two checkers) before any
  upload, and never take an upload copy while a regolf process is running (inside its write window the
  assembler carries the original for that row).
- Golf (first pass and regolf) runs only the passes in the row's route (`route_rules.json` `golf.passes`:
  default `G1,G2,G3,G3s[,G4]` since rc4, tiny kernel-decide rows `G5,G3`). G5/G6/G2s/G4h do not run on
  default routes unless listed there (rc2 ran every pass on every row; on 53 rc2 records no accepted edit
  came from a pass outside the route list, measured). A row keeps the pass list sealed in its
  `input/route.json`, and regolf reads that same list (`regolf.golf_settings`), so a row routed before the
  rc4 switch never runs G3s; only rows prepared from a rc4 checkout do.

### Transfer repair (deprecated-alias renames; `transfer.py`, hot-fix 2026-11-04)

A candidate that compiles on the first-listed toolchain but fails an older listed toolchain
only with unknown identifiers that the newer pinned library maps through
`@[deprecated] alias OLD := NEW` (rehearsal F036: `Finset.card_univ_sdiff` -> `Finset.card_univ_diff`,
token-neutral, 84.21 -> 89.22 measured) is repaired automatically, without any API call:

* `select_final` reads the failing toolchain's saved `compatibility/<sha>/<env>/check.log`; when
  every unknown-identifier/unknown-constant error names a key of the row's alias map, the repaired
  text (`repair:<parent label>`, origin `golf`, parent sha, edit list in `golf/selection.json`
  `repairs` and `golf/winners.json`) is validated like any finalist (at most 2 per selection).
* Golf never spends its budget on a parent whose saved all-version check failed
  (`compatibility/<sha>/skipped.json` or an invalid result): its repair is validated first and
  golfed instead when it holds (`select.golf_parents`, at most 1 validation per row,
  `transfer.MAX_REPAIRS_PARENTS`); an unrepaired parent is left out of golf and select_final can
  still repair it from its cached failure.
* Time bound (fix 2026-11-04): a repair validation is never started unless
  `transfer.validation_reserve` seconds remain before the phase deadline (the golf/selection
  deadline of the row worker, `golf_deadline` of `finalize_row`, the regolf deadline):
  max(480 s, 2 x slowest baseline compile x (listed toolchains + 3)), `FINAL60_REPAIR_RESERVE_S`
  overrides (ArkLib F036 measured: 19 s compiles -> 480 s; one repair validation = 8 compiles /
  268 s wall at 2 slots). In select_final a repair starts only before the phase deadline, like
  any finalist validation. Combined per-row bound inside the worker: 1 (golf_parents) + 2
  (select_final) = 3 repair validations of about (toolchains + 3) compiles each (cached checks
  excluded), and none after the phase deadline.
* Rejected before any compile: a text that still names a renamed lemma after the rewrite
  (spellings handled: full name, suffix under an open namespace, dot notation on a lowercase
  term, each with projections such as `.symm`/`.mp`; `Set.card_univ_sdiff` of another namespace
  is left alone), a repair equal to the original proof, static/official rule failures. A
  malformed `configs/final-environments.local.json` blocks repairs (fail closed) instead of
  failing the selection; `unknown identifier 'card_univ_sdiff'` (suffix spelling) resolves to
  the unique map key ending in that name.
* Alias maps (NEW -> OLD, kept only when OLD is declared in every other listed toolchain and NEW
  is missing in at least one) are built once per environment set from the prepared sources
  (project + `.lake/packages`, 6-14 s) and cached under `<run>/alias-maps/`
  (`FINAL60_ALIAS_MAP_DIR` overrides). Measured 2026-11-04: ArkLib v4.31.0/v4.30.0 598 pairs,
  CSLib v4.34.1 -> v4.31.0 1020 / -> v4.33.1 302, PutnamBench 398, LeanPool and PhysLib 0.
* Never on Strata rows (its v4.31.0 lakefile sets `warningAsError`, read from the checkout) or
  under a warning gate other than `off` (`FINAL60_WARNING_GATE`): the deprecation warning would
  break the build.

Post-hoc, for terminal rows (model proofs and worker publications of the original alike):

```bash
PYTHONPATH=src $PY -m lean_agent.final60 regolf --run-dir "$RUN" --rows 31-40 --transfer-repair [--repairs 3] [--margin 0.25]
```

re-examines the recorded candidates that failed only non-primary toolchains, repairs and validates
them (`--repairs` validations per row) and publishes through the regolf path when the validated
estimate beats the published one by `--margin`. A later plain `regolf` golfs the repaired incumbent.

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


## Hot-fix track since rc2 (2026-11-04; production tag `final60-rc4`)

Tags: `final60-rc2` (01f8c703, the verified base), `final60-rc3-hotfix` (rc2 + the first hot fixes),
`final60-rc4` (rc3 + transfer repair + G3s on the default route; the production tag). The 68 frozen
implementation files (`driver.implementation_files(final60=True)`: the `lean_agent` core, the
`experiments/final-batch-next/*.py` driver, `proof_tokens.py`, `final60/{contracts,catalog,transport,ledger,money}.py`)
are byte-identical across the three tags (measured at rc4: 68/68 sha256 equal, `git diff --stat final60-rc2`
over those paths empty), so a live run switches code without a new run dir: `touch "$RUN/supervisor/STOP"`,
wait until the watchdog has exited and no `lean_agent.final60 row` process remains, check the new tag out
in the production worktree, remove `STOP`, start the same launch line; every row resumes from disk and its
`frozen.json` check passes. What each behaviour adds and where it shows in the run directory:

| Added | Behaviour | Where it shows |
| --- | --- | --- |
| rc3 | Exploration wall-clock timer: the row exploration clock polls `time.time()` (the WSL2 monotonic clock ran about 7% slow; measured 43-46 s late per 600 s) | `rows/F0NN/stop-exploration.json` (`reason: row exploration clock`), `exploration_started_at` in `rows/F0NN/worker-state.json` |
| rc3 | Alternates: a checker-rejected publication is replaced by the row's next validated runner-up before the original; gated runners-up rank last; evidence is served from `final-prev-<sha12>-*` once `final/` was replaced | `published.json` `alternate`, `rows/F0NN/alternates.json`, `alternates_used` in `report.json` of the assembly, `golf/selection.json` `alternates` |
| rc3/rc4 | Golf passes G3s (sugar) and G4h (hint ddmin) exist; rc4 enables G3s on every default route right after G3 (measured gains on real proofs: F018 +0.24, F027 +0.18, F035 +0.22, F048 +0.47; G4h gained nothing and stays off); G4h/G6/G2s are valid route names enabled nowhere | `input/route.json` `golf.passes`, `golf/improve-*.json` `settings.passes` and `G3s:*` log entries, `worker-state.json` `golf.accepted` |
| rc3 | `regolf`: second API-free golf pass over published rows; repairs a publication interrupted between `write_selection` and `published.json` (`--repair-only`) | `rows/F0NN/regolf/*.json`, `regolf` list in `worker-state.json`, `published.json` `regolf` |
| rc4 | Transfer repair of deprecated-alias renames (`transfer.py`): in `select_final`, for the golf parents (`select.golf_parents`), post-hoc `regolf --transfer-repair`; bounded by the phase deadline | `golf/selection.json` `repairs`, `repair:*` entries in `golf/winners.json`, `golf-parents` records in `golf/events.jsonl`, `<run>/alias-maps/`, `rows/F0NN/regolf/*.json` `mode: transfer-repair` |
| ops | `--lean-memory-mib 16384` in the launch line (a Strata candidate of F004 aborted the Lean allocator under `-M4096`/`-M8192` and crashed the worker; under `-M16384` an ordinary compile failure, measured) | `run-options.json` `lean_memory_mib`, `environment.lean_memory_mib` in `rows/F0NN/worker-state.json` |

Golf compile budgets are unchanged by rc4 (`original_compiles 4`, best 8, other 4, row 12): G3s costs about
one compile per batch (token sugar, bullet flattening, `.intro`; a failing batch splits in halves). On the
60-row rc2 rehearsal records (measured) the best candidate had used a mean 3.08 compiles for probes + G1 +
G2 + G3, leaving a median 5 (at least 3 in 55 of 60 sessions) of its 8 for G3s and G4.

## Component dependencies

- transport (`catalog`, `transport`, `ledger`, `money`, `experiments/final-batch-next/openrouter_transport.py`)
  is required to seal or run any row; without it only `plan`, `status` and `assemble` work.
  The driver uses: `catalog.spec_for_model(model)`, `ledger.CostLedger(path, cap_usd=)`
  (`open_attempts(run_root=)`, `recover(id, step_dir=, key=)`, `attempts(problem)`),
  `ledger.BudgetExceeded`, `money.dispatch_guarded(...)` returning `.normalized`, `.receipt`,
  `.http_calls` (optional `.sub_attempts`), `money.ApiDisabled` (optional `RowApiDisabled`,
  `RowApiFrozen`), `transport.MockOpenRouter(responder)` where the responder is a str, a list
  (one outcome per call) or a callable `(body, spec, index) -> content | raw response dict | exception`,
  and the adapter's `ENDPOINT`, `PRICING`, `payload`,
  `request_cost`, `load_key`, `audit_step`.
  `normalized["usage"]["cost"]` must equal the step's total charge; a mismatch freezes the row's API.
  A recovered lost step is saved as `response.json` `{"id": "lost-F0NN-SSSS", "final60_lost": true,
  "choices": [], "usage": {"cost": total}, "_cost_receipt": {...}}`; `audit_step` must accept it.
- routing: `route`, `route_json`, `prompt_addendum`, `schedule`, `default_route` (stub otherwise).
- golf: `evaladapter.EvalAdapter`, `golf.improve`, `select.candidates_from_run`, `select_final`,
  `write_selection` (otherwise the driver's own selection is kept). Golf screens may pass
  `screen_single_pass=True` to `FinalEvaluator.evaluate` for primary-only screens.
