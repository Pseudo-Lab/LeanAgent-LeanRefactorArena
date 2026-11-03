#!/usr/bin/env python3
"""Build a prompt-design JSON whose case prompts name common refactoring moves instead of a block type.

The moves come from comparing the warm-up originals with the team's final proofs (count_patterns.py).
A move is attached only when the original proof shows its signal; the specific moves come first and
the general "reuse an existing theorem" move last. The v4 `common_prompt` is copied unchanged, as in
../analyze-prompts, so the result runs in the budgeted API runner with `--prompt`.

No model call, no Lean. Reads only `problem.statement` and `problem.original`.

usage (repository root):
  python experiments/pattern-prompts/make_pattern_prompts.py --packets experiments/problem-inputs \
      --base experiments/prompt-design/p01-p05-reasoning-prompts.v4.en.json --out experiments/pattern-prompts
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "analyze-prompts"))
from make_prompts import OBJECTIVE, route_cue  # noqa: E402

PATTERNS = {
    "split_by_def": "The original splits with `induction {x}` and then unfolds `{f}`, which the statement applies "
                    "to `{x}`: split along the definition of `{f}` (for example `fun_induction {f} ...`).",
    "have_chain": "The original builds a long chain of `have` steps. Most of them can usually go: pass facts "
                  "directly as arguments, or replace the chain with one existing theorem.",
    "automation": "The original repeats broad automation ({what}). Use one narrowly targeted call "
                  "(`simp only [..]`, one closer) and do not run `simp_all` over all hypotheses.",
    "exact_form": "Where the original searches (`decide`, long normalisation, numeric case checks), give the "
                  "exact witness, bound or library equation instead, which is usually much cheaper in heartbeats.",
    "combinator": "Close goals that end the same way once, with `<;>`, `all_goals`, `first | .. | ..` or "
                  "`repeat`, instead of one block per goal.",
    "reuse": "Replace whole parts of the argument with an existing theorem from the context or the library that "
             "already states them, instead of re-proving their content.",
}
ORDER = list(PATTERNS)   # specific signals first, the general reuse move last
HAVE_MIN, CLOSER_MIN, CASE_MIN = 5, 5, 4
CLOSERS = ("simp_all", "omega", "linarith", "grind", "aesop", "norm_num")


def pattern_signals(statement: str, original: str) -> list[tuple[str, dict]]:
    """Moves whose signal appears in the original proof, in ORDER."""
    body = original[len(statement):] if original.startswith(statement) else original
    count = lambda w: len(re.findall(r"(?<![\w.])" + re.escape(w) + r"(?![\w])", body))
    out = {"reuse": {}}
    if count("have") >= HAVE_MIN:
        out["have_chain"] = {}
    heavy = [f"`{w}` x{n}" for w in CLOSERS if (n := count(w)) >= CLOSER_MIN]
    if heavy:
        out["automation"] = {"what": ", ".join(heavy)}
    if count("case") + count("cases") >= CASE_MIN:
        out["combinator"] = {}
    cue = route_cue(statement, original)
    if cue:
        out["split_by_def"] = {"x": cue[0], "f": cue[1]}
    if count("decide") or count("calc") or count("norm_num"):
        out["exact_form"] = {}
    return [(n, out[n]) for n in ORDER if n in out]


def pattern_prompt(statement: str, original: str) -> tuple[list[str], str]:
    sig = pattern_signals(statement, original)
    items = " ".join(f"({k + 1}) " + PATTERNS[n].format(**a) for k, (n, a) in enumerate(sig))
    text = ("Refactoring moves that shortened proofs of this kind, chosen from signals in the original proof. "
            + items + " Try the moves in this order; compile at least one complete candidate for each of the "
            "first two before polishing one, and if three candidates in a row do not lower the objective, move on. "
            + OBJECTIVE)
    return [n for n, _ in sig], text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packets", type=Path, required=True, help="experiments/problem-inputs")
    ap.add_argument("--base", type=Path, required=True, help="v4 prompt-design JSON (common_prompt is copied)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--problems", nargs="+", default=["P01", "P02", "P03", "P04", "P05"])
    a = ap.parse_args()
    base = json.loads(a.base.read_text(encoding="utf-8"))
    prompts, moves = {}, {}
    for p in a.problems:
        prob = json.loads((a.packets / p / "agent-input.json").read_text(encoding="utf-8"))["problem"]
        moves[p], prompts[p] = pattern_prompt(prob["statement"], prob["original"])
        print(p, moves[p])
    obj = {"version": "pattern", "status": "experiment_condition",
           "changes": ["common_prompt copied unchanged from " + a.base.name + ".",
                       "case prompts: common refactoring moves whose signal appears in the original proof "
                       "(make_pattern_prompts.py); no block type."],
           "moves": moves, "language": "en", "scope": a.problems, "agent_safe": True,
           "contains_reference_proofs_or_metrics": False, "derived_from": a.base.name,
           "common_prompt": base["common_prompt"], "case_prompts": prompts}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "prompts-pattern.en.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")


if __name__ == "__main__":
    main()
