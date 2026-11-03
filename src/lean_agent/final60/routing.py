"""final60 routing: classify each row, choose its route, hints and schedule.

Deterministic and offline: no model call, no Lean, no network, no machine paths.
Inputs are the driver problem dict (``row``, ``name``, ``statement``,
``reference``, ``source``, ``environments``) or a raw benchmark row (``src``,
``version_info``, plus ``row``), and optionally the team baseline entry from
``docs/measurements/final60-baselines.json``.

Provenance (design 7.3 with amendments A15/A17): hints come only from the
generic playbooks in ``data/playbooks.json``, the warm-up-only PR #50 bank
(``data/warmup_bank.json``, commit 760b59e) and an in-run lesson bank built from
this run's own validated OpenRouter winners. Final-derived team banks (PR #73
``team-v1``) are used only when explicitly passed in ``bank_paths``, and then only
leave-one-out. Every hint passes ``leak_filter`` against the non-OpenRouter proofs
and against the row's own original proof, so hints never contain proof text.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re

from .. import portfolio as team_portfolio
from ..evaluator.tokens import proof_tokens, without_comments
from . import prompts
from .contracts import CAP_USD, SCHEMA, Route

DATA = prompts.DATA
prompt_addendum = prompts.prompt_addendum      # contract name (design 11.3); <= 2000 chars
insert_addendum = prompts.insert_addendum      # for the driver's prompt_text hook
split_addendum = prompts.split_addendum        # for the driver's validate_inputs hook
ROUTE_SCHEMA = "final60-route-v1"
LESSON_SCHEMA = "final60-lessons-v1"
WARMUP_BANK_COMMIT = "760b59e1e4e3b058c29e1954780367bb6f43dab8"
WARMUP_BANK_SOURCE = "experiments/strategy-retriever/bank/strategies.json"
TYPES = ("kernel-decide-tiny", "short-tactic", "structural-induction", "algebra-analysis-long", "competition")
MIN_LEAK_CHARS = 40          # PR #70 MIN_LEAK_CHARS
MAX_REQUEST_BYTES = 240_000  # transport refuses larger bodies (design section 5)

CLOSERS = ("simp_all", "omega", "linarith", "nlinarith", "norm_num", "positivity", "ring", "field_simp",
           "decide", "grind", "aesop", "tauto", "simpa")
SPLITS = ("induction", "cases", "rcases", "fun_induction", "match")
COUNTED = tuple(dict.fromkeys(("have", "case", "cases", "rcases", "obtain", "induction", "fun_induction", "match",
                               "simp", "calc", "exact", "apply", "refine", "constructor", "intro", "intros",
                               "unfold", "rw", "show", "fin_cases", "interval_cases", "all_goals") + CLOSERS))
LESSON_CLOSERS = ("grind", "simp_all", "omega", "nlinarith", "linarith", "norm_num", "positivity", "aesop",
                  "decide", "field_simp", "ring", "simpa", "tauto")
# PR #50 tag thresholds (features.py): a block kind owning half of the proof is its main kind.
MAIN_SHARE = 0.5
STATEMENT_FLAGS = {
    "exists": r"∃", "forall": r"∀", "iff": r"↔", "inequality": r"[≤≥<>]|\blt\b|\ble\b",
    "finset_sum": r"∑|∏|Finset\.sum|Finset\.prod", "matrix": r"\bMatrix\b", "real": r"ℝ|\bReal\b",
    "complex": r"ℂ|\bComplex\b", "nat_int": r"ℕ|ℤ|\bNat\b|\bInt\b", "list": r"\bList\b", "set": r"\bSet\b",
}


# ---------------------------------------------------------------- data files

@lru_cache(maxsize=None)
def rules() -> dict:
    value = json.loads((DATA / "route_rules.json").read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or tuple(value.get("types", ())) != TYPES:
        raise ValueError("Unexpected route_rules.json schema")
    return value


@lru_cache(maxsize=None)
def warmup_bank() -> dict:
    return json.loads((DATA / "warmup_bank.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def data_sha256() -> str:
    """Identity of the routing data (rules, playbooks, warm-up bank), recorded in route.json."""
    digest = hashlib.sha256()
    for name in ("route_rules.json", "playbooks.json", "warmup_bank.json"):
        digest.update(name.encode() + b"\0" + (DATA / name).read_bytes() + b"\0")
    return digest.hexdigest()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------- problem fields

def problem_reference(problem: dict) -> str:
    value = problem.get("reference", problem.get("src"))
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Problem has no reference proof (reference/src)")
    return value


def problem_row(problem: dict) -> int | None:
    row = problem.get("row")
    if type(row) is int:
        return row
    for key in ("id", "row_id", "problem_id"):
        match = re.search(r"F(\d{3})\b", str(problem.get(key, "")))
        if match:
            return int(match.group(1))
    return None


def problem_versions(problem: dict) -> tuple[list[str], list[str]]:
    """(environment ids, Lean versions), primary first, from either problem format."""
    source = str(problem.get("source", ""))
    environments = problem.get("environments")
    if isinstance(environments, list) and environments:
        environments = [str(item) for item in environments]
        versions = [item.split("-", 1)[1] if item.startswith(source + "-") else item for item in environments]
        return environments, versions
    versions = []
    for entry in problem.get("version_info") or ():
        if isinstance(entry, dict):
            versions.extend(str(key) for key in entry)
        elif isinstance(entry, str):
            versions.append(entry)
    return [f"{source}-{version}" for version in versions], versions


def load_baselines(path) -> dict | None:
    """The team baseline file, or None when absent (classification still works)."""
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def baseline_for(problem: dict, baselines: dict | None) -> dict | None:
    """The row's entry from a whole baseline file, or a per-row entry checked against the problem."""
    if not isinstance(baselines, dict):
        return None
    row, name = problem_row(problem), problem.get("name")
    if isinstance(baselines.get("problems"), list):
        for entry in baselines["problems"]:
            if (row is not None and entry.get("id") == f"F{row:03}") or (row is None and entry.get("name") == name):
                return entry
        return None
    if "id" in baselines and row is not None and baselines["id"] != f"F{row:03}":
        raise ValueError(f"Baseline entry {baselines['id']} does not belong to F{row:03}")
    if "name" in baselines and name is not None and baselines["name"] != name:
        raise ValueError("Baseline entry belongs to a different problem")
    return baselines


# ------------------------------------------------------------------ features

def _body(reference: str, statement: str) -> str:
    rest = reference[len(statement):] if statement and reference.startswith(statement) else reference
    match = re.match(r"\s*:=", rest)
    if match:
        rest = rest[match.end():]
    elif ":=" in rest and not reference.startswith(statement or "\0"):
        rest = rest.split(":=", 1)[1]
    try:
        return without_comments(rest)
    except ValueError:
        return rest


def _count(text: str, word: str) -> int:
    return len(re.findall(r"(?<![\w.'])" + re.escape(word) + r"(?![\w'])", text))


def _route_cue(statement: str, body: str):
    """PR #36 route cue (ported from PR #50 features.py): `induction x` + unfold/simp of f, statement applies f to x."""
    match = re.search(r"\binduction\s+([^\s<;]+)", body)
    if not match:
        return None
    x = match.group(1)
    flat = re.sub(r"\s+", " ", body)
    unfolded = [n for line in re.findall(r"\bunfold\s+([^\n]+)", body) for n in line.split()]
    simped = [n.strip() for group in re.findall(r"\bsimp(?:_all)?(?: only)?\s*\[([^\]]*)\]", flat)
              for n in group.split(",")]
    names = [n.lstrip("←").strip() for n in unfolded + simped]
    for f in dict.fromkeys(n for n in names if re.fullmatch(r"[\w.']+", n)):
        for occurrence in re.finditer(r"(?<![\w.])" + re.escape(f) + r"(?![\w'])", statement):
            if re.search(r"(?<![\w.])" + re.escape(x) + r"(?![\w'])", _after(statement, occurrence.end())):
                return [x, f]
    return None


def _after(text: str, start: int) -> str:
    depth, out = 0, []
    for char in text[start:]:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif char == "\n" and depth == 0:
            break
        out.append(char)
    return "".join(out)


def _block_shares(lines: list[str]) -> dict:
    """Share of body lines owned by case/have/calc blocks: a line-based port of PR #25 `kind_of`
    (case = `case `/`| `/`next ` heads, bullets count as other; have = have/obtain/let/suffices/set/replace)."""
    owner = [None] * len(lines)
    for index, line in enumerate(lines):
        if owner[index] is not None:
            continue
        stripped = line.lstrip()
        if stripped.startswith(("case ", "| ", "next ")):
            kind = "case"
        elif re.match(r"(?:have|obtain|let|suffices|set|replace)\b", stripped):
            kind = "have"
        elif re.match(r"calc\b", stripped) or stripped.startswith("_ "):
            kind = "calc"
        else:
            continue
        indent = len(line) - len(stripped)
        end = index + 1
        while end < len(lines) and len(lines[end]) - len(lines[end].lstrip()) > indent:
            end += 1
        for position in range(index, end):
            owner[position] = owner[position] or kind
    total = max(len(lines), 1)
    return {kind: round(owner.count(kind) / total, 4) for kind in ("case", "have", "calc")}


def _repeated_blocks(lines: list[str]) -> bool:
    seen = set()
    stripped = [line.strip() for line in lines]
    for start in range(len(stripped) - 2):
        window = "\n".join(stripped[start:start + 3])
        if len(window) < 40:
            continue
        if window in seen:
            return True
        seen.add(window)
    return False


def features(problem: dict, baseline: dict | None) -> dict:
    """Static, deterministic features of one row. `baseline` may be a whole baseline file or a row entry."""
    statement = str(problem.get("statement", ""))
    reference = problem_reference(problem)
    body = _body(reference, statement)
    lines = [line for line in body.splitlines() if line.strip()]
    entry = baseline_for(problem, baseline)
    environments, versions = problem_versions(problem)
    try:
        t0, t0_basis = proof_tokens(reference, statement), "lean-source-anchored-v1"
    except ValueError:
        provided = (entry or {}).get("provided_length", problem.get("proof_length"))
        t0, t0_basis = (provided, "provided") if type(provided) is int else (len(body.split()), "whitespace")
    primary = (entry or {}).get("primary_environment") or (environments[0] if environments else None)
    measured = ((entry or {}).get("environments") or {}).get(primary) or {}
    hb0 = measured.get("median_raw_heartbeats")
    hb0 = hb0 if type(hb0) is int else None
    counts = {word: _count(body, word) for word in COUNTED}
    counts["<;>"] = body.count("<;>")
    counts["simp only"] = len(re.findall(r"\bsimp(?:_all)? only\b", body))
    splits = sum(counts[word] for word in SPLITS)
    shares = _block_shares(lines)
    cue = _route_cue(statement, body)
    tags = set()
    for kind in ("case", "have", "calc"):
        if shares[kind] >= MAIN_SHARE:
            tags.add(kind + "_main")
    if cue:
        tags.add("route_cue")
    if _repeated_blocks(lines):
        tags.add("repeated_blocks")
    if any(counts[word] >= 5 for word in CLOSERS):
        tags.add("repeated_automation")
    if counts["decide"] or counts["calc"] or counts["norm_num"]:
        tags.add("search_or_calculation")
    if re.search(r"\.elim\b", body) or _count(body, "fun") >= 3:
        tags.add("proof_terms")
    if re.search(r"\bsimp(?:_all)?(?: only)?\s*\[[^\]]*,[^\]]*,", body):
        tags.add("simp_lists")
    try:
        clean_statement = without_comments(statement)
    except ValueError:
        clean_statement = statement
    words = rules()["classify"]["unknown_source_structural_statement_words"]
    return {
        "row": problem_row(problem), "name": problem.get("name"), "source": str(problem.get("source", "")),
        "environments": environments, "versions": versions, "n_versions": len(versions),
        "primary_environment": primary, "t0": t0, "t0_basis": t0_basis, "hb0": hb0,
        "hb_basis": "team-baseline-median-raw" if hb0 is not None else None,
        "reference_chars": len(reference), "body_lines": len(lines), "body_chars": len(body),
        "term_mode": not re.match(r"\s*by\b", body), "uses_decide": counts["decide"] > 0,
        "kernel_decide": bool(re.search(r"\bdecide\s*\+\s*kernel|\bdecide\s*\(\s*config|\+kernel\b", body)),
        "counts": counts, "closers": sum(counts[word] for word in CLOSERS), "splits": splits,
        "lines_per_split": round(len(lines) / splits, 3) if splits else None,
        "kind_share": shares, "route_cue": cue, "tags": sorted(tags),
        "statement": {**{flag: len(re.findall(pattern, clean_statement)) for flag, pattern in STATEMENT_FLAGS.items()},
                      "relation_words": sorted(word for word in words if re.search(r"\b" + re.escape(word), clean_statement)),
                      "chars": len(statement)},
        "hb_per_token": round(hb0 / t0, 1) if hb0 is not None and t0 else None,
    }


# ------------------------------------------------------------ classification

def _is_type(kind: str, feat: dict, rule: dict) -> bool:
    t0 = feat["t0"]
    if kind == "kernel-decide-tiny":
        return t0 <= rule["kernel_decide_tiny_max_t0"] and feat["uses_decide"]
    if kind == "competition":
        return feat["source"] in rule["competition_sources"]
    if kind == "short-tactic":
        return t0 < rule["short_tactic_max_t0_exclusive"]
    if kind == "structural-induction":
        if feat["source"] in rule["structural_sources"]:
            return True
        if feat["source"] in rule["algebra_sources"] or feat["source"] in rule["competition_sources"]:
            return False
        dense = feat["splits"] and feat["body_lines"] / feat["splits"] <= rule["unknown_source_structural_lines_per_split"]
        return bool(dense or feat["statement"]["relation_words"])
    if kind == "algebra-analysis-long":
        return True
    raise ValueError("Unknown problem type " + kind)


def classify_features(feat: dict) -> str:
    rule = rules()["classify"]
    for kind in rule["order"]:
        if _is_type(kind, feat, rule):
            return kind
    return "algebra-analysis-long"


def classify(problem: dict, baseline: dict | None) -> str:
    """Design 7.1 problem type (deterministic; works without the baseline)."""
    return classify_features(features(problem, baseline))


# ------------------------------------------------------------- route parts

def _merge(base: dict, override: dict | None) -> dict:
    return {**base, **(override or {})}


def portfolio_for(problem_type: str) -> dict:
    spec = rules()["portfolio"]
    value = _merge(spec["default"], spec.get("by_type", {}).get(problem_type))
    team_portfolio.validate(value)
    return value


def golf_for(problem_type: str, t0: int | None) -> dict:
    spec = rules()["golf"]
    value = _merge(spec["default"], spec.get("by_type", {}).get(problem_type))
    ddmin = t0 is not None and t0 <= spec["ddmin_max_t0"] and "G4" in value["passes"]
    value["ddmin"] = bool(ddmin)
    value["passes"] = [name for name in value["passes"] if name != "G4" or ddmin]
    return value


def priority_for(problem_type: str, feat: dict, skip_llm: bool) -> float:
    spec = rules()["priority"]
    value = Decimal(str(spec["base"][problem_type]))
    weak = feat["row"] in spec["weak_rows"] or feat["source"] in spec["weak_sources"]
    if weak and not skip_llm:
        value += Decimal(str(spec["weak_boost"]))
    t0 = min(feat["t0"] or 0, spec["size_t0_cap"])
    value += Decimal(t0) / Decimal(spec["size_t0_per_point"])
    return float(round(value, 3))


def expected_score_for(problem_type: str, source: str) -> float:
    spec = rules()["expected_score"]
    if problem_type in spec:
        return float(spec[problem_type])
    return float(spec["by_source"].get(source, spec["default"]))


def wallclock_for(problem_type: str) -> int:
    spec = rules()["wallclock_budget_s"]
    return int(spec.get(problem_type, spec["default"]))


# --------------------------------------------------------------- leak filter

class LeakCorpus:
    """Whitespace-flattened non-OpenRouter proofs, reusable across rows.

    A text leaks when it shares a substring of at least `min_chars` characters with
    a proof (after flattening). Exact: every proof gram at aligned positions is
    checked against all text grams and confirmed by maximal extension.
    """

    def __init__(self, proofs=(), *, min_chars: int = MIN_LEAK_CHARS):
        if type(min_chars) is not int or min_chars < 2:
            raise ValueError("min_chars must be an integer of at least 2")
        self.min_chars = min_chars
        self.gram = min_chars // 2
        self.step = min_chars - self.gram + 1
        self.texts = []
        for proof in proofs:
            if isinstance(proof, str):
                value = prompts.flat(proof)
                if len(value) >= min_chars:
                    self.texts.append(value)

    def __len__(self):
        return len(self.texts)

    def mask(self, texts) -> list[bool]:
        flats = [prompts.flat(text) if isinstance(text, str) else "" for text in texts]
        gram, step, need = self.gram, self.step, self.min_chars
        index = {}
        for number, text in enumerate(flats):
            if len(text) < need:
                continue
            for position in range(len(text) - gram + 1):
                index.setdefault(text[position:position + gram], []).append((number, position))
        leaked = [False] * len(flats)
        if not index:
            return leaked
        for proof in self.texts:
            for start in range(0, len(proof) - gram + 1, step):
                hits = index.get(proof[start:start + gram])
                if not hits:
                    continue
                for number, position in hits:
                    if leaked[number]:
                        continue
                    text = flats[number]
                    left_text, left_proof = position, start
                    while left_text and left_proof and text[left_text - 1] == proof[left_proof - 1]:
                        left_text, left_proof = left_text - 1, left_proof - 1
                    right_text, right_proof = position + gram, start + gram
                    while right_text < len(text) and right_proof < len(proof) and text[right_text] == proof[right_proof]:
                        right_text, right_proof = right_text + 1, right_proof + 1
                    if right_text - left_text >= need:
                        leaked[number] = True
            if all(leaked):
                break
        return leaked


def _corpus(proofs, min_chars: int) -> LeakCorpus:
    if isinstance(proofs, LeakCorpus) and proofs.min_chars == min_chars:
        return proofs
    if isinstance(proofs, (str, bytes)):
        raise TypeError("non_openrouter_proofs must be a list of proof texts")
    return LeakCorpus(proofs, min_chars=min_chars)


def leak_filter(texts: list[str], non_openrouter_proofs, *, min_chars: int = MIN_LEAK_CHARS) -> list[str]:
    """Texts that share no >= min_chars whitespace-flattened substring with any listed proof."""
    texts = list(texts)
    mask = _corpus(non_openrouter_proofs, min_chars).mask(texts)
    return [text for text, leaked in zip(texts, mask) if not leaked]


# --------------------------------------------------------------------- banks

def _bank_score(match: dict, feat: dict) -> int | None:
    """PR #50 retriever score: all_tags required; any_tags/tactic_min need one hit when given."""
    tags, counts = set(feat["tags"]), feat["counts"]
    if not set(match.get("all_tags", [])) <= tags:
        return None
    hits = [tag for tag in match.get("any_tags", []) if tag in tags]
    hits += [word for word, minimum in match.get("tactic_min", {}).items() if counts.get(word, 0) >= minimum]
    if (match.get("any_tags") or match.get("tactic_min")) and not hits:
        return None
    return len(match.get("all_tags", [])) + len(hits)


def _warmup_card_text(card: dict) -> str:
    text = f"{card['title']}: {' '.join(card.get('application_guide', []))}"
    risks = " ".join(card.get("risk_notes", []))
    full = prompts.flat(text + (" Risk: " + risks if risks else ""))
    return full if len(full) <= prompts.MAX_HINT_CHARS else prompts.shorten(text)


def warmup_hints(feat: dict, *, limit: int, bank: dict | None = None) -> list[tuple[str, str]]:
    """Specific warm-up bank matches (general moves excluded), leave-one-out by problem name."""
    bank = bank if bank is not None else warmup_bank()
    ranked = []
    for index, card in enumerate(bank.get("strategies", [])):
        evidence = set((card.get("evidence") or {}).get("source_problem_ids", []))
        if feat["name"] and evidence == {feat["name"]}:
            continue
        score = _bank_score(card.get("match", {}), feat)
        if score:
            ranked.append((-score, index, card))
    version = bank.get("version", "warmup")
    return [(_warmup_card_text(card), f"warmup-bank:{version}:{card['id']}@{WARMUP_BANK_COMMIT[:7]}")
            for _, _, card in sorted(ranked, key=lambda item: item[:2])[:limit]]


def team_bank_hints(path: Path, problem: dict, *, limit: int) -> list[tuple[str, str]]:
    """Opt-in PR #73 bank: whole cards naming this problem are dropped; prose (title + guide) only."""
    from .. import strategy_bank, strategy_signals
    bank = json.loads(Path(path).read_text(encoding="utf-8"))
    strategy_bank.validate(bank)
    code, statement = problem_reference(problem), str(problem.get("statement", ""))
    feat = strategy_bank.features(code)
    if bank["schema_version"] == 2:
        feat["signals"] = strategy_signals.extract(statement, code)
    ranked = []
    for index, card in enumerate(bank["strategies"]):
        if any(item["problem"] == problem.get("name") for item in card["evidence"]):
            continue
        if card.get("metadata", {}).get("review_status") == "rejected":
            continue
        score = strategy_bank.score(card["match"], feat)
        if score is not None:
            ranked.append((-score, index, card))
    return [(prompts.shorten(f"{card['title']}: {card['guide']}"), f"team-bank:{bank['version']}:{card['id']}")
            for _, _, card in sorted(ranked, key=lambda item: item[:2])[:limit]]


def _lesson_records(path: Path) -> list[dict]:
    """Records of an in-run lesson bank; a bank not written yet (start of the run) is empty."""
    path = Path(path)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue  # a torn final line from a crash is ignored, never fatal
        if isinstance(value, dict) and value.get("schema") == LESSON_SCHEMA and isinstance(value.get("lessons"), list):
            records.append(value)
    return records


def lesson_hints(paths, feat: dict, problem_type: str, *, limit: int) -> list[tuple[str, str]]:
    """In-run lessons (A17): same source, never the same row, same type first, larger reduction first."""
    ranked = []
    for path in paths:
        for record in _lesson_records(path):
            if record.get("source") != feat["source"] or record.get("row") == feat["row"] \
                    or record.get("name") == feat["name"]:
                continue
            reduction = (record.get("metrics") or {}).get("token_reduction_pct", 0)
            reduction = reduction if isinstance(reduction, (int, float)) else 0
            for number, lesson in enumerate(record["lessons"]):
                if isinstance(lesson, str):
                    ranked.append(((record.get("problem_type") != problem_type, -reduction,
                                    record.get("row") or 0, number), lesson, record.get("row")))
    ranked.sort(key=lambda item: item[0])
    result, seen = [], set()
    for _, lesson, row in ranked:
        if lesson in seen:
            continue
        seen.add(lesson)
        result.append((lesson, f"in-run-lesson:F{row:03}" if type(row) is int else "in-run-lesson"))
        if len(result) >= limit:
            break
    return result


def _bank_kind(path: Path) -> str:
    path = Path(path)
    if path.suffix == ".jsonl":
        return "lessons"
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and "scope" in value and "schema_version" in value:
        return "team"
    if isinstance(value, dict) and isinstance(value.get("strategies"), list):
        return "warmup"
    raise ValueError(f"Unknown bank format: {path.name}")


# --------------------------------------------------------------------- route

def _hint_candidates(problem: dict, feat: dict, problem_type: str, bank_paths) -> list[tuple[str, str]]:
    spec = rules()["hints"]
    book = prompts.playbooks()
    typed = book["types"].get(problem_type, [])
    core = spec["playbook_core"]
    items = [(text, f"playbook:{problem_type}:{index + 1}") for index, text in enumerate(typed[:core])]
    if feat["n_versions"] >= spec["many_versions_min"]:
        items.append((book["conditional"]["many_versions"].format(versions=", ".join(feat["versions"])),
                      "playbook:conditional:many_versions"))
    if feat["hb0"] is not None and feat["hb0"] >= spec["hb_heavy_min_raw"]:
        items.append((book["conditional"]["hb_heavy"].format(hb_millions=f"{feat['hb0'] / 1_000_000:.0f}"),
                      "playbook:conditional:hb_heavy"))
    kinds = [(Path(path), _bank_kind(path)) for path in bank_paths]
    items += lesson_hints([path for path, kind in kinds if kind == "lessons"], feat, problem_type,
                          limit=spec["lessons"])
    items += warmup_hints(feat, limit=spec["bank_cards"])
    for path, kind in kinds:
        if kind == "team":
            items += team_bank_hints(path, problem, limit=spec["bank_cards"])
        elif kind == "warmup":
            items += warmup_hints(feat, limit=spec["bank_cards"],
                                  bank=json.loads(path.read_text(encoding="utf-8")))
    items += [(text, f"playbook:{problem_type}:{core + index + 1}") for index, text in enumerate(typed[core:])]
    return items


def select_hints(problem: dict, feat: dict, problem_type: str, *, non_openrouter_proofs,
                 bank_paths=()) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Sanitized, leak-filtered, de-duplicated hints that fit the addendum limits."""
    sanitized, seen = [], set()
    for text, source in _hint_candidates(problem, feat, problem_type, bank_paths):
        value = prompts.sanitize_hint(text)
        if value and value not in seen:
            seen.add(value)
            sanitized.append((value, source))
    texts = [text for text, _ in sanitized]
    mask = _corpus(non_openrouter_proofs, MIN_LEAK_CHARS).mask(texts)
    own = LeakCorpus([problem_reference(problem)]).mask(texts)
    kept = [item for item, bad, mine in zip(sanitized, mask, own) if not bad and not mine]
    order = prompts.fit_hints(problem_type, [text for text, _ in kept],
                              max_hints=min(prompts.MAX_HINTS, rules()["hints"]["max_hints"]))
    return tuple(kept[i][0] for i in order), tuple(kept[i][1] for i in order)


def route(problem: dict, baseline: dict | None, *, non_openrouter_proofs, bank_paths=(),
          diversity: bool = False) -> Route:
    """The frozen per-row route (design 7.2): type, portfolio, hints, golf budget, priority."""
    feat = features(problem, baseline)
    if feat["row"] is None:
        raise ValueError("Problem needs a row number (row or an F0NN id)")
    problem_type = classify_features(feat)
    skip_llm = problem_type in rules()["skip_llm_types"]
    hints, sources = ((), ()) if skip_llm else select_hints(
        problem, feat, problem_type, non_openrouter_proofs=non_openrouter_proofs, bank_paths=bank_paths)
    value = Route(
        row=feat["row"], name=str(problem.get("name", "")), source=feat["source"], problem_type=problem_type,
        skip_llm=skip_llm, portfolio=portfolio_for(problem_type),
        role_models={"scout-c": "gen_alt"} if diversity and not skip_llm else {},
        hints=hints, hint_sources=sources, golf=golf_for(problem_type, feat["t0"]),
        priority=priority_for(problem_type, feat, skip_llm), wallclock_budget_s=wallclock_for(problem_type),
        expected_score=expected_score_for(problem_type, feat["source"]))
    validate_route(value, problem)
    return value


def route_all(problems, baselines, *, non_openrouter_proofs, bank_paths=(), diversity=False) -> list[Route]:
    """Routes for many rows with one shared leak corpus."""
    corpus = _corpus(non_openrouter_proofs, MIN_LEAK_CHARS)
    return [route(problem, baselines, non_openrouter_proofs=corpus, bank_paths=bank_paths, diversity=diversity)
            for problem in problems]


def default_route(problem: dict) -> Route:
    """Stub for callers when routing fails: full loop, team portfolio + merger_until_budget, no hints."""
    try:
        feat = features(problem, None)
        problem_type = classify_features(feat)
    except Exception:  # the stub must never fail on an odd problem
        feat = {"row": problem_row(problem), "source": str(problem.get("source", "")), "t0": None}
        problem_type = "algebra-analysis-long"
    row = feat["row"]
    if row is None:
        raise ValueError("Problem needs a row number (row or an F0NN id)")
    portfolio = dict(rules()["portfolio"]["default"], merger_until_budget=True)
    team_portfolio.validate(portfolio)
    golf = golf_for("algebra-analysis-long" if problem_type == "kernel-decide-tiny" else problem_type, feat["t0"])
    return Route(row=row, name=str(problem.get("name", "")), source=feat["source"], problem_type=problem_type,
                 skip_llm=False, portfolio=portfolio, role_models={}, hints=(), hint_sources=(), golf=golf,
                 priority=0.0, wallclock_budget_s=int(rules()["wallclock_budget_s"]["default"]),
                 expected_score=None)


# ---------------------------------------------------------------- validation

def validate_route(value: Route, problem: dict | None = None) -> None:
    """Every constraint of design 11.3; raises ValueError on the first violation."""
    if value.problem_type not in TYPES:
        raise ValueError("Unknown problem type " + str(value.problem_type))
    team_portfolio.validate(value.portfolio)
    if len(value.hints) != len(value.hint_sources) or len(value.hints) > prompts.MAX_HINTS:
        raise ValueError("Hints and hint sources must align, at most 6 hints")
    if value.skip_llm and (value.hints or value.role_models):
        raise ValueError("A skip_llm route carries no hints or role models")
    for hint in value.hints:
        problems = prompts.hint_problems(hint)
        if problems:
            raise ValueError("Invalid hint: " + "; ".join(problems))
    if set(value.role_models) - set(team_portfolio.BRANCHES) or any(not isinstance(v, str) for v in value.role_models.values()):
        raise ValueError("role_models maps portfolio branches to catalog keys")
    golf = value.golf
    for key in ("original_compiles", "top_k", "max_compiles_best", "max_compiles_other", "max_compiles_row", "minutes"):
        if type(golf.get(key)) is not int or golf[key] < 0:
            raise ValueError("Golf budget needs non-negative integer " + key)
    if not isinstance(golf.get("passes"), list) or set(golf["passes"]) - {"G1", "G2", "G3", "G4", "G5"}:
        raise ValueError("Unknown golf pass")
    if type(value.wallclock_budget_s) is not int or value.wallclock_budget_s <= 0:
        raise ValueError("wallclock_budget_s must be a positive integer")
    addendum = prompts.prompt_addendum(value)
    if problem is not None:
        reference = problem_reference(problem)
        config = {"agent": {"portfolio": value.portfolio}}
        team_portfolio.validate_shared_inputs(config, reference, addendum, {"entries": []})
        if any(LeakCorpus([reference]).mask(value.hints)):
            raise ValueError("A hint shares text with the original proof")
        if value.row != problem_row(problem):
            raise ValueError("Route row differs from the problem row")


# ------------------------------------------------------------ serialization

def _sorted(value):
    if isinstance(value, dict):
        return {key: _sorted(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_sorted(item) for item in value]
    return value


def route_json(value: Route, *, prior_cost_usd: str | Decimal = "0") -> dict:
    """input/route.json content (sorted keys). The rendered addendum is stored so validation never re-renders."""
    prior = Decimal(str(prior_cost_usd))
    if prior < 0 or prior >= CAP_USD:
        raise ValueError("prior_cost_usd must be within [0, cap)")
    data = dataclasses.asdict(value)
    data.update(schema=SCHEMA, route_schema=ROUTE_SCHEMA, prompt_addendum=prompts.prompt_addendum(value),
                prompt_addendum_sha256=_sha(prompts.prompt_addendum(value)), cost_stop_usd=str(CAP_USD),
                prior_cost_usd=str(prior), routing_data_sha256=data_sha256(),
                warmup_bank={"source": WARMUP_BANK_SOURCE, "commit": WARMUP_BANK_COMMIT})
    return _sorted(data)


def route_from_json(data: dict) -> Route:
    """Inverse of route_json (extra keys are checked, not trusted)."""
    if data.get("schema") != SCHEMA or data.get("route_schema") != ROUTE_SCHEMA:
        raise ValueError("Not a final60 route.json")
    names = [item.name for item in dataclasses.fields(Route)]
    missing = [name for name in names if name not in data and name != "expected_score"]
    if missing:
        raise ValueError("route.json lacks " + ", ".join(missing))
    kwargs = {name: data[name] for name in names if name in data}
    kwargs["hints"] = tuple(kwargs["hints"])
    kwargs["hint_sources"] = tuple(kwargs["hint_sources"])
    value = Route(**kwargs)
    if data.get("prompt_addendum", "") != prompts.prompt_addendum(value):
        raise ValueError("route.json addendum differs from its hints")
    return value


# --------------------------------------------------------- schedule / budget

def schedule(routes, ready) -> list[int]:
    """Ready rows in launch order: priority (desc), then row number. Unready rows are omitted."""
    ready = set(ready)
    best = {}
    for item in routes:
        if item.row in ready and (item.row not in best or item.priority > best[item.row].priority):
            best[item.row] = item
    return [item.row for item in sorted(best.values(), key=lambda item: (-item.priority, item.row))]


def request_bound_usd(spec, request_bytes: int) -> Decimal:
    """Design 5 worst case: (bytes + 4096) at max(prompt, cache write) + max_tokens at completion."""
    price_in = max(Decimal(str(spec.prompt_usd_per_mtok)), Decimal(str(spec.cache_write_usd_per_mtok)))
    total = Decimal(request_bytes + 4096) * price_in + Decimal(spec.max_tokens) * Decimal(str(spec.completion_usd_per_mtok))
    return total / Decimal(1_000_000)


def worst_case_calls(value: Route, spec, typical_request_bytes: int) -> int:
    """How many requests of this size the per-problem cap admits even if each costs its bound."""
    if type(typical_request_bytes) is not int or typical_request_bytes < 0:
        raise ValueError("typical_request_bytes must be a non-negative integer")
    if value.skip_llm or typical_request_bytes >= MAX_REQUEST_BYTES:
        return 0
    bound = request_bound_usd(spec, typical_request_bytes)
    return int(CAP_USD // bound) if bound > 0 else 0


def budget_plan(value: Route, spec, typical_request_bytes: int) -> dict:
    """Report view of the per-row money plan (estimates; the transport ledger enforces the cap)."""
    calls = worst_case_calls(value, spec, typical_request_bytes)
    return {"row": value.row, "skip_llm": value.skip_llm, "cap_usd": str(CAP_USD), "model_key": spec.key,
            "request_bytes": typical_request_bytes,
            "bound_usd_per_call": str(request_bound_usd(spec, typical_request_bytes)) if calls else None,
            "worst_case_calls": calls,
            "portfolio_evaluations": None if value.skip_llm else
            3 * value.portfolio.get("scout_evaluations", 6) + value.portfolio.get("merger_evaluations", 22),
            "merger_until_budget": bool(value.portfolio.get("merger_until_budget")) and not value.skip_llm,
            "wallclock_budget_s": value.wallclock_budget_s,
            "basis": "worst case per request = (bytes + 4096) x max(prompt, cache write) + max_tokens x completion"}


def explain(problem: dict, baseline: dict | None) -> dict:
    """Plan/status view: features plus the type decision (no hints, no I/O)."""
    feat = features(problem, baseline)
    kind = classify_features(feat)
    return {"row": feat["row"], "name": feat["name"], "problem_type": kind,
            "skip_llm": kind in rules()["skip_llm_types"], "features": feat}


# ------------------------------------------------------------ in-run lessons

def lessons_from_winner(problem: dict, winner_code: str, *, metrics: dict | None = None) -> list[str]:
    """1 prose lesson from a validated winner: tactic-family changes only, no proof text (A17)."""
    statement = str(problem.get("statement", ""))
    reference = problem_reference(problem)
    original, winner = _body(reference, statement), _body(winner_code, statement)
    before = {word: _count(original, word) for word in COUNTED}
    after = {word: _count(winner, word) for word in COUNTED}
    before["<;>"], after["<;>"] = original.count("<;>"), winner.count("<;>")
    try:
        reduction = 100 * (1 - proof_tokens(winner_code, statement) / proof_tokens(reference, statement))
    except (ValueError, ZeroDivisionError):
        return []
    if reduction <= 0:
        return []
    moves = []
    if before["have"] >= 4 and after["have"] <= before["have"] // 2:
        moves.append("removed or inlined most intermediate `have` steps")
    split_before = sum(before[word] for word in SPLITS)
    split_after = sum(after[word] for word in SPLITS)
    if split_before and not split_after:
        moves.append("avoided the explicit induction or case split")
    if after["<;>"] > before["<;>"]:
        moves.append("closed parallel goals together with `<;>`")
    gained = sorted(((after[word] - before[word], word) for word in LESSON_CLOSERS if after[word] > before[word]),
                    key=lambda item: (-item[0], item[1]))[:2]
    if gained:
        moves.append("relied on " + " and ".join(f"`{word}`" for _, word in gained))
    if before["calc"] and not after["calc"]:
        moves.append("replaced the `calc` chain")
    if before["rw"] >= 4 and after["rw"] <= before["rw"] // 2:
        moves.append("dropped most `rw` steps")
    if not moves:
        return []
    kind = classify_features(features(problem, None))
    extra = ""
    hb = (metrics or {}).get("hb_reduction_pct")
    if isinstance(hb, (int, float)) and hb > 0:
        extra = f" and heartbeats by {hb:.0f}%"
    text = (f"Lesson from a validated OpenRouter winner on another {problem.get('source', '')} problem ({kind}): "
            f"it cut proof tokens by {reduction:.0f}%{extra}; it " + ", ".join(moves) + ".")
    value = prompts.sanitize_hint(prompts.shorten(text))
    return [value] if value else []


def record_lessons(path, problem: dict, winner_code: str, *, run_root: str, metrics: dict | None = None,
                   non_openrouter_proofs=()) -> list[str]:
    """Append this row's lessons to the in-run bank (JSONL, one record per row and winner)."""
    lessons = leak_filter(lessons_from_winner(problem, winner_code, metrics=metrics), non_openrouter_proofs)
    if not lessons:
        return []
    feat = features(problem, None)
    record = {"schema": LESSON_SCHEMA, "row": feat["row"], "name": problem.get("name"), "source": feat["source"],
              "problem_type": classify_features(feat), "lessons": lessons, "winner_sha256": _sha(winner_code),
              "metrics": {key: value for key, value in (metrics or {}).items()
                          if key in ("token_reduction_pct", "hb_reduction_pct", "score")},
              "origin": "validated-openrouter-winner", "run_root": str(run_root),
              "recorded_at": datetime.now(timezone.utc).isoformat()}
    if record["metrics"].get("token_reduction_pct") is None:
        statement = str(problem.get("statement", ""))
        record["metrics"]["token_reduction_pct"] = round(
            100 * (1 - proof_tokens(winner_code, statement) / proof_tokens(problem_reference(problem), statement)), 2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # non-POSIX hosts run without a lock
        fcntl = None
    with path.open("a+", encoding="utf-8") as stream:
        if fcntl:
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            stream.seek(0)
            for line in stream.read().splitlines():
                try:
                    old = json.loads(line)
                except ValueError:
                    continue
                if old.get("row") == record["row"] and old.get("winner_sha256") == record["winner_sha256"]:
                    return lessons
            stream.seek(0, os.SEEK_END)
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            if fcntl:
                fcntl.flock(stream, fcntl.LOCK_UN)
    return lessons


# ----------------------------------------------------------------------- CLI

def load_outside_proofs(paths) -> list[str]:
    """Proof texts from .lean files and top-level `proof` fields of .json/.jsonl rows (PR #70 shape)."""
    found = []
    for path in map(Path, paths):
        files = sorted(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else [path]
        for file in files:
            if file.suffix == ".lean":
                found.append(file.read_text(encoding="utf-8"))
            elif file.suffix in (".json", ".jsonl"):
                text = file.read_text(encoding="utf-8")
                rows = [json.loads(line) for line in text.splitlines() if line.strip()] \
                    if file.suffix == ".jsonl" else json.loads(text)
                for row in rows if isinstance(rows, list) else [rows]:
                    if isinstance(row, dict) and isinstance(row.get("proof"), str):
                        found.append(row["proof"])
    return found


def main(argv=None) -> int:
    """Offline route preview; the orchestrator calls route() directly."""
    import argparse
    parser = argparse.ArgumentParser(prog="python -m lean_agent.final60.routing",
                                     description="final60 route preview (no model call, no Lean)")
    parser.add_argument("--problems", type=Path, help="directory of driver problems F0NN.json")
    parser.add_argument("--dataset", type=Path, help="benchmark JSONL; rows are numbered from 1")
    parser.add_argument("--baselines", type=Path, help="team baseline file (final60-baselines.json)")
    parser.add_argument("--non-openrouter", type=Path, action="append", default=[],
                        help="file or directory of non-OpenRouter proofs to leak-filter against")
    parser.add_argument("--bank", type=Path, action="append", default=[],
                        help="opt-in bank JSON or in-run lesson JSONL")
    parser.add_argument("--rows", type=int, nargs="*")
    parser.add_argument("--diversity", action="store_true")
    parser.add_argument("--out", type=Path, help="write {F0NN: route.json} here")
    args = parser.parse_args(argv)
    if args.problems:
        problems = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.problems.glob("F[0-9][0-9][0-9].json"))]
    elif args.dataset:
        lines = [line for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
        problems = [dict(json.loads(line), row=index) for index, line in enumerate(lines, 1)]
    else:
        parser.error("give --problems or --dataset")
    if args.rows:
        problems = [problem for problem in problems if problem_row(problem) in set(args.rows)]
    baselines = load_baselines(args.baselines) if args.baselines else None
    routes = route_all(problems, baselines, non_openrouter_proofs=load_outside_proofs(args.non_openrouter),
                       bank_paths=args.bank, diversity=args.diversity)
    for item in routes:
        print(f"F{item.row:03} {item.source:12} {item.problem_type:22} skip_llm={str(item.skip_llm):5} "
              f"priority={item.priority:7.3f} hints={len(item.hints)} addendum={len(prompt_addendum(item))}")
    print("schedule:", " ".join(f"F{row:03}" for row in schedule(routes, {item.row for item in routes})))
    if args.out:
        args.out.write_text(json.dumps({f"F{item.row:03}": route_json(item) for item in routes},
                                       ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
