#!/usr/bin/env python3
"""Compare finished batch roots run under different portfolio settings (no Lean, no API).

Reads problems/F###/summary.json and input/config.json under each root and prints, per problem and
condition, the score (length and heartbeat reduction plus all-version compatibility, averaged),
spend, calls and evaluations. Only completed summaries with all-version validity are scored.

usage (repository root):
  python experiments/final-batch-next/compare_conditions.py runs/final-batch-next/AB-C0 runs/final-batch-next/AB-C1 ...
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def score(summary):
    if summary.get("status") != "completed" or not summary.get("all_versions_valid"):
        return None
    base, final = summary["baseline"], summary["final"]
    length = 100 * (1 - final["tokens"] / base["tokens"])
    heartbeat = 100 * (1 - final["raw_heartbeats"] / base["raw_heartbeats"])
    return (length + heartbeat + 100) / 3


def condition(root):
    configs = sorted(Path(root).glob("problems/F*/input/config.json"))
    settings = json.loads(configs[0].read_text())["agent"].get("portfolio") if configs else None
    return "single context" if settings is None else json.dumps(settings, sort_keys=True)


def load(root):
    rows = {}
    for path in sorted(Path(root).glob("problems/F*/summary.json")):
        summary = json.loads(path.read_text())
        evaluations = sum((summary.get("portfolio") or {}).get("evaluations", {}).values())
        rounds = (summary.get("portfolio") or {}).get("completed_rounds", [])
        evaluations += sum(sum(r["evaluations"].values()) for r in rounds)
        rows[path.parent.name] = {"score": score(summary), "cost": float(summary["cost_usd"]),
                                  "calls": summary["calls"], "evaluations": evaluations,
                                  "stop": summary.get("stop_reason")}
    return rows


def main(roots):
    data = {root: load(root) for root in roots}
    problems = sorted({p for rows in data.values() for p in rows})
    for i, root in enumerate(roots):
        print(f"C{i}: {root}\n    {condition(root)}")
    print()
    print("problem " + "".join(f"{f'C{i} score/$':>18}" for i in range(len(roots))))
    for p in problems:
        cells = []
        for root in roots:
            r = data[root].get(p)
            if r is None:
                cells.append("-")
            else:
                shown = "fail" if r["score"] is None else "%.1f" % r["score"]
                cells.append("%s / %.2f" % (shown, r["cost"]))
        print(f"{p:7} " + "".join(f"{c:>18}" for c in cells))
    print()
    common = [p for p in problems if all(data[r].get(p) and data[r][p]["score"] is not None for r in roots)]
    for i, root in enumerate(roots):
        rows = [data[root][p] for p in common]
        if rows:
            print(f"C{i}: mean score {statistics.mean(r['score'] for r in rows):.2f} on {len(rows)} common problems, "
                  f"mean ${statistics.mean(r['cost'] for r in rows):.2f}, mean evaluations "
                  f"{statistics.mean(r['evaluations'] for r in rows):.1f}")
    print("Scores use this batch's own baseline measurements; compare conditions only on the same problems.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
