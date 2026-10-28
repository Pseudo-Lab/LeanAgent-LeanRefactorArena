"""Replay two real Arena problems in pinned, offline macOS compiler processes.

This is a feasibility pilot, not the official worker or a model experiment.
It reuses prepared caches, makes no API calls, and never changes a checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from refactor_eval.lean import ALLOWED_AXIOMS, WRAPPER, sha256
from refactor_eval.session import implementation_hash, write_json
from refactor_eval.tokens import proof_tokens, validate_declaration

ARENA_REVISION = "8fdaaaa25b993ae8d894e9bb756c3ae222b58507"
BENCHMARK_SHA256 = "6209680cf00cde0765b77b24834cd72c64dd585b2f7e3f2a58209980ab59a804"
CASES = {
    "CallElimCorrect.extractedOldExprInVars": "02-strata",
    "putnam_1964_a4": "13-putnambench",
}
# Compiler processes can read the host, but cannot write any file or use a network.
# Source-tool read confinement is tested separately. This is not full isolation.
PROFILE = "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"
GIT = shutil.which("git")


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(project, *args):
    if not GIT:
        raise ValueError("Git is required to verify prepared checkouts")
    p = subprocess.run([GIT, "-C", str(project), *args],
                       capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise ValueError(p.stderr)
    return p.stdout.strip()


def check_checkout(project, commit):
    actual = git(project, "rev-parse", "HEAD")
    if actual != commit:
        raise ValueError(f"Wrong checkout: {project}: {actual} != {commit}")
    dirty = git(project, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise ValueError(f"Tracked checkout files changed: {project}: {dirty}")


def bounded_read(root, relative):
    """Prototype source tool. The root is bound by the runner, never by an agent."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("source path must be relative and cannot traverse parents")
    target = (root / path).resolve(strict=True)
    if not target.is_relative_to(root.resolve()):
        raise ValueError("source path escaped its bound root")
    if target.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("source file exceeds pilot read limit")
    return target.read_text()


def inventory(roots):
    """Hash actual compiler/library artifacts, including private/server oleans."""
    files = {}
    for label, root in roots.items():
        if not root.is_dir():
            raise ValueError(f"Missing prepared artifacts: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files[f"{label}/{path.relative_to(root)}"] = digest_file(path)
    return files


def resolve_environment(row, version, commit, args):
    project = (args.learn_root / "Strata" if row["source"] == "strata" else
               args.learn_root / ".cache" / f"mathlib-{commit}").resolve()
    check_checkout(project, commit)
    toolchain = (args.toolchains_root / f"leanprover--lean4---{version}").resolve()
    expected = f"leanprover/lean4:{version}"
    if (project / "lean-toolchain").read_text().strip() != expected:
        raise ValueError("lean-toolchain does not match official version_info")
    manifest = json.loads((project / "lake-manifest.json").read_text())
    dependencies = []
    roots = {"project-lib": project / ".lake/build/lib/lean",
             "compiler-bin": toolchain / "bin", "compiler-lib": toolchain / "lib"}
    lean_path = []
    for package in manifest["packages"]:
        if package["type"] != "git":
            raise ValueError("Pilot only supports resolved Git dependencies")
        folder = (project / manifest["packagesDir"] / package["name"]).resolve()
        check_checkout(folder, package["rev"])
        dependencies.append({"name": package["name"], "project": str(folder),
                             "commit": package["rev"]})
        lib = folder / ".lake/build/lib/lean"
        # Cli can be present in the manifest without any compiled modules used here.
        if lib.is_dir():
            roots["dependency-" + package["name"]] = lib
            lean_path.append(str(lib))
    lean_path.append(str(project / ".lake/build/lib/lean"))
    lean = toolchain / "bin/lean"
    version_text = subprocess.check_output([str(lean), "--version"], text=True).strip()
    if f"version {version[1:]}," not in version_text:
        raise ValueError(f"Actual compiler mismatch: {version_text}")
    flags = ["-Dexperimental.module=true"] if row["source"] == "strata" else []
    return {"label": version, "project": str(project), "commit": commit,
            "compiler": str(lean), "compiler_version": version_text,
            "flags": flags, "lean_path": lean_path, "dependencies": dependencies,
            "manifest_sha256": digest_file(project / "lake-manifest.json"),
            "toolchain_sha256": digest_file(project / "lean-toolchain"),
            "runtime_roots": {k: str(v) for k, v in roots.items()}}, roots


def assemble(row, code, source, nonce=None):
    validate_declaration(code, row["statement"])
    declaration = code
    if nonce:
        declaration = ("set_option Elab.async false in\n#refactor_eval " +
                       json.dumps(nonce) + " " + json.dumps(row["name"]) + "\n" + code)
    if row["source"] == "strata":
        if source.count(row["src"]) != 1:
            raise ValueError("Official original declaration must occur exactly once")
        before, after = source.split(row["src"])
        result = before + declaration + after
    else:
        result = row["header"] + declaration + "\n"
    if nonce:
        imports = list(re.finditer(r"(?m)^(?:public )?import [^\n]+", result))
        if not imports:
            raise ValueError("No original import section")
        at = imports[-1].end()
        result = result[:at] + "\nimport Lean\n" + WRAPPER + result[at:]
    return result


def clean_environment(env, scratch):
    # Do not inherit PATH, LEAN_PATH, ELAN_TOOLCHAIN, HOME, or provider credentials.
    return {"PATH": str(Path(env["compiler"]).parent) + ":/usr/bin:/bin",
            "HOME": str(scratch), "TMPDIR": str(scratch), "LANG": "en_US.UTF-8",
            "LEAN_PATH": os.pathsep.join(env["lean_path"])}


def invoke(command, env, scratch, timeout, profile):
    argv = ["/usr/bin/sandbox-exec", "-f", str(profile), *map(str, command)]
    started = time.monotonic()
    process = subprocess.Popen(argv, cwd=scratch, env=clean_environment(env, scratch),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    timed_out = False
    try:
        output = process.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        output = process.communicate()[0]
    return {"command": argv, "returncode": process.returncode, "timed_out": timed_out,
            "seconds": round(time.monotonic() - started, 4),
            "environment": clean_environment(env, scratch),
            "output": output.decode("utf-8", errors="replace")}


def evaluate(row, code, source, env, directory, args, *, measure=True):
    directory.mkdir(parents=True, exist_ok=False)
    profile = directory / "compiler.sb"
    profile.write_text(PROFILE)
    result = {"valid": False, "tokens": proof_tokens(code, row["statement"]),
              "candidate_sha256": sha256(code), "runs": []}
    phases = ["check", "measure"] if measure else ["check"]
    for phase in phases:
        nonce = uuid.uuid4().hex if phase == "measure" else None
        scratch = directory / phase
        relative = Path(row["file_path"] or "Candidate.lean")
        path = scratch / relative
        path.parent.mkdir(parents=True)
        content = assemble(row, code, source, nonce)
        path.write_text(content)
        command = [env["compiler"], *env["flags"], "--root=" + str(scratch), str(path)]
        record = invoke(command, env, scratch, args.timeout, profile)
        log = record.pop("output")
        log_path = directory / (phase + ".log")
        log_path.write_text(log)
        record.update(phase=phase, source=str(path), source_sha256=sha256(content),
                      log=str(log_path), log_sha256=sha256(log))
        result["runs"].append(record)
        if record["returncode"] or record["timed_out"]:
            result["error"] = log[-4000:]
            break
        if nonce:
            reports = re.findall(r"REFACTOR_EVAL " + nonce + r" (\{[^\n]*\})", log)
            if len(reports) != 1:
                raise ValueError("Missing or duplicate measurement report")
            report = json.loads(reports[0])
            if report["target"] != row["name"] or not set(report["axioms"]) <= ALLOWED_AXIOMS:
                raise ValueError("Wrong target or unexpected axioms")
            if type(report["raw"]) is not int or report["raw"] < 0 or report["scaled"] != report["raw"] // 1000:
                raise ValueError("Invalid heartbeat report")
            result["measurement"] = report
    else:
        result["valid"] = True
    write_json(directory / "result.json", result)
    print(f"{row['name']} {env['label']} {directory.name}: {result['valid']}", flush=True)
    return result


def probes(env, directory):
    directory.mkdir(parents=True)
    profile = directory / "compiler.sb"
    profile.write_text(PROFILE)
    protected = directory / "protected.txt"
    protected.write_text("unchanged")
    # Opening for append without writing is harmless even if confinement fails.
    write = invoke(["/bin/sh", "-c", ': >> "$1"', "probe", str(protected)],
                   env, directory, 10, profile)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            control = True
        network = invoke(["/usr/bin/nc", "-z", "-w", "1", "127.0.0.1", str(port)],
                         env, directory, 10, profile)
    source = directory / "source"
    source.mkdir()
    (source / "ok.lean").write_text("theorem ok : True := by trivial")
    (source / "escape.lean").symlink_to(protected)
    reads = {"allowed": bounded_read(source, "ok.lean").startswith("theorem")}
    for key, path in {"parent": "../protected.txt", "absolute": str(protected),
                      "symlink": "escape.lean"}.items():
        try:
            bounded_read(source, path)
            reads[key + "_blocked"] = False
        except ValueError:
            reads[key + "_blocked"] = True
    # A harmless stand-in for an environment file exercises changed-content rejection.
    expected = digest_file(protected)
    protected.write_text("changed")
    detected = digest_file(protected) != expected
    protected.write_text("unchanged")
    return {"compiler_write_blocked": write["returncode"] != 0,
            "compiler_write_probe": write, "network_control_connected": control,
            "compiler_network_blocked": network["returncode"] != 0,
            "compiler_network_probe": network, "source_tool": reads,
            "changed_content_detected": detected,
            "compiler_read_isolation": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--learn-root", type=Path, required=True)
    parser.add_argument("--toolchains-root", type=Path, default=Path.home() / ".elan/toolchains")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.learn_root = args.learn_root.resolve()
    if platform.system() != "Darwin":
        raise ValueError("This pilot uses macOS sandbox-exec; a Linux backend is not implemented")
    if digest_file(args.benchmark) != BENCHMARK_SHA256:
        raise ValueError("Benchmark differs from the reviewed Arena snapshot")
    args.output.mkdir(parents=True, exist_ok=False)
    rows = [json.loads(line) for line in args.benchmark.read_text().splitlines() if line.strip()]
    rows = [row for row in rows if row["name"] in CASES]
    if len(rows) != len(CASES):
        raise ValueError("Missing pilot problems")
    report = {"scope": "local feasibility pilot; not official scoring or a model run",
              "arena_revision": ARENA_REVISION, "benchmark_sha256": BENCHMARK_SHA256,
              "platform": platform.platform(), "evaluator_sha256": implementation_hash(),
              "pilot_sha256": digest_file(Path(__file__)), "cases": [], "api_calls": 0,
              "limits": ["Compiler file reads are not OS-confined; source tool is path-confined",
                         "Uses existing compiled caches; no clean rebuild or Linux container test",
                         "One measurement process per proof/environment; local heartbeat only",
                         "No official submission or official worker equivalence test",
                         "No live model, sub-agent scheduling, or API budget enforcement test"]}
    write_json(args.output / "benchmark-cases.json", rows)
    exported = []
    for row in rows:
        key = CASES[row["name"]]
        folder = args.output / key
        folder.mkdir()
        original = row["src"]
        origin = args.learn_root / "examples/lean-refactor/problems" / key / "candidates/arena-all-sol-high-2026-10-09.lean"
        candidate = origin.read_bytes().decode("utf-8")
        validate_declaration(original, row["statement"])
        validate_declaration(candidate, row["statement"])
        (folder / "original.lean").write_text(original)
        (folder / "candidate.lean").write_text(candidate)
        case = {"name": row["name"], "mode": "project_replacement" if row["source"] == "strata" else "standalone_header",
                "candidate_origin": str(origin), "candidate_sha256": sha256(candidate), "environments": []}
        report["cases"].append(case)
        for pair in row["version_info"]:
            version, commit = next(iter(pair.items()))
            env, roots = resolve_environment(row, version, commit, args)
            target = folder / version
            target.mkdir()
            print(f"Fingerprinting {key} {version}", flush=True)
            before = inventory(roots)
            env["artifacts_sha256"] = sha256(json.dumps(before, sort_keys=True))
            env["artifact_count"] = len(before)
            identity = {k: env[k] for k in ["label", "commit", "compiler_version", "flags", "manifest_sha256", "toolchain_sha256", "artifacts_sha256"]}
            env["environment_id"] = sha256(json.dumps(identity, sort_keys=True))
            write_json(target / "environment.lock.json", env)
            write_json(target / "artifact-hashes.json", before)
            source = (Path(env["project"]) / row["file_path"]).read_text() if row["file_path"] else ""
            if source:
                (target / "upstream.lean").write_text(source)
            entry = {"environment": env}
            case["environments"].append(entry)
            entry["probes"] = probes(env, target / "probes")
            for label, code in [("original", original), ("candidate", candidate)]:
                entry[label] = evaluate(row, code, source, env, target / label, args)
            # Export and parse the actual two-field Arena record before recompiling it.
            payload = json.loads(json.dumps({"name": row["name"], "proof": candidate}, ensure_ascii=False))
            if payload["name"] != row["name"] or sha256(payload["proof"]) != sha256(candidate):
                raise ValueError("Submission serialization changed the candidate")
            # Deliberately poison parent variables. invoke() must ignore all of them.
            previous = {k: os.environ.get(k) for k in ["PATH", "LEAN_PATH", "ELAN_TOOLCHAIN"]}
            try:
                os.environ.update(PATH="/invalid-path", LEAN_PATH="/invalid-library", ELAN_TOOLCHAIN="invalid")
                entry["export_replay"] = evaluate(row, payload["proof"], source, env,
                                                   target / "export-poisoned-parent", args, measure=False)
            finally:
                for k, v in previous.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            broken = row["statement"] + " := by\n  exact arena_pilot_missing_identifier\n"
            entry["invalid_control"] = evaluate(row, broken, source, env, target / "invalid-control", args, measure=False)
            after = inventory(roots)
            entry["artifacts_unchanged"] = before == after
            check_checkout(Path(env["project"]), commit)
            for dependency in env["dependencies"]:
                check_checkout(Path(dependency["project"]), dependency["commit"])
            entry["pins_unchanged"] = digest_file(Path(env["project"]) / "lake-manifest.json") == env["manifest_sha256"]
            if not entry["artifacts_unchanged"] or not entry["pins_unchanged"]:
                raise ValueError("Prepared environment changed during measurement")
            write_json(args.output / "report.json", report)
        if all(e["original"]["valid"] and e["candidate"]["valid"] and e["export_replay"]["valid"] for e in case["environments"]):
            exported.append({"name": row["name"], "proof": candidate})
    checks = [e for c in report["cases"] for e in c["environments"]]
    report["passed"] = len(exported) == 2 and all(
        not e["invalid_control"]["valid"] and e["artifacts_unchanged"] and
        e["probes"]["compiler_write_blocked"] and e["probes"]["compiler_network_blocked"] and
        all(e["probes"]["source_tool"].values()) for e in checks)
    if report["passed"]:
        output = args.output / "submission.jsonl"
        output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in exported))
        report["submission"] = {"path": str(output), "rows": len(exported), "sha256": digest_file(output)}
    write_json(args.output / "report.json", report)
    print(json.dumps({"passed": report["passed"], "output": str(args.output), "environments": len(checks)}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
