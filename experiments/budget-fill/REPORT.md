# Budget-fill pilot results

Six authorized trials are terminal and audited. Portfolio quota completion remains a separate outcome; no trial was retried or relabeled to hide an incomplete scout.

Total settled model cost: **$16.7266868** (cap $18). Completed portfolios: 4; verified stopped portfolios: 2. Costs use provider usage and frozen public prices, not a verified invoice.

| Problem | Arm | Cost | Score | Status | Reduced calls | Tail cost | Selected source first created in tail |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| F006 | adaptive | $2.841431 | 66.334389 | completed | 2 | $0.069602 | False |
| F006 | control | $2.755256 | 59.372448 | completed | 0 | $0 | False |
| F045 | adaptive | $2.839130 | 49.650753 | completed | 1 | $0.05496 | False |
| F045 | control | $2.790792 | 51.108443 | completed | 0 | $0 | False |
| F048 | adaptive | $2.8313790 | 44.162572 | stopped | 3 | $0.1752898 | False |
| F048 | control | $2.6686988 | 47.902344 | stopped | 0 | $0 | False |

## Interpretation

The observed paired mean score difference is +0.588160 points. This is one stochastic trajectory per arm/problem, so the difference does not isolate the output policy. More spending is not itself a score improvement.

Tail attribution below compares the selected source with the incumbent immediately before output reduction. A same-source result has zero additional selected-proof gain; changed-source deltas use primary screening measurements and are not a remeasured counterfactual.

- F006: 2 reduced-output calls; additional tail cost $0.069602; incremental selected primary-screening score delta +0.000000. Selected proof first created in the tail: False.
- F045: 1 reduced-output calls; additional tail cost $0.05496; incremental selected primary-screening score delta +0.000000. Selected proof first created in the tail: False.
- F048: 3 reduced-output calls; additional tail cost $0.1752898; incremental selected primary-screening score delta +0.000000. Selected proof first created in the tail: False.

## Stops and verification

- adaptive/F006: saved `completed/portfolio_budget_complete`; next policy reservation $0.22742 exceeds remaining $0.158569; scout exits `{'scout-a': 'quota', 'scout-b': 'quota', 'scout-c': 'quota'}`. Required versions: strata-v4.27.0, strata-v4.31.0. Truncations 0, invalid JSON 0.
- control/F006: saved `completed/portfolio_budget_complete`; next policy reservation $0.2558775 exceeds remaining $0.244744; scout exits `{'scout-a': 'quota', 'scout-b': 'quota', 'scout-c': 'quota'}`. Required versions: strata-v4.27.0, strata-v4.31.0. Truncations 0, invalid JSON 0.
- adaptive/F045: saved `completed/portfolio_budget_complete`; next policy reservation $0.2556225 exceeds remaining $0.160870; scout exits `{'scout-a': 'quota', 'scout-b': 'quota', 'scout-c': 'quota'}`. Required versions: leanpool-v4.34.0, leanpool-v4.35.0-rc3. Truncations 0, invalid JSON 0.
- control/F045: saved `completed/portfolio_budget_complete`; next policy reservation $0.25337 exceeds remaining $0.209208; scout exits `{'scout-a': 'quota', 'scout-b': 'quota', 'scout-c': 'quota'}`. Required versions: leanpool-v4.34.0, leanpool-v4.35.0-rc3. Truncations 0, invalid JSON 0.
- adaptive/F048: saved `stopped/cost_limit`; next policy reservation $0.365585 exceeds remaining $0.1686210; scout exits `{'scout-a': 'call_limit', 'scout-b': 'quota', 'scout-c': 'quota'}`. Required versions: leanpool-v4.34.0, leanpool-v4.35.0-rc3. Truncations 1, invalid JSON 1.
- control/F048: saved `stopped/cost_limit`; next policy reservation $0.37156 exceeds remaining $0.3313012; scout exits `{'scout-a': 'call_limit', 'scout-b': 'quota', 'scout-c': 'quota'}`. Required versions: leanpool-v4.34.0, leanpool-v4.35.0-rc3. Truncations 0, invalid JSON 0.

Every selected proof passed every required version. Baseline/final score inputs match actual evaluator results, with three fresh final primary-version measurements. Receipt normalization, request/response hashes, hard reservations, routing, cache evidence, source/log hashes and full environment boundary fingerprints passed audit.

Original runtime comparison and manager finished records are preserved with hashes. Post-analysis adds `all_trials_terminal` while preserving `all_trials_completed` and every original trial status. No frozen runtime, authorization, input, ledger or proof evidence was changed.

Compact JSON, selected proofs and source-evidence hash manifest are under `results/20261103-exp1-r1/`. Raw private API requests/responses and credentials are not included. This is local research evidence, not an official evaluation or an OpenRouter-eligible submission claim.

Reproduce the read-only audit with:

```sh
python3 -B experiments/budget-fill/analyze_results.py audit --root /ABS/RUN
```
