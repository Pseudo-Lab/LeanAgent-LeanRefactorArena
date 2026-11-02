#!/usr/bin/env python3
"""Expand an existing pinned Strata build without changing its frozen seed.

This bounded, local-only path performs no toolchain installation or downloads.
The general 17-environment installer and its 15 GiB guard remain unchanged.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "experiments/final-environment"),
               str(REPO / "experiments/final-batch-next")]
from bootstrap import dataset, digest, write
from resolve import resolve
from lean_agent.prepared import freeze, PreparedLeanEvaluator
from resources import wait_for_memory

ACCOUNT = "/Users/jwkweon/00_work/00_project/.git-accounts/account.py"
CACHE = Path(os.environ["PROJECT_CACHE_DIR"])
GIB = 1024 ** 3


def git(project, *args):
    return subprocess.check_output(["git", "-C", str(project), *args], text=True).strip()


def verify_source(project, revision):
    if git(project, "rev-parse", "HEAD") != revision or git(project, "diff", "--name-only", "HEAD", "--"):
        raise ValueError("Source pin or tracked bytes changed: " + str(project))


def snapshot(seed, version, revision, visited):
    seed = seed.resolve()
    verify_source(seed, revision)
    dest = REPO / "sources/final-expanded/checkouts" / version / seed.name
    if str(dest) in visited:
        return dest
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        # APFS clonefile is mandatory: fail instead of silently making a full copy.
        subprocess.run(["/bin/cp", "-cR", str(seed), str(dest)], check=True)
        subprocess.run(["/usr/bin/python3", ACCOUNT, "setup", "personal"], cwd=dest, check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["/usr/bin/python3", ACCOUNT, "verify-login"], cwd=dest, check=True,
                       stdout=subprocess.DEVNULL)
    verify_source(dest, revision)
    visited[str(dest)] = (seed, revision)
    manifest = json.loads((seed / "lake-manifest.json").read_text())
    for entry in manifest.get("packages", []):
        name = entry["name"].strip("«»")
        dependency = snapshot(seed / manifest.get("packagesDir", ".lake/packages") / name,
                              version, entry["rev"], visited)
        link = dest / manifest.get("packagesDir", ".lake/packages") / name
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise ValueError("Unexpected copied dependency directory; preserved: " + str(link))
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(dependency, target_is_directory=True)
    original_build = seed / ".lake/build"
    cached = CACHE / "lean-build" / version / seed.name
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        if original_build.exists():
            subprocess.run(["/bin/cp", "-cR", str(original_build.resolve()), str(cached)], check=True)
        else:
            cached.mkdir()
    build = dest / ".lake/build"
    if build.is_symlink():
        build.unlink()
    elif build.exists():
        raise ValueError("Unexpected materialized build folder; preserved")
    build.parent.mkdir(parents=True, exist_ok=True)
    build.symlink_to(cached, target_is_directory=True)
    return dest


def invoke(command, project, child, log, initial_free):
    reserve = 3 * GIB
    if shutil.disk_usage(REPO).free < reserve:
        raise RuntimeError("Local incremental build reserve below 3 GiB")
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    print("RUN", log.name, flush=True)
    with log.open("w") as stream:
        process = subprocess.Popen(list(map(str, command)), cwd=project, env=child,
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                free = shutil.disk_usage(REPO).free
                if free < reserve or initial_free - free > 2 * GIB:
                    raise RuntimeError("Bounded incremental build exceeded its disk reserve/budget")
                if time.monotonic() - start > 1800:
                    raise RuntimeError("Incremental module build exceeded 30 minutes")
                time.sleep(1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    receipt = {"command": list(map(str, command)), "cwd": str(project), "returncode": process.returncode,
               "seconds": round(time.monotonic() - start, 3), "log_sha256": digest(log)}
    write(log.with_suffix(".receipt.json"), receipt)
    if process.returncode:
        raise RuntimeError(log.name + " failed:\n" + log.read_text(errors="replace")[-5000:])
    return receipt


def prepare(env_id, registry, rows, lock, initial_free):
    seed_state = registry["environments"][env_id]
    if seed_state["source"] != "strata":
        raise ValueError("This local-only expansion supports existing Strata seeds")
    target = next(e for e in lock["environments"] if e["id"] == env_id)
    folder = REPO / "sources/final/environments" / env_id
    existing = json.loads((folder / "environment.json").read_text())
    if set(target["problem_rows"]) <= {loc["row"] for loc in existing.get("locations", [])}:
        PreparedLeanEvaluator(REPO / existing["prepared_environment"]).verify()
        print("REUSE SEALED", env_id, flush=True)
        return existing
    history = folder / "history" / (digest(folder / "environment.json") + ".json")
    if not history.exists():
        write(history, existing)
    visited = {}
    project = snapshot(REPO / seed_state["project"], target["version"], target["revision"], visited)
    env = {**target, "project": str(project.relative_to(REPO))}
    locations = resolve(env, rows)
    if any(loc["kind"] not in {"exact_src", "whitespace_src"} for loc in locations):
        raise ValueError("Complete reference extent is required")
    compiler = (REPO / "sources/final/toolchains" / target["version"]).resolve()
    actual = subprocess.check_output([str(compiler / "bin/lean"), "--version"], text=True).strip()
    if not actual.startswith("Lean (version " + target["version"][1:] + ","):
        raise ValueError("Compiler version mismatch")
    temp = CACHE / "build-tmp"
    temp.mkdir(parents=True, exist_ok=True)
    child = {**os.environ, "PATH": str(compiler / "bin") + ":" + os.environ["PATH"],
             "LEAN_NUM_THREADS": "1", "MATHLIB_NO_CACHE_ON_UPDATE": "1",
             "TMPDIR": str(temp), "XDG_CACHE_HOME": str(CACHE / "xdg")}
    output = REPO / "runs/manual/final60-environment-prep-20261102" / env_id
    modules = sorted({loc["module"] for loc in locations})
    wait_for_memory(log_path=output / "build.memory.json")
    build = invoke([compiler / "bin/lake", "build", *["+" + m for m in modules]],
                   project, child, output / "modules.build.log", initial_free)
    private = any("module" == line.strip() for loc in locations
                  for line in (project / loc["file_path"]).read_text().splitlines())
    check_dir = project / (modules[0].split(".")[0] if private else "") / "ArenaEnvironmentChecks"
    check_dir.mkdir(exist_ok=True)
    probe = check_dir / "FinalBaselines.lean"
    probe.write_text(("module\n" if private else "") + "import Lean\n" +
                     "".join(("import all " if private else "import ") + m + "\n" for m in modules) +
                     "".join("#check " + loc["name"] + "\n" for loc in locations))
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(probe, output / "imports.lean")
    try:
        check = invoke([compiler / "bin/lake", "lean", probe, "--", "-j1", "-M4096"],
                       project, child, output / "imports.log", initial_free)
    finally:
        probe.unlink(missing_ok=True)
        if not any(check_dir.iterdir()):
            check_dir.rmdir()
    lean_path = subprocess.check_output([str(compiler / "bin/lake"), "env", "printenv", "LEAN_PATH"],
                                       cwd=project, env=child, text=True).strip()
    paths = []
    for entry in lean_path.split(os.pathsep):
        p = Path(entry)
        p = (p if p.is_absolute() else project / p).resolve()
        if p.is_dir() and p not in paths:
            paths.append(p)
    for p in [compiler / "lib/lean", compiler / "lib"]:
        if p not in paths:
            paths.append(p)
    for dest, (seed, revision) in visited.items():
        verify_source(Path(dest), revision)
        verify_source(seed, revision)
    manifest = folder / "prepared-expanded.json"
    freeze(paths, target["revision"], manifest, sandbox="macos-readonly", verification="stat-cache")
    state = {**env, "status": "ready", "stage": "sealed",
             "actual_compiler": actual,
             "compiler": str((REPO / "sources/final/toolchains" / target["version"] / "bin/lean").relative_to(REPO)),
             "manifest_sha256": digest(project / "lake-manifest.json"),
             "toolchain_sha256": digest(project / "lean-toolchain"), "locations": locations,
             "lean_path": lean_path, "prepared_environment": str(manifest.relative_to(REPO)),
             "prepared_manifest_sha256": digest(manifest), "records": [build, check],
             "seed_environment_state_sha256": history.stem,
             "validation_scope": "Pinned APFS source/build snapshots; full Strata benchmark module build and type checks. HB measured separately."}
    write(folder / "environment.json", state)
    registry["environments"][env_id] = state
    write(REPO / "configs/final-environments.local.json", registry)
    print("SEALED", env_id, "rows", target["problem_rows"], flush=True)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", action="append", required=True)
    parser.add_argument("--compiler-lock", type=Path, required=True)
    args = parser.parse_args()
    initial_free = shutil.disk_usage(REPO).free
    if initial_free < 4 * GIB:
        raise RuntimeError("Local-only incremental expansion needs 4 GiB free initially")
    registry = json.loads((REPO / "configs/final-environments.local.json").read_text())
    lock = json.loads((REPO / "configs/final-environments.lock.json").read_text())
    rows = dataset()
    with args.compiler_lock.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            for name in args.environment:
                prepare(name, registry, rows, lock, initial_free)
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
