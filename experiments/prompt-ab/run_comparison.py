#!/usr/bin/env python3
"""Authorized six-pair prompt pilot using the existing durable final harness.

Prepare/preflight do not call the model. Run is explicitly paid, bounded at $12.
All runtime sources are copied and sealed before either arm dispatches a call.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
ROWS = [2, 7, 9, 41, 48, 49]
ARMS = {"control": "baseline", "treatment": "structure-repair-v1"}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def now():
    return datetime.now(timezone.utc).isoformat()


def runtime(root):
    sys.path.insert(0, str(root / "runtime/src"))
    sys.path.insert(0, str(root / "runtime/experiments/final-batch-next"))
    return importlib.import_module("driver")


def verify_experiment(root):
    protocol = read(root / "protocol.json")
    if protocol["rows"] != ROWS or protocol["arms"] != ARMS or protocol["total_cap_usd"] != "12.00":
        raise ValueError("Experiment differs from the approved six-pair/$12 scope")
    for relative, digest in read(root / "experiment-frozen.json").items():
        if sha(root / relative) != digest:
            raise ValueError("Frozen experiment source changed: " + relative)


def prepare(root, environment_repo):
    if root.exists():
        raise ValueError("Prepare requires a new experiment root")
    destination = root / "runtime"
    destination.mkdir(parents=True)
    shutil.copytree(REPO / "src", destination / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for directory in ("experiments/final-batch-next", "experiments/proof-analyze", "examples/actions"):
        shutil.copytree(REPO / directory, destination / directory, ignore=shutil.ignore_patterns("__pycache__"))
    script = destination / "experiments/prompt-ab/run_comparison.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__), script)
    # Record the checked-in verifier source and sealed snapshot hashes.
    # Historical paid runtimes remain immutable and are not rebuilt here.
    origins = {}
    for filename in ("evaluator.py", "evaluation_cache.py", "fast_prepared.py", "test_fast_prepared.py"):
        source = REPO / "experiments/final-batch-next" / filename
        target = destination / "experiments/final-batch-next" / filename
        text = source.read_text()
        if filename == "evaluator.py":
            text = text.replace("(env : Environment) : Array Name", "(env : _root_.Lean.Environment) : Array _root_.Lean.Name")
            text = text.replace("axioms.toList.map Name.toString", "axioms.toList.map _root_.Lean.Name.toString")
        target.write_text(text)
        origins[filename] = {"source_sha256": sha(source), "snapshot_sha256": sha(target)}
    (destination / "sources").mkdir()
    (destination / "sources/final").symlink_to(environment_repo / "sources/final", target_is_directory=True)
    (destination / "configs").mkdir()
    shutil.copyfile(environment_repo / "configs/final-environments.local.json", destination / "configs/final-environments.local.json")
    manifest = destination / "dashboard/public/data/final-results.json"
    manifest.parent.mkdir(parents=True)
    shutil.copyfile(REPO / "dashboard/public/data/final-results.json", manifest)
    protocol = {"created_at": now(), "rows": ROWS, "arms": ARMS, "total_cap_usd": "12.00",
        "per_problem_per_arm_cap_usd": "1.00", "repetitions": 1,
        "model": "gpt-6.1-sol", "reasoning_effort": "high", "max_problem_workers": 2,
        "primary_endpoint": "paired final score improvement from the shared historical-best seed",
        "secondary_endpoints": ["settled cost", "unique valid candidates", "repeated lookups", "first improvement cost", "compiler seconds"],
        "shared_preflight": "Control preflight measured once and copied identically to treatment before any paid dispatch; full environment boundaries still checked per trial.",
        "limitations": "One trajectory per condition/problem; selected cohort is exploratory, not a significance test or unbiased benchmark.",
        "verifier_sources": origins}
    save(root / "protocol.json", protocol)
    files = [p for p in destination.rglob("*") if p.is_file() and "__pycache__" not in p.parts and "sources" not in p.relative_to(destination).parts]
    files.append(root / "protocol.json")
    save(root / "experiment-frozen.json", {str(p.relative_to(root)): sha(p) for p in files})
    d = runtime(root)
    control = root / "control"
    d.prepare_inputs(control, ROWS, workers=1, portfolio_settings=None,
                     prompt_variant="baseline", strict_cap=True)
    treatment = root / "treatment"
    for row in ROWS:
        source = d.folder(control, row) / "input"
        target = d.folder(treatment, row) / "input"
        shutil.copytree(source, target)
        text = (source / "prompt.txt").read_text()
        context = text.split("<original_context>\n", 1)[1][:-len("\n</original_context>\n")]
        (target / "prompt.txt").write_text(d.prompt_text(context, "structure-repair-v1", True))
        d.atomic(target / "prompt-policy.json", d.prompt_variants.policy("structure-repair-v1", True))
        d.validate_inputs(treatment, row)
    for arm in ARMS:
        d.seal_inputs(root / arm, ROWS)
    verify_experiment(root)
    print(json.dumps({"experiment": str(root), "trials": 12, "cap_usd": "12.00", "api_calls": 0}), flush=True)


def preflight(root):
    verify_experiment(root)
    d = runtime(root)
    for arm in ARMS:
        d.verify_frozen(root / arm)
        if read(root / arm / "ledger.json")["attempts"]:
            raise ValueError("Shared preflight cannot change after any paid dispatch")
    control, treatment = root / "control", root / "treatment"
    d.preflight(control, ROWS)
    # Copy only shared initial verification evidence, never model trajectories.
    for row in ROWS:
        source, target = d.folder(control, row), d.folder(treatment, row)
        for name in ("baseline", "warm-start", "reference-compatibility"):
            if not (target / name).exists():
                shutil.copytree(source / name, target / name)
        for name in ("initial-state.json", "state.json", "preflight.json"):
            if not (target / name).exists():
                shutil.copyfile(source / name, target / name)
        save(target / "shared-preflight.json", {"source_arm": "control", "at": now(),
            "initial_state_sha256": sha(source / "initial-state.json"), "paid_attempts_at_copy": 0})
    if not (treatment / "evaluation-cache").exists():
        shutil.copytree(control / "evaluation-cache", treatment / "evaluation-cache")
    d.preflight(treatment, ROWS)
    for row in ROWS:
        if read(d.folder(control, row) / "initial-state.json") != read(d.folder(treatment, row) / "initial-state.json"):
            raise ValueError("Paired starting states differ")
    save(root / "preflight.json", {"status": "ready", "at": now(), "api_calls": 0})


def run(root, key_file):
    verify_experiment(root)
    if read(root / "preflight.json")["status"] != "ready":
        raise ValueError("Shared preflight is not ready")
    d = runtime(root)
    original_verify, original_dispatchable = d.verify_frozen, d.check_dispatchable
    def verify(path):
        verify_experiment(root)
        original_verify(path)
    def dispatchable(path, ledger):
        if (root / "operator/stop.json").exists():
            raise ValueError("Experiment stopped after a failed trial; inspect before resuming")
        original_dispatchable(path, ledger)
        for arm in ARMS:
            other = root / arm
            if other.resolve() != Path(path).resolve():
                original_dispatchable(other, read(other / "ledger.json"))
    d.verify_frozen, d.check_dispatchable = verify, dispatchable
    for arm in ARMS:
        verify(root / arm)
        auth = read(root / arm / "authorization.json")
        if auth["rows"] != ROWS or auth["last_call_may_overshoot"] is not False or Decimal(auth["per_problem_target_usd"]) != 1:
            raise ValueError("Paid scope/cap mismatch")
    os.environ["OPENAI_API_KEY"] = d.transport.load_key(key_file)
    jobs = [(arm, row) for index, row in enumerate(ROWS)
            for arm in (list(ARMS) if index % 2 == 0 else list(reversed(ARMS)))]
    def trial(arm, row):
        if (root / "operator/stop.json").exists():
            raise ValueError("No new trial after failure")
        save(root / "operator" / f"{arm}-F{row:03}-start.json", {"at": now(), "pid": os.getpid()})
        value = d.run_problem(root / arm, row)
        save(root / "operator" / f"{arm}-F{row:03}-end.json", {"at": now(), "status": value["status"]})
        return value
    failures = []
    with d.locked(root / "operator/manager.lock", blocking=False), ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(trial, arm, row): (arm, row) for arm, row in jobs}
        for future in as_completed(futures):
            arm, row = futures.pop(future)
            try:
                value = future.result()
                if value["status"] != "completed":
                    raise ValueError("Trial did not complete")
            except Exception as exc:
                error = d.compact_worker_failure(exc)
                failures.append({"arm": arm, "row": row, **error})
                if not (root / "operator/stop.json").exists():
                    save(root / "operator/stop.json", {"at": now(), **failures[-1]})
            save(root / "operator/status.json", {"at": now(), "remaining": len(futures), "failures": failures})
    if failures:
        raise ValueError("Experiment stopped; inspect operator/stop.json, no automatic paid retries")
    compare(root)


def compare(root):
    verify_experiment(root)
    d = runtime(root)
    from lean_agent import action_memory
    reports = {}
    audit = importlib.import_module("report")
    for arm in ARMS:
        reports[arm] = audit.build_report(root / arm, require_complete=True)
        save(root / arm / "report.json", reports[arm])
        if not reports[arm]["audit_passed"]:
            raise ValueError("Failed final audit for " + arm + ": " + str(reports[arm]["audit_errors"]))
    paired = []
    def score(value, baseline):
        return 100 - 100 / 3 * (value["tokens"] / baseline["tokens"] + value["raw_heartbeats"] / baseline["raw_heartbeats"])
    for row in ROWS:
        values, initial = {}, None
        for arm in ARMS:
            folder = d.folder(root / arm, row)
            seed = read(folder / "initial-state.json")
            if initial is not None and seed != initial:
                raise ValueError("Paired initial states differ")
            initial = seed
            summary, state = read(folder / "summary.json"), read(folder / "state.json")
            history = state["exploration"]["history"]
            lookups = action_memory.lookups(history)
            candidates = {k:v for k,v in state["exploration"]["candidates"].items() if v.get("step", 0)>0}
            valid = {v["sha256"] for v in candidates.values() if v["valid"]}
            initial_score = score(seed["best"], seed["baseline"])
            final_score = score(summary["final"], seed["baseline"])
            changed = summary["selected"]["sha256"] != seed["best"]["sha256"]
            first = next((h["cost_usd_after"] for h in history if h.get("candidate_id") and
                candidates[h["candidate_id"]]["valid"] and candidates[h["candidate_id"]]["rank_numerator"] < seed["best"]["rank_numerator"]), None)
            values[arm] = {"seed_score": initial_score, "final_score": final_score,
                "measured_delta": final_score-initial_score, "source_changed": changed,
                "delta_for_changed_source": final_score-initial_score if changed else 0,
                "cost_usd": summary["cost_usd"], "calls": summary["calls"], "evaluated_candidates": len(candidates),
                "unique_valid_candidates": len(valid), "lookup_calls": sum(v["count"] for v in lookups.values()),
                "repeated_lookups": sum(v["count"]-1 for v in lookups.values()),
                "first_improvement_cost_usd": first, "selected_sha256": summary["selected"]["sha256"]}
        paired.append({"row": row, **values, "treatment_minus_control": values["treatment"]["delta_for_changed_source"]-values["control"]["delta_for_changed_source"]})
    total = sum((Decimal(v["known_total_usd"]) for v in reports.values()), Decimal(0))
    if total > 12:
        raise ValueError("Aggregate spend exceeds approved $12")
    output = {"at": now(), "audit_passed": True, "total_cost_usd": str(total), "paired": paired,
        "mean_treatment_minus_control": sum(x["treatment_minus_control"] for x in paired)/len(paired),
        "note": "Exploratory six-pair pilot, one trajectory each. Same-source fresh-HB noise is reported but not counted as source improvement."}
    save(root / "comparison.json", output)
    print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "preflight", "run", "report"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--environment-repo", type=Path)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "prepare":
        if args.environment_repo is None:
            parser.error("prepare requires --environment-repo")
        prepare(root, args.environment_repo.resolve())
    elif args.command == "preflight":
        preflight(root)
    elif args.command == "run":
        if args.key_file is None:
            parser.error("run requires an explicit --key-file")
        run(root, args.key_file)
    else:
        compare(root)


if __name__ == "__main__":
    main()
