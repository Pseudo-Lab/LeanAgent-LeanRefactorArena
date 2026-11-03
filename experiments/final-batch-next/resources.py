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


def memory_snapshot():
    result = {"at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}
    pressure = _read_command(["/usr/bin/memory_pressure", "-Q"])
    match = re.search(r"memory free percentage:\s*(\d+)%", pressure or "")
    if match:
        result["free_percent"] = int(match.group(1))
    else:
        # Linux portability for reproduction; this machine uses the macOS branch.
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                values[key] = int(value.split()[0])
            result["free_percent"] = 100 * values["MemAvailable"] // values["MemTotal"]
        except (OSError, ValueError, KeyError):
            result["free_percent"] = None
    swap = _read_command(["/usr/sbin/sysctl", "-n", "vm.swapusage"])
    if swap is not None:
        result["swap"] = swap
    return result


def wait_for_memory(log_path=None, *, min_free_percent=15, max_wait_seconds=300):
    """Wait before launching Lean; an unavailable monitor fails closed.

    Call while holding the global Lean lock, so two waiting evaluators cannot
    both observe sufficient memory and start compilers at the same time.
    """
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


@contextmanager
def compiler_slot(lock_path, *, slots=2, min_free_percent=15, headroom_per_active=10):
    """Bound read-only compilers across processes; coexist with legacy exclusive users.

    An admission lock serializes slot reservations and memory checks. Held slot
    locks reserve capacity before a compiler starts and are released on crashes.
    Additional active compilers require additional free-memory headroom.
    """
    if type(slots) is not int or not 1 <= slots <= 3:
        raise ValueError("Compiler slots must be between 1 and 3")
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
                        for number in range(3):
                            stream = Path(str(lock_path) + f".slot-{number}").open("a+")
                            try:
                                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except BlockingIOError:
                                active += 1
                                stream.close()
                            else:
                                available.append(stream)
                        snapshot = memory_snapshot()
                        free = snapshot["free_percent"]
                        if free is None:
                            raise RuntimeError("Memory monitor unavailable; no compiler admitted")
                        if active < slots and available and free >= min_free_percent + headroom_per_active * active:
                            lease = available.pop(0)
                    finally:
                        for stream in available:
                            stream.close()
                if lease is None:
                    if time.monotonic() - start >= 1200:
                        raise RuntimeError("Timed out waiting for safe compiler capacity")
                    time.sleep(0.25)
            yield
        finally:
            if lease is not None:
                lease.close()
            fcntl.flock(compatibility, fcntl.LOCK_UN)
