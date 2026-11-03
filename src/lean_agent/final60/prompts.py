"""final60 routing prompt addendum: hint hygiene, rendering and placement.

Pure string functions, no I/O except reading the packaged playbooks. The addendum
is the only change routing makes to the frozen driver prompt (PR #62 measured that
changing the default prompt does not help). It is placed as one delimited block
directly before ``<original_context>`` so the driver's context extraction keeps
working and validation can strip it again byte-exactly.

Limits (design 7.2): at most 6 hints, each at most 300 characters, no inline Lean
snippet longer than 39 characters, the whole addendum at most 2,000 characters.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

MAX_HINTS = 6
MAX_HINT_CHARS = 300
MAX_LEAN_SNIPPET = 39
MAX_ADDENDUM_CHARS = 2000
MAX_PROMPT_CHARS = 60000

BEGIN = "<routing_notes>\n"
END = "\n</routing_notes>\n"
CONTEXT_MARKER = "<original_context>\n"
_RESERVED = ("<original_context", "</original_context", "<routing_notes", "</routing_notes")
# Lean-looking syntax that must stay inside backticks (prose never needs it).
_CODE_OUTSIDE_TICKS = re.compile(r":=|<;>|=>|[⟨⟩←·]|\bby\s+(?:simp|exact|intro|rw|cases|induction)\b")


@lru_cache(maxsize=None)
def playbooks() -> dict:
    return json.loads((DATA / "playbooks.json").read_text(encoding="utf-8"))


def flat(text: str) -> str:
    """Whitespace-flattened text, the same normalisation as the PR #70 checker."""
    return re.sub(r"\s+", " ", text).strip()


def lean_spans(text: str) -> list[str] | None:
    """Inline code spans in backticks, or None when backticks are unbalanced or fenced."""
    if "```" in text or text.count("`") % 2:
        return None
    return text.split("`")[1::2]


def hint_problems(text: str) -> list[str]:
    """Why a hint is unusable; [] means it satisfies every hint rule."""
    problems = []
    if not text:
        problems.append("empty")
    if len(text) > MAX_HINT_CHARS:
        problems.append(f"longer than {MAX_HINT_CHARS} characters")
    if "\n" in text:
        problems.append("contains a newline")
    if any(marker in text for marker in _RESERVED):
        problems.append("contains a reserved prompt marker")
    spans = lean_spans(text)
    if spans is None:
        problems.append("unbalanced or fenced backticks")
    else:
        if any(len(span) > MAX_LEAN_SNIPPET for span in spans):
            problems.append(f"Lean snippet longer than {MAX_LEAN_SNIPPET} characters")
        prose = "".join(text.split("`")[0::2])
        if _CODE_OUTSIDE_TICKS.search(prose):
            problems.append("Lean syntax outside backticks")
    return problems


def sanitize_hint(text: str) -> str | None:
    """Flatten whitespace; return None when the hint breaks a rule (never repairs code)."""
    if not isinstance(text, str):
        return None
    value = flat(text)
    return None if hint_problems(value) else value


def shorten(text: str, limit: int = MAX_HINT_CHARS) -> str:
    """Cut prose at the last sentence end within the limit (never inside a code span)."""
    value = flat(text)
    if len(value) <= limit:
        return value
    cut = value[:limit]
    ends = [m.end() for m in re.finditer(r"[.;!?](?=\s|$)", cut) if cut[:m.end()].count("`") % 2 == 0]
    return cut[:ends[-1]].strip() if ends else ""


def header(problem_type: str) -> str:
    return playbooks()["header"].format(problem_type=problem_type)


def render(problem_type: str, hints) -> str:
    """The delimited block for these hints; '' when there is nothing to say."""
    hints = list(hints)
    if not hints:
        return ""
    body = header(problem_type) + "\n" + "\n".join("- " + hint for hint in hints)
    return BEGIN + body + END


def prompt_addendum(route) -> str:
    """Addendum for a contracts.Route (empty for skip_llm rows or rows without hints)."""
    if route.skip_llm or not route.hints:
        return ""
    text = render(route.problem_type, route.hints)
    if len(text) > MAX_ADDENDUM_CHARS:
        raise ValueError(f"F{route.row:03} routing addendum exceeds {MAX_ADDENDUM_CHARS} characters")
    return text


def fit_hints(problem_type: str, hints, *, limit: int = MAX_ADDENDUM_CHARS, max_hints: int = MAX_HINTS) -> list[int]:
    """Indices of the hints kept, in order, so the rendered block stays within the limit."""
    kept = []
    for index, hint in enumerate(hints):
        if len(kept) >= max_hints:
            break
        trial = [hints[i] for i in kept] + [hint]
        if len(render(problem_type, trial)) <= limit:
            kept.append(index)
    return kept


def insert_addendum(prompt: str, addendum: str) -> str:
    """Place the block directly before the first <original_context> marker."""
    if not addendum:
        return prompt
    if not (addendum.startswith(BEGIN) and addendum.endswith(END)):
        raise ValueError("Routing addendum lacks its delimiters")
    if BEGIN in prompt:
        raise ValueError("Prompt already carries a routing addendum")
    if CONTEXT_MARKER not in prompt:
        raise ValueError("Prompt lacks the original context marker")
    head, tail = prompt.split(CONTEXT_MARKER, 1)
    result = head + addendum + CONTEXT_MARKER + tail
    if len(result) > MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt with routing addendum exceeds {MAX_PROMPT_CHARS} characters")
    return result


def split_addendum(prompt: str) -> tuple[str, str]:
    """Inverse of insert_addendum: (prompt without the block, the block or '')."""
    if CONTEXT_MARKER not in prompt:
        return prompt, ""
    head, tail = prompt.split(CONTEXT_MARKER, 1)
    start = head.find(BEGIN)
    if start < 0:
        return prompt, ""
    if not head.endswith(END) or head.find(BEGIN, start + 1) >= 0:
        raise ValueError("Malformed routing addendum placement")
    return head[:start] + CONTEXT_MARKER + tail, head[start:]
