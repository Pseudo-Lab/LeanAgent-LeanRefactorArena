"""Build final-benchmark imports and validate untouched reference source modules."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess
import time

from bootstrap import REPO, ROOT, plan, dataset, write, digest, command, package_name
from resolve import resolve


def process_env(version):
    binary = ROOT / "toolchains" / version / "bin"
    git_bin = str(Path(shutil.which("git")).parent)
    limit = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else 2
    threads = os.environ.get("ARENA_BUILD_THREADS", str(limit))
    if not threads.isdigit() or not 1 <= int(threads) <= limit:
        raise ValueError(f"ARENA_BUILD_THREADS must be between 1 and {limit}")
    return {"PATH": str(binary) + ":" + str(ROOT / "bin") + ":" + git_bin + ":/opt/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()), "TMPDIR": "/tmp", "LANG": "C.UTF-8",
            "LEAN_NUM_THREADS": threads, "MATHLIB_NO_CACHE_ON_UPDATE": "1",
            "XDG_CACHE_HOME": str(ROOT / "cache"),
            "MATHLIB_CACHE_DIR": str(ROOT / "cache" / version)}


def invoke(argv, project, env, log, *, timeout=7200):
    log.parent.mkdir(parents=True, exist_ok=True)
    print("RUN", log.name, flush=True)
    started = time.monotonic()
    with log.open("w") as stream:
        result = subprocess.run(list(map(str, argv)), cwd=project, env=env,
                                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    rec = {"command": list(map(str, argv)), "cwd": str(project), "returncode": result.returncode,
           "seconds": round(time.monotonic() - started, 3), "log": str(log.relative_to(REPO)),
           "log_sha256": digest(log)}
    write(log.with_suffix(".receipt.json"), rec)
    if result.returncode:
        raise RuntimeError("Failed " + log.name + ":\n" + log.read_text(errors="replace")[-5000:])
    return rec


def imports(text):
    # Use the existing nested comment scanner. Only source imports are read;
    # statements and dataset comments are never interpreted as agent commands.
    from lean_agent.evaluator.tokens import without_comments
    clean = without_comments(text)
    result = []
    for line in clean.splitlines():
        match = re.match(r"\s*(?:public\s+)?(?:meta\s+)?import\s+(.*)", line)
        if match:
            for word in match[1].split():
                if word != "all" and re.fullmatch(r"[\w.]+", word):
                    result.append(word)
    return result


def roots(project):
    manifest = json.loads((project / "lake-manifest.json").read_text())
    result = [project]
    for entry in manifest["packages"]:
        path = project / manifest.get("packagesDir", ".lake/packages") / package_name(entry["name"])
        result.append(path / entry["subDir"] if entry.get("subDir") else path)
    return result


def cache_imports(project, locations, rows):
    search = roots(project)
    seen, external, unresolved = set(), set(), set()
    prefixes = {"Mathlib", "Aesop", "Batteries", "Qq", "ProofWidgets", "Plausible", "ImportGraph", "LeanSearchClient"}

    def visit(module):
        if module in seen:
            return
        seen.add(module)
        first = module.split(".")[0]
        if first in prefixes:
            external.add(module)
            return
        if first in {"Init", "Lean", "Std", "Lake"}:
            return
        relative = module.replace(".", "/") + ".lean"
        source = next((root / relative for root in search if (root / relative).is_file()), None)
        if source is None:
            unresolved.add(module)
            return
        for dep in imports(source.read_text()):
            visit(dep)

    for location in locations:
        if location["module"]:
            visit(location["module"])
        else:
            for dep in imports(rows[location["row"]-1]["header"]):
                visit(dep)
    return {"external_roots": sorted(external), "traversed_modules": len(seen),
            "unresolved_source_imports": sorted(unresolved)}


def prepare_one(env, rows):
    project = REPO / env["project"]
    version = env["version"]
    compiler = ROOT / "toolchains" / version
    if not (compiler / "bin/lean").exists():
        raise ValueError("Pinned compiler is not prepared")
    state_dir = ROOT / "environments" / env["id"]
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "environment.json"
    old = json.loads(state_path.read_text()) if state_path.exists() else {}
    actual = command([compiler / "bin/lean", "--version"]).strip()
    if not actual.startswith("Lean (version " + version[1:] + ","):
        raise ValueError("Compiler version mismatch")
    if command(["git", "-C", project, "rev-parse", "HEAD"]).strip() != env["revision"]:
        raise ValueError("Source pin mismatch")
    if command(["git", "-C", project, "diff", "--name-only", "HEAD", "--"]).strip():
        raise ValueError("Pinned source has tracked edits")
    if old.get("status") == "ready":
        if digest(project / "lake-manifest.json") != old["manifest_sha256"]:
            raise ValueError("Prepared source manifest changed")
        if old.get("prepared_environment"):
            from lean_agent.prepared import PreparedLeanEvaluator
            PreparedLeanEvaluator(REPO / old["prepared_environment"]).verify()
        print("ALREADY READY", env["id"], flush=True)
        return old
    locations = resolve(env, rows)
    closure = cache_imports(project, locations, rows)
    write(state_dir / "locations.json", locations)
    write(state_dir / "import-plan.json", closure)
    state = {**env, "status": "preparing", "actual_compiler": actual,
             "compiler": str((compiler / "bin/lean").relative_to(REPO)),
             "manifest_sha256": digest(project / "lake-manifest.json"),
             "toolchain_sha256": digest(project / "lean-toolchain"),
             "locations": locations, "records": []}
    write(state_path, state)
    child = process_env(version)
    lake = compiler / "bin/lake"
    mathlib = project if env["source"] == "putnambench" else project / ".lake/packages/mathlib"
    if mathlib.is_dir() and closure["external_roots"] and os.environ.get("ARENA_SOURCE_BUILD") != "1":
        log = state_dir / "cache.log"
        if not log.with_suffix(".receipt.json").exists() or json.loads(log.with_suffix(".receipt.json").read_text())["returncode"]:
            state["stage"] = "mathlib-cache"
            write(state_path, state)
            invoke([lake, "exe", "cache", "get", *closure["external_roots"]], project, child, log)
    modules = sorted({location["module"] for location in locations if location["module"]})
    for module in modules:
        state["stage"] = "build-" + module
        write(state_path, state)
        log = state_dir / (module + ".build.log")
        # Source builds must not stall while Lake probes Reservoir barrels.
        cache_flag = ["--no-cache"] if os.environ.get("ARENA_SOURCE_BUILD") == "1" else []
        rec = invoke([lake, *cache_flag, "build", "+" + module], project, child, log)
        state["records"].append(rec)
        write(state_path, state)
    private_imports = any(re.search(r"(?m)^module\s*$", (project / loc["file_path"]).read_text())
                          for loc in locations if loc.get("file_path"))
    checks = project / (modules[0].split(".")[0] if private_imports else "") / "ArenaEnvironmentChecks"
    checks.mkdir(exist_ok=True)
    references = []
    state["stage"] = "reference-checks"
    write(state_path, state)
    if env["source"] == "putnambench":
        for location in locations:
            index = location["row"]
            row = rows[index-1]
            state["stage"] = f"reference-F{index:03d}"
            write(state_path, state)
            source = checks / (f"Reference{index:03d}.lean")
            source.write_text(row["header"] + row["src"] + "\n#print axioms " + row["name"] + "\n")
            log = state_dir / (f"reference-{index:03d}.log")
            rec = invoke([lake, "lean", source, "--", "-j1", "-M4096"], project, child, log, timeout=600)
            references.append({"row": index, "name": row["name"], "kind": "canonical_standalone", "compile": rec})
    else:
        source = checks / "Imports.lean"
        source.write_text(("module\n" if private_imports else "") + "import Lean\n" +
                          "".join(("import all " if private_imports else "import ") + module + "\n" for module in modules) +
                          "\n" + "".join("#check " + location["name"] + "\n" for location in locations))
        rec = invoke([lake, "lean", source, "--", "-j1", "-M4096"], project, child, state_dir / "reference-imports.log", timeout=600)
        references = [{"row": loc["row"], "name": loc["name"], "kind": loc["kind"], "compile": rec} for loc in locations]
    if digest(project / "lake-manifest.json") != state["manifest_sha256"]:
        raise ValueError("Build changed the pinned manifest")
    if command(["git", "-C", project, "diff", "--name-only", "HEAD", "--"]).strip():
        raise ValueError("Build changed tracked source")
    state.update(status="ready", stage="complete", references=references,
                 validation_scope="Pinned source module build plus target type/import check; no heartbeat measurement or complete axiom-policy audit.",
                 lean_path=command([lake, "env", "printenv", "LEAN_PATH"], cwd=project, env=child).strip(),
                 model_api_calls=0)
    write(state_path, state)
    print("ENVIRONMENT READY", env["id"], flush=True)
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append")
    args = parser.parse_args()
    rows = dataset()
    environments = plan()["environments"]
    unknown = set(args.only or []) - {env["id"] for env in environments}
    if unknown:
        parser.error("Unknown pinned environments: " + ", ".join(sorted(unknown)))
    order = {"strata": 0, "putnambench": 1, "cslib": 2, "physlib": 3, "leanpool": 4, "arklib": 5}
    failures = []
    for env in sorted(environments, key=lambda e: (order[e["source"]], e["version"])):
        if args.only and env["id"] not in args.only:
            continue
        if shutil.disk_usage(ROOT).free < 15 * 1024**3:
            raise ValueError("Free space below 15 GiB; build stopped without deleting evidence")
        try:
            prepare_one(env, rows)
        except Exception as error:
            print("ENVIRONMENT FAILED", env["id"], str(error), flush=True)
            failures.append({"id": env["id"], "error": str(error)})
            state_path = ROOT / "environments" / env["id"] / "environment.json"
            if state_path.exists():
                state = json.loads(state_path.read_text())
                state.update(status="failed", error=str(error))
                write(state_path, state)
        write(ROOT / "build-failures.json", failures)
    if failures:
        raise SystemExit(1)
