# Structure and repair prompt pilot

This pilot compares `baseline` with `structure-repair-v1` on F002, F007, F009,
F041, F048 and F049. The user authorized **$12 total**, at most **$1 per problem
per arm**. There is one trajectory per arm/problem; this is exploratory evidence,
not a statistically powered benchmark. The cohort was chosen from prior results
to cover repeated retrieval, late gains, early structural gains and difficult
dependent proofs. It is not an unbiased sample of the final60.

The treatment makes the optimization loop explicit: identify repeated proof
work, propose one structural hypothesis, inspect only a concrete missing bridge,
preserve working branches during local repair, reconsider repeated obstructions
without new evidence, and judge length and HB together. It adds no problem IDs,
known solutions or problem-specific hints. The JSON protocol remains unchanged.

The coordinator explicitly selects single-context (`portfolio_settings=None`)
preparation for both arms, independent of the Final runner's scout/merger default.
Both arms use the same verified historical-best source, original scoring
baseline, corpus, persistent action memory, model, seed, output limit and Lean
verifier. Thus the control is the current warm-start/memory harness, not the old
cold-start $3 run. The only intentional model-input difference is the optimization
guidance text. Larger treatment input is included in its actual cost.

`prepare` snapshots the current harness and its checked-in fast inventory verifier
into the run's private `runtime/`, including its Lean namespace qualification fixes.
The completed pilot used its earlier sealed runtime; its source hashes are retained
in the published `experiment-frozen.json`. New preparations snapshot the reviewed
checkout, and do not modify or recreate that historical runtime. Environment sources/toolchains are read through
the existing prepared checkout; their definitions and old runs are not modified.
The snapshot, prompt policy, configuration and inputs are sealed before dispatch.
Execute the copied coordinator for preflight/run/report so later working-tree
edits cannot change an active experiment.

`preflight` freshly measures the original and historical seed and checks required
versions using the control arm. It copies only this initial verification evidence
to treatment before any paid call, giving exactly identical paired starting
states. The reuse is recorded in `shared-preflight.json`. Each trial still checks
full environment content at its boundaries and performs independent three-sample
final measurement. Model trajectories and exploration caches are not shared.

Two problem workers share the existing serial Lean lock and 15% free-memory gate.
Pair order alternates control/treatment and treatment/control by problem. Every
new model request checks both arms for unresolved billing. A failure stops further
dispatch and queued trials; no automatic paid retries or termination of in-flight
requests. A second coordinator is excluded by a lock. Strict reservation checks
run before dispatch and again under the ledger lock. The final report reconstructs
the rejected next request to audit each under-cap budget stop.

Commands (only `run` makes paid API calls):

```sh
python3 -B experiments/prompt-ab/run_comparison.py prepare \
  --root runs/prompt-ab/NEW-RUN --environment-repo /path/to/prepared-runtime
python3 -B runs/prompt-ab/NEW-RUN/runtime/experiments/prompt-ab/run_comparison.py preflight \
  --root runs/prompt-ab/NEW-RUN
python3 -B runs/prompt-ab/NEW-RUN/runtime/experiments/prompt-ab/run_comparison.py run \
  --root runs/prompt-ab/NEW-RUN --key-file /path/to/authorized/.env
python3 -B runs/prompt-ab/NEW-RUN/runtime/experiments/prompt-ab/run_comparison.py report \
  --root runs/prompt-ab/NEW-RUN
```

Primary endpoint: paired final combined-score improvement over the shared seed.
Secondary endpoints: settled cost, unique valid candidates, repeated lookup calls,
and cost at first exploratory improvement. Same-source final HB fluctuations are
reported as measurement differences but not counted as a new-proof improvement.
Final per-arm receipt/proof audits must pass before comparison is published.
No automatic official submission, dashboard replacement or PR merge is performed.

After completion, the separate read-only timing analysis excludes shared
preflight work and historical compiler time attached to cache hits:

```sh
python3 -B experiments/prompt-ab/analyze_timings.py runs/prompt-ab/NEW-RUN \
  > runs/prompt-ab/NEW-RUN/timings.json
python3 -B experiments/prompt-ab/analyze_trajectories.py runs/prompt-ab/NEW-RUN \
  > runs/prompt-ab/NEW-RUN/trajectories.json
```

API, compiler and lock-wait durations are sums over workers; do not add them
across simultaneous trials and call that experiment wall time.
Trajectory analysis records the action and cost at each new best source, exact
duplicate candidates, rejected actions, and valid candidates that did not improve
the incumbent. Exploration scores are single-sample; final outcomes use fresh
three-sample verification.

The completed 2026-11-03 pilot report is in
[pilot report](results/20261103-structure-repair-usd12-r1/REPORT.md).
All 12 trials passed audit at $9.1743265 total. The treatment's paired mean gain
over control was +0.166 points, with substantial differences by problem; it
remains an opt-in variant rather than replacing the baseline default.
