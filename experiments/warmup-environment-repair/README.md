# Pinned environment repair evidence

This directory records actual CI verification attempts and their preparation/compilation logs. It is retained in the experiment commit history and removed from the final tree.

| Evidence | Actions run | Outcome |
|---|---|---|
| primary | 39944569159 | Mathlib v4.26 verified; ArkLib v4.31 built, then package-name audit failed. |
| remaining | 39944826874 | Mathlib v4.25 verified; v4.27 exceeded 2 GiB; ArkLib builds completed, then package-name audit failed. |
| retry-putnam | 39953916716 | Mathlib v4.27 exceeded 4 GiB. |
| final-putnam-v427 | 39954553496 | Mathlib v4.27 originals and all candidates passed at 6 GiB. |
| arklib-v428-memory4 | 39953916716 | Original execution exceeded 4 GiB. |
| final-arklib-v429 | 39953916716 | P10 and P11 originals and candidates passed. |
| final-arklib-v430 | 39953916716 | P10 and P11 originals and candidates passed. |
| retry-arklib-v428 | 39956098384 | P10 original and candidate passed after an automatic 6 to 8 GiB retry. |
| final-arklib-v431 | 39953916716 | Original compilation passed, but measurement exceeded 4 GiB. |

Final published evidence is stored separately under submissions/warmup/verification-results.json. A successful workflow means the measurement attempt completed; consult each baseline/candidate valid field for proof validity. Every published measurement pairs the original and candidate in the same pinned environment.
