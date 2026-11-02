#!/usr/bin/env python3
"""Prepare selected Final environments with pinned sources and central caches."""
from __future__ import annotations

import argparse
import fcntl
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
import bootstrap
import prepare
import toolchains
import finalize
from finalize import preserve_and_clean_probes, canonical_whitespace_check
from lean_agent.prepared import freeze, PreparedLeanEvaluator
from resources import wait_for_memory

CACHE = Path(os.environ["PROJECT_CACHE_DIR"])
ENV = Path(os.environ["PROJECT_ENV_DIR"])
SHARED = Path(os.environ["PROJECT_STORAGE_ROOT"]) / "cache/_shared"
ACCOUNT = "/Users/jwkweon/00_work/00_project/.git-accounts/account.py"
GIB = 1024 ** 3


def ensure_toolchain(version):
    compat = bootstrap.ROOT / "toolchains" / version
    dest = ENV / "toolchains" / version
    dest.parent.mkdir(parents=True, exist_ok=True)
    provenance = {"kind": "existing-pinned-toolchain"}
    if not compat.exists():
        installed = Path.home() / ".elan/toolchains" / ("leanprover--lean4---" + version)
        if installed.is_dir():
            compat.symlink_to(installed, target_is_directory=True)
            provenance = {"kind": "matching-installed-toolchain", "path": str(installed)}
        else:
            if not dest.exists():
                provenance = toolchains.local_archive(version, dest) or toolchains.download_release(version, dest)
            compat.symlink_to(dest, target_is_directory=True)
    actual = bootstrap.command([compat / "bin/lean", "--version"]).strip()
    if not actual.startswith("Lean (version " + version[1:] + ","):
        raise ValueError("Pinned compiler version mismatch")
    if not (compat / "lib/lean/libLean.a").is_file():
        raise ValueError("Full native compiler archive is required")
    path = bootstrap.ROOT / "toolchains.json"
    receipt = json.loads(path.read_text()) if path.exists() else {"schema_version": 1, "toolchains": {}}
    old = receipt["toolchains"].get(version, {})
    receipt["toolchains"][version] = {
        "version": version, "path": str(compat.relative_to(REPO)), "actual_version": actual,
        "lean_sha256": toolchains.file_sha(compat / "bin/lean"),
        "lake_sha256": toolchains.file_sha(compat / "bin/lake"),
        "provenance": old.get("provenance", provenance)}
    bootstrap.write(path, receipt)


original_fetch = bootstrap.fetch


def managed_fetch(url, version, revision):
    path = bootstrap.checkout_path(url, version, revision)
    if not (path / ".git").exists():
        subprocess.run(["/usr/bin/python3", ACCOUNT, "init", "personal", str(path)], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["/usr/bin/python3", ACCOUNT, "verify-login"], cwd=path, check=True,
                       stdout=subprocess.DEVNULL)
        bootstrap.command(["git", "-C", path, "remote", "add", "origin", url])
    path = original_fetch(url, version, revision)
    cached = CACHE / "lean-build" / version / path.name
    build = path / ".lake/build"
    if build.is_symlink():
        if build.resolve() != cached.resolve():
            raise ValueError("Existing build points to another cache; preserved")
    elif build.exists():
        if cached.exists():
            raise ValueError("Build/cache collision; preserved")
        cached.parent.mkdir(parents=True, exist_ok=True)
        build.rename(cached)
        build.symlink_to(cached, target_is_directory=True)
    else:
        cached.mkdir(parents=True, exist_ok=True)
        build.parent.mkdir(parents=True, exist_ok=True)
        build.symlink_to(cached, target_is_directory=True)
    return path


original_process_env = prepare.process_env


def central_process_env(version):
    child = original_process_env(version)
    temporary = CACHE / "build-tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    (SHARED / "mathlib").mkdir(parents=True, exist_ok=True)
    child.update(TMPDIR=str(temporary), XDG_CACHE_HOME=str(CACHE / "xdg"),
                 MATHLIB_CACHE_DIR=str(SHARED / "mathlib"), LEAN_NUM_THREADS="1",
                 LAKE_ARTIFACT_CACHE="false")
    # The parent PATH includes the available zstd tool and account-managed Git.
    child["PATH"] += ":" + os.environ["PATH"]
    return child


def bounded_invoke(argv, project, child, log, *, timeout=7200):
    log.parent.mkdir(parents=True, exist_ok=True)
    wait_for_memory(log_path=log.with_suffix(".memory.json"))
    started = time.monotonic()
    print("RUN", log.name, flush=True)
    with log.open("w") as stream:
        process = subprocess.Popen(list(map(str, argv)), cwd=project, env=child, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                if shutil.disk_usage(REPO).free < 5 * GIB:
                    raise RuntimeError("Environment preparation reached the 5 GiB disk reserve")
                if time.monotonic() - started > timeout:
                    raise RuntimeError("Environment preparation command timed out")
                time.sleep(1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    receipt = {"command": list(map(str, argv)), "cwd": str(project), "returncode": process.returncode,
               "seconds": round(time.monotonic() - started, 3),
               "log": str(log.relative_to(REPO)), "log_sha256": bootstrap.digest(log)}
    bootstrap.write(log.with_suffix(".receipt.json"), receipt)
    if process.returncode:
        raise RuntimeError(log.name + " failed:\n" + log.read_text(errors="replace")[-5000:])
    return receipt


def prepare_one(env, registry, lock):
    state_path = bootstrap.ROOT / "environments" / env["id"] / "environment.json"
    old = json.loads(state_path.read_text()) if state_path.exists() else {}
    if old.get("status") == "ready" and old.get("prepared_environment"):
        PreparedLeanEvaluator(REPO / old["prepared_environment"]).verify()
        print("REUSE SEALED", env["id"], flush=True)
        return
    ensure_toolchain(env["version"])
    if shutil.disk_usage(REPO).free < 15 * GIB:
        raise RuntimeError("Less than 15 GiB free before new environment preparation")
    source_lock = bootstrap.ROOT / "source-lock.json"
    previous = json.loads(source_lock.read_text()) if source_lock.exists() else {"checkouts": []}
    try:
        bootstrap.fetch_all({**lock, "environments": [env]})
    finally:
        current = json.loads(source_lock.read_text()) if source_lock.exists() else {"checkouts": []}
        combined = {x["path"]: x for x in previous["checkouts"]}
        combined.update({x["path"]: x for x in current["checkouts"]})
        bootstrap.write(source_lock, {"schema_version": 1, "dataset_sha256": lock["dataset_sha256"],
                                      "checkouts": list(combined.values())})
    rows = bootstrap.dataset()
    state = prepare.prepare_one(env, rows)
    for loc in state["locations"]:
        if loc["kind"] == "whitespace_src":
            canonical_whitespace_check(env, loc, rows)
    state["saved_checker_inputs"] = preserve_and_clean_probes(env, state["locations"])
    project = REPO / state["project"]
    paths = []
    for entry in state["lean_path"].split(os.pathsep):
        path = Path(entry)
        path = (path if path.is_absolute() else project / path).resolve()
        if path.is_dir() and path not in paths:
            paths.append(path)
    compiler = (bootstrap.ROOT / "toolchains" / env["version"]).resolve()
    for path in [compiler / "lib/lean", compiler / "lib"]:
        if path not in paths:
            paths.append(path)
    for parent in [p.parent for p in list(paths) if p.name == "lean"]:
        if parent not in paths and any(p.suffix in {".a", ".so", ".dylib"}
                                       for p in parent.iterdir() if p.is_file()):
            paths.append(parent)
    manifest = state_path.parent / "prepared-environment.json"
    freeze(paths, env["revision"], manifest, sandbox="macos-readonly", verification="stat-cache")
    state.update(prepared_environment=str(manifest.relative_to(REPO)),
                 prepared_manifest_sha256=bootstrap.digest(manifest), stage="sealed")
    bootstrap.write(state_path, state)
    registry["environments"][env["id"]] = state
    bootstrap.write(REPO / "configs/final-environments.local.json", registry)
    print("SEALED", env["id"], "rows", env["problem_rows"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", action="append", required=True)
    parser.add_argument("--compiler-lock", type=Path, required=True)
    args = parser.parse_args()
    downloads = SHARED / "lean-releases"
    downloads.mkdir(parents=True, exist_ok=True)
    link = bootstrap.ROOT / "downloads"
    if not link.exists():
        link.symlink_to(downloads, target_is_directory=True)
    if link.resolve() != downloads.resolve():
        raise ValueError("Compiler download cache is not centralized")
    bootstrap.fetch = managed_fetch
    prepare.process_env = central_process_env
    prepare.invoke = bounded_invoke
    finalize.process_env = central_process_env
    finalize.invoke = bounded_invoke
    lock = bootstrap.plan()
    registry = json.loads((REPO / "configs/final-environments.local.json").read_text())
    for name in args.environment:
        env = next(e for e in lock["environments"] if e["id"] == name)
        with args.compiler_lock.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                prepare_one(env, registry, lock)
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
