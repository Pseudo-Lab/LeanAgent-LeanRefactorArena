# PseudoLab LeanAgent — Lean Refactor Arena

Final60 inference code for the closed-source LLM track. This archive contains the harness,
prompts, evaluator adapters, submission checks and fixed environment pins. Proof JSONL is a
separate submission; the commands below generate a new 60-row `submission.jsonl` from a fresh run.
Use the source in this archive rather than checking out an older release tag.

## Model and budget

- All submitted model calls use OpenRouter: `--transport openrouter`. OpenAI-direct and mock
  transports are development modes and their outputs are refused by final assembly.
- Model: `openai/gpt-6.1-sol`, provider `openai` only, no fallback, reasoning effort `high`,
  `max_tokens: 8192`, seed 42, timeout 900 seconds, non-streaming JSON mode. Every role uses the
  same model unless an explicit alternative is selected. The commands below use the defaults.
- Hard limit: **US$2.99 per problem**, including retries, discarded candidates and declared prior
  spend. Each request reserves its worst-case cost before dispatch. The charge is the greater
  of OpenRouter's reported cost and the list-price cost of returned usage; an unresolved lost
  response is charged conservatively at its reservation bound.
- Fixed seeds do not make API sampling deterministic. Repeated runs can produce different proofs.

## Warm-up material and archive contents

The built-in warm-up strategy bank, its loader and its prompt-injection path have been removed.
`route_rules.json` keeps `hints.bank_cards: 0`; the old warm-up bank format is not accepted through
`--bank`. There is no instruction to consult warm-up solutions or skills in the final60 prompt.
New runs start cold, without previous solutions, seeds or carried proofs. Generic playbooks and
lessons derived from this run's own validated OpenRouter winners remain available.

The code ZIP uses an explicit runtime file list. It excludes `skills/`, `solutions/`, `dashboard/`,
`submissions/`, `runs/`, historical experiments, warm-up bank copies and local credentials.
The benchmark and prepared Lean environments are supplied by the organizers and are not bundled.
The archive includes the final60 driver, token counter, checkers, pins, operating instructions and
runtime tests. A ZIP manifest alongside the archive records the source commit, excluded paths and
archive SHA-256.

rc5 disabled warm-up bank cards by setting `bank_cards` to zero. This archive also removes the
underlying data and code. These changes apply to newly prepared inputs: previously sealed run
inputs and their stored prompts are not rewritten. Before reusing an earlier run's results,
inspect its saved `input/route.json` and request prompts for `warmup-bank:` sources.

## Requirements

- Linux x86_64 with bubblewrap (`bwrap`) on `PATH` or set through `ARENA_BWRAP`.
- Python 3.12 or newer; the runtime uses the standard library only. Git and zstd are needed for
  source and environment operations.
- Prepared Lean toolchains v4.26.0, v4.27.0, v4.30.0, v4.31.0, v4.33.1, v4.34.0, v4.34.1 and
  v4.35.0-rc3. The fixed source revisions are in `configs/final-environments.lock.json`:
  17 environments, six source libraries and 127 problem-version pairs.
- About 100 GB for the prepared environments and at least 32 GiB of memory. The documented
  production machine was Windows 11 / WSL2 Ubuntu 24.04.2, x86_64, 28 threads, about 45 GiB memory.

## Connect the organizer-provided inputs

The ZIP delivers code only. Use the final benchmark JSONL and the organizer-provided Lean
installations. `PREPARED` below is the prepared environment root, which must expose this layout:

```text
$PREPARED/
  configs/final-environments.local.json
  sources/final/
    problems/F001.json ... F060.json
    environments/<environment-id>/environment.json
    checkouts/...
    toolchains/<version>/bin/lean
```

The local registry and environment manifests must describe the paths on the reproduction machine;
copying manifests with absolute paths from a different machine is insufficient. Use the source
revisions in the lock file and the Linux toolchains on Linux. The dataset SHA-256 must be
`d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`; the harness checks it.

In a freshly unpacked archive, set the following absolute paths to the supplied inputs and your
chosen interpreter. `RUN` must be a new directory outside the unpacked code. `KEY` is a dotenv
file outside the code containing `OPENROUTER_API_KEY=...`. Use a normal OpenRouter API key.

```bash
cd LeanAgent-LeanRefactorArena
export PY=/absolute/path/to/python3.12
export PREPARED=/absolute/path/to/prepared-environment
export DATASET=/absolute/path/to/benchmark_data_final.jsonl
export RUN=/absolute/path/to/new-final60-run
export KEY=/absolute/path/to/openrouter.env
export DEADLINE=2026-11-05T20:59:59+09:00  # replace with a future time for reproduction
export PYTHONPATH="$PWD/src" FINAL60_PYTHON="$PY"

# Link the provided environments and machine-local registry; do not overwrite existing inputs.
ln -s "$PREPARED/sources" sources
ln -s "$PREPARED/configs/final-environments.local.json" configs/final-environments.local.json
```

The links are created after extraction and are not shipped in the ZIP. The environment root
must already contain the per-problem metadata, compiled projects and registry shown above.
`plan` checks coverage; it does not download the benchmark, install Lean or prepare missing metadata.

## Run and assemble

```bash
# 1. Check coverage and routes without model calls or Lean compilation.
"$PY" -B -m lean_agent.final60 plan --run-dir "$RUN" --dataset "$DATASET" \
  --prepared-repo "$PREPARED"
# Inspect $RUN/plan.json: all 60 rows must have ready environments before the paid run.

# 2. Free endpoint and key checks.
"$PY" -B experiments/final-batch-next/openrouter_transport.py key-status --key-file "$KEY"
"$PY" -B experiments/final-batch-next/openrouter_transport.py endpoint-check

# 3. Run all 60 rows. Use bash because archive file permissions are 0644.
bash scripts/final60_supervise.sh "$RUN" --key-file "$KEY" --dataset "$DATASET" \
  --prepared-repo "$PREPARED" --rows 1-60 --transport openrouter \
  --deadline "$DEADLINE" --lean-memory-mib 16384

# 4. Inspect state and create the final proof JSONL.
"$PY" -B -m lean_agent.final60 status --run-dir "$RUN"
"$PY" -B -m lean_agent.final60 assemble --run-dir "$RUN" --dataset "$DATASET" --final
```

The watchdog runs in the foreground and restarts the supervisor after a recoverable failure.
Stop gracefully with `touch "$RUN/supervisor/STOP"`. Use a future deadline for a later reproduction:
the historical competition deadline is the code default. The supervisor stops new paid work
before the deadline to leave time for selection and final checks.

## Per-problem settings

All rows use the same launch command. Routes depend on the statement, original proof, source,
size and listed Lean versions. The commands above use the default prompts.

| Setting | Rows or condition | Effect |
| --- | --- | --- |
| `priority.weak_rows` | Empty (`[]`) | No row-number-specific priority boost. Older row lists derived from earlier final runs are not used. |
| `kernel-decide-tiny` | Classified from the supplied original proof | API-free golf; no LLM calls. |
| `competition` | PutnamBench | Fixed scout/merger evaluation counts; other types can continue the merger within budget. |
| `--lean-memory-mib 16384` | All rows in the command above | Same Lean allocator limit for each row. |

The actual route, prompt and options for each row are saved under
`$RUN/rows/F0NN/problems/F0NN/input/` and in `$RUN/run-options.json`. Reruns or additional golf passes
must be documented from their own records, including any prior spend; they are not implied by the
fresh-run command above.

## Outputs and final checks

- `$RUN/submission.jsonl`: 60 rows. An improved proof is used only when the selected proof and
  report hashes agree, its OpenRouter run audit passes, its spend is within the cap, and the rules,
  provenance and compatibility checks accept it. Otherwise the row keeps the supplied original.
- `$RUN/report.json` and `report.md`: per-row origin, calls, spend and local score estimates.
- `$RUN/checks/rules.json`, `provenance.json` and `official.json`: submission check results.
- `$RUN/SUBMIT-READY.txt`: final assembly timestamp, submitted file hash and readiness summary.

Before upload, check `report.json` has `checks_passed: true`, that there are 60 unique theorem
names, and that the SHA-256 of the exact uploaded file matches `submission_sha256` in the report.
A code cleanup does not certify an independently assembled or historical proof JSONL.

## Offline tests and code ZIP

```bash
# Runtime tests, without paid API calls. Some tests require local Lean inputs and may skip.
"$PY" -B -m unittest discover -s tests -p 'test_final60_*.py'
"$PY" -B -m unittest discover -s experiments/final-batch-next -p 'test_*.py'

# Build the code archive from a Git checkout; this command needs the repository index.
"$PY" -B -m lean_agent.final60 package --repo . --name LeanAgent-LeanRefactorArena \
  --out /absolute/path/to/code.zip
```

The unpacked ZIP does not require Git metadata for inference. Rebuilding a ZIP with `package`
requires a Git checkout. The technical report is submitted separately on OpenReview; names,
affiliations and contact information belong in that report.
