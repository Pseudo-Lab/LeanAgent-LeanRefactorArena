# final60: the production run (operator checklist)

Companion to `docs/final60/RUNBOOK.md` (commands and flags). This page is the order of operations
for the one real run and what the user, not an agent, does by hand. Placeholders: `$REPO` (a
clone), `$PROD` (the run worktree), `$RUN` (the run directory), `$KEY` (the OpenRouter dotenv),
`$PY` (the virtualenv's python). No machine path is tracked anywhere.

## 1. A dedicated run worktree at a fixed commit

Every row root freezes the driver, the harness files and the money modules by hash. Editing any
frozen file in the worktree that rows run from stops those rows at their next request
(`Frozen input/implementation changed`). So production runs from its own worktree at one commit
that nobody edits, and every hot-fix goes to another checkout first.

```bash
COMMIT=<assembled final60 commit>
git -C "$REPO" worktree add "$PROD" "$COMMIT"            # detached, never a shared branch
git -C "$PROD" tag -f final60-run "$COMMIT"
ln -sfn "<shared sources folder>" "$PROD/sources"        # prepared environments; untracked
cp "<registry with all 60 rows>" "$PROD/configs/final-environments.local.json"
mkdir -p "$PROD/benchmarks/arena/final-d53690b057f9"
cp "<benchmark_data_final.jsonl>" "$PROD/benchmarks/arena/final-d53690b057f9/"   # SHA-256 is checked
cd "$PROD" && git status --short                         # must list only the untracked inputs above
```

Rules for the run worktree: no `git checkout`, `pull`, `merge` or editor in it until the final
upload is done; `status` reports `frozen_code_ok` first and a `false` there means a row root will
stop. Routing, golf, select and orchestrator modules are not frozen and may be hot-fixed, but
only through a new commit checked out in a *second* worktree, followed by a supervisor restart
there with the same `--run-dir` (rows resume from disk).

## 2. Machine preparation, WSL restart before launch (never during)

- `C:\Users\user\.wslconfig` holds the memory limit for WSL2 (`[wsl2] memory=46GB`, `swap=16GB`).
  It takes effect only after `wsl --shutdown`, which kills every Lean process, every environment
  build and every row worker. Restart WSL **before** the launch, at a quiet point agreed with the
  other agents, and never while the run is live.
- After the restart, confirm the limit and the sandbox before anything paid:
  `free -g` (total about 46 GiB), `ls "$PROD/sources/final/bin/bwrap"` (the shipped sandbox; row
  workers and the supervisor prepend `<sources>/final/bin` to `PATH`), and a dry run
  (`run --dry-run --rows 11,12 --max-rows 2` in a separate run dir).
- Stop every non-final60 Lean job (OpenAI dev runs, CI, integration checks). `ps -eo pid,rss,comm | grep lean`
  must show only final60 compiles once the run starts.
- Memory bound per compile: the evaluator passes `-M$ARENA_LEAN_MEMORY_MIB` to Lean. The row
  worker sets it per row: 16384 MiB for Mathlib-based sources (arklib, cslib, leanpool, physlib,
  putnambench; `import Mathlib` alone peaks near 6.1 GB RSS and aborts under the frozen 4096), 4096
  otherwise; `--lean-memory-mib N` or `FINAL60_LEAN_MEMORY_MIB` overrides every row. A Lean abort
  (exit -6, or 134 under bwrap) in a failed preflight is set aside and retried, never cached.
- Compiler slots: `--compiler-slots N` (2..8) is sized down to what MemTotal holds
  (`(MemTotal - mem-reserve-gib) / gib-per-compile`), and every compile is still admitted only when
  MemAvailable covers the reserve plus one more compile. `supervisor/memory.jsonl` logs lean RSS
  (sum, max, anonymous) and MemAvailable every `--memory-log-seconds` (30 s); `status.json`
  carries the last sample and the peaks. If the first hour's peak stays under about 60 % of
  MemTotal, restart the supervisor with a higher `--compiler-slots` (8 at most) and a smaller
  `--gib-per-compile` (about 2.5); rows resume from disk.
- `--transport NAME` is handed to row workers unchanged (`FINAL60_TRANSPORT` and `--transport`),
  for the transport component's variants; omit it for the default OpenRouter transport.

## 3. Launch, monitor, deadline

```bash
cd "$PROD"
PYTHONPATH=src $PY -m lean_agent.final60 plan --run-dir "$RUN" --prepared-repo "$PROD"   # 60 ready expected
nohup setsid scripts/final60_supervise.sh "$RUN" --key-file "$KEY" --rows 1-60 \
    --max-rows 8 --compiler-slots 6 --deadline 2026-11-04T20:59:59+09:00 --soft-stop-min 100 \
    > "$RUN.watchdog.out" 2>&1 < /dev/null &
PYTHONPATH=src $PY -m lean_agent.final60 status --run-dir "$RUN"
```

`plan` fails a route (the row keeps its original) when the primary toolchain, the first listed
one on which heartbeats are measured, is not the newest listed toolchain (research item 10a); the
plan entry names it under `missing`. The deadline actions (soft stop at -100 min, final assembly
every 10 min from -60 min, `SUBMIT-READY.txt` at -20 min) are automatic.

Every assembly runs three checkers on each improved row and reverts a failing row to its
original: PR #64 rules, PR #70 provenance, and the verbatim Space intake filter plus
`check_static` (golf `rules.py`, research item 3). The intake filter also runs over all 60
originals (`checks/official.json`); a rejected original cannot be reverted and would reject the
whole upload, so `SUBMIT-READY.txt` then says `DO NOT UPLOAD` and names the row. Measured on
2026-11-04: all 60 originals pass the filter and `check_static`.

## 4. Uploads (the user uploads; agents never do)

1. **Interim upload**, once rows 11-30 are `published` (about 12:00-14:00 KST): upload the rolling
   `$RUN/submission.jsonl` after a gate that passed (`report.json` `checks_passed: true`). The
   other rows hold their originals (33.33 each, never 0). Read "My submissions" per row: zero-shot
   n/m, length and heartbeats as "N of ref", and any error text; keep the page text under
   `$RUN/official/interim-<time>.txt` for the calibration comparison (item 10b).
2. **Final upload** at 19:30-19:45 KST from `SUBMIT-READY.txt` (written at deadline - 20 min, or by
   `assemble --final` by hand). Upload only when it is at least as good as the interim file on
   every row; the leaderboard keeps only the latest submission.
3. At most **one later upload**, only if it gains at least 0.3 and is never worse on any row; not
   after 20:15 KST and never after 20:45 KST (queue limits: 2 pending per user, 60 s cooldown).
4. **Code ZIP**, before 20:59:59 KST under the same username:
   `PYTHONPATH=src $PY -m lean_agent.final60 package --out "$RUN/code.zip" --repo "$PROD"`.
   It packs tracked files only, needs a top-level README, refuses symlinks and secret-looking
   content, leaves out `declaration-indexes/`, `quarantine/` and competitor artifacts, and asserts
   the ZIP listing is clean (`code.zip.manifest.json` lists what was left out).

## 5. The report (four sections, written after the final upload)

`report.json` / `report.md` from the final assembly are the source; the written report has exactly
these sections, each with measured numbers marked as measured and estimates as estimates:

1. **Submission and checks**: submission sha256, rows improved vs original, the three checkers'
   results, `checks/official.json`, the upload times and what "My submissions" showed.
2. **Money**: total, mean and max spend per problem from the per-row `ledger.json` and the SQLite
   mirror (every call, including retries and discarded candidates), prior spend declared, the
   cap (2.99), and the provenance-checker verdict.
3. **Per-row outcomes**: origin, local score estimate vs official value where known, toolchains
   compiled, lean memory bound, golf acceptances, stop reason; rows that fell back and why.
4. **Failures and logs**: every environment, compile, transport or supervisor failure with the log
   path (`supervisor/events.jsonl`, `supervisor/logs/F0NN.log`, `supervisor/memory.jsonl`, the row
   root), what was retried, and what remains open.
