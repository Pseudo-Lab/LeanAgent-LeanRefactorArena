#!/usr/bin/env python3
"""Rule-based strategy retriever: original proof -> top-k strategies from a small bank.

Matching uses only static features of the original proof (features.py); the problem name is never a
search key. A strategy whose evidence comes only from the problem being solved is left out for that
problem (leave-one-out), so final-benchmark strategies can be added later without feeding a problem
its own solution. No Lean, no model call.

Match rule for a bank entry `match`:
  all_tags   every tag present
  any_tags / tactic_min   at least one tag present or one count at its minimum (if either is given)
  {}         general move, used only to fill up to k
Score = number of satisfied conditions; ties keep bank order.

usage (repository root):
  python experiments/strategy-retriever/retriever.py --jsonl benchmark_data_final.jsonl --out retrieved.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from features import features  # noqa: E402

BANK = HERE / "bank" / "strategies.json"


def load_bank(path: Path = BANK) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["strategies"]


def score(match: dict, feat: dict) -> int | None:
    """Number of satisfied conditions, 0 for a general move, None if the entry does not apply."""
    tags, counts = set(feat["tags"]), feat["counts"]
    all_tags = match.get("all_tags", [])
    if not set(all_tags) <= tags:
        return None
    alt = [t for t in match.get("any_tags", []) if t in tags]
    alt += [w for w, n in match.get("tactic_min", {}).items() if counts.get(w, 0) >= n]
    if (match.get("any_tags") or match.get("tactic_min")) and not alt:
        return None
    return len(all_tags) + len(alt)


def leave_one_out(entry: dict, problem: str | None) -> bool:
    """True if the entry's only evidence is the problem being solved."""
    ids = set(entry.get("evidence", {}).get("source_problem_ids", []))
    return bool(problem) and ids == {problem}


def retrieve(statement: str, original: str, bank: list[dict], k: int = 3, problem: str | None = None) -> dict:
    feat = features(statement, original)
    usable = [(i, e) for i, e in enumerate(bank) if not leave_one_out(e, problem)]
    scored = [(s, i, e) for i, e in usable if (s := score(e["match"], feat)) is not None]
    specific = sorted((x for x in scored if x[0] > 0), key=lambda x: (-x[0], x[1]))
    general = [x for x in scored if x[0] == 0]
    chosen = (specific + general)[:k]
    return {"features": feat,
            "strategies": [{"id": e["id"], "title": e["title"], "score": s, "when_to_apply": e["when_to_apply"],
                            "application_guide": e["application_guide"], "risk_notes": e["risk_notes"]}
                           for s, _, e in chosen],
            "excluded_leave_one_out": [e["id"] for e in bank if leave_one_out(e, problem)]}


def render(result: dict) -> str:
    """Plain text block for a Planner prompt."""
    lines = ["Candidate strategies (retrieved from the original proof's structure; hypotheses, not guarantees):"]
    for n, s in enumerate(result["strategies"], 1):
        lines.append(f"{n}. [{s['id']}] {s['title']}. When: {s['when_to_apply']} "
                     f"Steps: {' '.join(s['application_guide'])} Risk: {' '.join(s['risk_notes'])}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", type=Path, required=True, help="benchmark JSONL (name, statement, src)")
    ap.add_argument("--bank", type=Path, default=BANK)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--sources", nargs="*", help="only these sources (default: all)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    bank = load_bank(a.bank)
    out = {}
    for row in map(json.loads, a.jsonl.open(encoding="utf-8")):
        if a.sources and row.get("source") not in a.sources:
            continue
        r = retrieve(row["statement"], row["src"], bank, a.k, row["name"])
        out[row["name"]] = {"source": row.get("source"), "strategy_ids": [s["id"] for s in r["strategies"]],
                            "tags": r["features"]["tags"], "prompt": render(r)}
        print(row["name"], out[row["name"]]["strategy_ids"], out[row["name"]]["tags"])
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
