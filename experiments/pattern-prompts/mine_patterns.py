#!/usr/bin/env python3
"""Count signal tactics in the warm-up originals and in the team's final proofs.

The counts show which refactoring moves recur across problems regardless of block type:
long `have` chains removed, broad automation reduced, per-goal blocks closed once, splits
following a definition, searches replaced by exact forms. make_pattern_prompts.py attaches
those moves when the original proof shows the same signal.

No model call, no Lean.

usage (repository root):
  python experiments/pattern-prompts/mine_patterns.py --originals benchmark_data_warmup.jsonl \
      --final submission.jsonl --out experiments/pattern-prompts/mined.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SIGNALS = ["have", "simp_all", "omega", "linarith", "grind", "aesop", "norm_num", "case", "cases",
           "induction", "fun_induction", "decide", "calc", "<;>", "all_goals", "first", "repeat"]


def count(body: str, word: str) -> int:
    tail = r"(?![\w])" if word[-1].isalnum() or word[-1] == "_" else ""
    return len(re.findall(r"(?<![\w.])" + re.escape(word) + tail, body))


def body_of(proof: str, statement: str) -> str:
    return proof[len(statement):] if proof.startswith(statement) else proof.split(":=", 1)[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--originals", type=Path, required=True, help="warm-up benchmark jsonl (name, statement, src)")
    ap.add_argument("--final", type=Path, required=True, help="final proofs jsonl (name, proof)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    rows = [json.loads(l) for l in a.originals.read_text(encoding="utf-8").splitlines() if l.strip()]
    final = {r["name"]: r["proof"] for r in
             (json.loads(l) for l in a.final.read_text(encoding="utf-8").splitlines() if l.strip())}
    head = "| # | 출처 | " + " | ".join(f"`{w}`" for w in SIGNALS) + " |"
    L = ["# 웜업 원본과 최종 증명의 신호 전술 개수", "", "칸은 `원본 → 최종`. 0 → 0은 비움.", "", head,
         "| ---: | --- | " + " | ".join("---" for _ in SIGNALS) + " |"]
    for k, r in enumerate(rows, 1):
        o = body_of(r["src"], r["statement"])
        f = body_of(final.get(r["name"], ""), r["statement"])
        cells = []
        for w in SIGNALS:
            x, y = count(o, w), count(f, w)
            cells.append("" if x == y == 0 else f"{x}→{y}")
        L.append(f"| {k} | {r.get('source', '')} | " + " | ".join(cells) + " |")
    md = "\n".join(L) + "\n"
    a.out.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
