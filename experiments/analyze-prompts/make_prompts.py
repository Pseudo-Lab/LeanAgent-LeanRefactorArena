#!/usr/bin/env python3
"""Build prompt-design JSON files for the budgeted API runner from the proof type only.

Block kinds come from ../proof-analyze (first word of each block: case, calc, have, other).
Two ways of turning the shares into a hint:
  hard  the strategy text of the largest kind only (one type per proof)
  soft  the shares of all kinds and the strategy texts of every kind at or above MIN_SHARE
Four conditions share the v4 `common_prompt` and differ only in `case_prompts`:
  common     empty case prompts (baseline)
  type-hard  hard hint
  type-soft  soft hint
  v4      hand-written case prompts (the existing v4 file, used as is)

No model call, no Lean. Reads only `problem.statement` and `problem.original` from
`experiments/problem-inputs/PXX/agent-input.json`.

usage (repository root):
  python experiments/analyze-prompts/make_prompts.py --packets experiments/problem-inputs \
      --base experiments/prompt-design/p01-p05-reasoning-prompts.v4.en.json --out experiments/analyze-prompts
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "proof-analyze"))
from analyze import analyze  # noqa: E402

MIN_SHARE = 25.0   # percent; a block kind contributes its strategy text at or above this share
STRATEGY = {
    "case": ("Branches: separately written branches often repeat the same steps. Before editing branches "
             "one by one, check whether several branches reach the same remaining goal after one "
             "normalization step, and whether a different way of splitting the cases lets one shared rule "
             "close them together. Keep a branch separate only if it needs its own argument."),
    "calc": ("Calculation steps: where a step can be shortened, first try these calculation shortcuts: "
             "(1) if the same computation appears more than once, prove one general equation once and reuse "
             "it with `simp only [..]`; (2) combine several arithmetic steps into one `ring` equation instead "
             "of stacking `have`s; (3) apply an existing library theorem directly with explicit values instead "
             "of re-proving its content; (4) apply the lexical options in the common instructions to the "
             "remaining steps. Do not unfold everything for one automation call: a short proof can still be "
             "expensive."),
    "have": ("Intermediate claims: keep every `have` that a later step actually needs; remove or inline only "
             "the claims that are unused or used once."),
}
NAMES = {"case": "`case` branches", "calc": "`calc` steps", "have": "`have` claims", "other": "other tactics"}


def case_prompt(statement: str, original: str, mode: str) -> tuple[list[str], str]:
    ks = analyze(original, statement)["kind_share"]
    order = sorted(ks.items(), key=lambda kv: -kv[1])
    if mode == "hard":
        top = next((k for k, v in order if k in STRATEGY), None)
        if top is None:
            return [], "No main block kind; start from the largest block."
        return [top], f"This proof is mainly {NAMES[top]} ({ks[top]}% of proof tokens). " + STRATEGY[top]
    shares = ", ".join(f"{NAMES[k]} {v}%" for k, v in order)
    chosen = [k for k, v in order if k in STRATEGY and v >= MIN_SHARE]
    text = f"Share of proof tokens by block kind in the original proof: {shares}."
    if chosen:
        text += (" Divide your effort in proportion to these shares. Strategy for each main kind, "
                 "in order of share: " + " ".join(STRATEGY[k] for k in chosen))
    else:
        text += " No main block kind; start from the largest block."
    return chosen, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packets", type=Path, required=True, help="experiments/problem-inputs")
    ap.add_argument("--base", type=Path, required=True, help="v4 prompt-design JSON (common_prompt is copied)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--problems", nargs="+", default=["P01", "P02", "P03", "P04", "P05"])
    a = ap.parse_args()
    base = json.loads(a.base.read_text(encoding="utf-8"))
    meta = {"language": "en", "scope": a.problems, "agent_safe": True,
            "contains_reference_proofs_or_metrics": False, "derived_from": a.base.name,
            "common_prompt": base["common_prompt"]}
    common = {"version": "common-only", "status": "experiment_condition",
              "changes": ["common_prompt copied unchanged from " + a.base.name + "; case prompts empty."],
              **meta, "case_prompts": {p: "" for p in a.problems}}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "prompts-common.en.json").write_text(json.dumps(common, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    packets = {p: json.loads((a.packets / p / "agent-input.json").read_text(encoding="utf-8"))["problem"]
               for p in a.problems}
    for mode, rule in (("hard", "strategy text of the largest block kind only"),
                       ("soft", f"block-kind shares and the strategy texts of kinds with share >= {MIN_SHARE}%")):
        prompts, kinds = {}, {}
        for p, prob in packets.items():
            kinds[p], prompts[p] = case_prompt(prob["statement"], prob["original"], mode)
        obj = {"version": "type-" + mode, "status": "experiment_condition",
               "changes": ["common_prompt copied unchanged from " + a.base.name + ".",
                           "case prompts: " + rule + " (make_prompts.py)."],
               "main_kinds": kinds, **meta, "case_prompts": prompts}
        (a.out / f"prompts-type-{mode}.en.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for p in a.problems:
            print(f"[{mode}] {p} {kinds[p]} {prompts[p][:120]}")


if __name__ == "__main__":
    main()
