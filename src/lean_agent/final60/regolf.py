"""Second, API-free golf pass over rows that are already published (run plan section 6, Stage 10).

``python -m lean_agent.final60 regolf --run-dir RUN --rows ROWS [--compiles 24] [--margin 0.25]
[--minutes 30] [--compiler-slots N] [--report-only] [--repair-only] [--allow-dev-roots]
[--transfer-repair [--repairs N]]``

For every selected row that is terminal (RowState ``published``, ``done`` or ``fallback``)
and whose ``published.json`` is a model-produced publication (origin ``openrouter-run`` of a
submittable OpenRouter root; with ``--allow-dev-roots`` also the mock/dry-run and
OpenAI-direct development roots, for testing only), the pass

1. takes the row's ``worker.lock`` (a row whose worker holds it is skipped) and checks the
   frozen code exactly as a resumed worker does (``driver.verify_frozen``);
2. golfs the incumbent ``selected.lean`` with the normal passes (``golf.improve``) under a
   budget of ``--compiles`` screens; screens and probes are cached by content, so variants
   the first pass already tried cost nothing;
3. runs ``select_final`` over the incumbent plus the golf winners (every listed toolchain and
   the same fresh 3x primary measurement as the normal path; the incumbent re-check is free);
4. only when the validated local estimate beats the published estimate by at least
   ``--margin`` points: ``write_selection`` (selected.lean, final/, summary.json), a rebuilt
   ``report.json`` and, last, a rewritten ``published.json``, each written atomically, so the
   next rolling assembly picks the new proof up. If the rebuilt report fails its audit or does
   not show the gain, the previous selection is restored the same way (``write_selection``
   from the kept ``final-prev-*`` evidence, report, then ``published.json``).

Before anything else under the lock the pass repairs an interrupted publication: when
``selected.lean`` (or ``report.json``) no longer matches ``published.json`` because a regolf or
alternates-fallback publication was killed between ``write_selection`` and ``published.json``,
the published proof is restored from its kept ``final-prev-<sha12>-*`` evidence (the rollback
path above), the report is rebuilt and ``published.json`` rewritten; the row's record says
``repaired``. ``--repair-only`` does just that and never golfs.

``--transfer-repair`` (hotfix 2026-11-04) replaces step 2 by the deprecated-alias transfer
repair (``transfer``): the row's recorded candidates whose saved all-version check failed
only on non-primary toolchains (exploration's own check or the selection's validation)
are repaired by the alias map of the row's environment set, validated like any finalist,
and the best one is published through the same path (step 3-4) when it beats the published
estimate by ``--margin``. In this mode rows that publish the original (not a fallback) are
eligible too, since those are the rows that lost the most. At most
``transfer.MAX_REPAIRS_POSTHOC`` repairs are validated per row. No golf pass runs; a
later plain ``regolf`` golfs the repaired incumbent. The interrupted-publication repair above
runs first in every mode.

Never any API call: no transport is imported and the ledger is untouched. Rows that are not
terminal are never touched. ``--report-only`` lists what would run (no Lean, no write).
Every attempt is recorded under ``rows/F0NN/regolf/`` and appended to the ``regolf`` list of
``worker-state.json`` (the first pass's ``golf`` block stays); the golf stage itself records
its usual ``golf/improve-*.json``, ``golf/winners.json``, ``golf/events.jsonl`` and
``golf/selection.json``. A published regolf also adds a ``regolf`` event to the RowState.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import time
import traceback

from .contracts import Candidate, EvalResult, Selection
from .orchestrator import (DEFAULT_DEADLINE, TERMINAL, Layout, RunOptions, atomic_bytes, atomic_json, driver_modules,
                           json_bytes, load_non_openrouter, load_rowstate, normalized_sha, now_iso, parse_deadline,
                           parse_rows, problem_packet, read_json, save_rowstate, sha_bytes, sha_text)
from . import golf, scoring, select, transfer

DEFAULT_COMPILES = 24
DEFAULT_MARGIN = 0.25
DEFAULT_MINUTES = 30.0
# rowworker.RowWorker.PUBLISH_MARGIN: the gain over the original (100/3) any publication needs.
PUBLISH_MARGIN = 0.25
# Keep this much of the row deadline for the final validation (golf.DEFAULTS["validation_reserve_s"]).
VALIDATION_RESERVE_S = 480
# The run's last 20 minutes belong to the final assemblies (supervisor deadline actions).
DEADLINE_RESERVE_S = 20 * 60
SCHEMA = "final60-regolf-v1"


class WorkerBusy(Exception):
    pass


class RowLock:
    """The row worker's flock (rows/F0NN/worker.lock); a live worker makes the row busy."""

    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
            raise WorkerBusy("a worker holds " + str(self.path)) from None
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps({"pid": os.getpid(), "at": now_iso(), "regolf": True}) + "\n")
        stream.flush()
        self.stream = stream
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.stream, fcntl.LOCK_UN)
        self.stream.close()
        return False


def read_or(path, default):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return default


def eligibility(layout, row, *, allow_dev_roots=False, allow_original=False):
    """(ok, reason): a terminal row whose publication is a model proof of a submittable root.

    With ``allow_original`` (transfer repair) a worker publication of the original (one that
    carries ``selected_sha256`` and ``report_sha256``; not a fallback) is eligible too.
    """
    from . import transports
    root, folder = layout.row_root(row), layout.row_folder(row)
    state = load_rowstate(layout, row)
    if state.status not in TERMINAL:
        return False, f"not terminal (status {state.status})"
    if not (root / "published.json").exists():
        return False, "not published"
    published = read_or(root / "published.json", {})
    original_ok = (allow_original and published.get("origin") == "original"
                   and isinstance(published.get("selected_sha256"), str) and isinstance(published.get("report_sha256"), str))
    if published.get("origin") != "openrouter-run" and not original_ok:
        return False, "publishes the original (" + str(published.get("reason") or "no reason")[:160] + ")"
    missing = [name for name in ("authorization.json", "ledger.json", "report.json") if not (root / name).exists()]
    missing += [name for name in ("selected.lean", "summary.json", "final/result.json", "input/problem.json")
                if not (folder / name).exists()]
    if missing:
        return False, "missing run evidence: " + ", ".join(missing)
    authorization = read_or(root / "authorization.json", {})
    submittable, why = transports.is_submittable(authorization)
    if not submittable and not allow_dev_roots:
        return False, f"development root ({why}); --allow-dev-roots is for testing only"
    code = (folder / "selected.lean").read_text(encoding="utf-8")
    if sha_text(code) != published.get("selected_sha256"):
        return False, "selected.lean changed after publication"
    if sha_bytes((root / "report.json").read_bytes()) != published.get("report_sha256"):
        return False, "report.json changed after publication"
    if not isinstance(published.get("local_score_estimate"), (int, float)):
        return False, "publication carries no local score estimate"
    return True, None


def run_options(layout, *, compiler_slots=None, deadline=None):
    """The run's saved options (run-options.json) for the evaluator environment; flags override."""
    saved = read_or(layout.options, {})
    chosen = parse_deadline(deadline or saved.get("deadline") or DEFAULT_DEADLINE)
    slots = int(compiler_slots or saved.get("compiler_slots") or 2)
    memory = saved.get("lean_memory_mib")
    return RunOptions(run_dir=layout.run_dir, compiler_slots=max(1, min(8, slots)), deadline=chosen,
                      prepared_repo=Path(saved["prepared_repo"]).resolve() if saved.get("prepared_repo") else None,
                      transport=saved.get("transport"), lean_memory_mib=int(memory) if memory else None,
                      mem_reserve_gib=float(saved.get("mem_reserve_gib", 6.0)),
                      gib_per_compile=float(saved.get("gib_per_compile", 3.5)))


def golf_settings(route, compiles, minutes):
    """The row's route golf settings with the whole budget on the single incumbent."""
    settings = {**golf.DEFAULTS, **dict((route or {}).get("golf") or {})}
    settings.update(top_k=1, original_compiles=int(compiles), max_compiles_best=int(compiles),
                    max_compiles_other=0, max_compiles_total=int(compiles), minutes=float(minutes),
                    non_improving_stop=max(int(settings.get("non_improving_stop", 4)), int(compiles) // 2),
                    validation_reserve_s=VALIDATION_RESERVE_S)
    return settings


def incumbent_candidate(root, row, folder):
    """The published selected.lean as a Candidate (its exploration or golf screen when known)."""
    code = (folder / "selected.lean").read_text(encoding="utf-8")
    for candidate in select.candidates_from_run(root, row):
        if candidate.code == code:
            return candidate
    summary = read_or(folder / "summary.json", {})
    origin = (summary.get("golf") or {}).get("origin")
    return Candidate(code, sha_text(code), origin if origin in ("model", "golf") else "model",
                     (summary.get("golf") or {}).get("parent_sha256"), "selected", None)


def kept_evidence(folder, digest):
    """The newest kept ``final-prev-<sha12>-*`` directory whose receipt names ``digest`` (or None)."""
    if not digest or len(digest) < 12:
        return None
    for path in sorted(folder.glob(f"final-prev-{digest[:12]}-*"), key=lambda item: item.name, reverse=True):
        if read_or(path / "evaluation-request.json", {}).get("candidate_sha256") == digest:
            return path
    return None


def interrupted_publication(layout, row):
    """A model publication cut between ``write_selection`` and ``published.json`` (or None).

    ``selected.lean`` or ``report.json`` differs from what ``published.json`` certifies, so the
    assembler would silently carry the original for this row (assemble.published_proof).
    """
    root, folder = layout.row_root(row), layout.row_folder(row)
    published = read_or(root / "published.json", None)
    if not isinstance(published, dict) or published.get("origin") != "openrouter-run":
        return None
    if not (folder / "selected.lean").exists() or not (root / "report.json").exists():
        return None
    digest = str(published.get("selected_sha256") or "")
    current = sha_text((folder / "selected.lean").read_text(encoding="utf-8"))
    report_ok = sha_bytes((root / "report.json").read_bytes()) == published.get("report_sha256")
    if current == digest and report_ok:
        return None
    return {"published": published, "published_sha256": digest, "current_sha256": current, "report_ok": report_ok,
            "kept": kept_evidence(folder, digest)}


def published_candidate(layout, row, digest):
    """The published proof (sha256 ``digest``) from the row's own records, or None.

    Exploration candidates and golf winners (select.candidates_from_run), the incumbent regolf
    saved before publishing, select_final's stored alternates, then the driver's step candidates.
    """
    root, folder = layout.row_root(row), layout.row_folder(row)
    try:
        for candidate in select.candidates_from_run(root, row, top=10 ** 6):
            if candidate.sha256 == digest:
                return candidate
    except (OSError, ValueError, KeyError, TypeError):
        pass
    saved = read_or(root / "regolf" / "incumbents" / f"{digest[:12]}.json", {})
    if isinstance(saved.get("code"), str) and sha_text(saved["code"]) == digest:
        origin = saved.get("origin") if saved.get("origin") in ("model", "golf") else "model"
        return Candidate(saved["code"], digest, origin, saved.get("parent_sha256"), saved.get("label") or "published", None)
    paths = [folder / "golf" / "alternates" / (digest[:12] + ".lean")] + sorted(folder.glob("steps/*/candidate.lean"))
    for path in paths:
        try:
            code = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if sha_text(code) == digest:
            return Candidate(code, digest, "model", None, "published", None)
    return None


def previous_selection(adapter, folder, candidate, score):
    """The incumbent as a Selection whose evidence is the kept ``final-prev-<sha12>-*`` copy."""
    evidence = kept_evidence(folder, candidate.sha256)
    if evidence is None:
        kept = sorted(folder.glob(f"final-prev-{candidate.sha256[:12]}-*"), key=lambda path: path.name)
        if not kept:
            raise ValueError("no kept final evidence for the previous selection")
        evidence = kept[-1]
    measured = adapter.to_eval(read_json(evidence / "result.json"), evidence)
    if not measured.valid:
        raise ValueError("kept final evidence of the previous selection is not valid")
    envs = {env: True for env in adapter.environments}
    validated = EvalResult(True, measured.tokens, measured.raw_heartbeats, envs, None, "", str(evidence))
    return Selection(candidate=candidate, validated=validated, score=float(score), beat_original=True,
                     considered=(candidate.label,))


class RegolfRow:
    """One regolf pass over one published row. Every Lean compile goes through EvalAdapter."""

    def __init__(self, layout, row, opts, *, compiles=DEFAULT_COMPILES, margin=DEFAULT_MARGIN,
                 minutes=DEFAULT_MINUTES, allow_dev_roots=False, repair_only=False, transfer_repair=False,
                 repairs=None):
        self.layout, self.row, self.opts = layout, int(row), opts
        self.compiles, self.margin, self.minutes = int(compiles), float(margin), float(minutes)
        self.allow_dev_roots, self.repair_only = bool(allow_dev_roots), bool(repair_only)
        self.transfer_repair = bool(transfer_repair)
        self.repairs = int(repairs) if repairs is not None else transfer.MAX_REPAIRS_POSTHOC
        self.root = layout.row_root(row)
        self.folder = layout.row_folder(row)
        self.started = time.time()
        self.record = {"schema": SCHEMA, "row": self.row, "at": now_iso(), "compiles_budget": self.compiles,
                       "margin": self.margin, "action": None, "reason": None, "mode": "transfer-repair" if self.transfer_repair else "golf"}

    def eligible(self):
        return eligibility(self.layout, self.row, allow_dev_roots=self.allow_dev_roots, allow_original=self.transfer_repair)

    # -- hooks (tests patch these) -------------------------------------------------------------
    def adapter(self):
        from .evaladapter import EvalAdapter
        return EvalAdapter(self.root, self.row)

    def configure(self, packet):
        from .rowworker import configure_environment
        return configure_environment(self.opts, packet)

    def verify_frozen(self):
        driver, _ = driver_modules()
        driver.verify_frozen(self.root)

    def build_report(self):
        _, report = driver_modules()
        return report.build_report(self.root)

    # -- state helpers -------------------------------------------------------------------------
    def worker_state(self):
        return read_or(self.layout.worker_path(self.row), {})

    def note(self, **values):
        self.record.update(values)
        return self.record

    def finish(self, action, reason=None, **values):
        self.note(action=action, reason=reason, seconds=round(time.time() - self.started, 3), **values)
        try:
            path = self.root / "regolf" / f"{time.time_ns()}.json"
            atomic_json(path, self.record)
            state = self.worker_state()
            history = list(state.get("regolf") or [])
            history.append({key: self.record.get(key) for key in (
                "at", "action", "reason", "incumbent_estimate", "regolf_estimate", "selected_sha256", "label",
                "compiles", "seconds", "accepted", "considered")})
            atomic_json(self.layout.worker_path(self.row), {**state, "regolf": history[-20:], "updated_at": now_iso()})
        except OSError:
            pass
        return self.record

    # -- the pass ------------------------------------------------------------------------------
    def run(self):
        ok, reason = self.eligible()
        # A row whose files changed after publication may be an interrupted publication: repair under the lock.
        if not ok and "changed after publication" not in str(reason):
            return self.note(action="skipped", reason=reason)
        try:
            with RowLock(self.root / "worker.lock"):
                return self.locked()
        except WorkerBusy as exc:
            return self.note(action="skipped", reason=str(exc))

    def locked(self):
        try:
            self.verify_frozen()
        except (OSError, ValueError) as exc:
            return self.finish("skipped", "frozen code check failed: " + str(exc)[:300])
        try:
            repaired = self.repair()
        except Exception as exc:   # the row stays as it is; the operator sees the record
            return self.finish("error", "repair failed: " + f"{type(exc).__name__}: {exc}"[:500],
                               traceback=traceback.format_exc()[-4000:])
        if repaired is not None:
            return repaired
        # Re-read under the lock: a worker may have republished between the check and the lock.
        ok, reason = self.eligible()
        if not ok:
            return self.note(action="skipped", reason=reason)
        if self.repair_only:
            return self.note(action="skipped", reason="repair-only: publication intact")
        deadline = min(self.started + self.minutes * 60 + VALIDATION_RESERVE_S,
                       self.opts.deadline_epoch() - DEADLINE_RESERVE_S)
        if deadline - VALIDATION_RESERVE_S <= time.time():
            return self.finish("skipped", "no time left before the run deadline")
        try:
            return self.repair_and_select(deadline) if self.transfer_repair else self.golf_and_select(deadline)
        except Exception as exc:   # a failed pass never changes the row
            return self.finish("error", f"{type(exc).__name__}: {exc}"[:500], traceback=traceback.format_exc()[-4000:])

    def repair_and_select(self, deadline):
        """``--transfer-repair``: alias-repair the recorded transfer failures, then select/publish."""
        published = read_json(self.root / "published.json")
        incumbent_estimate = float(published.get("local_score_estimate") or scoring.ORIGINAL_SCORE)
        problem = read_json(self.folder / "input/problem.json")
        try:
            packet = problem_packet(self.row)
        except (OSError, ValueError):
            packet = None
        environment = self.configure(packet)
        outside = {normalized_sha(entry["proof"]) for entry in load_non_openrouter(self.layout)}
        adapter = self.adapter()
        incumbent = incumbent_candidate(self.root, self.row, self.folder)
        self.note(incumbent_estimate=incumbent_estimate, incumbent_sha256=incumbent.sha256,
                  incumbent_label=incumbent.label, environment=environment,
                  compiler_parallelism=getattr(getattr(adapter, "ev", None), "compiler_parallelism", None))
        blocked = transfer.gate_blocks(adapter, problem)
        if blocked:
            return self.finish("skipped", "transfer repair not allowed: " + blocked, compiles=adapter.compiles)
        pool, known = [incumbent], {incumbent.sha256}
        records, budget = [], self.repairs
        # Recorded candidates whose saved all-version check failed, best screen estimate first.
        failed = [candidate for candidate in select.candidates_from_run(self.root, self.row)
                  if candidate.origin != "original" and candidate.sha256 not in known
                  and transfer.compat_status(self.folder, candidate.sha256) == "invalid"]
        failed.sort(key=lambda candidate: (-(adapter.screen_score(candidate.screen) or 0.0) if candidate.screen else 0.0,
                                           candidate.sha256))
        for candidate in failed:
            if budget <= 0 or time.time() >= deadline:
                break
            repaired, _, record = transfer.repair_known(adapter, problem, candidate, blocked=frozenset(outside),
                                                        deadline=deadline)
            records.append(record)
            if "valid" in record or "error" in record:
                budget -= 1
            if repaired is not None and repaired.sha256 not in known and normalized_sha(repaired.code) not in outside:
                pool.append(repaired)
                known.add(repaired.sha256)
        self.note(repairs=records, examined=len(failed), accepted=[c.label for c in pool[1:]],
                  winners=[item.sha256 for item in pool[1:]], compiles=adapter.compiles)
        if len(pool) == 1:
            return self.finish("kept", "no transfer failure repaired", compiles=adapter.compiles)
        record_path = self.folder / "golf" / "selection.json"
        previous_record = record_path.read_bytes() if record_path.exists() else None
        selection = select.select_final(adapter, problem, pool, k=3, deadline=deadline,
                                        non_openrouter_sha256=frozenset(outside))
        gain = selection.score - incumbent_estimate
        self.note(regolf_estimate=selection.score, selected_sha256=selection.candidate.sha256,
                  label=selection.candidate.label, considered=list(selection.considered), gain=gain,
                  compiles=adapter.compiles)
        improves = (selection.beat_original and selection.candidate.sha256 != incumbent.sha256
                    and gain + 1e-9 >= self.margin
                    and selection.score >= scoring.ORIGINAL_SCORE + PUBLISH_MARGIN)
        if not improves:
            if previous_record is not None:
                atomic_bytes(self.folder / "golf" / f"regolf-selection-{time.time_ns()}.json", record_path.read_bytes())
                atomic_bytes(record_path, previous_record)
            reason = ("validated estimate does not beat the incumbent by the margin"
                      if selection.candidate.sha256 != incumbent.sha256 else "incumbent stays the best validated")
            return self.finish("kept", reason, compiles=adapter.compiles)
        return self.publish_selection(adapter, incumbent, incumbent_estimate, selection)

    def golf_and_select(self, deadline):
        published = read_json(self.root / "published.json")
        incumbent_estimate = float(published["local_score_estimate"])
        problem = read_json(self.folder / "input/problem.json")
        try:
            packet = problem_packet(self.row)
        except (OSError, ValueError):
            packet = None
        environment = self.configure(packet)
        route = read_or(self.folder / "input/route.json", {})
        settings = golf_settings(route, self.compiles, self.minutes)
        outside = {normalized_sha(entry["proof"]) for entry in load_non_openrouter(self.layout)}
        adapter = self.adapter()
        incumbent = incumbent_candidate(self.root, self.row, self.folder)
        self.note(incumbent_estimate=incumbent_estimate, incumbent_sha256=incumbent.sha256,
                  incumbent_label=incumbent.label, environment=environment,
                  compiler_parallelism=getattr(getattr(adapter, "ev", None), "compiler_parallelism", None))
        results = golf.improve(adapter, problem, [incumbent], settings, deadline=deadline,
                               non_openrouter_sha256=frozenset(outside))
        pool, known = [incumbent], {incumbent.sha256}
        for result in results:
            best = result.best
            if best.sha256 not in known and best.origin == "golf" and normalized_sha(best.code) not in outside:
                pool.append(best)
                known.add(best.sha256)
        accepted = [name for result in results for name in result.accepted]
        tried = sum(result.tried for result in results)
        self.note(accepted=accepted, tried=tried, winners=[item.sha256 for item in pool[1:]], compiles=adapter.compiles)
        if len(pool) == 1:
            return self.finish("kept", "golf found no better variant", compiles=adapter.compiles)
        # The previous selection record is restored when nothing is published (select_final rewrites it).
        record_path = self.folder / "golf" / "selection.json"
        previous_record = record_path.read_bytes() if record_path.exists() else None
        selection = select.select_final(adapter, problem, pool, k=3, deadline=deadline,
                                        non_openrouter_sha256=frozenset(outside))
        gain = selection.score - incumbent_estimate
        self.note(regolf_estimate=selection.score, selected_sha256=selection.candidate.sha256,
                  label=selection.candidate.label, considered=list(selection.considered), gain=gain,
                  compiles=adapter.compiles)
        improves = (selection.beat_original and selection.candidate.sha256 != incumbent.sha256
                    and gain + 1e-9 >= self.margin
                    and selection.score >= scoring.ORIGINAL_SCORE + PUBLISH_MARGIN)
        if not improves:
            if previous_record is not None:
                atomic_bytes(self.folder / "golf" / f"regolf-selection-{time.time_ns()}.json", record_path.read_bytes())
                atomic_bytes(record_path, previous_record)
            reason = ("validated estimate does not beat the incumbent by the margin"
                      if selection.candidate.sha256 != incumbent.sha256 else "incumbent stays the best validated")
            return self.finish("kept", reason, compiles=adapter.compiles)
        return self.publish_selection(adapter, incumbent, incumbent_estimate, selection)

    def repair(self):
        """Restore a publication that was cut between write_selection and published.json.

        Returns the row's record when a repair was attempted (``repaired``, or ``skipped`` with
        the reason it could not be done), None when the publication is intact.
        """
        found = interrupted_publication(self.layout, self.row)
        if found is None:
            return None
        published, digest = found["published"], found["published_sha256"]
        info = {"previous_sha256": digest, "previous_estimate": published.get("local_score_estimate"),
                "interrupted_sha256": found["current_sha256"], "report_matched": found["report_ok"],
                "accepted": None, "compiles": 0, "rolled_back": True, "repaired": True}
        self.note(repair=info)
        if found["kept"] is None:
            return self.finish("skipped", "interrupted publication: no kept final-prev evidence for the published proof "
                               + digest[:12] + "; restore it by hand before the next upload")
        candidate = published_candidate(self.layout, self.row, digest)
        if candidate is None:
            return self.finish("skipped", "interrupted publication: the published proof text " + digest[:12]
                               + " is in no row record; restore it by hand before the next upload")
        try:
            packet = problem_packet(self.row)
        except (OSError, ValueError):
            packet = None
        self.configure(packet)
        adapter = self.adapter()
        estimate = published.get("local_score_estimate")
        restored = previous_selection(adapter, self.folder, candidate,
                                      float(estimate) if isinstance(estimate, (int, float)) else scoring.ORIGINAL_SCORE)
        select.write_selection(self.root, self.row, restored)
        report = self.build_report()
        value = self.publish(report, {**info, "audit_errors": list(report.get("audit_errors") or [])[:4]})
        return self.finish("repaired", "interrupted publication restored from kept final evidence of " + digest[:12],
                           compiles=0, published=value["origin"], audit_passed=report["audit_passed"],
                           selected_sha256=value["selected_sha256"], regolf_estimate=value["local_score_estimate"])

    def publish_selection(self, adapter, incumbent, incumbent_estimate, selection):
        """write_selection -> report.json -> published.json; roll back if the audit disagrees."""
        # The incumbent's text, so a kill inside the publication window can be repaired (see repair()).
        atomic_json(self.root / "regolf" / "incumbents" / f"{incumbent.sha256[:12]}.json",
                    {"sha256": incumbent.sha256, "code": incumbent.code, "origin": incumbent.origin,
                     "label": incumbent.label, "parent_sha256": incumbent.parent_sha256, "at": now_iso()})
        select.write_selection(self.root, self.row, selection)
        report = self.build_report()
        entry = next((item for item in report["rows"] if item["row"] == self.row), {})
        score = entry.get("local_score_estimate")
        agreed = (report["audit_passed"] and entry.get("selected_sha256") == selection.candidate.sha256
                  and isinstance(score, (int, float)) and score + 1e-9 >= incumbent_estimate + self.margin)
        if agreed:
            value = self.publish(report, {"previous_sha256": incumbent.sha256, "previous_estimate": incumbent_estimate,
                                          "accepted": self.record.get("accepted"), "compiles": adapter.compiles,
                                          "rolled_back": False})
            state = load_rowstate(self.layout, self.row)
            state.selected_sha256 = value["selected_sha256"]
            state.score_estimate = value["local_score_estimate"]
            save_rowstate(self.layout, state, {"event": "regolf", "origin": value["origin"],
                                               "score": value["local_score_estimate"],
                                               "previous_score": incumbent_estimate})
            return self.finish("published", None, compiles=adapter.compiles, published=value["origin"],
                               audit_passed=report["audit_passed"])
        problems = list(report.get("audit_errors") or [])[:4] or [f"report estimate {score} for {entry.get('selected_sha256')}"]
        self.note(audit_errors=problems)
        restored = previous_selection(adapter, self.folder, incumbent, incumbent_estimate)
        select.write_selection(self.root, self.row, restored)
        report = self.build_report()
        value = self.publish(report, {"previous_sha256": incumbent.sha256, "previous_estimate": incumbent_estimate,
                                      "accepted": self.record.get("accepted"), "compiles": adapter.compiles,
                                      "rolled_back": True, "rejected_sha256": selection.candidate.sha256,
                                      "audit_errors": problems})
        return self.finish("rolled-back", "rebuilt report did not confirm the regolfed selection: " + "; ".join(problems)[:400],
                           compiles=adapter.compiles, published=value["origin"], audit_passed=report["audit_passed"])

    def publish(self, report, regolf_info):
        """The row worker's publication record (rowworker.audit_and_publish) plus a ``regolf`` block."""
        problem = read_json(self.folder / "input/problem.json")
        report_bytes = json_bytes(report)
        atomic_bytes(self.root / "report.json", report_bytes)
        entry = next((item for item in report["rows"] if item["row"] == self.row), {})
        code = (self.folder / "selected.lean").read_text(encoding="utf-8")
        score = entry.get("local_score_estimate")
        improved = (report["audit_passed"] and "final" in entry
                    and normalized_sha(code) != normalized_sha(problem["reference"])
                    and isinstance(score, (int, float)) and score >= scoring.ORIGINAL_SCORE + PUBLISH_MARGIN)
        value = {"row": self.row, "name": problem["name"], "at": now_iso(),
                 "origin": "openrouter-run" if improved else "original",
                 "selected_sha256": sha_text(code), "report_sha256": sha_bytes(report_bytes),
                 "audit_passed": report["audit_passed"],
                 "local_score_estimate": score if improved else scoring.ORIGINAL_SCORE,
                 "cost_usd": entry.get("known_cost_usd"), "calls": entry.get("calls"), "status": entry.get("status"),
                 "golf": self.worker_state().get("golf"), "regolf": {"schema": SCHEMA, "at": now_iso(), **regolf_info}}
        if not improved:
            value["reason"] = ("row audit failed: " + "; ".join(report["audit_errors"][:4])[:600]
                               if not report["audit_passed"] else
                               f"no validated improvement over the original (local estimate {score})")
        atomic_json(self.root / "published.json", value)   # last, after report.json (critic A13)
        return value


def report_only(layout, rows, *, allow_dev_roots=False, allow_original=False):
    out = []
    for row in rows:
        ok, reason = eligibility(layout, row, allow_dev_roots=allow_dev_roots, allow_original=allow_original)
        entry = {"row": row, "eligible": ok, "reason": reason}
        if ok:
            published = read_or(layout.row_root(row) / "published.json", {})
            entry.update(incumbent_estimate=published.get("local_score_estimate"),
                         selected_sha256=published.get("selected_sha256"),
                         busy=lock_held(layout.row_root(row) / "worker.lock"))
        elif "changed after publication" in str(reason):
            found = interrupted_publication(layout, row)
            if found is not None:
                entry.update(interrupted=True, published_sha256=found["published_sha256"],
                             current_sha256=found["current_sha256"], repairable=found["kept"] is not None,
                             busy=lock_held(layout.row_root(row) / "worker.lock"))
        out.append(entry)
    return out


def lock_held(path):
    path = Path(path)
    if not path.exists():
        return False
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


def regolf(run_dir, rows, *, compiles=DEFAULT_COMPILES, margin=DEFAULT_MARGIN, minutes=DEFAULT_MINUTES,
           compiler_slots=None, deadline=None, report_only_mode=False, allow_dev_roots=False, repair_only=False,
           row_class=RegolfRow, transfer_repair=False, repairs=None):
    layout = Layout(run_dir)
    rows = [int(row) for row in rows]
    if report_only_mode:
        return {"run_dir": str(layout.run_dir), "report_only": True, "transfer_repair": bool(transfer_repair),
                "rows": report_only(layout, rows, allow_dev_roots=allow_dev_roots, allow_original=bool(transfer_repair))}
    opts = run_options(layout, compiler_slots=compiler_slots, deadline=deadline)
    if compiler_slots:
        os.environ["FINAL60_COMPILER_SLOTS"] = str(opts.compiler_slots)
        os.environ["ARENA_COMPILER_PARALLELISM"] = str(opts.compiler_slots)
    out = []
    for row in rows:
        record = row_class(layout, row, opts, compiles=compiles, margin=margin, minutes=minutes,
                           allow_dev_roots=allow_dev_roots, repair_only=repair_only, transfer_repair=transfer_repair,
                           repairs=repairs).run()
        out.append({key: record.get(key) for key in (
            "row", "mode", "action", "reason", "incumbent_estimate", "regolf_estimate", "gain", "selected_sha256", "label",
            "accepted", "considered", "tried", "compiles", "seconds", "published", "audit_passed", "repairs")})
        print(json.dumps(out[-1], ensure_ascii=False, default=str), flush=True)
    counts = {}
    for item in out:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    return {"run_dir": str(layout.run_dir), "rows": out, "counts": counts, "api_calls": 0}


def add_parser(commands):
    parser = commands.add_parser("regolf", help="Second API-free golf pass over published rows (Stage 10)")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--rows", required=True, help="Rows, e.g. 11-30 or 12,13")
    parser.add_argument("--compiles", type=int, default=DEFAULT_COMPILES, help="Golf screen budget per row")
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN,
                        help="Minimum validated gain (points) over the published estimate")
    parser.add_argument("--minutes", type=float, default=DEFAULT_MINUTES, help="Golf wall-clock budget per row")
    parser.add_argument("--compiler-slots", type=int, help="Compiler pool slots to use (default: the run's)")
    parser.add_argument("--deadline", help="Run deadline override (ISO with offset)")
    parser.add_argument("--report-only", action="store_true", help="List eligible rows; no Lean, no write")
    parser.add_argument("--repair-only", action="store_true",
                        help="Only restore publications interrupted between write_selection and published.json; no golf")
    parser.add_argument("--allow-dev-roots", action="store_true",
                        help="Testing only: also mock/dry-run and OpenAI-direct roots")
    parser.add_argument("--transfer-repair", action="store_true",
                        help="Alias-repair recorded candidates that failed only non-primary toolchains instead of golfing "
                             "(rows publishing the original are eligible too); no API, validation only")
    parser.add_argument("--repairs", type=int, default=transfer.MAX_REPAIRS_POSTHOC,
                        help="--transfer-repair: repair validations per row (each is all versions + fresh 3x)")
    return parser


def main(args):
    rows = parse_rows(args.rows)
    if not 1 <= args.compiles <= 200:
        raise SystemExit("--compiles must be 1..200")
    if args.margin < 0:
        raise SystemExit("--margin must be >= 0")
    value = regolf(args.run_dir, rows, compiles=args.compiles, margin=args.margin, minutes=args.minutes,
                   compiler_slots=args.compiler_slots, deadline=args.deadline, report_only_mode=args.report_only,
                   allow_dev_roots=args.allow_dev_roots, repair_only=bool(getattr(args, "repair_only", False)),
                   transfer_repair=bool(getattr(args, "transfer_repair", False)),
                   repairs=getattr(args, "repairs", None))
    print(json.dumps({key: item for key, item in value.items() if key != "rows"} if not args.report_only else value,
                     ensure_ascii=False, default=str), flush=True)
    return 0
