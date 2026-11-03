# Main scout → merger: single-run results and best-record archive

The submitted artifact is a harness. Its measured mean is **75.124957**, compared with the earlier single-run **74.123456**. The dashboard combines the best proof per problem across runs and averages **76.863606** for these 20; that number is not the performance of one executable harness.

All 20 problems terminated and passed final required-version checks and fresh 3 primary HB samples. Ten reached 40 candidate evaluations; ten stopped before a worst-case next API reservation could cross the strict per-problem cap. Raw provider receipts and all evidence hashes passed audit. Combined cost **USD44.8076882**, including initial failed exploratory calls USD5.1492053; continuation cost USD39.6584829. There were 282 initial calls and 1339 continuation calls; all settled. Costs are usage×frozen prices, not invoice verified.

Policy: `gpt-6.1-sol`, high reasoning, seed 42; three scouts×6, merger 22; bounded-v1 research guard. PR67 rounds/merger-until-budget were NOT enabled. This is not a matched comparison with the older run: prior failed-call expenses reduce F001/F002/F041 budgets. PR69 pilot is separate and excluded. No model or Lean calls were added to create this export.

## Scout / merger observations

| Stage | API calls | Evaluated candidates | Valid candidates | Valid / evaluated |
|---|---:|---:|---:|---:|
| scout-a | 278 | 119 | 57 | 47.9% |
| scout-b | 189 | 117 | 79 | 67.5% |
| scout-c | 196 | 111 | 71 | 64.0% |
| merge | 676 | 343 | 236 | 68.8% |

Valid here means the candidate passed the primary-version evaluation; final selected proofs separately pass every required version. Tool calls do not count as candidate evaluations. Stage order gives scouts first access to easy gains, so observed stage improvements do not isolate causal effectiveness.

- [Interactive per-call score graphs](../../dashboard/public/reports/scout20.html): API-call or spend axis, problem filtering; distinguishes provisional trajectories from final verified endpoints.
- [Exact result/evidence summaries](results.json), [prior dashboard selection](prior-dashboard.json).
- [All 20 proofs produced by this run](../../solutions/main-scout20/).
- [Best-of-run archive](../../solutions/final20/): replaces only F006/F008/F042/F044/F046/F048/F049/F050, retaining 12 stronger incumbents. Each uses its own paired baseline and unchanged tokenizer/environment fingerprints.

Reproduce the read-only export with `dashboard/scripts/export_scout20.py --current <parallel-r3> --historical <historical runs> --repo <checkout>`. Full private API/source logs remain in local run archives; public summaries contain hashes rather than private machine paths or transcripts. Initial code snapshot is PR66; execution scheduling continues under the audited PR68 pool. Freeze/migration manifests remain local. No automatic merge or official submission occurred.

Regenerate the standalone HTML after exporting: `python dashboard/scripts/render_scout20.py --repo <checkout>`.
