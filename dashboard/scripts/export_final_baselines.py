"""Export existing final baseline evidence only; never run Lean or call a model."""
import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

DATASET_SHA = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def supplemental_root(roots, problem_id, env_id, row):
    for root in roots:
        receipt = root / "groups" / (env_id + ".json")
        if not receipt.exists():
            continue  # Still measuring; only publish groups with a final boundary check.
        group = read(receipt)
        if not group.get("boundary_verified"):
            continue
        rows = [r for r in group["rows"] if r["row"] == row and r["valid"]]
        if not rows:
            continue
        result = root / "problems" / problem_id / "baseline/result.json"
        input_path = root / "problems" / problem_id / "input/problem.json"
        require(len(rows) == 1 and digest(result) == rows[0]["result_sha256"]
                and digest(input_path) == rows[0]["input_sha256"], f"{problem_id}: supplemental receipt mismatch")
        require(group["initial_fingerprints"] == group["final_fingerprints"], "Environment boundary mismatch")
        return root
    return None


def export(dataset, run_root, supplements=()):
    require(digest(dataset) == DATASET_SHA, "Unexpected final dataset SHA-256")
    records = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    require(len(records) == 60, "Expected 60 final problems")
    problems = []
    for row, record in enumerate(records, 1):
        problem_id = f"F{row:03d}"
        primary_version, primary_revision = next(iter(record["version_info"][0].items()))
        env_id = f"{record['source']}-{primary_version}"
        row_root = run_root
        if not (run_root / "problems" / problem_id / "baseline/result.json").exists():
            row_root = supplemental_root(supplements, problem_id, env_id, row) or run_root
        folder = row_root / "problems" / problem_id
        result_path = folder / "baseline/result.json"
        local = None
        if result_path.exists():
            problem_path = folder / "input/problem.json"
            problem = read(problem_path)
            require(problem["dataset_sha256"] == DATASET_SHA and problem["row"] == row
                    and problem["reference"] == record["src"] and problem["name"] == record["name"]
                    and problem["statement"] == record["statement"], f"{problem_id}: input mismatch")
            result = read(result_path)
            require(result["valid"] is True and result.get("error") is None, f"{problem_id}: invalid baseline")
            env = result["environments"][env_id]
            require(env["valid"] is True and env.get("error") is None, f"{problem_id}: invalid primary pin")
            evidence = [{"path": str(p.relative_to(row_root)), "sha256": digest(p)}
                        for p in [problem_path, result_path]]
            samples, measured_at = [], []
            for run in env["runs"]:
                require(run["returncode"] == 0 and not run["timed_out"], f"{problem_id}: failed invocation")
                for key in ["source", "log"]:
                    path = folder / "baseline" / env_id / run[key]
                    require(path.resolve().is_relative_to(folder.resolve()), "Evidence outside problem folder")
                    require(digest(path) == run[f"{key}_sha256"], f"{problem_id}: changed {key} evidence")
                    evidence.append({"path": str(path.relative_to(row_root)), "sha256": digest(path)})
                if "measurement" in run:
                    measurement = run["measurement"]
                    log = (folder / "baseline" / env_id / run["log"]).read_text()
                    parsed = [json.loads(line.split(" ", 2)[2]) for line in log.splitlines()
                              if line.startswith("REFACTOR_EVAL ")]
                    require(parsed == [measurement] and measurement["target"] == record["name"],
                            f"{problem_id}: measurement log mismatch")
                    require(measurement["scaled"] == measurement["raw"] // 1000, "Unexpected HB units")
                    samples.append(measurement["raw"])
                    measured_at.append(run["memory_after"]["at"])
            require(len(samples) in (1, 3) and sum(r.get("phase") != "axiom-frontier-audit" for r in env["runs"]) == 1 + len(samples),
                    f"{problem_id}: expected check + 1 or 3 measurements")
            raw = statistics.median(samples)
            scaled = statistics.median([s // 1000 for s in samples])
            require(raw == env["median_raw_heartbeats"] and scaled == env["median_heartbeats"],
                    f"{problem_id}: median mismatch")
            local = {"runId": row_root.name, "sampleCount": len(samples), "tokens": result["tokens"], "rawHeartbeats": raw, "scaledHeartbeats": scaled,
                     "rawSamples": samples, "measuredAt": max(measured_at), "evidence": evidence}
        problems.append({"id": problem_id, "row": row, "name": record["name"], "source": record["source"],
                         "providedLength": record["proof_length"], "primaryVersion": primary_version,
                         "primaryRevision": primary_revision, "requiredVersions": [next(iter(v)) for v in record["version_info"]],
                         "local": local})
    return {"schemaVersion": 1, "dataset": "final-baselines", "datasetSha256": DATASET_SHA,
            "generatedAt": datetime.now(timezone.utc).isoformat(), "runId": run_root.name,
            "measurementPolicy": "primary-pin-local-samples", "problems": problems}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--supplement", action="append", type=Path, default=[], help="Additional baseline-only run; repeatable")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "public/data/final-baselines.json")
    args = parser.parse_args()
    snapshot = export(args.dataset, args.run_root, args.supplement)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    measured = sum(p["local"] is not None for p in snapshot["problems"])
    print(f"Exported 60 problems: {measured} measured baselines, {60 - measured} missing; no compiler/API calls")
