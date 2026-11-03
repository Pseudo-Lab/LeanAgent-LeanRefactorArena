# Frozen Bank inputs

`bank.json` is the 20-card `dashboard-mechanisms-v2-team-1` object actually embedded in every initial/run-07 config. All cards are review_required. `evidence.jsonl` contains 126 observation links derived from the same 80 dashboard before/after pairs, including joint changes and non-improving candidates. It is source observation, not a model generation trajectory or an independent effectiveness dataset.

`reference-five-card-bank.json` preserves the earlier five-card reference for the planned comparison. This pilot did not run that comparison arm. Contextual retrieval is text/regex based, top-1, and uses the visible incumbent. Own-problem evidence is excluded from transfer support; hidden-original scout hints are withheld. Metadata objectives are empty, and no empirical success/version bonus is inferred.
