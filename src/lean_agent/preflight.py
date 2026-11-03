"""Feature 1: check a prepared compiler and target-free context before generation."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import time

from .artifacts import sha, write
from .evaluator.lean import render, validate_template


class CheckFailed(ValueError):
    def __init__(self, stage, reason, message, *, kind="environment"):
        super().__init__(message)
        self.stage, self.reason, self.kind = stage, reason, kind


def resolve_command(command, expected, project, *, elan_home=None):
    """Resolve installed elan shims without invoking elan or downloading toolchains.

    This experiment supports direct Lean commands only; Lake and custom wrappers
    need a prepared-environment adapter and must not silently bypass this check.
    """
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise CheckFailed("environment", "invalid_command", "Lean command must be a nonempty argument list", kind="configuration")
    pin = Path(project) / "lean-toolchain"
    if not pin.is_file():
        raise CheckFailed("environment", "missing_toolchain_file", "Missing lean-toolchain file")
    actual_pin = pin.read_text().strip()
    if actual_pin != expected:
        raise CheckFailed("environment", "toolchain_mismatch", f"Configured {expected}; project declares {actual_pin}")
    found = shutil.which(command[0])
    if found is None:
        raise CheckFailed("environment", "compiler_not_found", "Lean executable not found: " + command[0])
    executable = Path(found).absolute()
    home = Path(elan_home or os.environ.get("ELAN_HOME", Path.home() / ".elan")).expanduser().resolve()
    is_shim = executable.parent.resolve() == home / "bin" or executable.resolve().name in ("elan", "elan.exe")
    # ELAN_HOME may point to a different installation from the launcher on PATH.
    # Recognize the default launcher too, then resolve the toolchain in ELAN_HOME.
    for shim in (home / "bin/lean", Path.home() / ".elan/bin/lean", executable.with_name("elan")):
        if shim.exists():
            is_shim = is_shim or os.path.samefile(executable, shim)
    if is_shim:
        if not re.fullmatch(r"leanprover/lean4:v[0-9][A-Za-z0-9.\-]*", expected):
            raise CheckFailed("environment", "unsupported_toolchain", "Only pinned released Lean toolchains are supported", kind="configuration")
        executable = home / "toolchains" / expected.replace("/", "--").replace(":", "---") / "bin/lean"
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise CheckFailed("environment", "toolchain_not_installed", "Prepared compiler is missing: " + str(executable))
    elif executable.name not in ("lean", "lean.exe"):
        raise CheckFailed("environment", "unsupported_command", "Use a direct Lean executable; Lake/custom wrappers are not supported", kind="configuration")
    executable = executable.resolve()
    if executable.name not in ("lean", "lean.exe"):
        raise CheckFailed("environment", "unsupported_command", "Resolved executable is not a direct Lean compiler", kind="configuration")
    return [str(executable), *command[1:]]


class Recorder:
    def __init__(self, root, execute):
        self.root, self.execute, self.records = root, execute, []

    def invoke(self, stage, command, cwd, timeout, **kwargs):
        directory = self.root / "checks" / stage
        directory.mkdir(parents=True, exist_ok=True)
        number = len(self.records) + 1
        log = directory / f"{number:02}.log"
        started = time.monotonic()
        try:
            result = self.execute(command, cwd, timeout, **kwargs)
        except OSError as exc:
            log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            record = {"command": command, "returncode": None, "timed_out": False,
                      "seconds": time.monotonic() - started, "exception_type": type(exc).__name__}
            self._save(stage, log, record)
            raise CheckFailed(stage, "process_start_failed", str(exc)) from exc
        record = {k: v for k, v in result.items() if k not in ("output", "stderr")}
        output = result.get("output", "")
        if result.get("stderr"):
            output += "\n[stderr]\n" + result["stderr"]
        log.write_text(output, encoding="utf-8")
        self._save(stage, log, record)
        return result

    def _save(self, stage, log, record):
        record = {**record, "stage": stage, "log": str(log.relative_to(self.root)),
                  "log_sha256": sha(log.read_bytes())}
        self.records.append(record)
        write(log.with_suffix(".json"), record)


def check(environment, root, evaluator, *, progress=None):
    """Persist diagnostics; return failed results without calling any model."""
    started = time.monotonic()
    recorder = Recorder(root, evaluator.execute)
    stage, fingerprint = "environment", None
    result = {"schema_version": 1, "status": "failed", "model_requests": 0, "api_calls": 0}
    try:
        if progress:
            progress.enter("environment", phase="preflight")
        environment = dict(environment)
        environment["command"] = resolve_command(environment["command"], environment["toolchain"], environment["project"])
        compiler = Path(environment["command"][0])
        write(root / "compiler-before-check.json", {"command": environment["command"],
              "sha256": sha(compiler.read_bytes()), "expected_toolchain": environment["toolchain"]})
        fingerprint = evaluator.fingerprint(environment, executor=lambda *a, **kw: recorder.invoke("environment", *a, **kw))
        if Path(fingerprint["compiler"]).resolve() != compiler:
            raise CheckFailed(stage, "compiler_prefix_mismatch", "--print-prefix does not identify the resolved compiler")
        write(root / "environment.json", fingerprint)
        stage = "context"
        if progress:
            progress.finish(paths=["environment.json"])
            progress.enter("context", phase="preflight")
        validate_template(environment["template"])
        # A harmless anonymous declaration consumes docstrings and scoped
        # `omit/open/set_option ... in` prefixes attached to the target slot.
        # The target itself remains absent: no original/candidate proof,
        # measurement wrapper, extra import or options are introduced.
        context = render(environment["template"], "example : True := True.intro\n", "", None)
        directory = root / "checks/context"
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "context.lean"
        source.write_text(context, encoding="utf-8")
        write(directory / "source.json", {"path": str(source.relative_to(root)), "sha256": sha(source.read_bytes())})
        response = recorder.invoke(stage, [*environment["command"], "--root=" + str(directory), str(source)],
                                   Path(environment["project"]), environment["timeout_seconds"])
        if response["timed_out"]:
            raise CheckFailed(stage, "local_timeout", "Context check exceeded the local process limit; cause undetermined", kind="timeout")
        if response["returncode"]:
            raise CheckFailed(stage, "context_compile_failed", "Target-free context did not compile; inspect the compiler log (context or unsupported template)", kind="unknown")
        # Detect changes during the probes before accepting the prepared environment.
        if sha(compiler.read_bytes()) != fingerprint["compiler_sha256"]:
            raise CheckFailed("environment", "compiler_changed", "Compiler changed during preflight")
        result.update(status="passed", stage="context", error=None, environment=fingerprint,
                      effective_command=environment["command"])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        timed_out = any(r["timed_out"] for r in recorder.records)
        result.update(stage=getattr(exc, "stage", stage), error={
            "kind": getattr(exc, "kind", "timeout" if timed_out else "environment"),
            "reason": getattr(exc, "reason", "fingerprint_failed" if stage == "environment" else "context_check_failed"),
            "message": str(exc), "exception_type": type(exc).__name__})
        diagnostic = root / "checks" / result["stage"] / "diagnostic.log"
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        diagnostic.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        result["diagnostic_log"] = str(diagnostic.relative_to(root))
    result.update(commands=recorder.records, seconds=time.monotonic() - started,
                  compiler_invocations=len(recorder.records),
                  context_compilations=sum(r["stage"] == "context" for r in recorder.records))
    write(root / "preflight.json", result)
    if progress:
        progress.finish("passed" if result["status"] == "passed" else "failed", ["preflight.json"])
    return result
