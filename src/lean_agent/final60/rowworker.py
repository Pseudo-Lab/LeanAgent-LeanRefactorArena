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

from .orchestrator import (Layout, atomic_bytes, atomic_json, coverage, driver_modules, json_bytes, load_dataset,
                           load_non_openrouter, load_rowstate, normalized_sha, now_iso, problem_packet,
                           prompt_addendum, read_json, route_dict, route_for, row_settings, row_spend, save_rowstate,
                           sha_bytes, sha_text)

RESOURCE_PHRASES = ("safe compiler capacity", "memory pressure stayed", "memory monitor unavailable")
EXIT_RETRYABLE = 75   # EX_TEMPFAIL: resource wait timed out; the supervisor does not count a crash


class WorkerBusy(Exception):
    pass


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


def configure_environment(opts):
    """Pool and memory settings for this process and its evaluators (driver hook 5, resources.py)."""
    os.environ.setdefault("FINAL60_COMPILER_SLOTS", str(opts.compiler_slots))
    os.environ.setdefault("FINAL60_MEM_RESERVE_GIB", str(opts.mem_reserve_gib))
    os.environ.setdefault("FINAL60_GIB_PER_COMPILE", str(opts.gib_per_compile))
    os.environ.setdefault("FINAL60_ADMISSION_SPACING_S", "5")
    remaining = max(300, int(opts.deadline_epoch() - time.time()))
    os.environ["FINAL60_RESOURCE_WAIT_S"] = str(remaining)


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
        configure_environment(self.opts)
        if self.opts.key_file is not None and not self.opts.dry_run:
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
                                        route_sha256=sha_bytes(route_bytes), addendum=prompt_addendum(route))
                atomic_json(inputs / "final60.json", settings)
            settings = read_json(inputs / "final60.json")
        if bool(settings.get("dry_run")) != bool(self.opts.dry_run):
            raise ValueError("This row root was prepared with a different --dry-run setting; use a fresh run dir")
        self.driver.prepare_inputs(self.root, [self.row], workers=1, cold_start=True,
                                   prompt_variant="baseline", strict_cap=True)
        self.driver.seal_inputs(self.root, [self.row])

    def preflight(self):
        if not self.preflight_ready():
            self.driver.preflight(self.root, [self.row])

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
        remaining = started + self.exploration_budget() - time.time()
        timer = None
        if remaining <= 0:
            self.flag("stop-exploration.json", "row exploration clock")
        else:
            timer = threading.Timer(remaining, self.flag, ("stop-exploration.json", "row exploration clock"))
            timer.daemon = True
            timer.start()
        self.status("salvage" if (self.root / "salvage.json").exists() else "exploring")
        try:
            self.driver.run_problem(self.root, self.row)
        finally:
            if timer is not None:
                timer.cancel()

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
            results = golf.improve(adapter, problem, pool[:top], settings, deadline=deadline)
            known = {candidate.sha256 for candidate in pool}
            for result in results:
                if result.best.sha256 not in known and clean(result.best):
                    pool.append(result.best)
                    known.add(result.best.sha256)
            self.status("validating")
            selection = select.select_final(adapter, problem, pool, k=3, deadline=deadline)
            select.write_selection(self.root, self.row, selection)
            self.update_worker(golf={"accepted": [result.accepted for result in results], "selected": selection.candidate.label,
                                     "score": selection.score, "beat_original": selection.beat_original,
                                     "considered": list(selection.considered)})
        except Exception as exc:  # golf/selection never fail the row (contract 11.5)
            self.update_worker(golf="error: " + f"{type(exc).__name__}: {exc}"[:500] + "; driver selection kept",
                               golf_traceback=traceback.format_exc()[-4000:])

    def audit_and_publish(self):
        problem = read_json(self.folder / "input/problem.json")
        report = self.report.build_report(self.root)
        report_bytes = json_bytes(report)
        atomic_bytes(self.root / "report.json", report_bytes)
        entry = next((item for item in report["rows"] if item["row"] == self.row), {})
        selected = self.folder / "selected.lean"
        code = selected.read_text(encoding="utf-8") if selected.exists() else None
        improved = (report["audit_passed"] and code is not None and "final" in entry
                    and normalized_sha(code) != normalized_sha(problem["reference"]))
        value = {"row": self.row, "name": problem["name"], "at": now_iso(),
                 "origin": "openrouter-run" if improved else "original",
                 "selected_sha256": sha_text(code) if code is not None else None,
                 "report_sha256": sha_bytes(report_bytes), "audit_passed": report["audit_passed"],
                 "local_score_estimate": entry.get("local_score_estimate") if improved else 100 / 3,
                 "cost_usd": entry.get("known_cost_usd"), "calls": entry.get("calls"),
                 "status": entry.get("status"), "golf": self.worker_state().get("golf")}
        if not improved:
            value["reason"] = ("row audit failed: " + "; ".join(report["audit_errors"][:4])[:600]
                               if not report["audit_passed"] else "no validated improvement over the original")
        atomic_json(self.root / "published.json", value)   # critic A13: after report.json
        self.state = load_rowstate(self.layout, self.row)
        self.state.selected_sha256 = value["selected_sha256"]
        self.state.score_estimate = value["local_score_estimate"]
        self.state.last_error = None if report["audit_passed"] else value.get("reason")
        save_rowstate(self.layout, self.state)
        self.status("published", origin=value["origin"])
        return self.state

    def fallback(self, reason):
        problem = problem_packet(self.row)
        atomic_json(self.root / "published.json", {"row": self.row, "name": problem["name"], "at": now_iso(),
                                                   "origin": "original", "reason": reason})
        self.status("fallback", reason=reason)
        return self.state


def run_row(run_dir, row, opts):
    """Run (or resume) one row; returns its RowState. Never runs twice concurrently."""
    layout = Layout(run_dir)
    path = layout.row_root(row) / "worker.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        raise WorkerBusy(f"F{row:03} already has a live worker") from None
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
        fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()
