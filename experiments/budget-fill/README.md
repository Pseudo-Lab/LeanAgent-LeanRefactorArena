# Output-budget tail fitting pilot

Compares main commit `a517db26b8eee1b58f30810dca5d66000c810748` (#67) with an output-only tail policy on F006, F045 and F048, at most $3 per arm/problem and $18 total. Both arms use the same frozen implementation, original proof, prompts, environment, model and scout quotas. Both add strict reservation checking in every phase: #67 itself guards only the final budget-ended merger. This pilot does not claim the unmodified main driver enforces a global hard cap.

The adaptive arm leaves requests unchanged until their conservative worst-case reservation will not fit. In the final merger it then finds the largest `max_completion_tokens` that fits, retaining at least 2048 tokens. The byte-based input reservation and frozen list prices are unchanged. If even the minimum cannot fit, ordinary budget termination applies. The change can leave substantial money unused when input reservation dominates; reaching $2.8–2.9 is an empirical question, not guaranteed. More spending is not treated as a score improvement.

The coordinator copies and seals its runtime. An exclusive per-row lock prevents concurrent additions to that row's ledger; the all-phase guard checks settled plus reserved cost before dispatch. Both arms are checked for unresolved billing before every request. One process runs one trial at a time, sharing the existing two API slots and prepared environment's compiler lock with other pilots. A failed process stops the queue with no automatic paid retry. Healthy detached managers must not be duplicated. The machine is kept awake while the manager is alive.

F006 had prior main20 score 62.75, F045 48.88, and F048 48.36. Their original lengths are 972, 1756 and 2879 proof tokens, spanning Strata and LeanPool. Those observations motivated selection; this is Final adaptation, not an unseen holdout. One trajectory per arm does not separate strategy effects from API variation.

Each trial freshly checks the original and required versions before paid work, and uses the main runner's all-version final candidate selection and fresh three-sample final measurement. Costs are calculated from actual OpenAI response usage and frozen public list prices, not a verified invoice. Direct OpenAI research outputs are not claimed to satisfy official OpenRouter submission provenance.

```sh
python experiments/budget-fill/run_experiment.py prepare --root /ABS/NEW-RUN \
  --environment-repo /ABS/PREPARED-REPO --api-slots /ABS/SHARED-SLOTS
python /ABS/NEW-RUN/runtime/experiments/budget-fill/run_experiment.py manage \
  --root /ABS/NEW-RUN --key-file /ABS/.env
python /ABS/NEW-RUN/runtime/experiments/budget-fill/run_experiment.py audit --root /ABS/NEW-RUN
```

Only `manage` and `worker` make paid calls. `audit` recomputes provider costs, reservation caps, candidate hashes, required-version proof evidence and final measurements. Reports include actual spend, score, reduced-output calls and the next rejected reservation. No merge, submission, dashboard replacement or automatic paid retry is performed.
