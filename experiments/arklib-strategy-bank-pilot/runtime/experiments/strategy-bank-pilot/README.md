# ArkLib Strategy Bank paid pilot

Single-arm measurement: 20-card Bank, contextual retrieval, top-1, GPT-6.1 Sol high. This is not the planned 2x2 or strategy-count experiment. Every model action (including search and invalid responses) consumes the same per-problem budget.

The actual run uses OpenAI direct after the user corrected the supplied credential provider. It uses the common actions harness and the existing direct transport ported from final-batch-next into lean_agent.openai_direct. It retains raw provider responses separately from normalized token-price receipts. Costs are calculated from provider token counters and frozen public list prices, not invoice-verified amounts. Cache reads/writes and reasoning are accounted for without double-counting.

The shared serial ledger persists a request reservation before network dispatch. Both per-problem $2.50 and total $25 envelopes are checked. The prior OpenRouter HTTP401 has no successful generation or cost receipt; its $0.258152 reservation remains encumbered conservatively. The direct run therefore has $24.741848 available overall and $2.241848 for the first problem. The other nine retain $2.50 each. Maximum model calls: 40 per problem. An unknown outcome blocks further dispatch; the runner does not automatically retry or resume a paid root.

## Existing environment adapter

The input is the exact original JSONL under <LOCAL_HOME>/_feynlang/temp3 (SHA d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682). Only source=arklib rows are used. Prepared full-module templates and version/commit pins are read from the existing temp3 packets; the backing repositories are in temp2. Inputs contain original proofs and pre-target source excerpts only, with no historical improved proofs.

The temp3 evaluator and its Finset/Aesop-aware intake gate are frozen in the run. Their rendering preserves doc comments and scoped omit/include commands. The measurement Name.toString is explicitly qualified to avoid target-context shadowing. All compiler processes deny network/file writes (except /dev/null), and strip API credentials. No libraries are built or downloaded.

The primary Lean v4.31.0 library manifest hashes actual prepared files, with a full check at batch start/end and stat-cache validation at each candidate/fingerprint. Source and dependency Git pins are checked before execution. The mandatory original full-module check happens before the first paid request; preflight does not claim a separate declaration-free full-module compile (later source may depend on the removed target).

Screening: check + 1 fresh HB measurement in v4.31.0. Final selection: original and ranked valid candidates are checked in all required versions with 3 fresh HB measurements. Select the first full-valid candidate whose token ratio plus mean within-version HB ratio is below 2. Otherwise retain the original. This is a local score, not official worker output or an OpenRouter competition submission certificate.

## Evidence

Each completed problem produces common receipts/replay, a separate full-version verification tree, selected proof/hash, cost ledger and trace. Strategy IDs are model-declared selections; actual application is not inferred from a passing proof. Whole-candidate metric changes remain joint effects. New results do not automatically approve cards or add success/version ranking bonuses.

Report command (read-only against the active run):

```sh
python experiments/strategy-bank-pilot/report.py --root work/arklib10/pilot-openai-01 --output ../../outputs/arklib10-pilot --dataset <LOCAL_HOME>/_feynlang/temp3/benchmark_data_final.jsonl
```

Do not rerun a paid root. Keys/env files must never be copied into reports or archives.

## Verified continuation and fail-fast version checks

After the first required-version rejection in problem04, only the CPU verification controller was changed. Generation prompts, model, Bank, top-k, seed, call limits and reservations were preserved. All160 modelcalls were audited settled; no paid response was redispatched. Completed screening runs are reused only after common receipt replay. Completed positive/compile-negative compiler receipts are reused only after full source/context/candidate, compiler argv, source/log hash, sample count, allowed axioms and measurement-log checks. Resource failures/incomplete receipts are not accepted as cached successes. A failed required version rejects the candidate immediately; accepted final candidates still require all designated versions and3samples each. Original run/code snapshots and partial records are retained; runner-v2.py and verification-policy-update.json identify the change.

Use root selected/NN.lean or report proofs/NN.lean as the all-version selection. Nested runs/NN/selected.lean is the primary-version screening choice and can differ (problem04 is an observed example).

## Compatibility-first ordering and input correction

After problem07 repeatedly failed Lean4.30.0, the CPU controller checks versions with prior deterministic compile rejections first. Every required version remains mandatory; timeouts do not determine ordering. Completed verified receipts are reused with the same integrity checks, without repeating paid calls. `verification-order-update.json` and frozen runner-v4 identify this change.

Before problems08–10 started, their legacy model input was corrected: remove `original` only where it exactly duplicated `reference`, and add official `version_info` plus the screening version. The theorem and reference proof are unchanged; before/after request tests confirm unchanged Bank recommendations. Problems01–07 retain their previous inputs. `input-policy-update.json` records hashes and affected indices. This is an exploratory integration pilot with a disclosed input correction, not a uniform-condition comparison experiment.
