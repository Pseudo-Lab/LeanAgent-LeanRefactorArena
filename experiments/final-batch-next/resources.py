"""Read-only resource checks for the final batch's serial Lean worker."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone


def _read_command(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _env_number(name, default=None):
    """final60 knobs; unset keeps the team defaults exactly."""
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    number = float(value)
    if not number >= 0:
        raise ValueError(name + " must be a non-negative number")
    return number


def memory_snapshot():
    result = {"at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}
    pressure = _read_command(["/usr/bin/memory_pressure", "-Q"])
    match = re.search(r"memory free percentage:\s*(\d+)%", pressure or "")
    if match:
        result["free_percent"] = int(match.group(1))
        total = _read_command(["/usr/sbin/sysctl", "-n", "hw.memsize"])
        if total and total.isdigit():
            result["available_gib"] = round(int(total) * result["free_percent"] / 100 / 2**30, 3)
    else:
        # Linux portability for reproduction; this machine uses the macOS branch.
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                values[key] = int(value.split()[0])
            result["free_percent"] = 100 * values["MemAvailable"] // values["MemTotal"]
            result["available_gib"] = round(values["MemAvailable"] / 2**20, 3)
        except (OSError, ValueError, KeyError):
            result["free_percent"] = None
    swap = _read_command(["/usr/sbin/sysctl", "-n", "vm.swapusage"])
    if swap is not None:
        result["swap"] = swap
    return result


def wait_for_memory(log_path=None, *, min_free_percent=15, max_wait_seconds=None):
    """Wait before launching Lean; an unavailable monitor fails closed.

    Call while holding the global Lean lock, so two waiting evaluators cannot
    both observe sufficient memory and start compilers at the same time.
    final60 sets FINAL60_RESOURCE_WAIT_S to wait up to its row deadline instead of 300 s.
    """
    if max_wait_seconds is None:
        max_wait_seconds = _env_number("FINAL60_RESOURCE_WAIT_S", 300)
    start = time.monotonic()
    while True:
        snapshot = memory_snapshot()
        snapshot.update(min_free_percent=min_free_percent,
                        waited_seconds=round(time.monotonic() - start, 3))
        if log_path is not None:
            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as stream:
                stream.write(json.dumps(snapshot, sort_keys=True) + "\n")
        if snapshot["free_percent"] is None:
            raise RuntimeError("Memory monitor unavailable; no Lean process started")
        if snapshot["free_percent"] >= min_free_percent:
            return snapshot
        if time.monotonic() - start >= max_wait_seconds:
            raise RuntimeError("Memory pressure stayed above the launch threshold; no Lean process started")
        time.sleep(5)


def admits(snapshot, active, *, min_free_percent=15, headroom_per_active=10, reserve_gib=None, gib_per_compile=3.5):
    """Admission rule for one more compiler.

    Default (team PR #68): free% >= min + headroom x active. With FINAL60_MEM_RESERVE_GIB
    set, an absolute rule replaces it: MemAvailable >= reserve + one compile's budget.
    """
    if reserve_gib is None:
        free = snapshot["free_percent"]
        if free is None:
            raise RuntimeError("Memory monitor unavailable; no compiler admitted")
        return free >= min_free_percent + headroom_per_active * active
    available = snapshot.get("available_gib")
    if available is None:
        raise RuntimeError("Memory monitor unavailable; no compiler admitted")
    return available >= reserve_gib + gib_per_compile


@contextmanager
def compiler_slot(lock_path, *, slots=2, min_free_percent=15, headroom_per_active=10):
    """Bound read-only compilers across processes; coexist with legacy exclusive users.

    An admission lock serializes slot reservations and memory checks. Held slot
    locks reserve capacity before a compiler starts and are released on crashes.
    Additional active compilers require additional free-memory headroom.
    """
    if type(slots) is not int or not 1 <= slots <= 8:
        raise ValueError("Compiler slots must be between 1 and 8")
    reserve = _env_number("FINAL60_MEM_RESERVE_GIB")
    per_compile = _env_number("FINAL60_GIB_PER_COMPILE", 3.5)
    timeout = _env_number("FINAL60_RESOURCE_WAIT_S", 1200)
    spacing = _env_number("FINAL60_ADMISSION_SPACING_S", 0)
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as compatibility:
        fcntl.flock(compatibility, fcntl.LOCK_SH)
        lease = None
        try:
            start = time.monotonic()
            while lease is None:
                with Path(str(lock_path) + ".admission").open("a+") as admission:
                    fcntl.flock(admission, fcntl.LOCK_EX)
                    available = []
                    try:
                        active = 0
                        for number in range(slots):
                            stream = Path(str(lock_path) + f".slot-{number}").open("a+")
                            try:
                                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except BlockingIOError:
                                active += 1
                                stream.close()
                            else:
                                available.append(stream)
                        recent = False
                        if spacing:
                            # Let the previous compiler's memory show up before the next admission.
                            admission.seek(0)
                            try:
                                recent = time.time() - float(admission.read().strip() or 0) < spacing
                            except ValueError:
                                recent = False
                        snapshot = memory_snapshot()
                        if (active < slots and available and not recent
                                and admits(snapshot, active, min_free_percent=min_free_percent,
                                           headroom_per_active=headroom_per_active,
                                           reserve_gib=reserve, gib_per_compile=per_compile)):
                            lease = available.pop(0)
                            if spacing:
                                admission.seek(0)
                                admission.truncate()
                                admission.write(str(time.time()))
                                admission.flush()
                    finally:
                        for stream in available:
                            stream.close()
                if lease is None:
                    if time.monotonic() - start >= timeout:
                        raise RuntimeError("Timed out waiting for safe compiler capacity")
                    time.sleep(0.25)
            yield
        finally:
            if lease is not None:
                lease.close()
            fcntl.flock(compatibility, fcntl.LOCK_UN)
