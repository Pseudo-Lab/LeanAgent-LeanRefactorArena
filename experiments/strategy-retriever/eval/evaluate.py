#!/usr/bin/env python3
"""Does the retriever pick the strategies that were actually applied? (no Lean, no model call)

Ground truth: eval/ground_truth.json (applied refactorings mapped to bank S01-S09).
Compares the retriever's top-k specific strategies (S10/S11 general moves excluded) with
  - a constant baseline: the k most frequent ground-truth strategies for every problem
  - random choice of k strategies among S01-S09 (exact expectation)

usage (repository root):
  python experiments/strategy-retriever/eval/evaluate.py --jsonl benchmark_data_final.jsonl
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from retriever import load_bank, retrieve  # noqa: E402

GENERAL = {"S10", "S11"}
SPECIFIC = [f"S0{i}" for i in range(1, 10)]


def hit(truth: set, pred) -> bool:
    return bool(truth & set(pred))


def random_expectation(truth: set, k: int) -> float:
    combos = list(combinations(SPECIFIC, k))
    return sum(hit(truth, c) for c in combos) / len(combos) if k else 0.0


def evaluate(rows: dict, items: list, k: int = 3) -> dict:
    bank = load_bank()
    per = []
    for it in items:
        row = rows[it["problem"]]
        res = retrieve(row["statement"], row["src"], bank, k, row["name"])
        per.append({"id": it["id"], "problem": it["problem"], "truth": it["labels"],
                    "pred": [s["id"] for s in res["strategies"] if s["id"] not in GENERAL],
                    "tags": res["features"]["tags"]})
    labeled = [p for p in per if p["truth"]]
    freq = Counter(s for p in labeled for s in p["truth"])
    constant = [s for s, _ in freq.most_common(k)]
    return {"per_problem": per, "labeled": len(labeled), "unlabeled": len(per) - len(labeled),
            "retriever_hits": sum(hit(set(p["truth"]), p["pred"]) for p in labeled),
            "constant": constant, "constant_hits": sum(hit(set(p["truth"]), constant) for p in labeled),
            "random_expected": round(sum(random_expectation(set(p["truth"]), len(p["pred"])) for p in labeled), 2),
            "truth_freq": dict(freq.most_common()),
            "pred_freq": dict(Counter(s for p in per for s in p["pred"]).most_common())}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", type=Path, required=True)
    ap.add_argument("--truth", type=Path, default=HERE / "ground_truth.json")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    rows = {r["name"]: r for r in map(json.loads, a.jsonl.open(encoding="utf-8"))}
    r = evaluate(rows, json.loads(a.truth.read_text(encoding="utf-8"))["items"], a.k)
    for p in r["per_problem"]:
        mark = "-" if not p["truth"] else ("O" if hit(set(p["truth"]), p["pred"]) else "X")
        print(f'{p["id"]} {mark} truth={",".join(p["truth"]) or "(none)":10} pred={",".join(p["pred"]):14} {p["problem"]}')
    n = r["labeled"]
    print(f'\nlabeled {n}, no bank strategy applied {r["unlabeled"]}')
    print(f'retriever          {r["retriever_hits"]}/{n}')
    print(f'constant {",".join(r["constant"])}  {r["constant_hits"]}/{n}')
    print(f'random (expected)  {r["random_expected"]}/{n}')
    print(f'ground truth freq {r["truth_freq"]}\nretriever freq    {r["pred_freq"]}')
    if a.out:
        a.out.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
