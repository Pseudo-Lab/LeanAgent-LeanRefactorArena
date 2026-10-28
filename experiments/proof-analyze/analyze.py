#!/usr/bin/env python3
"""analyze(proof): static proof analysis handed to the LLM before it edits a proof.

No Lean compile and no model call. Given a declaration and its fixed statement,
returns a JSON-able dict that tells the agent
  - how long the proof is (official proof_length tokens),
  - what kind of proof it is (case / calc / have / mixed, plus a sub-type),
  - which blocks exist (id, src lines, tokens, share),
  - which blocks are worth editing first (targets, ranked by an estimated saving),
and two helpers for the harness:
  - focus_view(): the proof with one target block marked by EDIT-START/END comments,
  - splice(): put the model's replacement for that block back into the declaration.

Blocks and candidates come from block_analyzer.py (rules 1-4 of the block strategy).
Savings are estimates from token counts, not compiled results.

usage
  python analyze.py --jsonl warmup.jsonl --rows 1 15 --out results
  python analyze.py --decl proof.lean --statement stmt.lean
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import difflib  # noqa: E402

from block_analyzer import analyse  # noqa: E402
from proof_tokens import lex, proof_length  # noqa: E402


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))

SUBTYPE_SHARE = 25.0          # percent; second block kind at least this share -> sub-type
LENGTH_BUCKETS = ((300, "short"), (1500, "medium"))
TYPE_HINTS = {
    "case": "Branch proof. Compare branch bodies: identical bodies can share one `case a | b =>`; "
            "a tactic repeated in every branch can move before the split with `<;>`.",
    "calc": "Calculation chain. Adjacent steps closed by the same tactic can often be merged, "
            "or the whole chain replaced by one rewrite plus a closing tactic.",
    "have": "Intermediate-claim proof. Look for claims used once (inline them), claims never used "
            "(delete them) and claims proved twice up to renaming (prove once with arguments).",
    "mixed": "No dominant block kind. Start from the largest block.",
}
TARGET_HINTS = {
    "repeat": "These two blocks are the same argument up to local names (see `differs`). Prove it once as "
              "`have name : ∀ (args), claim := by ...` and call `name args` at both places; "
              "the differing tokens are candidate arguments.",
    "case_body": "These branches have (near-)identical bodies (see `differs`). If nothing differs, merge "
                 "them into one alternative `case a | b =>`; otherwise close both with a shared tactic "
                 "that covers the differing step.",
    "large": "This block holds a large share of the proof. Shorten it: replace manual steps by "
             "stronger closing tactics, drop intermediate claims that are not needed.",
}
NEEDS_COMPILE = ["unused_have (Lean linter linter.unusedVariables.analyzeTactics)",
                 "heartbeats", "axioms"]


def _length_bucket(n: int) -> str:
    for lim, name in LENGTH_BUCKETS:
        if n < lim:
            return name
    return "long"


def analyze(declaration: str, statement: str, source: str = "") -> dict:
    """Static analysis of one proof. `declaration` = full theorem text, `statement` = fixed part."""
    total = proof_length(declaration, statement)
    r = analyse({"src": declaration, "statement": statement, "proof_length": total,
                 "name": "", "source": source})
    blocks = []
    for b in r["blocks"]:
        if b["role"] != "block":
            continue
        bid = f"B{len(blocks) + 1}"
        blocks.append({"id": bid, "lines": [b["first_line"], b["last_line"]], "kind": b["kind"],
                       "head": b["head"], "tokens": b["tokens"], "share": b["share"],
                       "children": [{"lines": [c["first_line"], c["last_line"]], "kind": c["kind"],
                                     "head": c["head"], "tokens": c["tokens"]} for c in b["children"]]})

    def block_of(line):
        for x in blocks:
            if x["lines"][0] <= line <= x["lines"][1]:
                return x["id"]
        return None

    src_lines = declaration.split("\n")

    def region(first):
        """first (1-based) plus following lines indented deeper than it."""
        base = _indent(src_lines[first - 1])
        last = first
        for j in range(first, len(src_lines)):
            s = src_lines[j]
            if s.strip() and _indent(s) <= base:
                break
            if s.strip():
                last = j + 1
        return [first, last]

    def toks(rng):
        return [t for l in src_lines[rng[0] - 1:rng[1]] for t in (lex(l.strip()).split(" ") if l.strip() else [])]

    def differs(ra, rb):
        """Token pairs that differ between two regions (edit-distance alignment)."""
        A, B = toks(ra), toks(rb)
        out = []
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B, autojunk=False).get_opcodes():
            if op != "equal":
                out.append([" ".join(A[i1:i2]), " ".join(B[j1:j2])])
        return out

    targets = []
    for d in r["repeat_candidates"]:
        diff = differs(d["a"], d["b"])
        # identical up to renaming: one copy stays general, the other becomes a call (~5 tokens)
        exact = d["similarity"] == 1.0
        targets.append({"kind": "repeat", "lines": [d["a"], d["b"]],
                        "blocks": sorted({block_of(d["a"][0]), block_of(d["b"][0])} - {None}),
                        "heads": [d["a_head"], d["b_head"]], "tokens": d["tokens"],
                        "similarity": d["similarity"], "differs": diff[:8],
                        "est_saving": max(0, min(d["tokens"]) - 5) if exact else None})
    for d in r["case_candidates"]:
        ra, rb = region(d["a"]), region(d["b"])
        if any(t["lines"] == [ra, rb] for t in targets):
            continue  # same pair already listed as a repeat
        diff = differs([ra[0] + 1, ra[1]], [rb[0] + 1, rb[1]]) if ra[1] > ra[0] else []
        exact = d["similarity"] == 1.0 and not diff
        targets.append({"kind": "case_body", "lines": [ra, rb],
                        "blocks": sorted({block_of(d["a"]), block_of(d["b"])} - {None}),
                        "heads": [d["a_head"], d["b_head"]], "tokens": d["tokens"],
                        "similarity": d["similarity"], "differs": diff[:8],
                        "est_saving": min(d["tokens"]) if exact else None})
    # drop a pair nested inside another listed pair
    def inside(t, u):
        return all(u["lines"][k][0] <= t["lines"][k][0] and t["lines"][k][1] <= u["lines"][k][1] for k in (0, 1))
    targets = [t for t in targets if not any(u is not t and inside(t, u) and u["lines"] != t["lines"]
                                             and (u["similarity"] >= t["similarity"]) for u in targets)]
    if blocks:
        big = max(blocks, key=lambda x: x["tokens"])
        targets.append({"kind": "large", "lines": [big["lines"]], "blocks": [big["id"]],
                        "heads": [big["head"]], "tokens": [big["tokens"]], "share": big["share"],
                        "est_saving": None})
    # exact pairs (saving known) first, then near pairs by size, then the largest block
    targets.sort(key=lambda t: (0 if t["est_saving"] is not None else (2 if t["kind"] == "large" else 1),
                                -(t["est_saving"] if t["est_saving"] is not None else min(t["tokens"]))))
    for i, t in enumerate(targets, 1):
        t["id"] = f"T{i}"
        # one contiguous region the model rewrites; splice() puts the answer back here
        t["edit_span"] = [min(r_[0] for r_ in t["lines"]), max(r_[1] for r_ in t["lines"])]
        t["hint"] = TARGET_HINTS[t["kind"]]

    shares = sorted(((k, v) for k, v in r["kind_share"].items() if k != "other"), key=lambda kv: -kv[1])
    subtype = next((k for k, v in shares if k != r["type"] and v >= SUBTYPE_SHARE), None)
    return {
        "proof_tokens": total,
        "type": r["type"], "subtype": subtype, "kind_share": r["kind_share"],
        "tags": {"source": source or None, "length": _length_bucket(total),
                 "repeat_pairs": len(r["repeat_candidates"]),
                 "case_body_pairs": len(r["case_candidates"])},
        "type_hint": TYPE_HINTS[r["type"]],
        "blocks": blocks,
        "targets": targets,
        "needs_compile": NEEDS_COMPILE,
    }


def focus_view(declaration: str, lines: list[int], tag: str = "T") -> str:
    """Mark src lines [first, last] (1-based) with comments the model can see."""
    a, b = lines
    out = declaration.split("\n")
    pad = " " * (len(out[a - 1]) - len(out[a - 1].lstrip(" ")))
    out.insert(b, f"{pad}-- EDIT-END {tag}")
    out.insert(a - 1, f"{pad}-- EDIT-START {tag}")
    return "\n".join(out)


def splice(declaration: str, lines: list[int], replacement: str) -> str:
    """Replace src lines [first, last] (1-based) by `replacement`."""
    a, b = lines
    out = declaration.split("\n")
    return "\n".join(out[:a - 1] + replacement.rstrip("\n").split("\n") + out[b:])


def to_md(rows):
    L = ["# analyze(proof) 결과", "",
         "컴파일과 모델 호출 없이 계산함. 예상 감소량은 토큰 수로 낸 추정치이며 컴파일 결과가 아님.", "",
         "| # | 출처 | 토큰 | 길이 | 유형 | 보조 유형 | 블록 | 대상 | 1순위 대상 | 예상 감소 |",
         "| ---: | --- | ---: | --- | --- | --- | ---: | ---: | --- | ---: |"]
    for k, a in rows:
        t0 = a["targets"][0] if a["targets"] else None
        L.append(f"| {k} | {a['tags']['source']} | {a['proof_tokens']:,} | {a['tags']['length']} | {a['type']} | "
                 f"{a['subtype'] or '-'} | {len(a['blocks'])} | {len(a['targets'])} | "
                 f"{t0['kind'] + ' ' + ','.join(t0['blocks']) if t0 else '-'} | "
                 f"{t0['est_saving'] if t0 and t0['est_saving'] is not None else '-'} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl")
    ap.add_argument("--rows", nargs="*", type=int)
    ap.add_argument("--decl")
    ap.add_argument("--statement")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.decl:
        res = analyze(open(a.decl, encoding="utf-8").read(), open(a.statement, encoding="utf-8").read().rstrip("\n"))
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    rows = [json.loads(l) for l in open(a.jsonl, encoding="utf-8") if l.strip()]
    sel = a.rows or list(range(1, len(rows) + 1))
    done, bad = [], 0
    for k in sel:
        row = rows[k - 1]
        res = analyze(row["src"], row["statement"], row.get("source", ""))
        res["name"] = row["name"]
        ok = res["proof_tokens"] == row["proof_length"]
        bad += not ok
        done.append((k, res))
        print(f"{k:2d} {'ok ' if ok else 'DIFF'} tokens={res['proof_tokens']:5d} type={res['type']:5s} "
              f"sub={res['subtype'] or '-':5s} blocks={len(res['blocks']):2d} targets={len(res['targets'])}")
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            json.dump(res, open(os.path.join(a.out, f"P{k:02d}.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            t0 = res["targets"][0]
            open(os.path.join(a.out, f"P{k:02d}_focus.lean"), "w", encoding="utf-8").write(
                focus_view(row["src"], t0["edit_span"], t0["id"]))
    if a.out:
        open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write(to_md(done))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
