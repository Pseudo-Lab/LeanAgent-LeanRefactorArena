#!/usr/bin/env python3
"""route(proof): turn analyze() output into an ordered plan of rule steps, before any model call.

Cost: no model call and no compile (the plan itself). Steps marked compile=True are run later by the
rule scripts of the block strategy; steps marked model=True are left for the LLM.

usage
  python route.py --jsonl benchmark_data.jsonl --out plans      # one plan per row + plans/summary.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "proof-analyze"))
from analyze import analyze  # noqa: E402

# step catalogue: rules already implemented in the block strategy (experiments/block-strategy)
STEPS = {
    "merge_same_branches": {"rule": "규칙 8: 본문이 같은 분기를 `case a | b =>`로 합침", "script": "block_dp.py",
                            "compile": True, "model": False},
    "prune_unused_have": {"rule": "린터가 찾은 미사용 `have` 반복 제거", "script": "prune_unused.py",
                          "compile": True, "model": False},
    "generalise_repeat": {"rule": "이름만 다른 중복 `have`를 보조정리 하나로 묶음", "script": "block_dp.py",
                          "compile": True, "model": False},
    "llm_focus": {"rule": "analyze 대상 구간만 LLM에 넘김", "script": "(하네스)", "compile": True, "model": True},
}
LIBRARY = {"strata", "physlib", "cslib", "arklib"}


IDENT = re.compile(r"^(?:[^\W\d][\w'₀-₉!?]*|\d+)$")     # plain local name or numeral
POSTFIX = ("ᶜ", "⁻¹")                                       # `Aᶜ` is an expression, not a name
HAVE_HEAD = re.compile(r"^\s*(?:·\s*)?have\s+\S+\s*:.+:=\s*by\s*$")   # form block_dp.py can generalise


def _indent(l):
    return len(l) - len(l.lstrip(" "))


def _siblings(lines, a, b):
    """Two branch heads (1-based) are siblings: same indent and no line in between at a lower indent."""
    ia = _indent(lines[a - 1])
    if _indent(lines[b - 1]) != ia:
        return False
    return all(not l.strip() or _indent(l) >= ia for l in lines[a:b - 1])


def _args_only(t):
    """Every differing token pair is a plain name or numeral, so it can become an argument."""
    return bool(t["differs"]) and all(all(pair) and all(IDENT.match(x) and not any(p in x for p in POSTFIX)
                                                       for x in pair) for pair in t["differs"])


def route(info: dict, declaration: str) -> dict:
    """info = analyze(declaration, ...). Returns the ordered steps and why each was chosen."""
    lines = declaration.split("\n")
    steps, why = [], []
    merge = [t for t in info["targets"] if t["kind"] == "case_body" and t["est_saving"] is not None
             and _siblings(lines, t["lines"][0][0], t["lines"][1][0])]
    gen = [t for t in info["targets"] if t["kind"] == "repeat" and _args_only(t)
           and all(HAVE_HEAD.match(lines[r[0] - 1]) for r in t["lines"])]
    rest = [t for t in info["targets"] if t["kind"] in ("case_body", "repeat") and t not in merge and t not in gen]
    n_have = sum(1 for l in lines if re.match(r"\s*(?:·\s*)?have\b", l))

    if merge:
        steps.append("merge_same_branches")
        why.append(f"같은 부모 아래 본문이 같은 분기 쌍 {len(merge)}개")
    if n_have:
        steps.append("prune_unused_have")
        why.append(f"`have` {n_have}줄 (모델 비용 없이 컴파일만 씀)")
    if gen:
        steps.append("generalise_repeat")
        why.append(f"다른 토큰이 이름·숫자뿐인 중복 쌍 {len(gen)}개")
    steps.append("llm_focus")
    why.append(f"규칙으로 처리하지 못한 비슷한 쌍 {len(rest)}개와 가장 큰 블록" if rest
               else "남은 구간은 가장 큰 블록부터")
    src = (info["tags"]["source"] or "").lower()
    group = "library" if src in LIBRARY else ("competition" if src else "unknown")
    return {"type": info["type"], "subtype": info["subtype"], "source_group": group,
            "steps": [{"step": s, **STEPS[s]} for s in steps], "why": why,
            "llm_targets": [t["id"] for t in rest],
            "llm_classify_needed": info["type"] == "mixed" or not info["blocks"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.jsonl, encoding="utf-8") if l.strip()]
    os.makedirs(a.out, exist_ok=True)
    L = ["| # | 출처 | 유형 | 규칙 단계 (모델 호출 없음) | LLM 단계 | LLM 분류 필요 |",
         "| ---: | --- | --- | --- | --- | --- |"]
    for k, row in enumerate(rows, 1):
        info = analyze(row["src"], row["statement"], row.get("source", ""))
        plan = route(info, row["src"])
        plan["name"] = row["name"]
        json.dump(plan, open(os.path.join(a.out, f"P{k:02d}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rule_steps = [s["step"] for s in plan["steps"] if not s["model"]]
        L.append(f"| {k} | {row.get('source', '')} | {plan['type']}{'/' + plan['subtype'] if plan['subtype'] else ''} | "
                 f"{', '.join(rule_steps) or '-'} | llm_focus | {'예' if plan['llm_classify_needed'] else '아니오'} |")
    md = "\n".join(L) + "\n"
    open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write(md)
    print(md)


if __name__ == "__main__":
    main()
