"""Static proof checks run on every golf variant before any Lean compile.

Three rule sets, all text-only (no Lean, no network):

1. ``official``: the Space intake check, copied verbatim from
   delta-lab-ai/lean-refactor-arena ``app.py`` (``_FORBIDDEN_PATTERNS``, ``_HEARTBEAT_IDENT``,
   ``_MAX_PROOF_BYTES``, ``_strip_lean_comments``, ``_check_forbidden``) as fetched for the
   final60 design on 2026-11-04 02:12 KST (``design/refs/hf-space/app.py``). The team
   policy module documents the same intake at revision da5f650.
2. ``pr64``: ``scripts/check_submission_rules.py`` ``check_row`` from PR #64 (head c834dc1):
   column-0 commands, ``unsafe`` outside ``aesop (add unsafe ...)`` and its own pattern list.
3. ``policy``: ``experiments/final-batch-next/policy.py`` ``validate_declaration``, the gate
   FinalEvaluator applies to every non-reference candidate (tactic proof only, no options or
   auxiliary declarations). Checking it here only saves compiles.

``check_static`` returns a list of issues; an empty list means the text may be compiled.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[3]
OFFICIAL_SOURCE = ("https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena app.py "
                   "(copy fetched 2026-11-04 02:12 KST)")
PR64_SOURCE = "Pseudo-Lab/LeanAgent-LeanRefactorArena PR #64 scripts/check_submission_rules.py @ c834dc1"

# ---- 1. official intake (verbatim copy) ---------------------------------------------------
_FORBIDDEN_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("#eval", re.compile(r"#\s*eval\b")),
    ("#reduce", re.compile(r"#\s*reduce\b")),
    ("IO", re.compile(r"\bIO\b")),
    ("unsafe def/fun/theorem", re.compile(r"\bunsafe\s+(def|fun|theorem|lemma)\b")),
    ("extern", re.compile(r"\bextern\b")),
    ("initialize", re.compile(r"\binitialize\b")),
    ("@[implemented_by]", re.compile(r"@\[\s*implemented[_]?[Bb]y\b")),
    ("@[extern]", re.compile(r"@\[\s*extern\b")),
    ("sorry", re.compile(r"\bsorry\b")),
    ("sorryAx", re.compile(r"\bsorryAx\b")),
    ("admit", re.compile(r"\badmit\b")),
    ("axiom", re.compile(r"\baxiom\b")),
    ("native_decide", re.compile(r"\bnative_decide\b")),
    ("ofReduceBool", re.compile(r"\bofReduceBool\b")),
    ("ofReduceNat", re.compile(r"\bofReduceNat\b")),
    ("run_cmd", re.compile(r"\brun_cmd\b")),
    ("run_elab", re.compile(r"\brun_elab\b")),
    ("run_tac", re.compile(r"\brun_tacq?\b")),
    ("by_elab", re.compile(r"\bby_elabq?\b")),
    ("run_meta", re.compile(r"\brun_meta\b")),
    ("simproc", re.compile(r"\bd?simproc(?:_decl|_pattern)?\b")),
    ("eval%", re.compile(r"\beval%")),
    ("unsafe IO", re.compile(r"\bunsafe(?:Base|E)?IO\b")),
    ("decide +native", re.compile(r"\+\s*native\b|\bnative\s*:=\s*true\b")),
    ("#exit", re.compile(r"#\s*exit\b")),
    ("#count_heartbeats", re.compile(r"#\s*count_heartbeats\b")),
    ("attribute command", re.compile(r"(?m)^\s*attribute\b")),
    ("macro/elab/notation", re.compile(
        r"\b(macro|macro_rules|elab|elab_rules|notation|syntax)\b")),
    ("deriving instance", re.compile(r"\bderiving\s+instance\b")),
    ("auxiliary declaration", re.compile(
        r"(?m)^\s*(def|abbrev|instance|structure|inductive|class|opaque)\b")),
]

_HEARTBEAT_IDENT = re.compile(r"[\w.'!?«»]*heartbeat[\w'!?«»]*", re.IGNORECASE)

# Real proofs are a few KB; anything past this is resource exhaustion.
_MAX_PROOF_BYTES = 256 * 1024


def _strip_lean_comments(text: str) -> str:
    """Drop `/- … -/` blocks (nested) and `--` line tails (official scanner)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            out.append(c)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if text.startswith("/-", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/-", i):
                    depth += 1
                    i += 2
                elif text.startswith("-/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            out.append(" ")
            continue
        if text.startswith("--", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _check_forbidden(code: str) -> str | None:
    if (len(code) > _MAX_PROOF_BYTES
            or len(code.encode("utf-8", errors="surrogatepass")) > _MAX_PROOF_BYTES):
        return f"too large (> {_MAX_PROOF_BYTES // 1024} KiB of UTF-8 source)"
    stripped = _strip_lean_comments(code)
    for label, pat in _FORBIDDEN_PATTERNS:
        if pat.search(stripped):
            return label
    # Heartbeat APIs (get/set/addHeartbeats, …) tamper with the measurement;
    for m in _HEARTBEAT_IDENT.finditer(stripped):
        if m.group().replace("«", "").replace("»", "").split(".")[-1] != "maxHeartbeats":
            return f"{m.group()} (heartbeat measurement)"
    return None


# ---- 2. PR #64 static rules (copy of check_row) -------------------------------------------
_PR64_FORBIDDEN = [
    (r"#eval\b", "#eval"), (r"#reduce\b", "#reduce"), (r"(?<![\w.])IO\.", "IO"),
    (r"\bextern\b", "extern"), (r"\binitialize\b", "initialize"), (r"implemented_by", "implemented_by"),
    (r"\bsorry\b", "sorry"), (r"\badmit\b", "admit"), (r"\baxiom\b", "axiom"),
    (r"native_decide", "native_decide"), (r"decide\s*\+\s*native", "decide +native"), (r"ofReduceBool", "ofReduceBool"),
    (r"#count_heartbeats", "#count_heartbeats"), (r"getNumHeartbeats|withHeartbeats", "heartbeat API"),
    (r"\brun_tac\b", "run_tac"), (r"\bby_elab\b", "by_elab"), (r"\brun_meta\b", "run_meta"),
    (r"\bd?simproc\b", "simproc"), (r"eval%", "eval%"),
]
_PR64_TOP_LEVEL = re.compile(r"(?m)^(def|instance|attribute|macro|notation|syntax|theorem|lemma|abbrev|axiom|opaque|"
                             r"structure|inductive|class|open|namespace|section|end|set_option|@\[)\b")
_PR64_MAX_BYTES = 256 * 1024


def _pr64_strip_comments(text: str) -> str:
    return re.sub(r"--[^\n]*|/-.*?-/", " ", text, flags=re.S)


def pr64_issues(statement: str, proof: str) -> list[str]:
    issues = []
    if not proof.startswith(statement):
        issues.append("statement differs from the benchmark statement")
    body = _pr64_strip_comments(proof[len(statement):] if proof.startswith(statement) else proof)
    issues += [f"forbidden: {label}" for pattern, label in _PR64_FORBIDDEN if re.search(pattern, body)]
    for match in re.finditer(r"\bunsafe\b", body):
        if not re.search(r"add\s*$", body[max(0, match.start() - 12):match.start()]):
            issues.append("unsafe outside `aesop (add unsafe ...)`")
    if (m := _PR64_TOP_LEVEL.search(body)):
        issues.append(f"extra top-level command: {m.group(0)}")
    if len(proof.encode("utf-8")) > _PR64_MAX_BYTES:
        issues.append("proof exceeds 256 KiB")
    return issues


# ---- 3. team evaluator policy -----------------------------------------------------------
_policy = None


def _validate_declaration():
    global _policy
    if _policy is None:
        spec = importlib.util.spec_from_file_location(
            "final60_rules_policy", REPO / "experiments/final-batch-next/policy.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _policy = module.validate_declaration
    return _policy


def official_rejection(proof: str) -> str | None:
    """The Space intake verdict for a submitted proof text (None = accepted)."""
    return _check_forbidden(proof)


def check_static(proof: str, statement: str) -> list[str]:
    """All static issues of ``proof`` for ``statement``; [] means it may be compiled."""
    if not isinstance(proof, str) or not isinstance(statement, str):
        return ["proof and statement must be strings"]
    issues = []
    if not proof.startswith(statement):
        issues.append("statement: the theorem statement must be preserved byte-for-byte")
    try:
        rejection = _check_forbidden(proof)
    except (UnicodeError, ValueError) as exc:  # e.g. lone surrogates
        rejection = "invalid text: " + type(exc).__name__
    if rejection:
        issues.append("official: " + rejection)
    issues += ["pr64: " + issue for issue in pr64_issues(statement, proof)
               if issue != "statement differs from the benchmark statement"]
    if proof.startswith(statement):
        try:
            _validate_declaration()(proof, statement)
        except ValueError as exc:
            issues.append("policy: " + str(exc))
    return list(dict.fromkeys(issues))
