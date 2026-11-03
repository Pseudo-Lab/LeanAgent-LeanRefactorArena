"""Deterministic proof rewrites for golf: pure string functions, no Lean, no model.

Every rewrite is generic (it matches proof structure, never a row-specific literal) and
only produces *proposals*; golf accepts one only after a Lean screen shows a higher
official score. Positions are computed on a comment-masked copy of the declaration so a
commented-out tactic is never edited.

Public functions return ``list[(name, new_code)]`` (one edit applied each). The ``*_edits``
helpers return span ``Edit`` objects so golf can batch non-overlapping edits and split a
failing batch (ddmin-style) without recomputing positions.

Passes:
  G1 ``linter_edits``     warnings in a compile log inside the declaration: unused simp
                          arguments (PR #63 format, positions from Lean), unused ``have``
                          names, tactics reported as doing nothing or never executed.
  G2 ``closer_probe``     replace terminal blocks by ``try?``; ``apply_suggestions`` parses
                          "Try this" / "Try these" output (plain, ``[apply]`` and diff forms).
  G3 ``local_rewrites``   ``by exact t`` -> ``t``, merged rw/intro/simp-only lines,
                          ``simp .. at h; exact h`` -> ``simpa .. using h``, identical bullets
                          -> ``<;>``, eta, ``exact rfl`` -> ``rfl``, ``refine ⟨?_, ?_⟩`` ->
                          ``constructor``, ``apply f; exact h`` -> ``exact f h``,
                          ``simp only [..]`` -> ``simp``.
  G4 ``deletion_edits``   ``clear`` and ``show`` lines, ``have`` blocks whose name is never
                          referenced later; ``ddmin_batches`` enumerates batch deletions.
  G5 ``decide_variants``  generic kernel-decision forms for tiny ``decide`` proofs.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

BULLETS = ("·", ".")
SUGGESTION_BLOCKLIST = re.compile(r"\b(?:sorry|admit|native_decide)\b|\?(?:\s|$)|\b(?:exact|apply|rw|simp|try|aesop|hint)\?")


@dataclass(frozen=True)
class Edit:
    name: str
    start: int
    end: int
    replacement: str


# ---- basic text structure ---------------------------------------------------------------
def mask_comments(text: str) -> str:
    """Same-length copy with comments (nested) replaced by spaces; strings kept."""
    chars, i, n = list(text), 0, len(text)
    while i < n:
        if text[i] == '"':
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
        elif text.startswith("--", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            for j in range(i, end):
                chars[j] = " "
            i = end
        elif text.startswith("/-", i):
            begin, depth = i, 1
            i += 2
            while i < n and depth:
                if text.startswith("/-", i):
                    depth += 1
                    i += 2
                elif text.startswith("-/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            for j in range(begin, min(i, n)):
                if chars[j] != "\n":
                    chars[j] = " "
        else:
            i += 1
    return "".join(chars)


def by_offset(code: str, statement: str) -> int:
    """Index just after the top-level ``by`` that follows ``statement :=``."""
    if not code.startswith(statement):
        raise ValueError("The theorem statement must be preserved byte-for-byte")
    masked = mask_comments(code)
    match = re.compile(r"\s*:=\s*by\b").match(masked, len(statement))
    if not match:
        raise ValueError("Expected := by after the statement")
    return match.end()


def line_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each line, end excluding the newline."""
    spans, start = [], 0
    for index, char in enumerate(text):
        if char == "\n":
            spans.append((start, index))
            start = index + 1
    spans.append((start, len(text)))
    return spans


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def subtree_end(lines: list[str], index: int, base_indent: int | None = None) -> int:
    """Index after the last line belonging to line ``index`` (deeper indent continues it)."""
    base = indent_of(lines[index]) if base_indent is None else base_indent
    j = index + 1
    last = index
    while j < len(lines):
        if lines[j].strip():
            if indent_of(lines[j]) <= base:
                break
            last = j
        j += 1
    return last + 1


class Layout:
    """Line view of one declaration with masked text and the first tactic line."""

    def __init__(self, code: str, statement: str):
        self.code, self.statement = code, statement
        self.masked = mask_comments(code)
        self.by_end = by_offset(code, statement)
        self.spans = line_spans(code)
        self.lines = [code[a:b] for a, b in self.spans]
        self.mlines = [self.masked[a:b] for a, b in self.spans]
        self.by_line = next(i for i, (a, b) in enumerate(self.spans) if a <= self.by_end <= b)
        inline = self.masked[self.by_end:self.spans[self.by_line][1]].strip()
        self.inline = bool(inline)
        self.first = self.by_line if self.inline else self.by_line + 1

    def offset(self, line: int, column: int = 0) -> int:
        return self.spans[line][0] + column

    def line_of(self, position: int) -> int:
        for i, (a, b) in enumerate(self.spans):
            if a <= position <= b:
                return i
        return len(self.spans) - 1

    def tactic_lines(self):
        return [i for i in range(self.by_line + 1, len(self.lines)) if self.mlines[i].strip()]

    def delete_lines(self, start: int, stop: int) -> tuple[int, int]:
        """Span removing whole lines [start, stop) including one newline."""
        a = self.spans[start][0]
        b = self.spans[stop - 1][1]
        if b < len(self.code) and self.code[b] == "\n":
            b += 1
        elif a > 0 and self.code[a - 1] == "\n":
            a -= 1
        return a, b


def apply_edits(code: str, edits) -> str | None:
    """Apply non-overlapping edits; None if any two overlap."""
    ordered = sorted(edits, key=lambda e: (e.start, e.end))
    for left, right in zip(ordered, ordered[1:]):
        if right.start < left.end:
            return None
    out = code
    for edit in reversed(ordered):
        out = out[:edit.start] + edit.replacement + out[edit.end:]
    return out


def non_overlapping(edits) -> list[Edit]:
    """Greedy, in priority order, then sorted by position."""
    chosen = []
    for edit in edits:
        if all(edit.end <= other.start or other.end <= edit.start for other in chosen):
            chosen.append(edit)
    return sorted(chosen, key=lambda e: (e.start, e.end))


def singles(code: str, edits) -> list[tuple[str, str]]:
    out, seen = [], set()
    for edit in edits:
        new = apply_edits(code, [edit])
        if new is not None and new != code and new not in seen:
            seen.add(new)
            out.append((edit.name, new))
    return out


# ---- Lean message parsing ----------------------------------------------------------------
_HEADER = re.compile(r"^(?P<file>[^\n]*?):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>error|warning|info|information)"
                     r"(?:\([^)]*\))?:\s?(?P<text>.*)$")


@dataclass(frozen=True)
class Message:
    line: int          # 1-based, file relative
    col: int           # 0-based codepoints
    severity: str
    text: str


def parse_messages(log: str) -> list[Message]:
    messages, current = [], None
    for raw in log.splitlines():
        match = _HEADER.match(raw)
        if match:
            if current:
                messages.append(Message(current[0], current[1], current[2], "\n".join(current[3])))
            current = (int(match["line"]), int(match["col"]), match["sev"], [match["text"]])
        elif current is not None:
            current[3].append(raw)
    if current:
        messages.append(Message(current[0], current[1], current[2], "\n".join(current[3])))
    return messages


def clean_markup(text: str) -> str:
    """Drop Lean's plain-text diff markup: struck characters are deleted, marks removed."""
    out = []
    for char in text:
        if char in "̵̶̷̸":
            if out:
                out.pop()
            continue
        if unicodedata.combining(char) and char in "̲̳̱":
            continue
        out.append(char)
    return "".join(out)


def suggestions(message: Message) -> list[str]:
    """Tactic texts offered by a "Try this:" / "Try these:" message, in order."""
    text = clean_markup(message.text)
    match = re.search(r"Try (?:this|these):[ \t]*", text)
    if not match:
        return []
    rest = text[match.end():]
    lines = rest.split("\n")
    items: list[list[str]] = []
    inline = lines[0].strip()
    marker = re.compile(r"^(\s*)(?:\[apply\]|•|\*)\s*(.*)$")
    if inline:
        start = marker.match(lines[0])
        items.append([start[2] if start else inline])
        lines = lines[1:]
        item_indent = 0
    else:
        item_indent = None
    for raw in lines:
        if not raw.strip():
            if items and item_indent is None:
                continue
            item_indent = None if not items else item_indent
            continue
        stripped = raw.strip()
        if stripped.startswith("--"):
            item_indent = -1          # remaining-goals commentary ends the item
            continue
        found = marker.match(raw)
        if found and found[2]:
            items.append([found[2]])
            item_indent = len(found[1])
            continue
        if items and item_indent is not None and item_indent >= 0 and indent_of(raw) > item_indent:
            items[-1].append(stripped)
            continue
        if not items and indent_of(raw) > 0:
            items.append([stripped])
            item_indent = indent_of(raw) - 1
            continue
        if indent_of(raw) == 0:
            break                       # explanatory prose after the suggestions
    out = []
    for item in items:
        tactic = " ".join(part for part in item if part).strip()
        if tactic and not SUGGESTION_BLOCKLIST.search(tactic) and tactic not in out:
            out.append(tactic)
    return out


def _declaration_window(code: str, message: Message, decl_start_line: int):
    local = message.line - decl_start_line
    lines = code.count("\n") + 1
    return local if 0 <= local < lines else None


# ---- G1: linter-guided edits -------------------------------------------------------------
def _bracket_scan(text: str, start: int) -> int:
    """End of one simp argument beginning at ``start`` (stops at top-level ',' or ']')."""
    depth, i = 0, start
    pairs = {"(": ")", "[": "]", "{": "}", "⟨": "⟩"}
    closing = set(pairs.values())
    while i < len(text):
        char = text[i]
        if char in pairs:
            depth += 1
        elif char in closing:
            if depth == 0:
                break
            depth -= 1
        elif char == "," and depth == 0:
            break
        i += 1
    while i > start and text[i - 1] in " \t\n":
        i -= 1
    return i


def _remove_simp_argument(layout: Layout, position: int) -> Edit | None:
    text = layout.masked
    if position >= len(text) or position < layout.by_end:
        return None
    # Lean may point at the lemma name of `← lemma`; the arrow belongs to the argument.
    lead = position
    while lead > 0 and text[lead - 1] in " \t":
        lead -= 1
    for arrow in ("←", "<-"):
        if text[max(0, lead - len(arrow)):lead] == arrow:
            position = lead - len(arrow)
            break
    end = _bracket_scan(text, position)
    if end <= position:
        return None
    after = end
    while after < len(text) and text[after] in " \t\n":
        after += 1
    before = position
    while before > 0 and text[before - 1] in " \t\n":
        before -= 1
    if after < len(text) and text[after] == ",":
        stop = after + 1
        while stop < len(text) and text[stop] in " \t":
            stop += 1
        return Edit("G1:unused-simp-arg", position, stop, "")
    if before > 0 and text[before - 1] == ",":
        return Edit("G1:unused-simp-arg", before - 1, end, "")
    if before > 0 and text[before - 1] == "[" and after < len(text) and text[after] == "]":
        open_at = before - 1
        lead = open_at
        while lead > 0 and text[lead - 1] in " \t":
            lead -= 1
        return Edit("G1:unused-simp-arg", lead, after + 1, "")
    return None


def _segment_deletion(layout: Layout, position: int, name: str) -> Edit | None:
    """Delete one tactic starting at ``position``: a whole line, or one ``<;>``/``;`` segment."""
    line = layout.line_of(position)
    if line <= layout.by_line and not (line == layout.by_line and layout.inline):
        return None
    start_of_line = layout.spans[line][0]
    before = layout.masked[start_of_line:position]
    if not before.strip() and line > layout.by_line:
        stop = subtree_end(layout.mlines, line)
        a, b = layout.delete_lines(line, stop)
        return Edit(name, a, b, "")
    stripped = before.rstrip()
    for separator in ("<;>", ";"):
        if stripped.endswith(separator):
            sep_at = start_of_line + len(stripped) - len(separator)
            lead = sep_at
            while lead > start_of_line and layout.masked[lead - 1] in " \t":
                lead -= 1
            end = layout.spans[line][1]
            rest = layout.masked[position:end]
            cut = [m.start() for m in re.finditer(r"<;>|;", rest)]
            stop = position + (cut[0] if cut else len(rest.rstrip()))
            while stop > position and layout.masked[stop - 1] in " \t":
                stop -= 1
            return Edit(name, lead, stop, "")
    return None


def _have_block(layout: Layout, line: int) -> tuple[int, int] | None:
    """[start, stop) lines of a ``have`` that occupies whole lines."""
    if line <= layout.by_line:
        return None
    if not re.match(r"\s*(?:·\s*)?have\b", layout.mlines[line]):
        return None
    if re.match(r"\s*·", layout.mlines[line]):
        return None
    return line, subtree_end(layout.mlines, line)


def linter_span_edits(code: str, statement: str, log: str, decl_start_line: int) -> list[Edit]:
    layout = Layout(code, statement)
    edits: list[Edit] = []
    for message in parse_messages(log):
        if message.severity != "warning":
            continue
        local = _declaration_window(code, message, decl_start_line)
        if local is None:
            continue
        position = layout.offset(local, min(message.col, len(layout.lines[local])))
        text = message.text
        if text.startswith("This simp argument is unused"):
            edit = _remove_simp_argument(layout, position)
            if edit:
                edits.append(edit)
        elif (found := re.match(r"unused variable `([^`]+)`", text)):
            name = found[1]
            prefix = layout.masked[layout.spans[local][0]:position]
            if re.search(r"\bhave\s+$", prefix) and layout.masked.startswith(name, position):
                block = _have_block(layout, local)
                if block:
                    a, b = layout.delete_lines(*block)
                    edits.append(Edit("G1:drop-unused-have", a, b, ""))
                after = position + len(name)
                if re.match(r"\s*:", layout.masked[after:]):
                    edits.append(Edit("G1:anonymous-have", position - 1, after, ""))
        elif re.search(r"tactic does nothing|this tactic is never executed|is never executed", text):
            edit = _segment_deletion(layout, position, "G1:unused-tactic")
            if edit:
                edits.append(edit)
    unique, seen = [], set()
    for edit in edits:
        key = (edit.start, edit.end, edit.replacement)
        if key not in seen:
            seen.add(key)
            unique.append(edit)
    return unique


def linter_edits(code: str, statement: str, log: str, decl_start_line: int) -> list[tuple[str, str]]:
    return singles(code, linter_span_edits(code, statement, log, decl_start_line))


def declaration_start_line(source: str, code: str) -> int | None:
    """1-based line of ``code`` inside a compiled source file (PR #63 convention)."""
    at = source.find(code)
    return None if at < 0 else source.count("\n", 0, at) + 1


# ---- G3: local rewrites --------------------------------------------------------------------
_RW = re.compile(r"^(?P<indent> *)(?P<tac>rw|rewrite|rwa)\s*\[(?P<args>[^\[\]\n]*)\](?P<loc>\s+at\s+[^\n;]+?)?\s*$")
_INTRO = re.compile(r"^(?P<indent> *)intro\s+(?P<names>[^\n;<>]+?)\s*$")
_SIMP_ONLY = re.compile(r"^(?P<indent> *)simp only\s*\[(?P<args>[^\[\]\n]*)\](?P<loc>\s+at\s+[^\n;]+?)?\s*$")
_SIMP_AT = re.compile(r"^(?P<indent> *)simp(?P<only> only)?(?P<args>\s*\[[^\[\]\n]*\])?\s+at\s+(?P<hyp>[\w.'₀-₉]+)(?:\s+⊢)?\s*$")
_EXACT_ID = re.compile(r"^(?P<indent> *)exact\s+(?P<term>[\w.'₀-₉]+)\s*$")
_APPLY = re.compile(r"^(?P<indent> *)apply\s+(?P<fn>[^\n;<>]+?)\s*$")
_BULLET = re.compile(r"^(?P<indent> *)[·.]\s+(?P<body>\S[^\n]*?)\s*$")


def _single_line(layout: Layout, line: int) -> bool:
    return subtree_end(layout.mlines, line) == line + 1


def _block_end(layout: Layout, line: int) -> bool:
    """True if no further sibling follows ``line`` at the same indent in its block."""
    base = indent_of(layout.mlines[line])
    for j in range(subtree_end(layout.mlines, line), len(layout.mlines)):
        if layout.mlines[j].strip():
            return indent_of(layout.mlines[j]) < base
    return True


def _merge_runs(layout: Layout, pattern, combine, name) -> list[Edit]:
    edits, i, lines = [], layout.by_line + 1, layout.mlines
    while i < len(lines):
        match = pattern.match(lines[i])
        if not match or not _single_line(layout, i):
            i += 1
            continue
        run = [match]
        j = i + 1
        while j < len(lines):
            follow = pattern.match(lines[j])
            if not follow or follow["indent"] != match["indent"] or not _single_line(layout, j):
                break
            if not combine(run + [follow]):
                break
            run.append(follow)
            j += 1
        if len(run) > 1:
            replacement = combine(run)
            a = layout.spans[i][0]
            b = layout.spans[j - 1][1]
            edits.append(Edit(name, a, b, replacement))
        i = j if len(run) > 1 else i + 1
    return edits


def _combine_rw(run):
    locations = {(m["loc"] or "").strip() for m in run}
    if len(locations) != 1 or any(m["tac"] == "rwa" for m in run[:-1]):
        return None
    if any(not m["args"].strip() for m in run):
        return None
    loc = run[0]["loc"] or ""
    return f"{run[0]['indent']}{run[-1]['tac']} [{', '.join(m['args'].strip() for m in run)}]{loc}"


def _combine_intro(run):
    return f"{run[0]['indent']}intro {' '.join(m['names'].strip() for m in run)}"


def _combine_simp_only(run):
    locations = {(m["loc"] or "").strip() for m in run}
    if len(locations) != 1 or any(not m["args"].strip() for m in run):
        return None
    return f"{run[0]['indent']}simp only [{', '.join(m['args'].strip() for m in run)}]{run[0]['loc'] or ''}"


def _term_by_exact(layout: Layout) -> list[Edit]:
    edits = []
    pattern = re.compile(r"(?P<lead>:=|\(|⟨|,|=>)(?P<space>\s*)by\s+exact\s+")
    for match in pattern.finditer(layout.masked, layout.by_end):
        start = match.start("space")
        edits.append(Edit("G3:by-exact-term", start, match.end(), " " if match["lead"] in (":=", "=>", ",") else ""))
    return edits


def _simpa(layout: Layout) -> list[Edit]:
    edits = []
    for i in range(layout.by_line + 1, len(layout.mlines) - 1):
        simp = _SIMP_AT.match(layout.mlines[i])
        if not simp or not _single_line(layout, i):
            continue
        j = i + 1
        exact = _EXACT_ID.match(layout.mlines[j])
        if not exact or exact["indent"] != simp["indent"] or exact["term"] != simp["hyp"]:
            continue
        if not _single_line(layout, j):
            continue
        replacement = f"{simp['indent']}simpa{simp['only'] or ''}{simp['args'] or ''} using {simp['hyp']}"
        edits.append(Edit("G3:simpa-using", layout.spans[i][0], layout.spans[j][1], replacement))
    return edits


def _bullets(layout: Layout) -> list[Edit]:
    edits = []
    lines = layout.mlines
    for i in range(layout.by_line + 1, len(lines)):
        head = lines[i]
        if not head.strip() or not _single_line(layout, i) or re.match(r"\s*[·.]", head):
            continue
        indent = indent_of(head)
        bodies, j, last = [], i + 1, i
        while j < len(lines):
            if not lines[j].strip():
                j += 1
                continue
            bullet = _BULLET.match(lines[j])
            if not bullet or len(bullet["indent"]) != indent or not _single_line(layout, j):
                break
            bodies.append(bullet["body"])
            last = j
            j += 1
        if len(bodies) >= 2 and len(set(bodies)) == 1 and _ends_block(layout, j, indent):
            replacement = f"{head.rstrip()} <;> {bodies[0]}"
            edits.append(Edit("G3:identical-bullets", layout.spans[i][0], layout.spans[last][1], replacement))
    return edits


def _ends_block(layout: Layout, j: int, indent: int) -> bool:
    for k in range(j, len(layout.mlines)):
        if layout.mlines[k].strip():
            return indent_of(layout.mlines[k]) < indent
    return True


def _eta(layout: Layout) -> list[Edit]:
    edits = []
    pattern = re.compile(r"(?P<open>\(?)fun\s+(?P<x>[A-Za-z_][\w']*)\s*=>\s*(?P<f>[A-Za-z_][\w.']*)\s+(?P=x)(?![\w'.₀-₉])")
    for match in pattern.finditer(layout.masked, layout.by_end):
        if match["x"] in re.split(r"[.]", match["f"]):
            continue
        tail = layout.masked[match.end():]
        stripped = tail.lstrip(" ")
        if match["open"]:
            if not stripped.startswith(")"):
                continue
            close = match.end() + (len(tail) - len(stripped))
            edits.append(Edit("G3:eta", match.start(), close + 1, match["f"]))
        elif stripped[:1] in ("", "\n", ",", "]", "⟩", ")"):
            edits.append(Edit("G3:eta", match.start(), match.end(), match["f"]))
    return edits


def _exact_rfl(layout: Layout) -> list[Edit]:
    return [Edit("G3:exact-rfl", m.start(), m.end(), "rfl")
            for m in re.finditer(r"\bexact\s+rfl\b(?![\w'.])", layout.masked[:])
            if m.start() >= layout.by_end]


def _constructor(layout: Layout) -> list[Edit]:
    edits = []
    for m in re.finditer(r"(?m)^(?P<indent> *)(?:refine\s+⟨\?_,\s*\?_⟩|apply\s+And\.intro)\s*$", layout.masked):
        if m.start() >= layout.by_end:
            edits.append(Edit("G3:constructor", m.start(), m.end(), m["indent"] + "constructor"))
    return edits


def _apply_exact(layout: Layout) -> list[Edit]:
    edits = []
    for i in range(layout.by_line + 1, len(layout.mlines) - 1):
        apply = _APPLY.match(layout.mlines[i])
        if not apply or not _single_line(layout, i):
            continue
        j = i + 1
        exact = _EXACT_ID.match(layout.mlines[j])
        if not exact or exact["indent"] != apply["indent"] or not _single_line(layout, j) or not _block_end(layout, j):
            continue
        fn = apply["fn"].strip()
        if re.search(r"\s", fn) and not (fn.startswith("(") and fn.endswith(")")):
            fn = f"({fn})"
        edits.append(Edit("G3:apply-exact", layout.spans[i][0], layout.spans[j][1],
                          f"{apply['indent']}exact {fn} {exact['term']}"))
    return edits


def _simp_only_to_simp(layout: Layout, limit: int = 3) -> list[Edit]:
    found = []
    for m in re.finditer(r"\b(?P<tac>simp_all|simp|dsimp) only\s*\[(?P<args>[^\[\]]*)\]", layout.masked):
        if m.start() >= layout.by_end:
            found.append((len(m["args"]), m))
    found.sort(key=lambda pair: -pair[0])
    return [Edit("G3:simp-only-to-simp", m.start(), m.end(), m["tac"]) for _, m in found[:limit]]


def local_span_edits(code: str, statement: str) -> list[Edit]:
    layout = Layout(code, statement)
    edits = []
    edits += _term_by_exact(layout)
    edits += _merge_runs(layout, _RW, _combine_rw, "G3:merge-rw")
    edits += _merge_runs(layout, _INTRO, _combine_intro, "G3:merge-intro")
    edits += _simpa(layout)
    edits += _bullets(layout)
    edits += _eta(layout)
    edits += _exact_rfl(layout)
    edits += _constructor(layout)
    edits += _apply_exact(layout)
    edits += _merge_runs(layout, _SIMP_ONLY, _combine_simp_only, "G3:merge-simp-only")
    return edits


def risky_span_edits(code: str, statement: str, limit: int = 3) -> list[Edit]:
    """Semantics-changing rewrites tried one at a time (score decides)."""
    return _simp_only_to_simp(Layout(code, statement), limit)


def local_rewrites(code: str, statement: str) -> list[tuple[str, str]]:
    return singles(code, local_span_edits(code, statement) + risky_span_edits(code, statement))


# ---- G4: deletions ------------------------------------------------------------------------
def deletion_span_edits(code: str, statement: str) -> list[Edit]:
    layout = Layout(code, statement)
    edits = []
    lines = layout.mlines
    for i in range(layout.by_line + 1, len(lines)):
        text = lines[i]
        if re.match(r"\s*clear\b", text) and _single_line(layout, i):
            edits.append(Edit("G4:drop-clear", *layout.delete_lines(i, i + 1), ""))
        elif re.match(r"\s*show\b", text) and not re.search(r"\bfrom\b|:=", text):
            stop = subtree_end(lines, i)
            edits.append(Edit("G4:drop-show", *layout.delete_lines(i, stop), ""))
        elif (have := re.match(r"\s*have\s+(?P<name>[A-Za-z_][\w'₀-₉]*)?\s*:", text)):
            stop = subtree_end(lines, i)
            name = have["name"] or "this"
            later = layout.masked[layout.spans[stop - 1][1]:] if stop - 1 < len(layout.spans) else ""
            if not re.search(r"(?<![\w.'])" + re.escape(name) + r"(?![\w'₀-₉])", later):
                edits.append(Edit("G4:drop-unreferenced-have", *layout.delete_lines(i, stop), ""))
        elif i > layout.by_line + 1 and text.strip() and text == lines[i - 1] and _single_line(layout, i) \
                and _single_line(layout, i - 1) and not re.match(r"\s*[·.]", text):
            edits.append(Edit("G4:drop-duplicate-line", *layout.delete_lines(i, i + 1), ""))
    return edits


def ddmin_plan(edits: list[Edit], max_batches: int) -> list[list[Edit]]:
    """All edits, then halves, then quarters ... (at most ``max_batches`` batches)."""
    plan, level = [], [list(edits)]
    while level and len(plan) < max_batches:
        next_level = []
        for batch in level:
            if len(plan) >= max_batches:
                break
            if batch:
                plan.append(batch)
            if len(batch) > 1:
                middle = len(batch) // 2
                next_level += [batch[:middle], batch[middle:]]
        level = next_level
    return plan


def ddmin_batches(code: str, statement: str, max_batches: int) -> list[tuple[str, str]]:
    edits = non_overlapping(deletion_span_edits(code, statement))
    out = []
    for batch in ddmin_plan(edits, max_batches):
        new = apply_edits(code, batch)
        if new is not None and new != code:
            out.append((f"G4:ddmin-{len(batch)}", new))
    return out


# ---- G2: closer probes -------------------------------------------------------------------
def _blocks(layout: Layout) -> list[dict]:
    """Outermost replaceable sub-blocks: bullets, ``... := by`` proofs, ``=>`` arms."""
    found, lines = [], layout.mlines
    i = layout.by_line + 1
    while i < len(lines):
        text = lines[i]
        if not text.strip():
            i += 1
            continue
        stop = subtree_end(lines, i)
        bullet = re.match(r"^( *)([·.])\s+\S", text)
        opener = re.search(r"(:=\s*by|=>)\s*$", text) and not re.match(r"\s*conv", text)
        if bullet:
            found.append({"kind": "bullet", "start": i, "end": stop, "indent": len(bullet[1])})
            i = stop
        elif opener and stop > i + 1:
            found.append({"kind": "by" if text.rstrip().endswith("by") else "arm", "start": i, "end": stop,
                          "indent": indent_of(lines[i + 1])})
            i = stop
        else:
            i += 1
    return found


def closer_probe(code: str, statement: str, *, scope: str = "blocks", max_blocks: int = 8,
                 min_tokens: int = 6) -> tuple[str, list[dict]]:
    """Probe text with ``try?`` in place of terminal blocks, and the block map to read it."""
    layout = Layout(code, statement)
    if scope == "root":
        head = code[:layout.by_end]
        return head + "\n  try?\n", [{"id": 0, "kind": "root", "start": layout.first, "end": len(layout.lines),
                                     "indent": 2, "probe_line": head.count("\n") + 1,
                                     "statement_length": len(statement)}]
    blocks = []
    for block in _blocks(layout):
        text = "\n".join(layout.lines[block["start"]:block["end"]])
        if len(re.findall(r"[\w.']+|[^\s\w]", text)) >= min_tokens:
            blocks.append(block)
    blocks.sort(key=lambda b: -(b["end"] - b["start"]))
    blocks = sorted(blocks[:max_blocks], key=lambda b: b["start"])
    out_lines, probe_map, k = [], [], 0
    index = 0
    for number, block in enumerate(blocks):
        out_lines.extend(layout.lines[index:block["start"]])
        if block["kind"] == "bullet":
            probe_line = len(out_lines)
            out_lines.append(" " * block["indent"] + "· try?")
        else:
            out_lines.append(layout.lines[block["start"]])
            probe_line = len(out_lines)
            out_lines.append(" " * block["indent"] + "try?")
        probe_map.append({**block, "id": number, "probe_line": probe_line, "statement_length": len(statement)})
        index = block["end"]
    out_lines.extend(layout.lines[index:])
    return "\n".join(out_lines), probe_map


def replace_block(code: str, statement: str, block: dict, tactic: str) -> str:
    layout = Layout(code, statement)
    if block["kind"] == "root":
        return code[:layout.by_end] + "\n  " + tactic + ("\n" if code.endswith("\n") else "")
    lines = list(layout.lines)
    if block["kind"] == "bullet":
        new = [" " * block["indent"] + "· " + tactic]
    else:
        new = [lines[block["start"]], " " * block["indent"] + tactic]
    lines[block["start"]:block["end"]] = new
    return "\n".join(lines)


def _rough_tokens(text: str) -> int:
    return len(re.findall(r"[\w.']+|[^\s\w]", text))


def block_edit(code: str, statement: str, block: dict, tactic: str, name: str) -> Edit:
    """Span edit replacing one probed block by ``tactic`` (same result as replace_block)."""
    layout = Layout(code, statement)
    if block["kind"] == "root":
        tail = "\n" if code.endswith("\n") else ""
        return Edit(name, layout.by_end, len(code), "\n  " + tactic + tail)
    if block["kind"] == "bullet":
        a, b = layout.spans[block["start"]][0], layout.spans[block["end"] - 1][1]
        return Edit(name, a, b, " " * block["indent"] + "· " + tactic)
    a, b = layout.spans[block["start"] + 1][0], layout.spans[block["end"] - 1][1]
    return Edit(name, a, b, " " * block["indent"] + tactic)


def suggestion_span_edits(code: str, block_map: list[dict], log: str, *, decl_start_line: int = 1,
                          per_block: int = 2) -> list[list[Edit]]:
    """Per probed block, its suggested replacements as span edits, shortest first."""
    if not block_map:
        return []
    statement = code[:block_map[0]["statement_length"]]
    by_line = {block["probe_line"]: block for block in block_map}
    offered: dict[int, list[str]] = {}
    for message in parse_messages(log):
        local = message.line - decl_start_line
        if local in by_line:
            for tactic in suggestions(message):
                offered.setdefault(local, [])
                if tactic not in offered[local]:
                    offered[local].append(tactic)
    out = []
    for local, tactics in sorted(offered.items()):
        block = by_line[local]
        ranked = sorted(tactics, key=lambda t: (_rough_tokens(t), t))[:per_block]
        edits = [block_edit(code, statement, block, tactic, f"G2:try?:{block['kind']}@{block['start']}")
                 for tactic in ranked]
        out.append([edit for edit in edits if apply_edits(code, [edit]) != code])
    return [edits for edits in out if edits]


def apply_suggestions(code: str, block_map: list[dict], log: str, *, decl_start_line: int = 1,
                      per_block: int = 2) -> list[tuple[str, str]]:
    """Variants replacing each probed block by its shortest suggestions.

    ``decl_start_line`` is the 1-based line of the probe declaration in the compiled file
    (``EvalAdapter.probe_start_line``); log positions are file relative.
    """
    edits = suggestion_span_edits(code, block_map, log, decl_start_line=decl_start_line, per_block=per_block)
    return singles(code, [edit for block in edits for edit in block])


# ---- G5: kernel-decision variants -------------------------------------------------------------
def _head_predicate(statement: str) -> str | None:
    """Head constant of the conclusion after leading binders (``(x : T) →`` / ``∀ x,``)."""
    text = mask_comments(statement)
    colon = _top_level_colon(text)
    if colon is None:
        return None
    goal = text[colon + 1:]
    while True:
        stripped = goal.strip()
        binder = re.match(r"^\((?:[^()]|\([^()]*\))*\)\s*→", stripped) or re.match(r"^∀[^,]*,", stripped)
        if not binder:
            break
        goal = stripped[binder.end():]
    head = re.match(r"\s*([A-Za-z_][\w.']*)", goal)
    if not head or head[1] in ("fun", "by", "show", "if", "match", "let", "True", "False"):
        return None
    return head[1]


def _top_level_colon(text: str) -> int | None:
    depth = 0
    for index, char in enumerate(text):
        if char in "([{⟨":
            depth += 1
        elif char in ")]}⟩":
            depth -= 1
        elif char == ":" and depth == 0 and text[index:index + 2] != ":=":
            return index
    return None


def decide_variants(code: str, statement: str) -> list[tuple[str, str]]:
    layout = Layout(code, statement)
    body = layout.masked[layout.by_end:]
    if "decide" not in body:
        return []
    head = code[:layout.by_end]
    variants = []

    def add(name, tactics):
        new = head + "\n" + "\n".join("  " + tactic for tactic in tactics)
        if code.endswith("\n"):
            new += "\n"
        if new != code and all(new != other for _, other in variants):
            variants.append((name, new))

    add("G5:decide-kernel", ["decide +kernel"])
    add("G5:decide-kernel-revert", ["decide +kernel +revert"])
    predicate = _head_predicate(statement)
    if predicate:
        add("G5:unfold-decide-kernel", [f"unfold {predicate}", "decide +kernel"])
    add("G5:intros-decide-kernel", ["intros", "decide +kernel"])
    revert = re.search(r"(?m)^\s*revert\s+[^\n]+\n(\s*)decide \+kernel\s*$", body)
    if revert:
        merged = body[:revert.start()].rstrip("\n") + "\n" + revert[1].lstrip("\n") + "decide +kernel +revert"
        variants.append(("G5:merge-revert", head + merged.rstrip() + ("\n" if code.endswith("\n") else "")))
    if re.search(r"\bdecide \+kernel\b", body):
        variants.append(("G5:plain-decide", code[:layout.by_end] + code[layout.by_end:].replace("decide +kernel", "decide")))
    seen, out = set(), []
    for name, new in variants:
        if new != code and new not in seen:
            seen.add(new)
            out.append((name, new))
    return out
