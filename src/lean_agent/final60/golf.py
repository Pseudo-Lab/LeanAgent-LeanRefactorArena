"""Deterministic golf: compile-checked post-passes with no API spend.

``improve`` takes passing candidates (the original for golf-0, the top exploration
candidates for golf-1) and returns one ``GolfResult`` per candidate. A variant replaces
the incumbent only when its primary-version screen is valid and its official score
(mean of length, heartbeat and transfer axes, transfer assumed full) is strictly higher:
Delta L + Delta H > 0. Final selection re-validates on every listed version.

Pass order (amendment A14: linter and closer passes first):
  G5 decide variants (tiny ``decide`` proofs only), G1 linter-guided removals from the
  incumbent's own compile log, G2 ``try?`` closer probes (whole proof for short proofs,
  then terminal blocks), G3 local rewrites, G4 deletions, G2s ``simp?`` probe
  (``simp`` -> ``simp only [...]``, fewer heartbeats for more tokens; the score decides);
  then G1 again on a changed incumbent. Batches of non-overlapping edits are screened together and split in halves
  on failure (ddmin style; no splitting of deletions when T0 > ``ddmin_max_tokens``).

Stop rules: per-candidate compile budget, a per-call total, ``non_improving_stop``
consecutive non-improving compiles, two environment failures, the wall clock
(``minutes``) and the caller's deadline. A variant whose score bound with zero
heartbeats cannot beat the incumbent is skipped without compiling. Errors are caught per
variant and logged; golf never fails a row.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time

from .contracts import Candidate, EvalResult
from . import rewrites as rw, rules, scoring

# Amendment A7 budgets: <= 4 screens on the original, <= 12 per row on candidates (8 + 4).
DEFAULTS = {
    "original_compiles": 4,
    "top_k": 2,
    "max_compiles_best": 8,
    "max_compiles_other": 4,
    "max_compiles_total": 12,
    "minutes": 20,
    "non_improving_stop": 4,
    "ddmin_max_tokens": 600,
    "probe_timeout_s": 300,
    "root_probe_max_tokens": 150,
    "closer_blocks": 2,
    "probe_heartbeat_factor": 1.0,
    "suggestions_per_block": 2,
    "decide_max_tokens": 40,
    "linter_probe": False,
    "risky_rewrites": 2,
    "simp_probe": True,
    # A caller deadline also bounds the final validation that follows golf; keep this
    # much of it free (all versions + fresh 3x is about 4-12 Lean processes).
    "validation_reserve_s": 480,
}
LINTER_OPTIONS = ("linter.unusedSimpArgs true", "linter.unusedVariables true",
                  "linter.unusedTactic true", "linter.unreachableTactic true")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def provenance_sha(text: str) -> str:
    """PR #70 normalisation (strip outer newlines, trailing spaces per line)."""
    normalized = "\n".join(line.rstrip() for line in text.strip("\n").splitlines())
    return hashlib.sha256(normalized.encode()).hexdigest()


@dataclass
class GolfResult:
    best: Candidate
    tried: int
    accepted: list[str]
    log: list[dict]


class _Budget:
    def __init__(self, total: int, parent: "_Budget | None" = None):
        self.total, self.used, self.parent = int(total), 0, parent

    @property
    def left(self) -> int:
        own = self.total - self.used
        return min(own, self.parent.left) if self.parent else own

    def spend(self, count: int) -> None:
        self.used += count
        if self.parent:
            self.parent.spend(count)


class _Session:
    """Golf state for one candidate: incumbent, budget, stop rules and the log."""

    def __init__(self, adapter, statement: str, candidate: Candidate, *, budget: _Budget, deadline: float,
                 settings: dict, blocked=frozenset()):
        self.adapter, self.statement, self.root = adapter, statement, candidate
        self.budget, self.deadline, self.settings = budget, deadline, settings
        self.blocked = frozenset(blocked)
        self.t0, self.hb0 = adapter.baseline()
        self.code, self.result, self.score = candidate.code, candidate.screen, None
        self.seen = {sha(candidate.code)}
        self.accepted: list[str] = []
        self.log: list[dict] = []
        self.tried = self.non_improving = self.environment_failures = 0

    # ---- lifecycle -------------------------------------------------------------------------
    def ready(self) -> bool:
        if self.result is None:
            self.result = self._screen(self.code, "golf:parent:" + self.root.label)
        if self.result is None or not self.result.valid:
            self.log.append({"event": "parent-not-valid", "label": self.root.label})
            return False
        self.score = self.adapter.screen_score(self.result)
        return self.score is not None

    def alive(self) -> bool:
        return (self.budget.left > 0 and time.time() < self.deadline
                and self.non_improving < self.settings["non_improving_stop"]
                and self.environment_failures < 2)

    @property
    def tokens(self) -> int:
        return self.result.tokens

    def best_candidate(self) -> Candidate:
        if not self.accepted:
            return self.root
        return Candidate(code=self.code, sha256=sha(self.code), origin="golf", parent_sha256=self.root.sha256,
                         label=f"golf:{self.root.label}:{sha(self.code)[:12]}", screen=self.result)

    # ---- compiles ------------------------------------------------------------------------
    def _screen(self, code: str, label: str) -> EvalResult | None:
        before = self.adapter.compiles
        try:
            result = self.adapter.screen(code, label)
        except Exception as exc:  # golf errors never fail the row
            self.environment_failures += 1
            self.log.append({"event": "screen-error", "label": label, "error": f"{type(exc).__name__}: {exc}"[:500]})
            return None
        finally:
            used = self.adapter.compiles - before
            self.budget.spend(used)
        if used:
            self.tried += 1
        if result.error_kind == "environment":
            self.environment_failures += 1   # a timeout is a slow variant, not a broken machine
        return result

    def try_variant(self, name: str, code: str) -> bool:
        """Screen one proposal; adopt it iff the official score strictly improves."""
        if not self.alive():
            return False
        digest = sha(code)
        if digest in self.seen:
            return False
        self.seen.add(digest)
        entry = {"pass": name.split(":")[0], "name": name, "sha256": digest}
        if self.blocked and provenance_sha(code) in self.blocked:
            # PR #70 rejects a submission equal to a non-OpenRouter proof (amendment A12).
            self.log.append({**entry, "skipped": "equals-non-openrouter-proof"})
            return False
        issues = rules.check_static(code, self.statement)
        if issues:
            self.log.append({**entry, "skipped": "static", "issues": issues[:3]})
            return False
        try:
            tokens = self.adapter.tokens(code)
        except ValueError as exc:
            self.log.append({**entry, "skipped": "tokenizer", "error": str(exc)[:200]})
            return False
        entry["tokens"] = tokens
        if scoring.max_possible(tokens, self.t0) <= self.score + scoring.EPSILON:
            self.log.append({**entry, "skipped": "score-bound"})
            return False
        before = self.adapter.compiles
        result = self._screen(code, f"{name}:{self.root.label}")
        compiled = self.adapter.compiles - before
        if result is None:
            self.log.append({**entry, "compiled": compiled, "valid": False, "error_kind": "exception"})
            return False
        score = self.adapter.screen_score(result)
        better = result.valid and score is not None and scoring.improves(score, self.score)
        self.log.append({**entry, "compiled": compiled, "valid": result.valid, "raw_heartbeats": result.raw_heartbeats,
                         "score": score, "incumbent_score": self.score, "accepted": better,
                         "error_kind": result.error_kind})
        if better:
            self.code, self.result, self.score = code, result, score
            self.accepted.append(name)
            self.non_improving = 0
            return True
        if compiled:
            self.non_improving += 1
        return False

    def probe(self, text: str, label: str, options=()):
        if not self.alive():
            return None
        before = self.adapter.compiles
        try:
            returncode, log = self.adapter.probe(text, label, timeout_s=self.settings["probe_timeout_s"],
                                                 options=options)
            start = self.adapter.probe_start_line(text, options)
        except Exception as exc:
            self.log.append({"event": "probe-error", "label": label, "error": f"{type(exc).__name__}: {exc}"[:500]})
            return None
        finally:
            self.budget.spend(self.adapter.compiles - before)
        self.log.append({"event": "probe", "label": label, "returncode": returncode,
                         "compiled": self.adapter.compiles - before})
        return returncode, log, start


def search_edits(session: _Session, edits, pass_name: str, *, allow_split: bool = True) -> int:
    """Screen all non-overlapping edits at once, splitting a failing batch in halves."""
    edits = rw.non_overlapping(edits)
    if not edits:
        return 0
    base, applied, gained = session.code, [], 0
    queue = [edits]
    while queue and session.alive():
        batch = queue.pop(0)
        variant = rw.apply_edits(base, applied + batch)
        if variant is None or variant == session.code:
            continue
        kinds = sorted({edit.name.split(":", 1)[-1] for edit in batch})
        name = f"{pass_name}:{'+'.join(kinds)}x{len(batch)}"
        if session.try_variant(name, variant):
            applied += batch
            gained += 1
        elif len(batch) > 1 and allow_split:
            middle = len(batch) // 2
            queue[0:0] = [batch[:middle], batch[middle:]]
    return gained


def _linter_edits(session: _Session) -> list:
    edits, seen = [], set()
    for log, source in session.adapter.diagnostics(session.result):
        line = rw.declaration_start_line(source, session.code)
        if line is None:
            continue
        for edit in rw.linter_span_edits(session.code, session.statement, log, line):
            key = (edit.start, edit.end, edit.replacement)
            if key not in seen:
                seen.add(key)
                edits.append(edit)
    return edits


def pass_linter(session: _Session) -> int:
    edits = _linter_edits(session)
    if not edits and session.settings.get("linter_probe"):
        probed = session.probe(session.code, "G1:linter-probe", options=LINTER_OPTIONS)
        if probed and probed[2]:
            _, log, start = probed
            edits = rw.linter_span_edits(session.code, session.statement, log, start)
    # Removing an unused have outright and anonymising it overlap; the deletion goes first.
    edits.sort(key=lambda edit: (edit.name != "G1:drop-unused-have", edit.start))
    return search_edits(session, edits, "G1")


def probe_heartbeat_cap(session: _Session, searches: int) -> int:
    """Declaration ``maxHeartbeats`` for a search probe (thousands, Lean's unit).

    Measured 2026-11-04 on F027: four ``try?`` blocks under a 300 s wall limit were killed
    and Lean printed no message at all, because messages are emitted when the declaration
    finishes. A heartbeat cap instead ends the declaration with an error after the
    suggestions already logged, so they survive. Budget: the incumbent's own cost plus
    ``probe_heartbeat_factor`` times that per search, plus 20000.
    """
    scaled = max(1, int(session.result.raw_heartbeats or 0) // 1000)
    factor = float(session.settings["probe_heartbeat_factor"])
    return int(scaled * (1 + factor * max(1, searches)) + 20000)


def pass_closers(session: _Session) -> int:
    gained = 0
    scopes = (["root"] if session.tokens <= session.settings["root_probe_max_tokens"] else []) + ["blocks"]
    for scope in scopes:
        if not session.alive():
            break
        code = session.code
        try:
            text, block_map = rw.closer_probe(code, session.statement, scope=scope,
                                              max_blocks=session.settings["closer_blocks"])
        except ValueError:
            continue
        if not block_map:
            continue
        cap = probe_heartbeat_cap(session, len(block_map))
        probed = session.probe(text, f"G2:{scope}", options=(f"maxHeartbeats {cap}",))
        if not probed or not probed[2]:
            continue
        _, log, start = probed
        per_block = rw.suggestion_span_edits(code, block_map, log, decl_start_line=start,
                                             per_block=session.settings["suggestions_per_block"])
        if not per_block:
            continue
        if scope == "root":
            for edit in sorted((e for block in per_block for e in block), key=lambda e: len(e.replacement)):
                variant = rw.apply_edits(code, [edit])
                if variant and session.try_variant(edit.name, variant):
                    gained += 1
                    return gained          # the whole proof was replaced
            continue
        gained += search_edits(session, [block[0] for block in per_block], "G2")
        later = [block[1:] for block in per_block if len(block) > 1]
        if later and session.code == code:
            gained += search_edits(session, [block[0] for block in later], "G2", allow_split=False)
    return gained


def pass_local(session: _Session) -> int:
    gained = search_edits(session, rw.local_span_edits(session.code, session.statement), "G3")
    for _ in range(session.settings["risky_rewrites"]):
        if not session.alive():
            break
        options = [edit for edit in rw.risky_span_edits(session.code, session.statement)
                   if sha(rw.apply_edits(session.code, [edit]) or "") not in session.seen]
        if not options:
            break
        gained += search_edits(session, options[:1], "G3", allow_split=False)
    return gained


def pass_delete(session: _Session) -> int:
    allow_split = session.t0 <= session.settings["ddmin_max_tokens"]
    return search_edits(session, rw.deletion_span_edits(session.code, session.statement), "G4",
                        allow_split=allow_split)


def pass_simp_only(session: _Session) -> int:
    """``simp`` -> ``simp?`` suggestions (``simp only [...]``): more tokens, usually fewer HB."""
    if not session.settings.get("simp_probe", True):
        return 0
    try:
        text, sites = rw.simp_probe(session.code, session.statement)
    except ValueError:
        return 0
    if not sites:
        return 0
    probed = session.probe(text, "G2:simp?")
    if not probed or not probed[2]:
        return 0
    _, log, start = probed
    return search_edits(session, rw.simp_suggestion_edits(session.code, sites, log, decl_start_line=start), "G2s")


def pass_decide(session: _Session) -> int:
    if session.tokens > session.settings["decide_max_tokens"]:
        return 0
    variants = rw.decide_variants(session.code, session.statement)
    ranked = sorted(variants, key=lambda pair: (session.adapter.tokens(pair[1]), pair[0]))
    return sum(session.try_variant(name, code) for name, code in ranked)


PASSES = (("G5", pass_decide), ("G1", pass_linter), ("G2", pass_closers), ("G3", pass_local), ("G4", pass_delete),
          ("G2s", pass_simp_only))


def _run(session: _Session) -> None:
    for name, function in PASSES:
        if not session.alive():
            break
        try:
            function(session)
        except Exception as exc:  # a broken pass never fails the row
            session.log.append({"event": "pass-error", "pass": name, "error": f"{type(exc).__name__}: {exc}"[:500]})
    if session.accepted and session.alive():
        try:
            pass_linter(session)
        except Exception as exc:
            session.log.append({"event": "pass-error", "pass": "G1-repeat", "error": f"{type(exc).__name__}: {exc}"[:500]})


def improve(adapter, problem: dict, candidates: list[Candidate], route_golf: dict, *,
            deadline: float | None = None, non_openrouter_sha256=frozenset()) -> list[GolfResult]:
    """Golf each candidate in order within the route's compile and time budgets.

    Winners are also persisted under ``golf/winners/`` (see ``load_winners``) so a
    restarted row worker can still select them.
    """
    settings = {**DEFAULTS, **(route_golf or {})}
    started = time.time()
    stop_at = started + 60.0 * float(settings["minutes"])
    if deadline is not None:
        stop_at = min(stop_at, float(deadline) - float(settings["validation_reserve_s"]))
    statement = problem["statement"]
    if not candidates:
        return []
    original_only = all(candidate.origin == "original" for candidate in candidates)
    total = _Budget(settings["original_compiles"] if original_only else settings["max_compiles_total"])
    chosen = candidates[:1] if original_only else candidates[:max(0, int(settings["top_k"]))]
    results = []
    for index, candidate in enumerate(chosen):
        if total.left <= 0 or time.time() >= stop_at:
            reason = "compile budget" if total.left <= 0 else "time (deadline minus validation reserve)"
            results.append(GolfResult(best=candidate, tried=0, accepted=[],
                                      log=[{"event": "skipped", "label": candidate.label, "reason": reason}]))
            continue
        if candidate.origin == "original":
            allowance = settings["original_compiles"]
        else:
            allowance = settings["max_compiles_best"] if index == 0 else settings["max_compiles_other"]
        session = _Session(adapter, statement, candidate, budget=_Budget(allowance, total), deadline=stop_at,
                           settings=settings, blocked=non_openrouter_sha256)
        try:
            if session.ready():
                _run(session)
        except Exception as exc:
            session.log.append({"event": "golf-error", "error": f"{type(exc).__name__}: {exc}"[:500]})
        results.append(GolfResult(best=session.best_candidate(), tried=session.tried,
                                  accepted=list(session.accepted), log=session.log))
    _write_report(adapter, settings, results, started, total)
    _persist_winners(adapter, results)
    return results


WINNERS_SCHEMA = "final60-golf-winners-v1"


def _persist_winners(adapter, results) -> None:
    """Append golf winners (code + screen numbers) to ``golf/winners.json``."""
    try:
        folder = adapter.golf_dir
        index_path = folder / "winners.json"
        index = json.loads(index_path.read_text()) if index_path.exists() else {"schema": WINNERS_SCHEMA, "winners": []}
        known = {item["sha256"] for item in index["winners"]}
        changed = False
        for result in results:
            best = result.best
            if best.origin != "golf" or best.sha256 in known or best.screen is None:
                continue
            path = folder / "winners" / (best.sha256[:12] + ".lean")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(best.code)
            index["winners"].append({"sha256": best.sha256, "label": best.label, "parent_sha256": best.parent_sha256,
                                     "tokens": best.screen.tokens, "raw_heartbeats": best.screen.raw_heartbeats,
                                     "envs": best.screen.envs, "evidence_dir": best.screen.evidence_dir,
                                     "accepted": result.accepted, "code_path": path.name, "at": time.time()})
            known.add(best.sha256)
            changed = True
        if changed:
            temporary = index_path.with_name(index_path.name + f".tmp-{time.time_ns()}")
            temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(index_path)
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass


def load_winners(golf_dir) -> list[Candidate]:
    """Golf winners persisted by ``improve`` for this row, oldest first."""
    from pathlib import Path
    folder = Path(golf_dir)
    index_path = folder / "winners.json"
    if not index_path.exists():
        return []
    out = []
    for item in json.loads(index_path.read_text()).get("winners", []):
        path = folder / "winners" / item["code_path"]
        if not path.exists():
            continue
        code = path.read_text()
        if sha(code) != item["sha256"]:
            continue
        screen = EvalResult(True, item["tokens"], item["raw_heartbeats"], item["envs"], None, "", item["evidence_dir"])
        out.append(Candidate(code, item["sha256"], "golf", item.get("parent_sha256"), item["label"], screen))
    return out


def _write_report(adapter, settings, results, started, budget) -> None:
    try:
        folder = adapter.golf_dir
        folder.mkdir(parents=True, exist_ok=True)
        value = {"schema": "final60-golf-improve-v1", "started_at": started, "finished_at": time.time(),
                 "settings": settings, "compiles_used": budget.used,
                 "results": [{"best_label": r.best.label, "best_sha256": r.best.sha256, "origin": r.best.origin,
                              "parent_sha256": r.best.parent_sha256, "tried": r.tried, "accepted": r.accepted,
                              "best_tokens": r.best.screen.tokens if r.best.screen else None,
                              "best_raw_heartbeats": r.best.screen.raw_heartbeats if r.best.screen else None,
                              "log": r.log} for r in results]}
        path = folder / f"improve-{time.time_ns()}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    except (OSError, TypeError, AttributeError):
        pass
