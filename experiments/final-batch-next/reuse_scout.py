"""Issue #61's lexical diagnostic and a statement-only scout experiment."""

from difflib import SequenceMatcher
import re


def body_reuse(reference, candidate, statement):
    """Issue #61's simple tokens, not the Arena tokenizer or a score."""

    def tokens(text):
        body = text.removeprefix(statement)
        body = re.sub(r"--[^\n]*|/-.*?-/", " ", body, flags=re.S)
        return re.findall(r"[^\W\d][\w'.₀-₉]*|\d+|\S", body)

    original, final = tokens(reference), tokens(candidate)
    blocks = SequenceMatcher(None, original, final, autojunk=False).get_matching_blocks()
    return sum(block.size for block in blocks if block.size >= 3) / max(len(final), 1)


def use_scout(policy, source, reuse):
    return policy == "issue61" and source == "cslib" and reuse >= 0.95


def scout_packet(statement, legal_prefix):
    """No reference body, warm seed, draft, route hint, or previous feedback."""
    ids = set(re.findall(r"[\w.']{3,}", statement)) - {"theorem", "lemma", "Prop", "Type", "fun", "let"}
    hits = []
    for head in re.finditer(
        r"(?m)^[ \t]*(?:private |public |protected )?(?:lemma|theorem) ([\w.']+)([^\n]*)", legal_prefix
    ):
        signature = head[0].split(":=", 1)[0].strip()
        shared = ids.intersection(re.findall(r"[\w.']{3,}", signature))
        if shared:
            hits.append((len(shared), head.start(), head[1], signature))
    # Nearby declarations win lexical ties. Lean resolves actual accessibility.
    top = sorted(hits, reverse=True)[:4]
    return {
        "statement": statement,
        "preceding_heads": [item[3] for item in top],
        "premises": [item[2] for item in top],
        "instruction": "Construct a fresh proof from the statement and legal prior declarations.",
    }


def scout_candidate(packet):
    premises = packet["premises"]
    tactic = "solve_by_elim [" + ", ".join(premises) + "]" if premises else "exact?"
    return packet["statement"] + " := by\n  " + tactic
