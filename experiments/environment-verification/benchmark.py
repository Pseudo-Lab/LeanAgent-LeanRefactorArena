"""Compare a trusted Git baseline with cached verification using fresh Lean processes.

Uses prepared libraries and a native config. No installs, downloads, model calls,
candidate result reuse, or changes to the input files. Executes baseline code.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import platform
import statistics
import subprocess
import time
import types
from unittest.mock import patch

from lean_agent import artifacts, harness, prepared
from lean_agent.preflight import resolve_command

REPO = Path(__file__).resolve().parents[2]


def baseline(ref):
    revision = subprocess.check_output(["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=REPO, text=True).strip()
    source = subprocess.check_output(["git", "show", revision + ":src/lean_agent/prepared.py"], cwd=REPO)
    module = types.ModuleType("lean_agent._benchmark_baseline")
    module.__package__ = "lean_agent"
    exec(compile(source, "git:" + revision + ":prepared.py", "exec"), module.__dict__)
    return module.PreparedLeanEvaluator, revision, artifacts.sha(source)


def measured(action, library_files):
    counters = {"content_reads": 0, "content_bytes": 0}
    read_bytes = Path.read_bytes

    def read(path):
        data = read_bytes(path)
        if str(path) in library_files:
            counters["content_reads"] += 1
            counters["content_bytes"] += len(data)
        return data

    started = time.perf_counter()
    with patch.object(Path, "read_bytes", read):
        result = action()
    return result, {"seconds": time.perf_counter() - started, **counters}


def main(args):
    baseline_evaluator, revision, source_hash = baseline(args.baseline_ref)
    config, paths = harness.load_config(args.config.resolve())
    settings = artifacts.read(paths["prepared_environment"])
    problem = artifacts.read(paths["problem"])
    candidate = args.candidate.read_text() if args.candidate else problem["reference"]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "candidate.lean").write_text(candidate)
    environment = {"id": "fixed", "project": str(paths["project"]),
                   "template": paths["template"].read_text(),
                   **{k: config["lean"][k] for k in ("toolchain", "command", "timeout_seconds")}}
    environment["command"] = resolve_command(environment["command"], environment["toolchain"], paths["project"])
    repetitions = config["lean"]["repetitions"]
    library_files = settings["files"]
    report = {"scope": "local warm-filesystem measurement; fresh Lean processes; not official Arena evaluation",
              "created_at": datetime.now(timezone.utc).isoformat(), "host": platform.platform(),
              "python": platform.python_version(), "baseline_commit": revision,
              "baseline_prepared_sha256": source_hash,
              "cached_prepared_sha256": artifacts.sha(Path(prepared.__file__).read_bytes()),
              "benchmark_sha256": artifacts.sha(Path(__file__).read_bytes()),
              "problem": problem["id"], "candidate_sha256": artifacts.sha(candidate),
              "library_revision": settings["revision"], "files": len(library_files),
              "library_bytes": sum(Path(p).stat().st_size for p in library_files),
              "measurement_repetitions": repetitions, "model_calls": 0, "policies": {}}
    evaluators, fingerprints = {}, {}
    for policy in ("main", "stat-cache"):
        folder = output / policy
        folder.mkdir()
        manifest = folder / "environment.json"
        policy_settings = {k: v for k, v in settings.items() if k != "verification"}
        if policy == "stat-cache":
            policy_settings["verification"] = policy
        artifacts.write(manifest, policy_settings)
        evaluator = (baseline_evaluator if policy == "main" else prepared.PreparedLeanEvaluator)(manifest)
        evaluators[policy] = evaluator
        fingerprint, measurement = measured(lambda: evaluator.fingerprint(environment), library_files)
        artifacts.write(folder / "fingerprint.json", fingerprint)
        fingerprints[policy] = fingerprint
        report["policies"][policy] = {"initial_fingerprint": measurement, "hash_checks": [], "trials": []}
        print(json.dumps({"policy": policy, "initial_fingerprint": measurement}), flush=True)
    # Reverse order every trial to reduce filesystem cache/order bias.
    for trial in range(args.trials):
        for policy in (("main", "stat-cache") if trial % 2 == 0 else ("stat-cache", "main")):
            evaluator = evaluators[policy]
            row = report["policies"][policy]
            check = evaluator.verify if policy == "main" else lambda: evaluator.verify(full=False)
            _, measurement = measured(check, library_files)
            row["hash_checks"].append(measurement)
            result, measurement = measured(lambda: evaluator.evaluate(candidate, problem, [environment],
                output / policy / f"trial-{trial + 1}", repetitions), library_files)
            artifacts.write(output / policy / f"trial-{trial + 1}" / "result.json", result)
            runs = result["environments"].get("fixed", {}).get("runs", [])
            row["trials"].append({"valid": result["valid"], **measurement,
                "compiler_seconds": sum(r["seconds"] for r in runs), "compiler_processes": len(runs),
                "raw_heartbeats": [r["measurement"]["raw"] for r in runs if "measurement" in r],
                "tokens": result["tokens"]})
            print(json.dumps({"policy": policy, "trial": trial + 1, **row["trials"][-1]}), flush=True)
    for policy, evaluator in evaluators.items():
        fingerprint, measurement = measured(lambda: evaluator.fingerprint(environment), library_files)
        row = report["policies"][policy]
        row["final_fingerprint"] = measurement
        row["unchanged_environment"] = fingerprint == fingerprints[policy]
        row["median_hash_check_seconds"] = statistics.median(x["seconds"] for x in row["hash_checks"])
        row["median_candidate_seconds"] = statistics.median(t["seconds"] for t in row["trials"])
        samples = [n for t in row["trials"] for n in t["raw_heartbeats"]]
        row["median_raw_heartbeats"] = statistics.median(samples) if samples else None
    full, cached = (report["policies"][p] for p in ("main", "stat-cache"))
    report["hash_check_speedup"] = full["median_hash_check_seconds"] / cached["median_hash_check_seconds"]
    report["candidate_speedup"] = full["median_candidate_seconds"] / cached["median_candidate_seconds"]
    report["candidate_time_reduction_percent"] = 100 * (1 - cached["median_candidate_seconds"] / full["median_candidate_seconds"])
    trials = [t for row in report["policies"].values() for t in row["trials"]]
    report["all_valid"] = all(t["valid"] for t in trials)
    report["fresh_process_counts_match"] = all(t["compiler_processes"] == repetitions + 1 for t in trials)
    report["tokens_match"] = all(t["tokens"] == trials[0]["tokens"] for t in trials)
    report["exact_heartbeats_match"] = all(t["raw_heartbeats"] == trials[0]["raw_heartbeats"] for t in trials)
    report["all_environments_unchanged"] = all(r["unchanged_environment"] for r in report["policies"].values())
    artifacts.write(output / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "policies"}, indent=2), flush=True)
    return 0 if all(report[k] for k in ("all_valid", "fresh_process_counts_match", "tokens_match", "all_environments_unchanged")) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--baseline-ref", default="84412c8576a58110abeeaf9ec4a74a0055db554b")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    raise SystemExit(main(args))
