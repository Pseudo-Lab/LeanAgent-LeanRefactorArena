#!/usr/bin/env python3
"""Recompute the physlib/cslib condition comparison from results.json (no Lean, no API).

Unlike compare_conditions.py, rows that stopped at the $1 cost limit are scored too, as long as the
preserved best was valid on all versions: on these libraries almost every row ends at the cost limit.

usage: python3 experiments/final-batch-next/results/physlib-cslib-ab/summarize.py
"""
import json
import random
import statistics as st
from pathlib import Path

data = json.loads(Path(__file__).with_name("results.json").read_text())
rows = sorted(data["rows"])
conds = list(data["conditions"])
J = {c: {r: data["rows"][r][c]["J"] for r in rows if c in data["rows"][r]} for c in conds}
common = [r for r in rows if all(J[c].get(r) is not None for c in conds)]

print("row   " + "".join(f"{c:>7}" for c in conds))
for r in rows:
    print(f"{r}  " + "".join(f"{J[c][r]:7.3f}" if J[c].get(r) is not None else "   fail" for c in conds))
print(f"\nmean J on {len(common)} common rows: " + ", ".join(f"{c} {st.mean(J[c][r] for r in common):.3f}" for c in conds))

noise = [abs(J["C0"][r] - J["C0b"][r]) for r in common]
print(f"C0 vs C0b (same settings): |dJ| median {st.median(noise):.3f}, mean {st.mean(noise):.3f}, max {max(noise):.3f}")

random.seed(0)
base = {r: (J["C0"][r] + J["C0b"][r]) / 2 for r in common}
for c in conds:
    if c in ("C0", "C0b"):
        continue
    diffs = [J[c][r] - base[r] for r in common]
    means = sorted(st.mean(random.choices(diffs, k=len(diffs))) for _ in range(10000))
    print(f"{c} - mean(C0, C0b): {st.mean(diffs):+.3f}  95% CI [{means[250]:+.3f}, {means[9750]:+.3f}]  "
          f"better on {sum(d < 0 for d in diffs)}/{len(diffs)}")
best = {r: min(J[c][r] for c in conds if J[c].get(r) is not None) for r in rows}
print(f"best of {len(conds)} runs per row: mean {st.mean(best.values()):.3f}")
