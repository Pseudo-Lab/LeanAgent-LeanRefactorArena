# Pinned environment repair evidence

This directory records actual CI verification attempts and their preparation/compilation logs. It is retained in the experiment commit history and removed from the final tree.

- primary: Actions run 39944569159; Mathlib v4.26 verified, ArkLib v4.31 built but the package-name audit failed.
- remaining: Actions run 39944826874; Mathlib v4.25 verified, v4.27 hit the 2 GiB cap, ArkLib builds completed but the package-name audit failed.
- retry-putnam: Actions run 39953916716; v4.27 still hit the 4 GiB cap.

Final published evidence is stored separately under submissions/warmup/verification-results.json. A successful workflow means the measurement attempt completed; consult each baseline/candidate valid field for proof validity.
