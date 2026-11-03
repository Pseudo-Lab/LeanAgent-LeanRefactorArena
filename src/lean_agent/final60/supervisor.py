"""Supervisor: schedule row workers, restart them, honour the deadline, keep a valid submission.

- Liveness is the row's worker.lock (flock), never a PID file, so a restarted supervisor
  adopts live workers and never starts a duplicate row.
- Crashes are counted under the row status at death; restarts back off 60/180/600 s.
  A retryable resource timeout (exit 75) is not a crash. Eight crashes publish the original.
- New workers start only below --max-rows live workers and with MemAvailable >= --mem-start-gib.
- deadline - soft_stop_min: <run-dir>/stop-exploration.json (no new paid requests anywhere).
  deadline - 60 min: final assembly every 10 min; deadline - 20 min: last assembly and
  SUBMIT-READY.txt, no new workers. The submission always has 60 rows.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .orchestrator import (REPO, TERMINAL, Layout, atomic_json, coverage, load_dataset, load_rowstate, now_iso,
                           plan, prepend_tool_paths, read_json, save_options, save_rowstate)
from .rowworker import EXIT_RETRYABLE

BACKOFF = (60, 180, 600)
MAX_CRASHES = 8
EXIT_BUSY = 3
SLOT_FLOOR, SLOT_CEILING = 2, 8     # final60 roots need 2..8 shared compiler slots (driver.compiler_parallelism)


def refresh_coverage(layout, opts):
    """Re-inspect environment readiness for rows not yet ready; keep the planned routes."""
    value = read_json(layout.plan)
    waiting = [entry["row"] for entry in value["rows"] if not entry["ready"]]
    if waiting:
        data = load_dataset(opts.dataset or value.get("dataset"))
        covered = coverage(waiting, data, opts.prepared_repo)
        for entry in value["rows"]:
            if entry["row"] in covered:
                entry["missing"] = covered[entry["row"]].get("missing", [])
                entry["ready"] = not entry["missing"]
        value["ready"] = [entry["row"] for entry in value["rows"] if entry["ready"]]
        value["coverage_at"] = now_iso()
        atomic_json(layout.plan, value)
    return value


def lock_held(path):
    """True when another process holds an exclusive flock on path."""
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


def resources_module():
    if str(REPO / "experiments/final-batch-next") not in sys.path:
        sys.path.insert(0, str(REPO / "experiments/final-batch-next"))
    import resources
    return resources


def available_gib():
    return resources_module().memory_snapshot().get("available_gib")


def memory_total_gib(meminfo="/proc/meminfo"):
    """MemTotal in GiB (Linux /proc/meminfo, macOS sysctl); None when unknown."""
    try:
        for line in Path(meminfo).read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 2 ** 20, 3)
    except (OSError, ValueError, IndexError):
        pass
    total = resources_module()._read_command(["/usr/sbin/sysctl", "-n", "hw.memsize"])
    return round(int(total) / 2 ** 30, 3) if total and total.isdigit() else None


def lean_processes(proc="/proc"):
    """Live `lean` compilers as [{pid, rss_gib, anon_gib}] (Linux procfs; `ps` elsewhere)."""
    found = []
    root = Path(proc)
    if root.is_dir() and (root / "self").exists() or any(root.glob("[0-9]*/comm")):
        for entry in root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if (entry / "comm").read_text().strip() != "lean":
                    continue
                values = {}
                for line in (entry / "status").read_text().splitlines():
                    key, _, rest = line.partition(":")
                    if key in ("VmRSS", "RssAnon"):
                        values[key] = int(rest.split()[0])
                found.append({"pid": int(entry.name), "rss_gib": round(values.get("VmRSS", 0) / 2 ** 20, 3),
                              "anon_gib": round(values["RssAnon"] / 2 ** 20, 3) if "RssAnon" in values else None})
            except (OSError, ValueError, IndexError):
                continue
        return found
    try:
        listing = subprocess.run(["ps", "-axo", "pid=,rss=,comm="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return found
    for line in listing.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and Path(parts[2].strip()).name == "lean":
            found.append({"pid": int(parts[0]), "rss_gib": round(int(parts[1]) / 2 ** 20, 3), "anon_gib": None})
    return found


def memory_sample(memory=available_gib, proc="/proc"):
    """One line of supervisor/memory.jsonl: MemAvailable plus the RSS of every live lean process (item 4)."""
    processes = lean_processes(proc)
    return {"at": now_iso(), "available_gib": memory(), "lean_processes": len(processes),
            "lean_rss_gib": round(sum(item["rss_gib"] for item in processes), 3),
            "lean_rss_max_gib": round(max((item["rss_gib"] for item in processes), default=0.0), 3),
            "lean_anon_gib": round(sum(item["anon_gib"] or 0.0 for item in processes), 3)}


def size_compiler_slots(requested, total_gib, *, reserve_gib, gib_per_compile):
    """Compiler slots the machine can hold: min(requested, (MemTotal - reserve) / per-compile), in 2..8.

    Admission stays memory-gated per compile (resources.compiler_slot); this only keeps the pool
    size itself honest, e.g. 8 requested on 31 GiB with 6 + 3.5 GiB per compile gives 7.
    """
    requested = int(requested)
    if total_gib is None:
        return max(SLOT_FLOOR, min(SLOT_CEILING, requested))
    fit = int((float(total_gib) - float(reserve_gib)) // max(float(gib_per_compile), 0.1))
    return max(SLOT_FLOOR, min(SLOT_CEILING, requested, fit))


class Supervisor:
    def __init__(self, run_dir, opts, *, clock=time.time, sleep=time.sleep, popen=subprocess.Popen,
                 memory=available_gib, assembler=None, total_memory=memory_total_gib, proc="/proc"):
        self.layout, self.opts = Layout(run_dir), opts
        self.clock, self.sleep, self.popen, self.memory = clock, sleep, popen, memory
        if assembler is None:
            from .assemble import assemble as assembler
        self.assembler = assembler
        self.children = {}
        self.alive_before = set()
        self.published_seen = None
        self.last_heartbeat = 0.0
        self.last_final_assembly = 0.0
        self.last_coverage = 0.0
        self.last_rolling = 0.0
        self.last_memory = 0.0
        self.closed = False
        self.ready = set()
        self.proc = proc
        self.total_gib = total_memory()
        self.slots = size_compiler_slots(opts.compiler_slots, self.total_gib, reserve_gib=opts.mem_reserve_gib,
                                         gib_per_compile=opts.gib_per_compile)
        self.memory_last = None
        self.memory_peak = {"lean_rss_gib": 0.0, "lean_processes": 0, "min_available_gib": None}

    # -- memory log (research item 4) ---------------------------------------------------
    def log_memory(self, now, *, force=False):
        if not force and now - self.last_memory < self.opts.memory_log_seconds:
            return None
        self.last_memory = now
        try:
            sample = memory_sample(self.memory, self.proc)
        except Exception as exc:       # the log is diagnostic only
            self.event("memory_sample_error", error=f"{type(exc).__name__}: {exc}"[:300])
            return None
        # Live rows include workers adopted from an earlier supervisor (not in self.children).
        sample.update(compiler_slots=self.slots, live_rows=len(self.alive_before | set(self.children)))
        path = self.layout.supervisor / "memory.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as stream:
            stream.write(json.dumps(sample, sort_keys=True) + "\n")
        self.memory_last = sample
        peak = self.memory_peak
        peak["lean_rss_gib"] = max(peak["lean_rss_gib"], sample["lean_rss_gib"])
        peak["lean_processes"] = max(peak["lean_processes"], sample["lean_processes"])
        if sample.get("available_gib") is not None:
            peak["min_available_gib"] = (sample["available_gib"] if peak["min_available_gib"] is None
                                         else min(peak["min_available_gib"], sample["available_gib"]))
        return sample

    # -- persistence ---------------------------------------------------------------
    def event(self, kind, **values):
        path = self.layout.supervisor / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as stream:
            stream.write(json.dumps({"at": now_iso(), "event": kind, **values}, sort_keys=True, default=str) + "\n")

    def control(self, row):
        path = self.layout.control_path(row)
        return read_json(path) if path.exists() else {"crashes": {}, "restarts": 0, "next_start_at": 0}

    def save_control(self, row, value):
        atomic_json(self.layout.control_path(row), value)

    def alive(self, row):
        return lock_held(self.layout.row_root(row) / "worker.lock")

    # -- plan / coverage -----------------------------------------------------------
    def refresh_plan(self, now, *, force=False):
        if not force and now - self.last_coverage < self.opts.coverage_seconds and self.layout.plan.exists():
            return
        self.last_coverage = now
        try:
            if self.layout.plan.exists():
                value = refresh_coverage(self.layout, self.opts)
            else:
                value = plan(self.layout.run_dir, dataset=self.opts.dataset, prepared_repo=self.opts.prepared_repo,
                             diversity=self.opts.diversity, non_openrouter=self.opts.non_openrouter,
                             refresh_non_openrouter=not self.layout.non_openrouter.exists(),
                             assemble_submission=False)
        except Exception as exc:
            self.event("plan_error", error=f"{type(exc).__name__}: {exc}"[:500])
            if not self.layout.plan.exists():
                raise
            value = read_json(self.layout.plan)
        self.priorities = {entry["row"]: entry.get("priority", 0) for entry in value["rows"]}
        self.ready = set(value["ready"])

    # -- worker lifecycle ------------------------------------------------------------
    def reap(self, now):
        alive_now = set()
        for row in self.opts.rows:
            child = self.children.get(row)
            code = child.poll() if child is not None else None
            if child is not None and code is None:
                alive_now.add(row)
                continue
            if child is not None:
                self.children.pop(row)
                self.finished(row, code, now)
            elif self.alive(row):
                alive_now.add(row)
            elif row in self.alive_before:
                # An adopted worker (started by an earlier supervisor) ended.
                self.finished(row, None, now)
        self.alive_before = alive_now
        return alive_now

    def finished(self, row, code, now):
        state = load_rowstate(self.layout, row)
        control = self.control(row)
        control["last_exit"] = {"code": code, "at": now_iso(), "status": state.status}
        if state.status in TERMINAL or state.status == "waiting_env":
            control["next_start_at"] = now + (self.opts.coverage_seconds if state.status == "waiting_env" else 0)
        elif code == EXIT_RETRYABLE:
            control["next_start_at"] = now + BACKOFF[0]
        else:
            crashes = control.setdefault("crashes", {})
            crashes[state.status] = crashes.get(state.status, 0) + 1
            total = sum(crashes.values())
            control["next_start_at"] = now + BACKOFF[min(total, len(BACKOFF)) - 1]
            if total >= MAX_CRASHES:
                self.give_up(row, f"{total} worker crashes; last status {state.status}")
        self.save_control(row, control)
        self.event("worker_exit", row=row, code=code, status=state.status)

    def give_up(self, row, reason):
        root = self.layout.row_root(row)
        if not (root / "published.json").exists():
            atomic_json(root / "published.json", {"row": row, "at": now_iso(), "origin": "original", "reason": reason})
        state = load_rowstate(self.layout, row)
        state.status, state.last_error = "fallback", reason
        save_rowstate(self.layout, state, {"event": "supervisor_fallback", "reason": reason})

    def command(self, row):
        command = [self.opts.python, "-m", "lean_agent.final60", "row", "--run-dir", str(self.layout.run_dir),
                   "--row", str(row)]
        if self.opts.key_file is not None:
            command += ["--key-file", str(self.opts.key_file)]
        if self.opts.dry_run:
            command.append("--dry-run")
        if self.opts.transport:
            command += ["--transport", str(self.opts.transport)]
        if self.opts.lean_memory_mib:
            command += ["--lean-memory-mib", str(int(self.opts.lean_memory_mib))]
        return command

    def spawn(self, row, now):
        environment = dict(os.environ)
        source = str(REPO / "src")
        paths = [value for value in environment.get("PYTHONPATH", "").split(os.pathsep) if value]
        environment["PYTHONPATH"] = os.pathsep.join([source] + [value for value in paths if value != source])
        prepend_tool_paths(environment, self.opts.prepared_repo)      # shipped bwrap for compiler children
        environment.update(FINAL60_COMPILER_SLOTS=str(self.slots),
                           FINAL60_MEM_RESERVE_GIB=str(self.opts.mem_reserve_gib),
                           FINAL60_GIB_PER_COMPILE=str(self.opts.gib_per_compile))
        if self.opts.transport:
            environment["FINAL60_TRANSPORT"] = str(self.opts.transport)
        log = self.layout.log_path(row)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as stream:
            stream.write(f"\n=== {now_iso()} start F{row:03}\n")
            stream.flush()
            child = self.popen(self.command(row), cwd=str(REPO), env=environment, stdout=stream,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self.children[row] = child
        control = self.control(row)
        control["restarts"] = control.get("restarts", 0) + 1
        control["started_at"] = now_iso()
        self.save_control(row, control)
        self.event("worker_start", row=row, pid=getattr(child, "pid", None))

    def eligible(self, row, now):
        state = load_rowstate(self.layout, row)
        if state.status in TERMINAL or row in self.children or self.alive(row):
            return False
        if self.control(row).get("next_start_at", 0) > now:
            return False
        sealed = (self.layout.row_root(row) / "frozen.json").exists()
        if not sealed and now >= self.opts.deadline_epoch() - 60 * 60:
            return False      # too late to prepare a new row; it keeps the original
        return sealed or row in self.ready

    def start_rows(self, now, live):
        if self.closed:
            return
        order = sorted(self.opts.rows, key=lambda row: (-float(getattr(self, "priorities", {}).get(row, 0)), row))
        for row in order:
            if len(live) >= self.opts.max_rows:
                return
            if not self.eligible(row, now):
                continue
            free = self.memory()
            if free is None or free < self.opts.mem_start_gib:
                self.event("memory_gate", available_gib=free, row=row)
                return
            self.spawn(row, now)
            live.add(row)

    # -- deadline and assembly ----------------------------------------------------------
    def deadline_actions(self, now):
        deadline = self.opts.deadline_epoch()
        stop = self.layout.run_dir / "stop-exploration.json"
        if now >= deadline - self.opts.soft_stop_min * 60 and not stop.exists():
            atomic_json(stop, {"reason": "deadline soft stop", "at": now_iso(),
                               "deadline": self.opts.deadline.isoformat()})
            self.event("soft_stop")
        if now >= deadline - 20 * 60 and not self.closed:
            self.closed = True
            self.assemble(final=True)
            self.event("final_assembly", note="last scheduled assembly; no new workers")
        elif now >= deadline - 60 * 60 and now - self.last_final_assembly >= 600:
            self.last_final_assembly = now
            self.assemble(final=True)

    def assemble(self, *, final):
        try:
            result = self.assembler(self.layout.run_dir, final=final, dataset=self.opts.dataset)
            self.event("assemble", final=final, improved=result.get("improved"), checks=result.get("checks"))
            return result
        except Exception as exc:
            self.event("assemble_error", final=final, error=f"{type(exc).__name__}: {exc}"[:500])
            return None

    def published(self):
        return {row for row in range(1, 61) if (self.layout.row_root(row) / "published.json").exists()}

    def heartbeat(self, now, live, *, force=False):
        if not force and now - self.last_heartbeat < 60:
            return
        self.last_heartbeat = now
        states = {row: load_rowstate(self.layout, row).status for row in self.opts.rows}
        counts = {}
        for value in states.values():
            counts[value] = counts.get(value, 0) + 1
        atomic_json(self.layout.supervisor / "status.json", {
            "at": now_iso(), "pid": os.getpid(), "live_rows": sorted(live), "counts": counts,
            "deadline": self.opts.deadline.isoformat(), "closed": self.closed,
            "soft_stop": (self.layout.run_dir / "stop-exploration.json").exists(),
            "api_disabled": (self.layout.run_dir / "api-disabled.json").exists(),
            "available_gib": self.memory(), "max_rows": self.opts.max_rows,
            "compiler_slots": self.slots, "compiler_slots_requested": self.opts.compiler_slots,
            "memory_total_gib": self.total_gib, "memory": self.memory_last, "memory_peak": self.memory_peak,
            "published": len(self.published())})

    def finished_all(self):
        return all(load_rowstate(self.layout, row).status in TERMINAL for row in self.opts.rows)

    def tick(self):
        now = self.clock()
        self.refresh_plan(now)
        self.log_memory(now)
        self.deadline_actions(now)
        live = self.reap(now)
        self.start_rows(now, live)
        published = self.published()
        # Rolling assembly re-reads every published row's requests for the PR #70 leak test,
        # so it runs at most every assemble_seconds (and whenever no worker is live).
        if published != self.published_seen and (self.published_seen is None or not live
                                                 or now - self.last_rolling >= self.opts.assemble_seconds):
            self.published_seen = published
            self.last_rolling = now
            self.assemble(final=False)
        self.heartbeat(now, live)
        if now >= self.opts.deadline_epoch() or (self.layout.supervisor / "STOP").exists():
            return True
        return not live and not self.children and self.finished_all()

    def run(self):
        self.layout.supervisor.mkdir(parents=True, exist_ok=True)
        with (self.layout.supervisor / "supervisor.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({"supervisor": "already running", "run_dir": str(self.layout.run_dir)}), flush=True)
                return EXIT_BUSY
            save_options(self.layout, self.opts)
            self.event("supervisor_start", pid=os.getpid(), rows=len(self.opts.rows),
                       compiler_slots=self.slots, compiler_slots_requested=self.opts.compiler_slots,
                       memory_total_gib=self.total_gib, transport=self.opts.transport)
            self.refresh_plan(self.clock(), force=True)
            while not self.tick():
                self.sleep(self.opts.poll_seconds)
            self.assemble(final=True)
            self.heartbeat(self.clock(), set(), force=True)
            self.event("supervisor_exit", finished_all=self.finished_all())
        return 0


def supervise(run_dir, opts, **kwargs):
    """Run the supervisor until every selected row is terminal or the deadline passes."""
    return Supervisor(run_dir, opts, **kwargs).run()
