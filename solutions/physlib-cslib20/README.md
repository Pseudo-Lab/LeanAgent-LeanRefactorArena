# PhysLib and CSLib final 20

This directory contains the selected proofs for F011–F020 (PhysLib) and F021–F030 (CSLib) in final dataset `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`.

- `submission.jsonl` has the official `name`/`proof` schema; it has **not** been submitted to the arena.
- `F###.lean` files contain the same declarations for review.
- `manifest.json` records the exact theorem names, source revisions, proof hashes, local measurements and required Lean version pass counts. The 20 selected proofs passed all 42 required version checks. The representative version was measured three times for both reference and candidate.

The local mean is **53.6942** across these 20 rows (16 improvements, four unchanged references). This is a local score, not a team 60-problem or official score. No paid model calls were made in this run.

`proof_sha256` identifies the exact JSONL proof string. The review `.lean` files add one terminal newline; the dashboard publication retains a separate `proofFileSha256` for those bytes. The public bundle contains aggregate HB values and pass/repeat counts, not the raw HB samples or compiler logs. The dashboard labels these rows as published verification summaries.

The selected declarations were checked in the original module context with the team's `FinalEvaluator`. The local run receipts and environment snapshots are retained on the RTX 4090 WSL machine; the public manifest omits machine paths and API material. This PR publishes the verified selection first. Harness integration and any additional candidate search can follow in separate reviewable changes.
