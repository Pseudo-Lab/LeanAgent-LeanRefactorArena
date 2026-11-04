"""One row worker: route -> prepare/seal -> preflight -> explore -> golf/select -> audit -> publish.

Each step is resumable from disk: the driver's own state machine (state.json,
ledger.json, evaluation caches) carries exploration, and worker-state.json carries
the orchestrator's few flags. rows/F0NN/worker.lock (flock) is held for the
worker's lifetime, so a second worker for the same row exits immediately.
"""
from __future__ import annotations

from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import threading
import time
import traceback

from .orchestrator import (Layout, atomic_bytes, atomic_json, coverage, driver_modules, json_bytes, lean_memory_mib,
                           load_dataset, load_non_openrouter, load_rowstate, normalized_sha, now_iso, prepend_tool_paths,
                           problem_packet, prompt_addendum, read_json, route_dict, route_for, row_settings, row_spend,
                           save_rowstate, sha_bytes, sha_text, tool_paths)

RESOURCE_PHRASES = ("safe compiler capacity", "memory pressure stayed", "memory monitor unavailable")
EXIT_RETRYABLE = 75   # EX_TEMPFAIL: resource wait timed out; the supervisor does not count a crash
ABORT_CODES = (-6, 134)   # SIGABRT directly, or 128 + SIGABRT as the bwrap sandbox reports it
ABORT_MARKERS = ("excessive memory consumption", "lean::memory_exception")


class WorkerBusy(Exception):
    pass


class WallClockAlarm:
    """Call ``callback`` once ``time.time()`` reaches ``deadline`` (a wall-clock epoch).

    ``threading.Timer`` waits on the monotonic clock. On the WSL2 run host the monotonic
    clock ran about 7% slower than the host-synced wall clock (rehearsal 2026-11-04: every
    600 s exploration clock fired 43-46 s late), so the row exploration clock polls the
    wall clock instead; the poll period bounds how late the callback can be.
    """

    def __init__(self, deadline, callback, *, poll_s=5.0):
        self.deadline, self.callback, self.poll_s = float(deadline), callback, float(poll_s)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.fired = False

    def start(self):
        self.thread.start()
        return self

    def cancel(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            remaining = self.deadline - time.time()
            if remaining <= 0:
                self.fired = True
                self.callback()
                return
            self._stop.wait(min(self.poll_s, max(remaining, 0.01)))


def read_or(path, default):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return default


def resource_error(exc, folder=None):
    """A compiler-capacity or memory wait timeout is retryable, not a crash (critic A8)."""
    texts, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        texts.append(str(exc))
        exc = exc.__cause__ or exc.__context__
    if folder is not None:
        texts.append(json.dumps(read_or(Path(folder) / "progress.json", {})))
        steps = sorted((Path(folder) / "steps").glob("[0-9][0-9][0-9][0-9]")) if (Path(folder) / "steps").exists() else []
        for step in steps[-1:]:
            for path in sorted(step.glob("evaluation/*/result.json")):
                texts.append(json.dumps(read_or(path, {}).get("error") or {}))
    text = " ".join(texts).lower()
    return any(phrase in text for phrase in RESOURCE_PHRASES)


def allocator_abort(result):
    """A Lean memory abort (-M bound): exit -6/134 or the allocator's own message in any environment."""
    for value in (result.get("environments") or {}).values():
        message = str((value.get("error") or {}).get("message", "")).lower()
        if any(marker in message for marker in ABORT_MARKERS):
            return True
        if any(run.get("returncode") in ABORT_CODES for run in value.get("runs") or []):
            return True
    return False


def configure_environment(opts, problem=None):
    """Pool, sandbox PATH and memory settings for this process and its evaluators (driver hook 5)."""
    # The prepared sources ship the sandbox helper (bwrap on Linux) in <sources>/final/bin (lesson 1).
    prepend_tool_paths(os.environ, opts.prepared_repo)
    os.environ.setdefault("FINAL60_COMPILER_SLOTS", str(opts.compiler_slots))
    os.environ.setdefault("FINAL60_MEM_RESERVE_GIB", str(opts.mem_reserve_gib))
    os.environ.setdefault("FINAL60_GIB_PER_COMPILE", str(opts.gib_per_compile))
    os.environ.setdefault("FINAL60_ADMISSION_SPACING_S", "5")
    remaining = max(300, int(opts.deadline_epoch() - time.time()))
    os.environ["FINAL60_RESOURCE_WAIT_S"] = str(remaining)
    if opts.transport:
        os.environ["FINAL60_TRANSPORT"] = str(opts.transport)      # --transport passthrough for the transport component
    if problem is not None:
        # Lesson 4: the frozen -M4096 aborts Mathlib-based compiles; the evaluator reads this bound per compile.
        os.environ["ARENA_LEAN_MEMORY_MIB"] = str(lean_memory_mib(problem, prepared_repo=opts.prepared_repo,
                                                                  override=opts.lean_memory_mib))
    return {"PATH": os.environ["PATH"], "tool_paths": tool_paths(opts.prepared_repo),
            "lean_memory_mib": os.environ.get("ARENA_LEAN_MEMORY_MIB"), "transport": opts.transport,
            "compiler_slots": os.environ.get("FINAL60_COMPILER_SLOTS")}


class RowWorker:
    def __init__(self, layout, row, opts, state):
        self.layout, self.row, self.opts, self.state = layout, row, opts, state
        self.root = layout.row_root(row)
        self.folder = layout.row_folder(row)
        self.driver, self.report = driver_modules()

    # -- small state helpers -------------------------------------------------
    def status(self, value, **event):
        self.state = load_rowstate(self.layout, self.row)
        self.state.status = value
        self.state.spent_usd = str(row_spend(self.layout, self.row))
        save_rowstate(self.layout, self.state, {"event": "status", "status": value, **event})

    def worker_state(self):
        return read_or(self.layout.worker_path(self.row), {})

    def update_worker(self, **values):
        value = {**self.worker_state(), **values, "updated_at": now_iso()}
        atomic_json(self.layout.worker_path(self.row), value)
        return value

    def crashes(self):
        return read_or(self.layout.control_path(self.row), {}).get("crashes", {})

    def flag(self, name, reason, **extra):
        path = self.root / name
        if not path.exists():
            atomic_json(path, {"reason": reason, "at": now_iso(), **extra})

    # -- phases ----------------------------------------------------------------
    def run(self):
        if (self.root / "published.json").exists() and self.state.status == "published":
            return self.state
        try:
            packet = problem_packet(self.row)
        except (OSError, ValueError):
            packet = None
        environment = configure_environment(self.opts, packet)
        self.update_worker(environment={key: environment[key] for key in ("tool_paths", "lean_memory_mib", "transport",
                                                                           "compiler_slots")})
        if self.opts.key_file is not None and not self.opts.dry_run:
            if self.opts.transport == "openai":
                # Development transport: the OpenAI-direct wire reads its own key variable.
                from . import transports
                profile = transports.profile("openai")
                os.environ[profile.key_env] = profile.wire.load_key(Path(self.opts.key_file))
            else:
                os.environ["OPENROUTER_API_KEY"] = self.driver.transport_for({"backend": "openrouter"}).load_key(Path(self.opts.key_file))
        crashes = self.crashes()
        if not (self.root / "frozen.json").exists():
            data = load_dataset(self.opts.dataset or read_or(self.layout.plan, {}).get("dataset"))
            missing = coverage([self.row], data, self.opts.prepared_repo)[self.row].get("missing", [])
            if missing:
                self.status("waiting_env", missing=missing[:6])
                return self.state
            # A crash is counted under the status the row had when it died (supervisor control file).
            if crashes.get("ready", 0) >= 3:
                return self.fallback("preparation failed three times")
            self.status("ready")
            self.prepare()
        else:
            self.driver.verify_frozen(self.root)
        if crashes.get("prepared", 0) >= 3 and not self.preflight_ready():
            return self.fallback("preflight failed three times")
        self.status("prepared")
        self.preflight()
        self.status("preflighted")
        if crashes.get("salvage", 0) >= 3 and not (self.folder / "summary.json").exists():
            return self.fallback("salvage (no API) selection failed three times")
        self.explore(crashes)
        self.golf_and_select(crashes)
        return self.audit_and_publish()

    def preflight_ready(self):
        return read_or(self.folder / "preflight.json", {}).get("status") == "ready"

    def prepare(self):
        inputs = self.folder / "input"
        problem = problem_packet(self.row)
        with self.driver.locked(self.folder / "input.lock"):
            if not (inputs / "final60.json").exists():
                outside = [entry["proof"] for entry in load_non_openrouter(self.layout)]
                route = route_for(problem, non_openrouter_proofs=outside, diversity=self.opts.diversity)
                if route.row != self.row or route.name != problem["name"]:
                    raise ValueError("Route does not belong to this row")
                route_bytes = json_bytes(route_dict(route))
                atomic_bytes(inputs / "route.json", route_bytes)
                settings = row_settings(self.layout, self.row, route, cap=self.opts.cap_usd,
                                        prior=self.opts.prior_costs.get(self.row, Decimal(0)),
                                        compiler_slots=self.opts.compiler_slots, dry_run=self.opts.dry_run,
                                        route_sha256=sha_bytes(route_bytes), addendum=prompt_addendum(route),
                                        transport=self.opts.transport)
                atomic_json(inputs / "final60.json", settings)
            settings = read_json(inputs / "final60.json")
        if bool(settings.get("dry_run")) != bool(self.opts.dry_run):
            raise ValueError("This row root was prepared with a different --dry-run setting; use a fresh run dir")
        self.driver.prepare_inputs(self.root, [self.row], workers=1, cold_start=True,
                                   prompt_variant="baseline", strict_cap=True)
        self.driver.seal_inputs(self.root, [self.row])

    def preflight(self):
        if not self.preflight_ready():
            self.reset_failed_preflight()
            self.driver.preflight(self.root, [self.row])

    def reset_failed_preflight(self):
        """The driver caches a failed baseline; set aside evidence of environment failures only.

        A host/sandbox/memory failure says nothing about the original proof, so it is retried.
        A Lean allocator abort (-6, or 134 under bwrap; lesson 4) is retried too, under the row's
        ARENA_LEAN_MEMORY_MIB. A compile failure of the frozen original stays (the row then falls
        back after 3 tries).
        """
        if read_or(self.folder / "preflight.json", {}).get("status") != "failed":
            return
        for name in ("baseline", "reference-compatibility"):
            result = read_or(self.folder / name / "result.json", None)
            if not result or result.get("valid"):
                continue
            kinds = {(value.get("error") or {}).get("kind") for value in result.get("environments", {}).values()}
            if kinds & {"environment", "timeout", "resource"} or allocator_abort(result) or not result.get("environments"):
                (self.folder / name).rename(self.folder / f"{name}-failed-{time.time_ns()}")

    def exploration_budget(self):
        route = read_or(self.folder / "input/route.json", {})
        budget = int(route.get("wallclock_budget_s") or self.opts.exploration_minutes * 60)
        return min(budget, self.opts.exploration_minutes * 60)

    def explore(self, crashes):
        if (self.folder / "summary.json").exists():
            return
        if crashes.get("exploring", 0) >= 3 or crashes.get("salvage", 0):
            self.flag("salvage.json", "three worker crashes during exploration; no further API calls")
        started = self.worker_state().get("exploration_started_at")
        if started is None:
            started = time.time()
            self.update_worker(exploration_started_at=started)
        deadline = started + self.exploration_budget()
        alarm = None
        if time.time() >= deadline:
            self.flag("stop-exploration.json", "row exploration clock")
        else:
            # Wall-clock alarm (not threading.Timer): the monotonic clock may run slow (WSL2).
            alarm = WallClockAlarm(deadline, lambda: self.flag("stop-exploration.json", "row exploration clock")).start()
        self.status("salvage" if (self.root / "salvage.json").exists() else "exploring")
        try:
            self.driver.run_problem(self.root, self.row)
        finally:
            if alarm is not None:
                alarm.cancel()

    def golf_and_select(self, crashes):
        if self.worker_state().get("golf"):
            return
        if sum(crashes.get(phase, 0) for phase in ("golfing", "validating")) >= 3:
            self.update_worker(golf="skipped after three crashes; driver selection kept")
            return
        try:
            from . import evaladapter, golf, select
        except ImportError as exc:
            self.update_worker(golf="unavailable (" + str(exc)[:200] + "); driver selection kept")
            return
        self.status("golfing")
        try:
            route = read_json(self.folder / "input/route.json")
            settings = dict(route.get("golf") or {})
            minutes = float(settings.get("minutes", 20))
            deadline = min(time.time() + minutes * 60, self.opts.deadline_epoch() - 20 * 60)
            problem = read_json(self.folder / "input/problem.json")
            outside = {normalized_sha(entry["proof"]) for entry in load_non_openrouter(self.layout)}
            def clean(candidate):
                # Critic A12: never validate a text that equals a non-OpenRouter proof.
                return candidate.origin == "original" or normalized_sha(candidate.code) not in outside
            adapter = evaladapter.EvalAdapter(self.root, self.row)
            pool = [candidate for candidate in select.candidates_from_run(self.root, self.row, top=6) if clean(candidate)]
            top = max(1, int(settings.get("top_k", 2)))
            # The blocklist goes into golf and selection too: a golf session then skips a variant
            # that equals a non-OpenRouter proof instead of adopting it (and losing the whole
            # session when its final best is dropped here), and select_final never validates or
            # G1-fixes into one. A blocklisted text can therefore not win selection and be thrown
            # away by the assembler afterwards; the row selects its best clean candidate.
            # Transfer repair (hotfix 2026-11-04): a parent whose saved all-version check failed is
            # not golfed; its deprecated-alias repair is validated and golfed instead when it holds.
            parents = select.golf_parents(adapter, problem, pool, top, non_openrouter_sha256=outside)
            results = golf.improve(adapter, problem, parents, settings, deadline=deadline,
                                   non_openrouter_sha256=outside)
            known = {candidate.sha256 for candidate in pool}
            for result in results:
                if result.best.sha256 not in known and clean(result.best):
                    pool.append(result.best)
                    known.add(result.best.sha256)
            self.status("validating")
            selection = select.select_final(adapter, problem, pool, k=3, deadline=deadline,
                                            non_openrouter_sha256=outside)
            select.write_selection(self.root, self.row, selection)
            self.update_worker(golf={"accepted": [result.accepted for result in results], "selected": selection.candidate.label,
                                     "score": selection.score, "beat_original": selection.beat_original,
                                     "considered": list(selection.considered)})
        except Exception as exc:  # golf/selection never fail the row (contract 11.5)
            self.update_worker(golf="error: " + f"{type(exc).__name__}: {exc}"[:500] + "; driver selection kept",
                               golf_traceback=traceback.format_exc()[-4000:])

    # Minimum local-estimate gain (points) before a model proof replaces the original. The official
    # counter reports heartbeats in thousands and the measured run-to-run noise is far below this;
    # a noise-level or equal variant gains nothing and only adds provenance and transfer risk.
    PUBLISH_MARGIN = 0.25

    def audit_and_publish(self):
        problem = read_json(self.folder / "input/problem.json")
        value = publish(self.root, self.folder, self.row, problem, self.report, golf=self.worker_state().get("golf"),
                        margin=self.PUBLISH_MARGIN)
        self.state = load_rowstate(self.layout, self.row)
        self.state.selected_sha256 = value["selected_sha256"]
        self.state.score_estimate = value["local_score_estimate"]
        self.state.last_error = None if value["audit_passed"] else value.get("reason")
        save_rowstate(self.layout, self.state)
        self.status("published", origin=value["origin"])
        return self.state

    def fallback(self, reason):
        problem = problem_packet(self.row)
        atomic_json(self.root / "published.json", {"row": self.row, "name": problem["name"], "at": now_iso(),
                                                   "origin": "original", "reason": reason})
        self.status("fallback", reason=reason)
        return self.state


def publish(root, folder, row, problem, report_module, *, golf=None, margin=RowWorker.PUBLISH_MARGIN):
    """Audit the row root and write report.json, then published.json (critic A13: in that order).

    A non-original proof is published only when the audit passed and it scores better than the
    original (33.33) by at least ``margin``; an equal or noise-level variant would only add
    provenance and transfer risk. Returns the published.json value.
    """
    report = report_module.build_report(root)
    report_bytes = json_bytes(report)
    atomic_bytes(root / "report.json", report_bytes)
    entry = next((item for item in report["rows"] if item["row"] == row), {})
    selected = folder / "selected.lean"
    code = selected.read_text(encoding="utf-8") if selected.exists() else None
    score = entry.get("local_score_estimate")
    improved = (report["audit_passed"] and code is not None and "final" in entry
                and normalized_sha(code) != normalized_sha(problem["reference"])
                and isinstance(score, (int, float)) and score >= 100 / 3 + margin)
    value = {"row": row, "name": problem["name"], "at": now_iso(),
             "origin": "openrouter-run" if improved else "original",
             "selected_sha256": sha_text(code) if code is not None else None,
             "report_sha256": sha_bytes(report_bytes), "audit_passed": report["audit_passed"],
             "local_score_estimate": entry.get("local_score_estimate") if improved else 100 / 3,
             "cost_usd": entry.get("known_cost_usd"), "calls": entry.get("calls"),
             "status": entry.get("status"), "golf": golf}
    if not improved:
        value["reason"] = ("row audit failed: " + "; ".join(report["audit_errors"][:4])[:600]
                           if not report["audit_passed"] else
                           f"no validated improvement over the original (local estimate {score})")
    atomic_json(root / "published.json", value)
    return value


def try_row_lock(layout, row):
    """rows/F0NN/worker.lock taken non-blocking: the open stream, or None while a worker holds it."""
    path = layout.row_root(row) / "worker.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        return None
    return stream


def release_row_lock(stream):
    fcntl.flock(stream, fcntl.LOCK_UN)
    stream.close()


def fallback_to_alternate(layout, row, *, rejects, reason, report_module=None, margin=RowWorker.PUBLISH_MARGIN):
    """Assembly fallback: re-publish the row's best untried validated alternate, or report why not.

    The assembler calls this when the row's published proof is rejected (a checker, the
    non-OpenRouter blocklist or the row audit). The provenance checker certifies only the proof
    that equals the root's selected.lean under a passing report.json, so an alternate cannot be
    substituted in the submission text: it is published through the worker's own path
    (select.write_selection -> report.json -> published.json) and the assembler re-checks it in
    its next round. Alternates are the validated runners-up select_final recorded (best first);
    ``rejects(code)`` pre-checks each one (blocklist, rules, static filter) and every alternate
    is tried at most once (rows/F0NN/alternates.json). Nothing runs while the row's worker holds
    worker.lock; no model call and no Lean. Returns (code, published) or (None, why).
    """
    from . import select
    root, folder = layout.row_root(row), layout.row_folder(row)
    record_path = root / "alternates.json"
    record = read_or(record_path, {"row": row, "tried": [], "log": []})
    stream = try_row_lock(layout, row)
    if stream is None:
        return None, "row worker is live; alternates deferred to the next assembly"
    try:
        if report_module is None:
            _, report_module = driver_modules()
        problem = read_json(folder / "input/problem.json")
        selected = folder / "selected.lean"
        current = sha_text(selected.read_text(encoding="utf-8")) if selected.exists() else None
        if current and current not in record["tried"]:
            record["tried"].append(current)
        record["log"].append({"at": now_iso(), "event": "rejected", "selected_sha256": current, "reason": reason[:600]})
        try:
            alternates = select.alternates(root, row)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            alternates = []
            record["log"].append({"at": now_iso(), "event": "alternates-unreadable", "error": f"{type(exc).__name__}: {exc}"[:300]})
        outcome = (None, "no validated alternate left")
        for alternate in alternates:
            candidate = alternate.candidate
            if candidate.sha256 in record["tried"]:
                continue
            record["tried"].append(candidate.sha256)
            entry = {"at": now_iso(), "label": candidate.label, "sha256": candidate.sha256, "score": alternate.score}
            issues = list(rejects(candidate.code) or [])
            if issues:
                record["log"].append({**entry, "event": "skipped", "issues": issues[:4]})
                continue
            if not alternate.validated.valid or not (isinstance(alternate.score, (int, float)) and alternate.score >= 100 / 3 + margin):
                record["log"].append({**entry, "event": "skipped", "issues": ["not validated above the publish margin"]})
                continue
            try:
                select.write_selection(root, row, alternate)
                value = publish(root, folder, row, problem, report_module, golf=read_or(layout.worker_path(row), {}).get("golf"),
                                margin=margin)
            except Exception as exc:   # evidence missing or stale: the next alternate, never the row
                record["log"].append({**entry, "event": "publish-error", "error": f"{type(exc).__name__}: {exc}"[:500]})
                continue
            value["alternate"] = {"label": candidate.label, "origin": candidate.origin, "fallback_from": current,
                                  "reason": reason[:600]}
            atomic_json(root / "published.json", value)
            record["log"].append({**entry, "event": "published", "origin": value["origin"], "reason": value.get("reason")})
            if value["origin"] == "openrouter-run":
                outcome = (candidate.code, value)
                break
        del record["log"][:-60]
        atomic_json(record_path, record)
        return outcome
    finally:
        release_row_lock(stream)


def run_row(run_dir, row, opts):
    """Run (or resume) one row; returns its RowState. Never runs twice concurrently."""
    layout = Layout(run_dir)
    stream = try_row_lock(layout, row)
    if stream is None:
        raise WorkerBusy(f"F{row:03} already has a live worker")
    try:
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps({"pid": os.getpid(), "at": now_iso()}) + "\n")
        stream.flush()
        state = load_rowstate(layout, row)
        state.attempts += 1
        save_rowstate(layout, state, {"event": "worker_start", "pid": os.getpid()})
        try:
            return RowWorker(layout, row, opts, state).run()
        except Exception as exc:
            retryable = resource_error(exc, layout.row_folder(row))
            state = load_rowstate(layout, row)
            state.last_error = f"{type(exc).__name__}: {exc}"[:1500]
            save_rowstate(layout, state, {"event": "worker_error", "retryable": retryable,
                                          "error": state.last_error[:300]})
            exc.final60_retryable = retryable
            raise
    finally:
        release_row_lock(stream)
