"""Adapter-local candidate policy for the final dataset.

The public intake was inspected on 2026-11-01 at OFFICIAL_INTAKE_SOURCE.
Its targeted command patterns permit Finset cardinality, Array literals,
``#adaptation_note`` and aesop's ``add unsafe`` configuration.  The older
common harness conservatively rejects all ``#`` and ``unsafe`` occurrences.
This module keeps the common exact-statement/tactic-proof contract, the
public intake's executable/measurement exclusions, and the experiment's
additional prohibition on options and auxiliary declarations.  A successful
text check is not a Lean proof or a sandbox: the evaluator must also check
the complete source, target absence, generated axioms and pinned libraries.

Token counts remain the common versioned local metric.  ``length_audit``
records the separate historical line-boundary convention present in two
reference rows; it does not silently change the shared tokenizer.
"""
from __future__ import annotations

import re

from lean_agent.evaluator.tokens import proof_body, proof_tokens, without_comments

POLICY_ID = "final-single-tactic-public-intake-20261101-v1"
OFFICIAL_INTAKE_SOURCE = (
    "https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/da5f650/app.py"
)
OFFICIAL_INTAKE_REVISION = "da5f650"
MAX_PROOF_BYTES = 256 * 1024

# Independently grouped equivalents of the public intake's executable and
# trust-bypassing construct exclusions, followed by its contextual patterns.
_FORBIDDEN_WORDS = re.compile(
    r"\b(?:IO|extern|initialize|sorry|sorryAx|admit|axiom|native_decide|"
    r"ofReduceBool|ofReduceNat|run_cmd|run_elab|run_tacq?|by_elabq?|run_meta|"
    r"d?simproc(?:_decl|_pattern)?|unsafe(?:Base|E)?IO|macro|macro_rules|"
    r"elab|elab_rules|notation|syntax)\b"
)
_CONTEXTUAL_FORBIDDEN = (
    re.compile(r"#\s*(?:eval|reduce|exit|count_heartbeats)\b"),
    re.compile(r"\bunsafe\s+(?:def|fun|theorem|lemma)\b"),
    re.compile(r"@\[\s*implemented[_]?[Bb]y\b"),
    re.compile(r"\beval%"),
    re.compile(r"\+\s*native\b|\bnative\s*:=\s*true\b"),
    re.compile(r"(?m)^\s*attribute\b"),
    re.compile(r"\bderiving\s+instance\b"),
    re.compile(r"(?m)^\s*(?:def|abbrev|instance|structure|inductive|class|opaque)\b"),
)
_HEARTBEAT_IDENT = re.compile(r"[\w.'!?«»]*heartbeat[\w'!?«»]*", re.IGNORECASE)

# These are experiment restrictions beyond the public intake.  They preserve
# the single-declaration template boundary and fixed compiler configuration.
_EXTRA_BODY_FORBIDDEN = re.compile(
    r"\b(?:set_option|builtin_initialize|implemented_by|attribute|import|"
    r"namespace|section|end|def|abbrev|instance|structure|inductive|class|opaque|"
    r"theorem|lemma|example|variable|universe|export)\b"
)


def public_intake_rejection(code: str) -> str | None:
    """Return a diagnostic for the public source-pattern checks, if any."""
    try:
        size = len(code.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        return "invalid Unicode"
    if len(code) > MAX_PROOF_BYTES or size > MAX_PROOF_BYTES:
        return "proof exceeds public intake byte limit"
    stripped = without_comments(code)
    match = _FORBIDDEN_WORDS.search(stripped)
    if match:
        return "forbidden executable or trust construct: " + match.group()
    for pattern in _CONTEXTUAL_FORBIDDEN:
        match = pattern.search(stripped)
        if match:
            return "forbidden command or declaration: " + match.group().strip()
    for match in _HEARTBEAT_IDENT.finditer(stripped):
        name = match.group().replace("«", "").replace("»", "").split(".")[-1]
        if name != "maxHeartbeats":
            return "heartbeat measurement API: " + match.group()
    return None


def validate_declaration(declaration: str, statement: str) -> None:
    """Validate one exact-statement tactic declaration before executing Lean."""
    body = without_comments(proof_body(declaration, statement))
    if not re.match(r"\s*by\b", body):
        raise ValueError("Final batch accepts tactic proofs (:= by ...) only")
    rejection = public_intake_rejection(declaration)
    if rejection:
        raise ValueError(rejection)
    match = _EXTRA_BODY_FORBIDDEN.search(body)
    if match:
        raise ValueError("Auxiliary declaration, option or context command: " + match.group())


def length_audit(row: dict) -> dict:
    """Report the dataset denominator separately from common local tokens."""
    counted = proof_tokens(row["src"], row["statement"])
    declared = int(row["proof_length"])
    boundary = proof_body(row["src"], row["statement"])
    # The historical Appendix-J reconstruction counts the empty first line
    # after := when the reference puts `by` on the following line.  All sixty
    # dataset denominators are reproduced by this adjustment, but no worker
    # implementation-equivalence claim is made for arbitrary future syntax.
    historical = counted + int(bool(boundary) and not boundary.splitlines()[0].strip())
    return {
        "dataset_reference_tokens": declared,
        "local_reference_tokens": counted,
        "historical_boundary_reference_tokens": historical,
        "local_matches_dataset": counted == declared,
        "historical_boundary_matches_dataset": historical == declared,
        "official_worker_equivalence_verified": False,
    }
