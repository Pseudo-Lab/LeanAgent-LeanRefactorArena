# Team proposal integration

`bank.json` retains v2 signal gates, candidate hashes and single/multiple-problem observation status. Added metadata separates review approval from source observation. All cards remain `review_required`; no human approval or isolated effectiveness is inferred. Objectives are initially empty: no measured objective bonus is invented. `metadata.objectives` can declare intended objectives (not empirical gains); configured objective matches add 0.25. No success-rate/version bonus exists until audited evidence can support one.

`evidence.jsonl` has 126 strategy-observation links from all 80 reviewed pairs. They include joint changes and non-improving candidates. Missing attempt IDs, cost and fresh verification remain null/not_reverified. Exact original source records remain in dashboard-v2. This is not a generation trajectory.

Enable contextual retrieval in a new config:

```sh
python scripts/build_strategy_bank_team.py
python scripts/configure_strategy_bank.py --config configs/actions-smoke.json --bank strategy-bank/team-v1/bank.json --output work/team-config.json --contextual
PYTHONPATH=src python -m lean_agent run --config work/team-config.json --output work/team-run
python scripts/export_strategy_trace.py --run work/team-run --output work/team-trace.jsonl
```

The example uses fixture model responses with real Lean; it is a plumbing check, not strategy efficacy evidence. A paid run requires a separately configured OpenRouter model, provider, prices and hard budget.

Contextual retrieval analyzes the visible incumbent proof. It chooses hb/tokens by the larger incumbent/baseline ratio (a simple declared heuristic), excludes selected IDs of proof_rejected attempts in the visible recent-action window, and emits generic proposal-style strategy_hints. Infrastructure failures are not strategy failures. Hidden-original scout emits no hints or context. Existing configs without contextual=true preserve prior retrieval behavior. Repair may explicitly select an excluded strategy; exclusion affects recommendations, not permission to repair.

Actions propose/repair accept optional strategy_ids (0..3 configured IDs). No ID is inferred from free-text strategy. Exports distinguish recommended, declared selected, candidate written, application unreviewed, and verifier result. A passing candidate does not prove the declared transformation was applied, caused a gain, or passed all Arena versions. Actual application needs diff review; per-version receipts and all API costs need separate full evaluator evidence. Requests and events are snapshotted, auditable and replayable.

## Next empirical stage

1. Select a small set spanning generic, algebra, derivative and polynomial signals without selecting on post-run performance. Freeze problem hashes, Bank hash, model/provider, pricing, toolchains and scorer.
2. Run matched Bank OFF / contextual Bank ON with top-1 and identical generation/repair/cost limits. Randomize order; use several repeats when affordable. Preserve failed attempts.
3. Export trace rows. Review selected candidates' diffs and annotate actual application separately. Run full required-version evaluation; attach exact receipts and per-call cost records. Do not feed historical joint improvements into individual success bonuses.
4. Use the broader 2x2 Bank/retriever comparison only after cross-compatible metadata and the run logger are verified. A changed metadata/scoring policy must receive a new frozen Bank/experiment version.

This module does not add a separate Planner/Worker architecture or change providers. The existing actions agent performs planning/generation; strategy_hints is the adapter contract for a future distinct Planner.
