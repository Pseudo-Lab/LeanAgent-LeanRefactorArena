# Final20 verified proof selection

Contains F001–F010 (Strata) and F041–F050 (LeanPool) from final dataset
`d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`.
Each `.lean` file is the exact verified replacement declaration, **not a standalone module**.
`submission.jsonl` is a local export only; it has not been submitted to the competition.

The $3 run completed all20 problems in approximately 6h28m, using 2–3 concurrent
problem workers, two shared API slots and one shared Lean compiler slot. The
memory manager allowed up to four workers but did not find conditions for four.
All 2,141 API attempts settled. Usage × frozen list-price cost is **$55.7459113**
(maximum per problem $2.8235006); this is not an invoice-verified charge. Earlier
$1 experiments are separate historical expenses. No further paid calls were made
for this export.

The new run alone averages **74.123456**. Comparing completed historical evidence
in the same dataset, tokenizer and pinned environment retains the earlier proofs
for **F002, F006, F007, F008**. The selected20 average **74.468998**. These are local
estimates and the best of the audited completed run selections, not a global
optimum or official score. Each score uses that candidate's own paired original
baseline; small heartbeat differences across runs are preserved.

## Verification and provenance

The canonical public manifest is
[`final-results.json`](../../dashboard/public/data/final-results.json). It includes
exact proof text/hash, selected run ID, input/result hashes, source revisions,
environment fingerprints, compiler source/log/setup hashes, tokenizer identity,
paired baseline and candidate samples, current-run costs and comparison scores.
Current and historical frozen implementation hashes are recorded separately.
Private API transcripts and machine paths are excluded.

Before export, the current harness receipt audit passed for all20 rows. The
exporter independently checks selected source hashes, saved compiler sources and
logs, complete required-version results, baseline compatibility, unchanged full
content fingerprints at both run boundaries, and **three fresh primary-version
HB samples** for both original and candidate. It audits historical proof evidence
per problem; it does not claim that the entire historical60 run or its billing
completed. Cached compatibility checks in the new run were audited by the
current harness. Proofs were not needlessly recompiled for this publication.

Raw HB is used for scoring. Scaled HB is `floor(raw / 1000)`. The score is
`100 - (100 / 3) * (candidate_length / original_length + candidate_HB / original_HB)`
when all required versions pass. Length is the harness proof-body tokenizer count.

## Reproduce the export

Use the preserved run directories and their frozen runtime checkout. No API key
is used by the exporter. First rerun the frozen priority harness report with
`--require-complete --export`, then from this repository:

```sh
python3 dashboard/scripts/export_final_results.py \
  --runtime /path/to/frozen-runtime \
  --current /path/to/20261102-strata-leanpool-usd3-r1 \
  --previous /path/to/20261101-final60-usd1-r1 \
  --repo .
python3 -m unittest discover -s dashboard/scripts -p test_export_final_results.py
npm --prefix dashboard test
npm --prefix dashboard run data:check
npm --prefix dashboard run build
```

For an independent Lean rerun, prepare the final environments using
[`experiments/final-environment`](../../experiments/final-environment/README.md),
use the manifest's exact revisions and the original final problem context, and
pass each declaration to the existing `FinalEvaluator.evaluate` with
`repetitions=3, all_versions=True` in a new output directory. The target declaration
must replace the original in its original module context; importing the target
module and proving against itself is not a valid reproduction. Full private run
receipts are needed to reproduce this export's audit; the public hashes alone
are not a substitute for running Lean.

## Selected results

| Problem | Length original → candidate | Raw HB original → candidate | Score | Source |
|---|---:|---:|---:|---|
| F001 | 224 → 85 | 4,182,543 → 258,508 | 85.29 | $3 run |
| F002 | 904 → 573 | 4,367,942 → 3,204,627 | 54.42 | historical $1 run |
| F003 | 931 → 268 | 10,924,862 → 1,812,263 | 84.88 | $3 run |
| F004 | 291 → 83 | 21,349,352 → 980,676 | 88.96 | $3 run |
| F005 | 209 → 67 | 17,629,144 → 1,538,447 | 86.41 | $3 run |
| F006 | 972 → 669 | 8,898,103 → 4,878,691 | 58.78 | historical $1 run |
| F007 | 429 → 204 | 7,093,908 → 1,441,755 | 77.37 | historical $1 run |
| F008 | 968 → 882 | 7,351,678 → 4,512,866 | 49.17 | historical $1 run |
| F009 | 938 → 49 | 7,275,281 → 815,411 | 94.52 | $3 run |
| F010 | 1200 → 409 | 4,667,075 → 2,475,698 | 70.96 | $3 run |
| F041 | 2030 → 512 | 49,681,455 → 1,216,309 | 90.78 | $3 run |
| F042 | 1699 → 645 | 3,091,286 → 730,970 | 79.46 | $3 run |
| F043 | 2413 → 813 | 9,943,703 → 3,286,130 | 77.75 | $3 run |
| F044 | 2315 → 725 | 13,000,252 → 3,054,833 | 81.73 | $3 run |
| F045 | 1756 → 1088 | 53,089,872 → 43,407,819 | 52.09 | $3 run |
| F046 | 1645 → 814 | 11,484,649 → 2,952,223 | 74.94 | $3 run |
| F047 | 1509 → 601 | 6,122,522 → 1,247,642 | 79.93 | $3 run |
| F048 | 2879 → 2533 | 4,193,446 → 3,794,735 | 40.51 | $3 run |
| F049 | 746 → 429 | 194,028,210 → 36,841,765 | 74.50 | $3 run |
| F050 | 911 → 315 | 157,420,890 → 7,264,137 | 86.94 | $3 run |

The dashboard preserves the original60 baseline dataset and warmup results.
Its default is the competition-style combined score: five of these20 tiles are
red (≤60), fifteen green (>60); the other40 remain gray without invented results.
The displayed74.47 is the mean of these20, not an overall60 score.
