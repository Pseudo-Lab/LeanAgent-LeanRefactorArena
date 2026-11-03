"""Freeze historical proof sources, then seed only after current Lean checks.

Historical scores, costs and evaluation caches are never imported. A public
manifest is provenance for a source, not authority that the proof still passes.
"""
from pathlib import Path

from lean_agent import artifacts as a, harness as h
from policy import validate_declaration
from evaluation_cache import EvaluationCache

SEED_ID = "seed-best"
POLICY = "candidate-cache-final-compatibility-memory-warm-start-v2"


def snapshot(path, problem, *, reason=None):
    value = {"schema_version": 1, "problem_sha256": a.sha(a.canonical(problem)),
             "candidate": None, "reason": reason or "no_historical_result"}
    if path is None:
        return value
    path = Path(path)
    manifest = a.read(path)
    if (manifest.get("schemaVersion") != 1 or manifest.get("auditPassed") is not True
            or manifest.get("datasetSha256") != problem["dataset_sha256"]):
        raise ValueError("Warm-start manifest must be audited and match the dataset")
    rows = manifest["problems"]
    if len({row["row"] for row in rows}) != len(rows):
        raise ValueError("Duplicate warm-start problem rows")
    found = next((row for row in rows if row["row"] == problem["row"]), None)
    value["manifest_sha256"] = a.sha(path.read_bytes())
    if found is None:
        return value
    versions = found["versions"]
    if (found["name"] != problem["name"] or found["source"] != problem["source"]
            or len(versions) != len(problem["environments"])
            or {v["environment"] for v in versions} != set(problem["environments"])
            or any(v["status"] != "pass" for v in versions)):
        raise ValueError("Warm-start problem identity or required versions differ")
    value.update(reason="historical_best_requires_current_verification", candidate={
        "code": found["proof"], "sha256": found["candidateHash"], "run_id": found["runId"],
        "versions": versions})
    validate(value, problem)
    return value


def validate(seed, problem):
    if seed.get("schema_version") != 1 or seed.get("problem_sha256") != a.sha(a.canonical(problem)):
        raise ValueError("Warm-start frozen problem identity differs")
    candidate = seed["candidate"]
    if candidate is not None:
        if a.sha(candidate["code"]) != candidate["sha256"]:
            raise ValueError("Warm-start proof hash differs")
        validate_declaration(candidate["code"], problem["statement"])
        versions = candidate["versions"]
        if (len(versions) != len(problem["environments"])
                or {v["environment"] for v in versions} != set(problem["environments"])
                or any(v["status"] != "pass" for v in versions)):
            raise ValueError("Warm-start required versions differ")


def seed_state(state, seed, problem, primary, compatibility):
    validate(seed, problem)
    if state["step"] or state["calls"] or state["cost_usd"] != "0" or "portfolio" in state:
        raise ValueError("Warm-start requires an unbilled, non-portfolio initial state")
    if (not compatibility["valid"] or set(compatibility["environments"]) != set(problem["environments"])
            or not all(value["valid"] for value in compatibility["environments"].values())):
        raise ValueError("Warm-start failed current required-version verification; paid dispatch blocked")
    measured = h.metrics(primary)
    if measured is None or len(measured["raw_samples"]) != 3:
        raise ValueError("Warm-start requires three current primary measurements")
    if set(primary["environments"]) != {problem["environments"][0]}:
        raise ValueError("Warm-start primary environment differs")
    if any(value.get("cache") for value in primary["environments"].values()):
        raise ValueError("Warm-start primary measurements must be fresh")
    source = seed["candidate"]
    candidate = h.candidate(source["code"], primary, state["baseline"])
    memory = state["exploration"]
    memory["candidates"][SEED_ID] = {**candidate, "parent_id": "c000", "strategy": "verified historical best",
        "step": 0, "valid": True, "feedback": None, "provenance": {
            "run_id": source["run_id"], "manifest_sha256": seed["manifest_sha256"],
            "verification": "current primary fresh x3 and all required versions"}}
    improved = h.ranking(candidate) < h.ranking(state["best"])
    if improved:
        state["best"] = candidate
        memory["best_candidate_id"] = SEED_ID
    state["warm_start"] = {"candidate_id": SEED_ID, "sha256": source["sha256"],
                           "run_id": source["run_id"], "incumbent": improved}
    return state


def audit(folder):
    """Reconstruct the zero-cost seed from frozen input and current receipts."""
    folder = Path(folder)
    seed = a.read(folder / "input/warm-start.json")
    problem = a.read(folder / "input/problem.json")
    validate(seed, problem)
    if seed["candidate"] is None:
        return
    config = a.read(folder / "input/config.json")
    state = h.initial_state(problem, a.read(folder / "baseline/result.json"), config)
    code = seed["candidate"]["code"]
    for directory, options in (("primary", {"repetitions": 3, "fresh": True}),
                               ("compatibility", {"repetitions": 1, "all_versions": True})):
        expected = {"candidate_sha256": a.sha(code), "problem": problem, "options": options}
        path = folder / "warm-start" / directory
        if a.read(path / "evaluation-request.json") != expected:
            raise ValueError("Warm-start evaluation receipt differs")
        result = a.read(path / "result.json")
        for env, value in result["environments"].items():
            EvaluationCache(folder.parents[1] / "evaluation-cache").audit_reuse(
                value, problem=problem, code=code, environment=env)
            for record in value["runs"]:
                for field in ("source", "log"):
                    if a.sha((path / env / record[field]).read_bytes()) != record[field + "_sha256"]:
                        raise ValueError("Warm-start compiler evidence hash differs")
    seed_state(state, seed, problem, a.read(folder / "warm-start/primary/result.json"),
               a.read(folder / "warm-start/compatibility/result.json"))
    if a.read(folder / "initial-state.json") != state:
        raise ValueError("Warm-start initial state differs from measured evidence")
    saved = a.read(folder / "state.json")
    if saved["exploration"]["candidates"].get(SEED_ID) != state["exploration"]["candidates"][SEED_ID]:
        raise ValueError("Warm-start candidate changed or disappeared during exploration")
