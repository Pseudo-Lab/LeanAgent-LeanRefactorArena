#!/usr/bin/env python3
"""Prepare selected Final environments with pinned sources and central caches."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from final_cache_traces import HASH_CHECKER, invalidate_bad_traces, normalize_cache_traces, trace_outputs

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
INCREMENTAL_BUDGET = None
INITIAL_FREE = None
NAMESPACE = None
DEFER_STANDALONE_PROOFS = False
original_checkout_path = bootstrap.checkout_path
original_widget_tags = bootstrap.fetch_widget_tags


def checkout_path(url, version, revision):
    original = original_checkout_path(url, version, revision)
    return (bootstrap.ROOT / 'isolated-checkouts' / NAMESPACE / version / original.name
            if NAMESPACE else original)


def cache_path(version, name):
    base = CACHE / 'lean-build'
    return (base / NAMESPACE if NAMESPACE else base) / version / name


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def clone_seed(url, version, revision, destination):
    """Fork matching source/build bytes before extending a sealed dependency."""
    seed = original_checkout_path(url, version, revision)
    if not NAMESPACE or destination.exists() or not (seed / '.git').is_dir():
        return
    if (bootstrap.command(['git', '-C', seed, 'rev-parse', 'HEAD']).strip() != revision or
            bootstrap.command(['git', '-C', seed, 'diff', '--name-only', 'HEAD', '--']).strip()):
        raise ValueError('Seed source pin/bytes differ; original preserved')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / ('.clone-' + uuid.uuid4().hex)
    cached = cache_path(version, destination.name)
    try:
        subprocess.run(['/bin/cp', '-cR', str(seed), str(stage)], check=True)
        if (stage / '.lake').is_symlink():
            raise ValueError('Unexpected shared .lake container; original preserved')
        manifest = stage / 'lake-manifest.json'
        if manifest.exists():
            data = json.loads(manifest.read_text())
            packages = stage / data.get('packagesDir', '.lake/packages')
            if packages.is_symlink():
                raise ValueError('Unexpected shared packages container; original preserved')
            for entry in data.get('packages', []):
                link = packages / bootstrap.package_name(entry['name'])
                if link.is_symlink():
                    link.unlink()  # only the new APFS clone; bootstrap reconnects its dependencies
                elif link.exists():
                    raise ValueError('Copied dependency is not a managed link; preserved')
        source_build = seed / '.lake/build'
        if not cached.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            if source_build.is_dir():
                staging_build = cached.parent / ('.clone-' + uuid.uuid4().hex)
                try:
                    subprocess.run(['/bin/cp', '-cR', str(source_build.resolve()), str(staging_build)], check=True)
                    staging_build.rename(cached)
                finally:
                    if staging_build.exists():
                        shutil.rmtree(staging_build)
            else:
                cached.mkdir()
        link = stage / '.lake/build'
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise ValueError('Copied build is not a managed link; preserved')
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(cached, target_is_directory=True)
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    subprocess.run(['/usr/bin/python3', ACCOUNT, 'setup', 'personal'], cwd=destination,
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['/usr/bin/python3', ACCOUNT, 'verify-login'], cwd=destination,
                   check=True, stdout=subprocess.DEVNULL)
    print('COW SEED', version, destination.name, flush=True)


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
    clone_seed(url, version, revision, path)
    if not (path / ".git").exists():
        subprocess.run(["/usr/bin/python3", ACCOUNT, "init", "personal", str(path)], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["/usr/bin/python3", ACCOUNT, "verify-login"], cwd=path, check=True,
                       stdout=subprocess.DEVNULL)
        bootstrap.command(["git", "-C", path, "remote", "add", "origin", url])
    path = original_fetch(url, version, revision)
    cached = cache_path(version, path.name)
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
                 MATHLIB_CACHE_DIR=str(SHARED / "mathlib"), LEAN_NUM_THREADS="1", RAYON_NUM_THREADS="1",
                 LAKE_ARTIFACT_CACHE="false")
    # The parent PATH includes the available zstd tool and account-managed Git.
    child["PATH"] += ":" + os.environ["PATH"]
    return child


def bounded_invoke(argv, project, child, log, *, timeout=7200):
    log.parent.mkdir(parents=True, exist_ok=True)
    wait_for_memory(log_path=log.with_suffix(".memory.json"))
    started = time.monotonic()
    print("RUN", log.name, flush=True)
    split_errors = '--json' in argv and 'query' in argv
    error_path = log.with_suffix('.stderr.log')
    with log.open("w") as stream, (error_path.open('w') if split_errors else nullcontext(subprocess.STDOUT)) as errors:
        process = subprocess.Popen(list(map(str, argv)), cwd=project, env=child, stdout=stream,
                                   stderr=errors, start_new_session=True)
        try:
            while process.poll() is None:
                free = shutil.disk_usage(REPO).free
                if free < 5 * GIB:
                    raise RuntimeError("Environment preparation reached the 5 GiB disk reserve")
                if INCREMENTAL_BUDGET is not None and INITIAL_FREE - free > INCREMENTAL_BUDGET:
                    raise RuntimeError("Bounded incremental preparation exceeded its disk budget; unsealed outputs retained")
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
    if split_errors:
        receipt.update(stderr_log=str(error_path.relative_to(REPO)), stderr_sha256=bootstrap.digest(error_path))
    bootstrap.write(log.with_suffix(".receipt.json"), receipt)
    if process.returncode:
        raise RuntimeError(log.name + " failed:\n" + log.read_text(errors="replace")[-5000:] +
                           (error_path.read_text(errors='replace')[-2000:] if split_errors else ''))
    free = shutil.disk_usage(REPO).free
    if free < 5 * GIB or (INCREMENTAL_BUDGET is not None and INITIAL_FREE - free > INCREMENTAL_BUDGET):
        raise RuntimeError("Preparation command finished beyond its disk reserve/budget; outputs remain unsealed")
    return receipt


def prepare_one(env, registry, lock):
    global INITIAL_FREE
    state_path = bootstrap.ROOT / "environments" / env["id"] / "environment.json"
    old = json.loads(state_path.read_text()) if state_path.exists() else {}
    if old.get("status") == "ready" and old.get("prepared_environment"):
        if NAMESPACE and old['project'] != env['project']:
            raise ValueError('Existing sealed environment has a different source namespace; preserved')
        PreparedLeanEvaluator(REPO / old["prepared_environment"]).verify()
        print("REUSE SEALED", env["id"], flush=True)
        return
    if INCREMENTAL_BUDGET is not None:
        version = env["version"]
        installed = [bootstrap.ROOT / "toolchains" / version, ENV / "toolchains" / version,
                     Path.home() / ".elan/toolchains" / ("leanprover--lean4---" + version)]
        if not any((p / 'lib/lean/libLean.a').is_file() for p in installed):
            raise RuntimeError("Incremental mode requires a full compiler already installed separately")
    ensure_toolchain(env["version"])
    INITIAL_FREE = shutil.disk_usage(REPO).free
    if INCREMENTAL_BUDGET is None and INITIAL_FREE < 15 * GIB:
        raise RuntimeError("Less than 15 GiB free before new environment preparation")
    if INCREMENTAL_BUDGET is not None and INITIAL_FREE < 5 * GIB + INCREMENTAL_BUDGET:
        raise RuntimeError("Insufficient space for incremental budget plus 5 GiB reserve")
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
    # leantar 0.1.16 requires a log field when reading v3 traces, although its
    # writer omits empty logs. Normalize generated metadata before resuming an
    # unsealed legacy Mathlib cache so completed outputs remain reusable.
    cache_io = REPO / env['project'] / 'Cache/IO.lean'
    if NAMESPACE and cache_io.exists() and re.search(r'LEANTARVERSION\s*:=\s*"0\.1\.16"', cache_io.read_text()):
        build_roots = sorted((CACHE / 'lean-build' / NAMESPACE / env['version']).iterdir())
        outputs = trace_outputs(build_roots)
        invalidated = []
        if outputs:
            checker = state_path.parent / 'CacheOutputHashes.lean'
            checker.write_text(HASH_CHECKER)
            inputs = state_path.parent / 'cache-output-hashes.tsv'
            inputs.write_text(''.join(r['path'] + '\t' + r['expected'] + '\n' for r in outputs))
            log = state_path.parent / 'cache-output-verification.log'
            bounded_invoke([bootstrap.ROOT / 'toolchains' / env['version'] / 'bin/lean',
                            '-j1', '-M4096', '--run', checker.resolve(), inputs.resolve()],
                           REPO / env['project'], central_process_env(env['version']), log, timeout=600)
            lines = log.read_text().splitlines()
            if not lines or not lines[-1].startswith('CHECKED\t' + str(len(outputs)) + '\tBAD\t'):
                raise ValueError('Cache output hash audit did not complete')
            bad_paths = {line.split('\t')[1] for line in lines if line.startswith('BAD\t')}
            invalidated = invalidate_bad_traces(outputs, bad_paths, state_path.parent / 'legacy-trace-originals')
        normalized = normalize_cache_traces(build_roots, state_path.parent / 'legacy-trace-originals')
        bootstrap.write(state_path.parent / f'cache-trace-normalization-{time.time_ns()}.json', {
            'reason': 'leantar 0.1.16 omitted-empty-log compatibility; compiler outputs unchanged',
            'checked_outputs': len(outputs), 'invalidated_incomplete_traces': invalidated, 'modified': normalized})
        print('LEGACY CACHE OUTPUTS', len(outputs), 'REPAIR TRACES', len(invalidated),
              'NORMALIZED', len(normalized), flush=True)
        if invalidated:
            (state_path.parent / 'cache.receipt.json').unlink(missing_ok=True)
    state = prepare.prepare_one(env, rows, standalone_proofs=not DEFER_STANDALONE_PROOFS)
    if NAMESPACE:
        # Cached setup files contain absolute paths. Ask Lake for the relocated
        # setup after building dependencies rather than reusing seed paths.
        project = REPO / state['project']
        lake = bootstrap.ROOT / 'toolchains' / env['version'] / 'bin/lake'
        state['relocated_setups'] = []
        for module in sorted({loc['module'] for loc in state['locations'] if loc['module']}):
            log = state_path.parent / (module + '.setup.log')
            receipt = bounded_invoke([lake, '--quiet', '--no-build', '--json', 'query', '+' + module + ':setup'],
                                     project, central_process_env(env['version']), log)
            setup = json.loads(log.read_text())
            if not isinstance(setup, dict) or setup.get('name') != module or 'importArts' not in setup:
                raise ValueError('Lake did not produce the expected relocated module setup')
            path = project / '.lake/build/ir' / (module.replace('.', '/') + '.setup.json')
            bootstrap.write(path, setup)
            state['relocated_setups'].append({**receipt, 'setup_sha256': bootstrap.digest(path)})
    if INCREMENTAL_BUDGET is not None:
        state['preparation_resource_policy'] = {'incremental_budget_bytes': INCREMENTAL_BUDGET,
                                                'minimum_free_bytes': 5 * GIB,
                                                'initial_free_bytes': INITIAL_FREE}
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
    if NAMESPACE:
        for module in {loc['module'] for loc in state['locations'] if loc['module']}:
            setup_path = project / '.lake/build/ir' / (module.replace('.', '/') + '.setup.json')
            setup = json.loads(setup_path.read_text())
            for field in ['importArts', 'plugins', 'dynlibs']:
                for value in strings(setup.get(field)):
                    artifact = Path(value)
                    if artifact.is_absolute() and not any(artifact.resolve().is_relative_to(root) for root in paths):
                        raise ValueError('Relocated compiler setup escapes the prepared library roots: ' + value)
    manifest = state_path.parent / "prepared-environment.json"
    freeze(paths, env["revision"], manifest, sandbox="macos-readonly", verification="stat-cache")
    state.update(prepared_environment=str(manifest.relative_to(REPO)),
                 prepared_manifest_sha256=bootstrap.digest(manifest), stage="sealed")
    bootstrap.write(state_path, state)
    registry["environments"][env["id"]] = state
    bootstrap.write(REPO / "configs/final-environments.local.json", registry)
    print("SEALED", env["id"], "rows", env["problem_rows"], flush=True)


def main():
    global INCREMENTAL_BUDGET, NAMESPACE, DEFER_STANDALONE_PROOFS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", action="append", required=True)
    parser.add_argument("--compiler-lock", type=Path, required=True)
    parser.add_argument("--incremental-budget-gib", type=float,
                        help="Use an already installed compiler; bound new disk growth and retain 5 GiB free")
    parser.add_argument('--namespace', help='Fork matching pinned seeds before extending their sealed dependency builds')
    parser.add_argument('--defer-standalone-proofs', action='store_true',
                        help='Verify cached libraries/headers now; leave standalone proof and axiom checks to the evaluator')
    args = parser.parse_args()
    DEFER_STANDALONE_PROOFS = args.defer_standalone_proofs
    if args.incremental_budget_gib is not None:
        if not 0 < args.incremental_budget_gib <= 8:
            parser.error('Incremental budget must be greater than 0 and at most 8 GiB')
        INCREMENTAL_BUDGET = int(args.incremental_budget_gib * GIB)
    if args.namespace is not None:
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,40}', args.namespace):
            parser.error('Namespace must be a short lowercase identifier')
        NAMESPACE = args.namespace
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
    bootstrap.checkout_path = checkout_path
    if NAMESPACE:
        bootstrap.fetch_widget_tags = lambda: original_widget_tags(bootstrap.ROOT / 'isolated-checkouts' / NAMESPACE)
    registry = json.loads((REPO / "configs/final-environments.local.json").read_text())
    for name in args.environment:
        env = next(e for e in lock["environments"] if e["id"] == name)
        if NAMESPACE:
            env = {**env, 'project': str(checkout_path(env['url'], env['version'], env['revision']).relative_to(REPO))}
        with args.compiler_lock.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                prepare_one(env, registry, lock)
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
