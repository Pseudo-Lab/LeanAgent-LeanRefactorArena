"""Seal compiled final environments and make local runner manifests."""
from collections import Counter
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os
import shutil
import subprocess

from bootstrap import REPO, ROOT, plan, dataset, write, digest, command, EXPECTED, normalize_package_links
from prepare import process_env, invoke
from resolve import resolve
from toolchains import file_sha
from lean_agent.prepared import freeze, PreparedLeanEvaluator


def canonical_whitespace_check(env, location, rows):
    """Compile the dataset's exact bytes when the pinned source differs in spaces."""
    project = REPO / env["project"]
    row = rows[location["row"]-1]
    original = (project / location["file_path"]).read_text()
    start, end = location["statement_start_char"], location["declaration_end_char"]
    if start is None or end is None:
        raise ValueError("Canonical source boundary is not proven")
    content = original[:start] + row["src"] + original[end:]
    folder = project / location["module"].split(".")[0] / "ArenaEnvironmentChecks"
    folder.mkdir(exist_ok=True)
    source = folder / (f"Canonical{location['row']:03d}.lean")
    source.write_text(content)
    output = ROOT / "environments" / env["id"]
    saved = output / (f"canonical-{location['row']:03d}.lean")
    saved.write_text(content)
    try:
        rec = invoke([ROOT / "toolchains" / env["version"] / "bin/lake", "lean", source,
                      "--", "-j1", "-M4096"], project, process_env(env["version"]),
                     output / (f"canonical-{location['row']:03d}.log"), timeout=1200)
    finally:
        source.unlink(missing_ok=True)
    return {"row": location["row"], "source": str(saved.relative_to(REPO)),
            "source_sha256": digest(saved), "compile": rec}


def preserve_and_clean_probes(env, locations):
    """Keep exact checker inputs in evidence, remove temporary library modules."""
    project = REPO / env["project"]
    scope = {"ArenaEnvironmentChecks"}
    scope.update(loc["module"].split(".")[0] + "/ArenaEnvironmentChecks"
                 for loc in locations if loc["module"])
    out = ROOT / "environments" / env["id"] / "checks"
    records = []
    for name in sorted(scope):
        folder = project / name
        if not folder.exists():
            continue
        for source in sorted(folder.glob("*.lean")):
            if not (source.name in {"Imports.lean", "ImportsAll.lean"}
                    or source.name.startswith(("Reference", "Canonical"))):
                raise ValueError("Unexpected file in managed checker folder; preserved")
            saved = out / name / source.name
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(source.read_bytes())
            records.append({"original_module_path": source.relative_to(project).as_posix(),
                            "saved_source": str(saved.relative_to(REPO)), "sha256": digest(saved)})
            source.unlink()
        # Never remove non-checker contents or source folders.
        if not any(folder.iterdir()):
            folder.rmdir()
    return records


def main():
    lock, rows = plan(), dataset()
    states, missing = {}, []
    for env in lock["environments"]:
        file = ROOT / "environments" / env["id"] / "environment.json"
        state = json.loads(file.read_text()) if file.exists() else {}
        if state.get("status") != "ready":
            missing.append({"id": env["id"], "status": state.get("status", "not-built"), "stage": state.get("stage")})
        states[env["id"]] = state
    if missing:
        print(json.dumps({"not_ready": missing}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    normalize_package_links()
    compilers = json.loads((ROOT / "toolchains.json").read_text())["toolchains"]
    for version, compiler in compilers.items():
        if file_sha(ROOT / "toolchains" / version / "bin/lean") != compiler["lean_sha256"]:
            raise ValueError("Compiler executable changed after preparation")
    source_lock = json.loads((ROOT / "source-lock.json").read_text())
    for checkout in source_lock["checkouts"]:
        project = REPO / checkout["path"]
        if not (project / ".git").is_dir():
            raise ValueError("Dependency Git provenance missing: " + str(project))
        if command(["git", "-C", project, "rev-parse", "HEAD"]).strip() != checkout["revision"]:
            raise ValueError("Dependency revision changed")
        if command(["git", "-C", project, "diff", "--name-only", "HEAD", "--"]).strip():
            raise ValueError("Dependency source was modified")
        manifest = project / "lake-manifest.json"
        if checkout["manifest_sha256"] is not None and digest(manifest) != checkout["manifest_sha256"]:
            raise ValueError("Dependency manifest was modified")
    registry, summaries, kinds = {}, [], Counter()
    for env in lock["environments"]:
        print("SEAL", env["id"], flush=True)
        state = states[env["id"]]
        project = REPO / env["project"]
        locations = resolve(env, rows)
        kinds.update(loc["kind"] for loc in locations)
        canonical = [canonical_whitespace_check(env, loc, rows) for loc in locations if loc["kind"] == "whitespace_src"]
        if any(loc["kind"] not in {"exact_src", "whitespace_src", "standalone_header"} for loc in locations):
            raise ValueError("A reference proof has not been located completely")
        saved_checks = {row["saved_source"]: row for row in state.get("saved_checker_inputs", [])}
        saved_checks.update({row["saved_source"]: row for row in preserve_and_clean_probes(env, locations)})
        paths = []
        for name in state["lean_path"].split(os.pathsep):
            if not name:
                continue
            path = Path(name)
            if not path.is_absolute():
                path = project / path
            path = path.resolve()
            if path.is_dir() and path not in paths:
                paths.append(path)
        core = (ROOT / "toolchains" / env["version"] / "lib/lean").resolve()
        if core not in paths:
            paths.append(core)
        # Native precompiled packages and the compiler can load shared libraries
        # next to lib/lean; freeze those too, alongside the ordinary Lean paths.
        for parent in [p.parent for p in list(paths) if p.name == "lean"]:
            if parent not in paths and (parent == core.parent or
                    any(f.suffix in {".a", ".so", ".dylib"} for f in parent.iterdir() if f.is_file())):
                paths.append(parent)
        manifest = ROOT / "environments" / env["id"] / "prepared-environment.json"
        frozen = freeze(paths, env["revision"], manifest, sandbox="macos-readonly", verification="stat-cache")
        PreparedLeanEvaluator(manifest)  # Check compatibility with the common harness schema.
        state.update(locations=locations, canonical_byte_checks=canonical, saved_checker_inputs=list(saved_checks.values()),
                     prepared_environment=str(manifest.relative_to(REPO)), prepared_manifest_sha256=digest(manifest),
                     validation_scope="Pinned source module builds, target type/import checks, and canonical standalone/whitespace variants; no full axiom-policy audit or heartbeat measurement.")
        write(ROOT / "environments" / env["id"] / "environment.json", state)
        registry[env["id"]] = {**env, "status": "ready", "compiler": state["compiler"],
            "actual_compiler": state["actual_compiler"], "prepared_environment": str(manifest.relative_to(REPO)),
            "prepared_manifest_sha256": digest(manifest), "library_paths": [str(p) for p in paths],
            "command_example": "PYTHONPATH=src python3 -B experiments/final-environment/env.py " + env["id"] + " -- lake lean FILE.lean"}
        summaries.append({"id": env["id"], "version": env["version"], "revision": env["revision"],
                          "problem_rows": env["problem_rows"], "reference_checks": len(locations),
                          "prepared_library_files": frozen["files"], "prepared_manifest_sha256": digest(manifest), "status": "ready"})
    for index, row in enumerate(rows, 1):
        write(ROOT / "problems" / f"F{index:03d}.json", {"id": f"final-{EXPECTED[:12]}-F{index:03d}",
            "dataset_sha256": EXPECTED, "row": index, "name": row["name"], "statement": row["statement"],
            "reference": row["src"], "header": row["header"], "source": row["source"],
            "environments": [row["source"] + "-" + version for p in row["version_info"] for version in p]})
    write(REPO / "configs/final-environments.local.json", {"schema_version": 1, "dataset_sha256": EXPECTED, "environments": registry})
    python = REPO / ".venv/bin/python"
    python_info = json.loads(command([python, "-c",
        "import sys,json,importlib.metadata; print(json.dumps({'version':sys.version,'executable':sys.executable,'distributions':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()}}))"]))
    write(ROOT / "python-environment.json", python_info)
    result = {"schema_version": 1, "completed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
              "dataset_sha256": EXPECTED, "platform": "macOS arm64", "environment_count": len(summaries),
              "compiler_versions": lock["toolchain_versions"], "problem_count": len(rows),
              "compilers": [{"version": version, "actual_version": compiler["actual_version"],
                             "lean_sha256": compiler["lean_sha256"], "lake_sha256": compiler["lake_sha256"]}
                            for version, compiler in sorted(compilers.items())],
              "problem_version_combinations": sum(row["reference_checks"] for row in summaries),
              "source_matches": dict(kinds), "source_checkouts_verified": len(source_lock["checkouts"]),
              "python_version": python_info["version"], "python_package_installed": python_info["distributions"].get("lean-agent-arena"),
              "environment_sources_unmodified": True, "heartbeat_measurements": 0, "model_api_calls": 0,
              "validation_scope": "Environment preparation and original-reference compilation/type checks. Candidate text gate and official scoring are separate.",
              "environments": summaries}
    write(REPO / "experiments/final-environment/preparation-results.json", result)
    write(ROOT / "current-failures.json", [])
    print(json.dumps({k: v for k, v in result.items() if k != "environments"}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
