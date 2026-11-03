#!/usr/bin/env python3
"""Build prompt-design JSON files for the budgeted API runner from the proof type only.

Block kinds come from ../proof-analyze (first word of each block: case, calc, have, other).
Three ways of turning the shares into a hint:
  hard   the strategy text of the largest kind only (one type per proof)
  soft   the shares of all kinds and the strategy texts of every kind at or above MIN_SHARE
  route  revised per-type text, plus a route cue, repeated-block locations and an objective sentence
Five conditions share the v4 `common_prompt` and differ only in `case_prompts`:
  common           empty case prompts (baseline)
  type-hard        hard hint
  type-soft        soft hint
  type-hard-route  route hint
  v4               hand-written case prompts (the existing v4 file, used as is)

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
# route mode: per-type strategy revised after the P01 comparison (type-hard kept unchanged above)
STRATEGY_ROUTE = {
    "case": (STRATEGY["case"] + " After choosing the split, close each branch with the cheapest step that works "
             "(`rfl`, `assumption`, `exact ..`, `simp only [..]`) before a broad `simp_all` or `grind` over all "
             "hypotheses: one blanket closer is short but can cost many heartbeats."),
    "calc": STRATEGY["calc"],
    "have": ("Intermediate claims: keep every `have` that a later step actually needs; remove or inline the ones "
             "that are unused or used once. If several claims, or two symmetric directions, differ only in names "
             "or values, prove one general `key` statement once and apply it to every instance (for example "
             "`simp only [key]` or `key _ _`) instead of repeating the argument."),
}
REPEAT = ("Near-duplicate blocks in the original declaration (line ranges {spans}). Consider one general "
          "statement proved once and reused for these places, if the objective improves.")
MENU_ITEMS = {
    "split_by_def": "split along the definition of `{f}` (for example `fun_induction {f} ...`), since the original "
                    "splits with `induction {x}` and then unfolds `{f}`",
    "no_induction": "no induction: build the goal directly from lemmas in the context about the predicates and "
                    "functions in the statement, as one chain of `refine`/`exact`/`rw`",
    "keep_split": "keep the original split; merge branches that end the same way and close them cheaply",
    "general_key": "prove one general `key` statement for the near-duplicate parts and reuse it",
    "library": "replace a long chain of steps with one existing library theorem or one cheap automation call",
    "keep_structure": "keep the original structure and shorten each step",
}
SWITCH = ("Route menu for this problem, in order: {items}. Compile at least one complete candidate on each of the "
          "first two routes before polishing one. If three candidates in a row do not lower the objective, switch "
          "to the next route in the menu instead of polishing further.")
OBJECTIVE = ("Judge every rewrite by the objective in the common instructions, which adds the token ratio and the "
             "heartbeat ratio: the shortest proof is not always the best. A helper lemma or a broad automation call "
             "is worth it only if what it saves in one ratio outweighs what it adds in the other.")


def _after(text: str, start: int) -> str:
    """Text after position `start` up to the end of the enclosing parenthesis group or line."""
    depth, out = 0, []
    for c in text[start:]:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif c == "\n" and depth == 0:
            break
        out.append(c)
    return "".join(out)


def route_cue(statement: str, original: str):
    """(x, f) if the original proof does `induction x`, unfolds or simps `f`, and the statement applies f to x.

    Reads only the original proof text and the statement. Unfolded names rank before simp-list names.
    """
    body = original[len(statement):] if original.startswith(statement) else original
    m = re.search(r"\binduction\s+([^\s<;]+)", body)
    if not m:
        return None
    x = m.group(1)
    flat = re.sub(r"\s+", " ", body)
    unfolded = [n for line in re.findall(r"\bunfold\s+([^\n]+)", body) for n in line.split()]
    simped = [n.strip() for lst in re.findall(r"\bsimp(?:_all)?(?: only)?\s*\[([^\]]*)\]", flat)
              for n in lst.split(",")]
    names = [n.lstrip("←").strip() for n in unfolded + simped]
    for f in dict.fromkeys(n for n in names if re.fullmatch(r"[\w.']+", n)):
        for occ in re.finditer(r"(?<![\w.])" + re.escape(f) + r"(?![\w'])", statement):
            if re.search(r"(?<![\w.])" + re.escape(x) + r"(?![\w'])", _after(statement, occ.end())):
                return x, f
    return None


def route_menu(top: str, cue: bool, repeats: bool) -> list[str]:
    """Ordered route options. The menu only names directions to try; it never contains a proof."""
    if top == "case":
        return (["split_by_def"] if cue else []) + ["no_induction", "keep_split"]
    return (["general_key"] if repeats else []) + ["library", "keep_structure"]


def case_prompt(statement: str, original: str, mode: str) -> tuple[list[str], str]:
    info = analyze(original, statement)
    ks = info["kind_share"]
    order = sorted(ks.items(), key=lambda kv: -kv[1])
    if mode in ("hard", "route"):
        top = next((k for k, v in order if k in STRATEGY), None)
        if top is None:
            return [], "No main block kind; start from the largest block."
        table = STRATEGY_ROUTE if mode == "route" else STRATEGY
        text = f"This proof is mainly {NAMES[top]} ({ks[top]}% of proof tokens). " + table[top]
        if mode == "route":
            cue = route_cue(statement, original) if top == "case" else None
            reps = [t for t in info["targets"] if t["kind"] == "repeat"]
            if reps:
                spans = "; ".join(" and ".join(f"{a}-{b}" for a, b in t["lines"]) for t in reps)
                text += " " + REPEAT.format(spans=spans)
            text += " " + SWITCH.format(items="; ".join(
                f"({k + 1}) " + MENU_ITEMS[i].format(x=cue[0] if cue else "", f=cue[1] if cue else "")
                for k, i in enumerate(route_menu(top, bool(cue), bool(reps)))))
            text += " " + OBJECTIVE
        return [top], text
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
                       ("soft", f"block-kind shares and the strategy texts of kinds with share >= {MIN_SHARE}%"),
                       ("route", "revised per-type strategy (cheap branch closers for case, one general key for have), "
                                 "plus a route cue when the original proof does `induction x` and unfolds a function "
                                 "the statement applies to x, the locations of repeated blocks, and an objective sentence")):
        prompts, kinds = {}, {}
        for p, prob in packets.items():
            kinds[p], prompts[p] = case_prompt(prob["statement"], prob["original"], mode)
        obj = {"version": "type-" + ("hard-route" if mode == "route" else mode), "status": "experiment_condition",
               "changes": ["common_prompt copied unchanged from " + a.base.name + ".",
                           "case prompts: " + rule + " (make_prompts.py)."],
               "main_kinds": kinds, **meta, "case_prompts": prompts}
        (a.out / f"prompts-type-{'hard-route' if mode == 'route' else mode}.en.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for p in a.problems:
            print(f"[{mode}] {p} {kinds[p]} {prompts[p][:120]}")


if __name__ == "__main__":
    main()
