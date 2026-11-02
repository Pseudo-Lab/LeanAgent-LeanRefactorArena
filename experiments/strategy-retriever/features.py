"""Static features of an original proof for rule-based strategy retrieval.

No Lean and no model call: reads only the statement and the original declaration text.
Block shares come from ../proof-analyze (PR #25). The route cue is the rule of PR #36
(type-hard-route) and the count signals follow PR #38 (pattern prompts).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "proof-analyze"))
from analyze import analyze  # noqa: E402

CLOSERS = ("simp_all", "omega", "linarith", "nlinarith", "grind", "aesop", "norm_num", "positivity")
COUNTED = ("have", "case", "cases", "rcases", "obtain", "induction", "simp", "simp_all", "decide", "calc",
           "norm_num", "exact", "apply", "refine", "constructor", "intro", "unfold", "rw") + CLOSERS
MAIN_SHARE = 50.0  # percent of proof tokens for a block kind to count as the main kind


def _body(statement: str, original: str) -> str:
    return original[len(statement):] if original.startswith(statement) else original


def _after(text: str, start: int) -> str:
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
    """(x, f) if the proof does `induction x`, unfolds or simps `f`, and the statement applies f to x (#36)."""
    body = _body(statement, original)
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


def features(statement: str, original: str) -> dict:
    """Counts, block shares and tags. Tags are the vocabulary used by bank `match` conditions."""
    body = _body(statement, original)
    count = {w: len(re.findall(r"(?<![\w.])" + re.escape(w) + r"(?![\w'])", body)) for w in COUNTED}
    try:
        info = analyze(original, statement)
    except ValueError:  # one-line proofs have no blocks
        info = {"kind_share": {}, "targets": [], "proof_length": None}
    share = info["kind_share"]
    cue = route_cue(statement, original)
    tags = set()
    for kind in ("case", "have", "calc"):
        if share.get(kind, 0) >= MAIN_SHARE:
            tags.add(f"{kind}_main")
    if cue:
        tags.add("route_cue")
    if any(t["kind"] == "repeat" for t in info["targets"]):
        tags.add("repeated_blocks")
    if any(count[w] >= 5 for w in CLOSERS):
        tags.add("repeated_automation")
    if count["decide"] or count["calc"] or count["norm_num"]:
        tags.add("search_or_calculation")
    if re.search(r"\.elim\b", body) or len(re.findall(r"\bfun\b", body)) >= 3:
        tags.add("proof_terms")
    if re.search(r"\bsimp(?:_all)?(?: only)?\s*\[[^\]]*,[^\]]*,", body):
        tags.add("simp_lists")
    return {"counts": count, "kind_share": share, "route_cue": list(cue) if cue else None,
            "tags": sorted(tags), "tokens": info.get("proof_length")}
