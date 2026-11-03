"""Final selection for one row root: all versions, fresh 3x heartbeat, never below the original.

``candidates_from_run`` reads the driver's exploration archive (state.json), the current
``selected.lean`` and the original. ``select_final`` drops texts that equal a
non-OpenRouter proof (PR #70 normalisation) or fail the static rules, orders the rest by
screening score and validates in that order (every listed version, then a fresh 3x primary
measurement) until a validated candidate is at least as good as every remaining screen
estimate or ``k`` validations were spent. A candidate is selected only if its official
score is strictly above the original's 100/3; otherwise the original is selected.

``write_selection`` publishes the choice in the layout ``report.build_report`` audits:
``selected.lean``, ``compatibility/<sha>/`` and a fresh ``final/`` (a previous ``final/`` is
moved to ``final-prev-<sha12>-<ns>``). It keeps the driver summary's status, stop reason,
portfolio, cost and call count, and only updates ``selected``, ``final``,
``all_versions_valid`` and a ``golf`` block. Rows without a driver summary (skip_llm, salvage
after a crash, API disabled) get a summary synthesized from state.json, the row's ledger
entries and the portfolio replay, with status ``stopped`` unless the portfolio completed.
Validated runners-up are kept in ``golf/selection.json`` (code in ``golf/alternates/``) so
assembly can fall back to the next validated candidate before the original.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import shutil
import time

from .contracts import Candidate, EvalResult, Selection
from . import rules, scoring
from .evaladapter import driver as _driver, sha, _read

SELECTION_SCHEMA = "final60-golf-selection-v1"
SUMMARY_SOURCE = "final60.select.write_selection"


def provenance_normalize(text: str) -> str:
    """PR #70 check_submission_provenance.normalize."""
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def provenance_sha(text: str) -> str:
    return hashlib.sha256(provenance_normalize(text).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _baseline_eval(folder: Path, primary: str) -> EvalResult | None:
    from lean_agent import harness as h
    path = folder / "baseline/result.json"
    if not path.exists():
        return None
    measured = h.metrics(_read(path))
    if measured is None:
        return None
    return EvalResult(True, measured["tokens"], measured["raw_heartbeats"], {primary: True}, None, "", str(path.parent))


def _evidence(folder: Path, cid: str, value: dict) -> Path:
    step = int(value.get("step") or 0)
    if not step:
        return folder / "baseline"
    base = folder / "steps" / f"{step:04}"
    return base / "autosolver" / "evaluation" if cid.endswith("-auto") else base / "evaluation"


def candidates_from_run(run_root: Path, row: int, *, top: int = 6, include_golf: bool = True) -> list[Candidate]:
    """Top valid exploration candidates, persisted golf winners, the current selected.lean,
    then the original (always last)."""
    from lean_agent import harness as h
    from . import golf
    d = _driver()
    folder = d.folder(Path(run_root).resolve(), row)
    problem = _read(folder / "input/problem.json")
    reference, primary = problem["reference"], problem["environments"][0]
    out, seen = [], set()
    state_path = folder / "state.json"
    if state_path.exists():
        state = _read(state_path)
        unique: dict[str, tuple[str, dict]] = {}
        for cid, value in sorted(state.get("exploration", {}).get("candidates", {}).items(),
                                 key=lambda item: (item[1].get("step", 0), item[0])):
            code = value.get("code")
            # Warm-start/imported seeds carry provenance and are never golf parents.
            if (cid == "seed-best" or "provenance" in value or not value.get("valid") or not isinstance(code, str)
                    or code == reference or sha(code) != value.get("sha256") or "rank_numerator" not in value):
                continue
            unique.setdefault(value["sha256"], (cid, value))
        for cid, value in sorted(unique.values(), key=lambda item: h.ranking(item[1]))[:max(0, top)]:
            screen = EvalResult(True, value["tokens"], value["raw_heartbeats"], {primary: True}, None, "",
                                str(_evidence(folder, cid, value)))
            out.append(Candidate(value["code"], value["sha256"], "model", None, cid, screen))
            seen.add(value["sha256"])
    if include_golf:
        for winner in golf.load_winners(folder / "golf"):
            if winner.sha256 not in seen and winner.code != reference:
                out.append(winner)
                seen.add(winner.sha256)
    selected = folder / "selected.lean"
    if selected.exists():
        code = selected.read_text()
        digest = sha(code)
        if digest not in seen and code != reference:
            summary = _read(folder / "summary.json") if (folder / "summary.json").exists() else {}
            golf = summary.get("golf") or {}
            origin = golf.get("origin") if golf.get("origin") in ("model", "golf") else "model"
            out.append(Candidate(code, digest, origin, golf.get("parent_sha256"), "selected", None))
            seen.add(digest)
    out.append(Candidate(reference, sha(reference), "original", None, "c000", _baseline_eval(folder, primary)))
    return out


def select_final_stub(run_root: Path, row: int) -> Candidate | None:
    """Fallback when golf/selection is unavailable: the driver's selected.lean as is."""
    folder = _driver().folder(Path(run_root).resolve(), row)
    path = folder / "selected.lean"
    if not path.exists():
        return None
    code = path.read_text()
    return Candidate(code, sha(code), "model", None, "selected", None)


def _existing_selection(adapter) -> tuple[str, Path] | None:
    """The row's current selected.lean when its final/ evidence already matches it."""
    folder = adapter.folder
    path, receipt = folder / "selected.lean", folder / "final" / "evaluation-request.json"
    if not path.exists() or not receipt.exists() or not (folder / "final/result.json").exists():
        return None
    code = path.read_text()
    return (code, folder / "final") if _read(receipt).get("candidate_sha256") == sha(code) else None


def select_final(adapter, problem: dict, pool: list[Candidate], *, k: int = 3, deadline: float | None = None,
                 non_openrouter_sha256=frozenset(), keep: int = 3) -> Selection:
    """Validate in screening order; return the best validated candidate or the original."""
    t0, hb0 = adapter.baseline()
    total = len(problem["environments"])
    reference, statement = problem["reference"], problem["statement"]
    blocked = {str(value) for value in non_openrouter_sha256}
    dropped, unique = [], {}
    existing = _existing_selection(adapter)
    for candidate in pool:
        code = candidate.code
        if code == reference or sha(code) in unique:
            continue
        if provenance_sha(code) in blocked:
            dropped.append({"label": candidate.label, "sha256": sha(code), "reason": "equals-non-openrouter-proof"})
            continue
        issues = rules.check_static(code, statement)
        if issues:
            dropped.append({"label": candidate.label, "sha256": sha(code), "reason": "static", "issues": issues[:3]})
            continue
        unique[sha(code)] = candidate
    ranked = []
    for candidate in unique.values():
        screen = candidate.screen
        if screen is None and existing and existing[0] == candidate.code:
            screen = adapter.to_eval(_read(existing[1] / "result.json"), existing[1])
        if screen is None:
            try:
                screen = adapter.screen(candidate.code, candidate.label)
            except Exception as exc:
                dropped.append({"label": candidate.label, "reason": "screen-error", "error": str(exc)[:300]})
                continue
        estimate = adapter.screen_score(screen) if screen.valid else None
        if estimate is None:
            dropped.append({"label": candidate.label, "sha256": candidate.sha256, "reason": "screen-invalid"})
            continue
        ranked.append((estimate, candidate))
    # The current audited selection (driver or earlier golf) is re-checked first: free, cached.
    ranked.sort(key=lambda item: (not (existing and item[1].code == existing[0]), -item[0], item[1].sha256))
    validated, considered, errors = [], [], []
    best = scoring.ORIGINAL_SCORE
    attempts = 0
    for estimate, candidate in ranked:
        free = existing is not None and candidate.code == existing[0]
        if not free:
            if not scoring.improves(estimate, best) or attempts >= k:
                continue
            # The deadline limits extra validations; the top candidate is always checked,
            # since publishing anything (even the original) needs one validation.
            if deadline is not None and time.time() >= deadline and attempts:
                break
            attempts += 1
        considered.append(candidate.label)
        try:
            result = adapter.validate(candidate.code, candidate.label, as_final=False)
        except Exception as exc:
            errors.append({"label": candidate.label, "error": f"{type(exc).__name__}: {exc}"[:500]})
            continue
        if not result.valid:
            errors.append({"label": candidate.label, "error_kind": result.error_kind, "message": result.message[-300:]})
            continue
        score = scoring.problem_score(result.tokens, result.raw_heartbeats, total, total, t0, hb0)
        validated.append((score, candidate, result))
        best = max(best, score)
    validated.sort(key=lambda item: (-item[0], item[1].sha256))
    winners = [item for item in validated if scoring.improves(item[0], scoring.ORIGINAL_SCORE)]
    if winners:
        score, chosen, result = winners[0]
        beat = True
    else:
        chosen = Candidate(reference, sha(reference), "original", None, "c000", adapter.reference_result())
        result = adapter.validate(reference, "c000", as_final=False)
        if not result.valid:
            raise ValueError("Original proof failed all-version validation: " + (result.message or "")[-500:])
        score, beat = scoring.ORIGINAL_SCORE, False
        considered.append("c000")
    selection = Selection(candidate=chosen, validated=result, score=score, beat_original=beat,
                          considered=tuple(considered))
    _fingerprint(adapter, result)
    _record(adapter, selection, winners[1:1 + max(0, keep - 1)], dropped, errors)
    return selection


def _fingerprint(adapter, result: EvalResult) -> None:
    target = Path(result.evidence_dir) / "environment-fingerprints.json"
    if not result.evidence_dir or target.exists():
        return
    try:
        fingerprints = adapter.verify_environments()
        if fingerprints is not None:
            _driver().atomic(target, {"full_content_verification": True, "verified_at": _now(),
                                      "environments": fingerprints})
    except Exception as exc:  # recorded; the measurement evidence itself is unchanged
        _driver().atomic(target.with_name("environment-fingerprints-error.json"),
                         {"at": _now(), "error": f"{type(exc).__name__}: {exc}"[:1000]})


def _entry(score: float, candidate: Candidate, result: EvalResult) -> dict:
    return {"label": candidate.label, "sha256": candidate.sha256, "origin": candidate.origin,
            "parent_sha256": candidate.parent_sha256, "score": score, "tokens": result.tokens,
            "raw_heartbeats": result.raw_heartbeats, "envs": result.envs, "evidence_dir": result.evidence_dir}


def _record(adapter, selection: Selection, alternates, dropped, errors) -> None:
    folder = adapter.golf_dir
    stored = []
    for score, candidate, result in alternates:
        path = folder / "alternates" / (candidate.sha256[:12] + ".lean")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(candidate.code)
        stored.append({**_entry(score, candidate, result), "code_path": str(path)})
    _driver().atomic(folder / "selection.json", {
        "schema": SELECTION_SCHEMA, "at": _now(), "beat_original": selection.beat_original,
        "selected": _entry(selection.score, selection.candidate, selection.validated),
        "considered": list(selection.considered), "alternates": stored, "dropped": dropped,
        "validation_errors": errors, "published": False})


def alternates(run_root: Path, row: int) -> list[Selection]:
    """Validated runners-up recorded by select_final, best first (for assembly fallback)."""
    folder = _driver().folder(Path(run_root).resolve(), row) / "golf"
    path = folder / "selection.json"
    if not path.exists():
        return []
    out = []
    for item in _read(path).get("alternates", []):
        code = Path(item["code_path"]).read_text()
        if sha(code) != item["sha256"]:
            continue
        candidate = Candidate(code, item["sha256"], item["origin"], item.get("parent_sha256"), item["label"], None)
        result = EvalResult(True, item["tokens"], item["raw_heartbeats"], item["envs"], None, "", item["evidence_dir"])
        out.append(Selection(candidate, result, item["score"], True, (item["label"],)))
    return out


# ---- publication -------------------------------------------------------------------------------
def _ledger_totals(root: Path, row: int) -> tuple[Decimal, int]:
    ledger = _read(root / "ledger.json") if (root / "ledger.json").exists() else {"attempts": {}}
    attempts = [item for item in ledger.get("attempts", {}).values() if item.get("row") == row]
    spent = sum((Decimal(str(item["cost_usd"])) for item in attempts if item.get("cost_usd") is not None),
                Decimal(0))
    return spent, len(attempts)


def _synthesized_summary(root: Path, folder: Path, row: int, problem: dict, stop_reason: str | None) -> dict:
    from lean_agent import autosolver, harness as h, portfolio
    d = _driver()
    state = _read(folder / "state.json")
    config = _read(folder / "input/config.json")
    authorization = _read(root / "authorization.json") if (root / "authorization.json").exists() else {}
    spent, calls = _ledger_totals(root, row)
    summary = {"row": row, "id": problem["id"], "name": problem["name"], "status": "stopped",
               "stop_reason": stop_reason or "selection_without_driver_summary",
               "cost_usd": str(spent), "calls": calls,
               "baseline": h.metrics(_read(folder / "baseline/result.json")),
               "official_evaluation": False, "finished_at": _now(),
               "verification_policy": d.VERIFICATION_POLICY, "summary_source": SUMMARY_SOURCE}
    if portfolio.enabled(config):
        replay = portfolio.summary(state, config)
        summary["portfolio"] = replay
        if portfolio.finished(state):
            summary["stop_reason"] = portfolio.stop_reason(state, config)
        elif portfolio.completed(state, config):
            summary["stop_reason"] = "portfolio_budget_complete"
        if replay.get("complete"):
            summary["status"] = "completed"
    if autosolver.enabled(config):
        summary["autosolver"] = state.get("autosolver", {"searches": 0, "model_calls": 0})
    summary.update(cost_basis=authorization.get("budget_cost_basis", "provider-token-usage-times-frozen-public-list-prices"),
                   invoice_verified=False, provider=authorization.get("provider"),
                   model=(config.get("model") or {}).get("id"))
    return summary


def _selected_entry(folder: Path, selection: Selection) -> dict:
    candidate, digest = selection.candidate, selection.candidate.sha256
    state_path = folder / "state.json"
    if state_path.exists():
        for cid, value in _read(state_path).get("exploration", {}).get("candidates", {}).items():
            if value.get("sha256") == digest and value.get("valid"):
                return {key: item for key, item in value.items() if key != "code"}
    return {"sha256": digest, "tokens": selection.validated.tokens,
            "raw_heartbeats": selection.validated.raw_heartbeats, "origin": candidate.origin,
            "label": candidate.label, "parent_sha256": candidate.parent_sha256}


def write_selection(run_root: Path, row: int, selection: Selection, *, stop_reason: str | None = None) -> dict:
    """Publish ``selection`` into the row folder (selected.lean, final/, summary.json)."""
    from lean_agent import harness as h
    d = _driver()
    root = Path(run_root).resolve()
    folder = d.folder(root, row)
    problem = _read(folder / "input/problem.json")
    code = selection.candidate.code
    digest = sha(code)
    if digest != selection.candidate.sha256:
        raise ValueError("Selection candidate hash differs from its code")
    if not selection.validated.valid:
        raise ValueError("Refusing to publish a selection without all-version validation")
    if code != problem["reference"] and rules.check_static(code, problem["statement"]):
        raise ValueError("Refusing to publish a statically invalid proof")
    compatibility = folder / "compatibility" / digest / "result.json"
    checked = _read(compatibility) if compatibility.exists() else None
    if (not checked or not checked.get("valid")
            or set(checked.get("environments", {})) != set(problem["environments"])):
        raise ValueError("Missing all-version evidence for the selection: " + str(compatibility))
    source = Path(selection.validated.evidence_dir).resolve()
    final = folder / "final"
    receipt = _read(source / "evaluation-request.json")
    if receipt.get("candidate_sha256") != digest or receipt.get("options", {}).get("fresh") is not True:
        raise ValueError("Validated measurement belongs to a different candidate or is not fresh")
    if source != final.resolve():
        staging = folder / f".final-staging-{os.getpid()}-{time.time_ns()}"
        shutil.copytree(source, staging)
        if final.exists():
            previous = final / "evaluation-request.json"
            old = _read(previous).get("candidate_sha256", "unknown") if previous.exists() else "unknown"
            final.rename(folder / f"final-prev-{old[:12]}-{time.time_ns()}")
        staging.rename(final)
    measured = h.metrics(_read(final / "result.json"))
    if measured is None or len(measured["raw_samples"]) != 3:
        raise ValueError("Published final measurement is invalid")
    temporary = folder / f"selected.lean.tmp-{os.getpid()}"
    temporary.write_text(code)
    os.replace(temporary, folder / "selected.lean")
    summary_path = folder / "summary.json"
    summary = _read(summary_path) if summary_path.exists() else _synthesized_summary(root, folder, row, problem, stop_reason)
    summary.update(selected=_selected_entry(folder, selection), final=measured, all_versions_valid=True)
    t0, hb0 = summary["baseline"]["tokens"], summary["baseline"]["raw_heartbeats"]
    summary["golf"] = {"schema": SELECTION_SCHEMA, "origin": selection.candidate.origin,
                       "label": selection.candidate.label, "parent_sha256": selection.candidate.parent_sha256,
                       "beat_original": selection.beat_original, "considered": list(selection.considered),
                       "score_estimate": scoring.problem_score(measured["tokens"], measured["raw_heartbeats"],
                                                               len(problem["environments"]),
                                                               len(problem["environments"]), t0, hb0),
                       "selected_at": _now()}
    d.atomic(summary_path, summary)
    d.atomic(folder / "progress.json", {"row": row, "status": summary["status"], "cost_usd": summary["cost_usd"],
                                         "at": _now(), "selected_sha256": digest})
    record = folder / "golf" / "selection.json"
    if record.exists():
        value = _read(record)
        if value.get("selected", {}).get("sha256") == digest:
            d.atomic(record, {**value, "published": True, "published_at": _now()})
    return summary


# ---- convenience entry points for the row worker ------------------------------------------------
def golf_original(run_root: Path, row: int, route_golf: dict | None = None, *, deadline: float | None = None,
                  non_openrouter_sha256=frozenset(), adapter=None) -> list:
    """golf-0: golf the original once (early fallback). Winners persist for selection."""
    from . import golf
    from .evaladapter import EvalAdapter
    adapter = adapter or EvalAdapter(run_root, row)
    reference = adapter.problem["reference"]
    original = Candidate(reference, sha(reference), "original", None, "c000", adapter.reference_result())
    return golf.improve(adapter, adapter.problem, [original], route_golf or {}, deadline=deadline,
                        non_openrouter_sha256=non_openrouter_sha256)


def finalize_row(run_root: Path, row: int, route_golf: dict | None = None, *, golf_deadline: float | None = None,
                 validation_deadline: float | None = None, non_openrouter_sha256=frozenset(),
                 stop_reason: str | None = None, adapter=None, run_golf: bool = True, k: int = 3) -> dict:
    """golf-1 on the top exploration candidates, then select_final and write_selection.

    Never raises for golf problems; raises only if nothing (not even the original) can be
    validated and published, so the caller can fall back to the dataset original.
    """
    from . import golf
    from .evaladapter import EvalAdapter
    adapter = adapter or EvalAdapter(run_root, row)
    problem = adapter.problem
    settings = {**golf.DEFAULTS, **(route_golf or {})}
    results, golf_error = [], None
    if run_golf:
        parents = [c for c in candidates_from_run(run_root, row) if c.origin == "model"][:settings["top_k"]]
        if parents:
            try:
                results = golf.improve(adapter, problem, parents, settings, deadline=golf_deadline,
                                       non_openrouter_sha256=non_openrouter_sha256)
            except Exception as exc:  # golf never fails the row
                golf_error = f"{type(exc).__name__}: {exc}"[:500]
    pool = candidates_from_run(run_root, row)
    selection = select_final(adapter, problem, pool, k=k, deadline=validation_deadline,
                             non_openrouter_sha256=non_openrouter_sha256)
    summary = write_selection(run_root, row, selection, stop_reason=stop_reason)
    return {"row": row, "selected_sha256": selection.candidate.sha256, "origin": selection.candidate.origin,
            "label": selection.candidate.label, "beat_original": selection.beat_original,
            "score_estimate": summary["golf"]["score_estimate"], "considered": list(selection.considered),
            "status": summary["status"], "golf_error": golf_error, "compiles": adapter.compiles,
            "golf": [{"best_sha256": r.best.sha256, "origin": r.best.origin, "tried": r.tried,
                      "accepted": r.accepted} for r in results]}
