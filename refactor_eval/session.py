"""Durable checkpoints, acceptance policy and final candidate selection."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
from pathlib import Path
import re
import os

from .lean import LeanEvaluator, read_text, sha256, validate_template
from .tokens import TOKENIZER_ID, proof_tokens, validate_declaration


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        stream.write(json_text(value))
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def positive_number(value, label, *, integer=False):
    if (type(value) not in ((int,) if integer else (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError(f"{label} must be a positive {'integer' if integer else 'number'}")
    return value


def valid_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def load_config(path: Path) -> tuple[dict, str]:
    path = path.resolve()
    raw = json.loads(read_text(path))
    def file(key, source=raw):
        return read_text((path.parent / source[key]).resolve())
    statement = file("statement_file").rstrip("\n")
    baseline = file("baseline_file")
    validate_declaration(baseline, statement)
    proof_tokens(baseline, statement)
    environments = []
    for entry in raw["environments"]:
        env = dict(entry)
        env["id"] = valid_id(env["id"])
        env["project"] = str((path.parent / env["project"]).resolve())
        env["template"] = file("template_file", env)
        del env["template_file"]
        validate_template(env["template"])
        if not isinstance(env.get("toolchain"), str) or not env["toolchain"].strip():
            raise ValueError("Every environment needs an explicit toolchain pin")
        env.setdefault("command", ["lake", "env", "lean"])
        if not isinstance(env["command"], list) or not env["command"] or any(
                not isinstance(part, str) or not part for part in env["command"]):
            raise ValueError("command must be a nonempty argv list, never a shell string")
        env["timeout_seconds"] = positive_number(env.get("timeout_seconds", 180), "timeout_seconds")
        environments.append(env)
    ids = [env["id"] for env in environments]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("At least one environment is required; environment IDs must be unique")
    scoring = {"token_weight": 0.5, "heartbeat_weight": 0.5,
               "minimum_gain": 0.0, "require_non_regression": False,
               **raw.get("scoring", {})}
    if set(scoring) != {"token_weight", "heartbeat_weight", "minimum_gain", "require_non_regression"}:
        raise ValueError("Unknown scoring option")
    for key in ("token_weight", "heartbeat_weight", "minimum_gain"):
        value = scoring[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} must be finite and nonnegative")
    weight_sum = scoring["token_weight"] + scoring["heartbeat_weight"]
    if not math.isfinite(weight_sum) or weight_sum <= 0:
        raise ValueError("Metric weights must have a finite positive sum")
    if type(scoring["require_non_regression"]) is not bool:
        raise ValueError("require_non_regression must be a boolean")
    primary = raw.get("scoring_environment", ids[0])
    if primary not in ids:
        raise ValueError("scoring_environment must name a configured environment")
    config = {"problem_id": valid_id(raw["problem_id"]), "name": raw["name"],
              "statement": statement, "environments": environments,
              "scoring_environment": primary, "scoring": scoring,
              "checkpoint_runs": positive_number(raw.get("checkpoint_runs", 1), "checkpoint_runs", integer=True),
              "final_runs": positive_number(raw.get("final_runs", 3), "final_runs", integer=True),
              "tokenizer": TOKENIZER_ID}
    if not isinstance(config["name"], str) or not config["name"]:
        raise ValueError("name must be the fully qualified target declaration")
    return config, baseline


def validate_result(result: dict, environment_ids: list[str], runs: int) -> None:
    """Do not rank malformed, partial or non-finite successful measurements."""
    if not isinstance(result, dict) or type(result.get("valid")) is not bool:
        raise ValueError("Evaluator did not return a validity flag")
    if not result["valid"]:
        return
    if type(result.get("tokens")) is not int or result["tokens"] <= 0:
        raise ValueError("Invalid measured token count")
    if set(result.get("environments", {})) != set(environment_ids):
        raise ValueError("Missing or unexpected evaluation environment")
    for row in result["environments"].values():
        hb = row.get("median_heartbeats")
        if (row.get("valid") is not True or type(hb) not in (int, float)
                or not math.isfinite(hb) or hb < 0):
            raise ValueError("Missing or invalid heartbeats")
        measures = [r["measurement"]["scaled"] for r in row.get("runs", []) if "measurement" in r]
        if len(measures) != runs:
            raise ValueError("Incomplete heartbeat repetitions")
        import statistics
        if statistics.median(measures) != hb:
            raise ValueError("Median does not match measured heartbeats")


def assess(result: dict, baseline: dict, config: dict, *, original=False) -> dict:
    if not result["valid"] or not baseline["valid"]:
        return {"eligible": False, "score": None, "reason": "verification_failed"}
    primary = config["scoring_environment"]
    base_hb = baseline["environments"][primary]["median_heartbeats"]
    hb = result["environments"][primary]["median_heartbeats"]
    # A zero scaled baseline has no relative improvement headroom. Penalize
    # positive values against one scaled heartbeat, avoiding division by zero.
    token_gain = 1 - result["tokens"] / baseline["tokens"]
    heartbeat_gain = (base_hb - hb) / max(base_hb, 1)
    policy = config["scoring"]
    total = policy["token_weight"] + policy["heartbeat_weight"]
    score = 100 * ((policy["token_weight"] / total) * token_gain + (policy["heartbeat_weight"] / total) * heartbeat_gain)
    reason = "eligible"
    if not original and score <= policy["minimum_gain"]:
        reason = "insufficient_gain"
    if policy["require_non_regression"] and (
            result["tokens"] > baseline["tokens"] or any(
                row["median_heartbeats"] > baseline["environments"][key]["median_heartbeats"]
                for key, row in result["environments"].items())):
        reason = "metric_regression"
    return {"eligible": original or reason == "eligible", "score": score, "reason": reason,
            "token_reduction_pct": 100 * token_gain, "heartbeat_reduction_pct": 100 * heartbeat_gain}


def implementation_hash() -> str:
    root = Path(__file__).parent
    return sha256(b"".join(p.read_bytes() for p in sorted(root.glob("*.py"))))


class Session:
    def __init__(self, directory: Path | str, evaluator=None):
        self.directory = Path(directory).resolve()
        self.evaluator = evaluator or LeanEvaluator()

    @contextmanager
    def _locked(self):
        with (self.directory / "session.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("Another process owns this evaluation session") from error
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _save(self, manifest):
        manifest["updated_at"] = now()
        write_json(self.directory / "manifest.json", manifest)

    def _load(self, *, allow_pending=False):
        manifest = json.loads(read_text(self.directory / "manifest.json"))
        if manifest["schema_version"] != 1:
            raise ValueError("Unsupported manifest schema")
        if manifest["implementation_sha256"] != implementation_hash():
            raise ValueError("Evaluator code changed; initialize a new run to avoid mixing measurements")
        if sha256(json_text(manifest["config"])) != manifest["config_sha256"]:
            raise ValueError("Frozen configuration changed")
        for candidate in manifest["candidates"]:
            code = read_text(self.directory / candidate["source"])
            if sha256(code) != candidate["sha256"]:
                raise ValueError(f"Candidate snapshot changed: {candidate['id']}")
        if manifest["selection"]:
            selection = manifest["selection"]
            if sha256((self.directory / selection["source"]).read_bytes()) != selection["winner"]["sha256"]:
                raise ValueError("Selected artifact changed")
        if manifest["pending"] and not allow_pending:
            raise ValueError("Interrupted measurement; inspect artifacts and run recover before continuing")
        return manifest

    def _check_environment(self, manifest):
        for env in manifest["config"]["environments"]:
            if self.evaluator.fingerprint(env) != manifest["fingerprints"][env["id"]]:
                raise ValueError(f"Evaluation environment changed: {env['id']}; start a new run")

    def _candidate(self, manifest, code, parent_id, note, candidate_id=None):
        candidate_id = candidate_id or f"candidate-{len(manifest['candidates']):04d}"
        filename = f"candidates/{candidate_id}.lean"
        path = self.directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(code)
        row = {"id": candidate_id, "parent_id": parent_id, "note": note,
               "source": filename, "sha256": sha256(code), "created_at": now(), "evaluations": []}
        manifest["candidates"].append(row)
        return row

    def _measure(self, manifest, candidate, phase, environments, runs, batch=None):
        index = len(candidate["evaluations"]) + 1
        artifact_path = f"evaluations/{candidate['id']}/{index:03d}-{phase}"
        pending = {"candidate_id": candidate["id"], "phase": phase, "batch": batch,
                   "artifacts": artifact_path, "started_at": now()}
        manifest["pending"] = pending
        self._save(manifest)  # A killed worker leaves a durable pending record.
        result = {"valid": False, "tokens": None, "environments": {}}
        try:
            code = read_text(self.directory / candidate["source"])
            result = self.evaluator.evaluate(code, manifest["config"], environments,
                                             self.directory / artifact_path, runs)
            validate_result(result, [env["id"] for env in environments], runs)
            self._check_environment(manifest)
        except Exception as error:
            if not isinstance(result, dict):
                result = {"tokens": None, "environments": {}}
            try:
                json_text(result)
            except (TypeError, ValueError):
                result = {"tokens": None, "environments": {}}
            result.update(valid=False, error={"kind": "evaluation_error", "message": str(error)})
        evaluation = {**pending, "finished_at": now(), "result": result}
        candidate["evaluations"].append(evaluation)
        manifest["pending"] = None
        self._save(manifest)
        return evaluation

    def initialize(self, config_path: Path | str) -> dict:
        config, baseline = load_config(Path(config_path))
        fingerprints = {env["id"]: self.evaluator.fingerprint(env) for env in config["environments"]}
        self.directory.mkdir(parents=True, exist_ok=False)
        with self._locked():
            manifest = {"schema_version": 1, "created_at": now(), "config": config,
                        "config_sha256": sha256(json_text(config)), "implementation_sha256": implementation_hash(),
                        "fingerprints": fingerprints, "candidates": [], "pending": None,
                        "incumbent": "baseline", "selection": None, "finalizations": [], "events": []}
            baseline_row = self._candidate(manifest, baseline, None, "Original proof", "baseline")
            envs = [env for env in config["environments"] if env["id"] == config["scoring_environment"]]
            measurement = self._measure(manifest, baseline_row, "checkpoint", envs, config["checkpoint_runs"])
            measurement["assessment"] = assess(measurement["result"], measurement["result"], config, original=True)
            self._save(manifest)
            if not measurement["result"]["valid"]:
                raise ValueError("Baseline verification failed; see manifest.json and evaluation logs")
            return manifest

    def status(self) -> dict:
        with self._locked():
            return self._load(allow_pending=True)

    def _baseline(self, manifest):
        result = manifest["candidates"][0]["evaluations"][0]["result"]
        if not result["valid"]:
            raise ValueError("Baseline is unverified; fix the problem/environment and initialize a new run")
        return result

    def checkpoint(self, code: str, *, parent_id: str | None = None, note: str = "") -> dict:
        if not isinstance(code, str) or not isinstance(note, str):
            raise ValueError("Candidate code and note must be strings")
        with self._locked():
            manifest = self._load()
            baseline = self._baseline(manifest)
            self._check_environment(manifest)
            parent_id = parent_id or manifest["incumbent"]
            if parent_id not in {row["id"] for row in manifest["candidates"]}:
                raise ValueError("Unknown parent_id")
            if any(batch["status"] == "running" for batch in manifest["finalizations"]):
                raise ValueError("Interrupted finalization; run recover first")
            manifest["selection"] = None  # New candidates invalidate any published selection.
            candidate = self._candidate(manifest, code, parent_id, note)
            config = manifest["config"]
            environments = [env for env in config["environments"] if env["id"] == config["scoring_environment"]]
            evaluation = self._measure(manifest, candidate, "checkpoint", environments, config["checkpoint_runs"])
            evaluation["assessment"] = assess(evaluation["result"], baseline, config)
            # Recompute from metrics: the previous stored score is not an authority.
            ranked = []
            for row in manifest["candidates"]:
                check = row["evaluations"][0]
                assessment = assess(check["result"], baseline, config, original=row["id"] == "baseline")
                if assessment["eligible"]:
                    ranked.append((assessment["score"], row))
            # Stable insertion order resolves exact ties; baseline is first.
            winner = max(ranked, key=lambda item: item[0])[1]
            evaluation["accepted"] = winner["id"] == candidate["id"]
            manifest["incumbent"] = winner["id"]
            self._save(manifest)
            return {"candidate_id": candidate["id"], "incumbent": winner["id"], **evaluation}

    def recover(self) -> dict:
        with self._locked():
            manifest = self._load(allow_pending=True)
            pending = manifest["pending"]
            if pending:
                candidate = next(row for row in manifest["candidates"] if row["id"] == pending["candidate_id"])
                candidate["evaluations"].append({**pending, "finished_at": now(), "result": {
                    "valid": False, "tokens": None, "environments": {},
                    "error": {"kind": "interrupted", "message": "Worker did not finish; never treated as measured"}}})
                manifest["pending"] = None
            for batch in manifest["finalizations"]:
                if batch["status"] == "running":
                    batch["status"] = "interrupted"
            manifest["selection"] = None
            manifest["events"].append({"type": "recovered", "at": now(), "pending": pending})
            self._save(manifest)
            return manifest

    def finalize(self) -> dict:
        with self._locked():
            manifest = self._load()
            self._baseline(manifest)
            self._check_environment(manifest)
            if any(row["status"] == "running" for row in manifest["finalizations"]):
                raise ValueError("Interrupted finalization; run recover first")
            config = manifest["config"]
            batch = {"id": f"final-{len(manifest['finalizations']) + 1:03d}", "status": "running", "started_at": now()}
            manifest["finalizations"].append(batch)
            manifest["selection"] = None
            self._save(manifest)
            ranked = []
            baseline = None
            for candidate in manifest["candidates"]:
                evaluation = self._measure(manifest, candidate, "final", config["environments"], config["final_runs"], batch["id"])
                if candidate["id"] == "baseline":
                    baseline = evaluation["result"]
                    if not baseline["valid"]:
                        batch.update(status="failed", reason="baseline_final_verification_failed", finished_at=now())
                        self._save(manifest)
                        raise ValueError("Final baseline verification failed; no candidate selected")
                assessment = assess(evaluation["result"], baseline, config, original=candidate["id"] == "baseline")
                evaluation["assessment"] = assessment
                ranked.append({"candidate_id": candidate["id"], "sha256": candidate["sha256"],
                               "evaluation": evaluation["artifacts"], **assessment})
                self._save(manifest)
            # Check once more immediately before publishing a final result.
            self._check_environment(manifest)
            eligible = [row for row in ranked if row["eligible"]]
            winner = max(eligible, key=lambda row: row["score"])
            candidate = next(row for row in manifest["candidates"] if row["id"] == winner["candidate_id"])
            code = read_text(self.directory / candidate["source"])
            if sha256(code) != winner["sha256"]:
                raise ValueError("Selected source changed during finalization")
            folder = self.directory / "selections" / batch["id"]
            folder.mkdir(parents=True, exist_ok=False)
            (folder / "selected.lean").write_text(code, encoding="utf-8")
            selection = {"batch": batch["id"], "selected_at": now(), "winner": winner,
                         "source": str((folder / "selected.lean").relative_to(self.directory)),
                         "ranking": sorted(ranked, key=lambda row: (not row["eligible"], -(row["score"] or 0))),
                         "scope": "Local evaluation in configured environments; not an official Arena score"}
            write_json(folder / "selection.json", selection)
            batch.update(status="complete", finished_at=now())
            manifest["selection"] = selection
            self._save(manifest)  # This pointer alone declares the selected artifact current.
            return selection

    def feedback(self) -> dict:
        """Small model-neutral protocol. Called before each generation step."""
        with self._locked():
            manifest = self._load()
            self._baseline(manifest)
            incumbent = next(row for row in manifest["candidates"] if row["id"] == manifest["incumbent"])
            latest = manifest["candidates"][-1]
            return {"problem_id": manifest["config"]["problem_id"], "statement": manifest["config"]["statement"],
                    "scoring": manifest["config"]["scoring"], "candidate_count": len(manifest["candidates"]) - 1,
                    "baseline": manifest["candidates"][0]["evaluations"][0]["result"],
                    "incumbent_id": incumbent["id"], "incumbent_code": read_text(self.directory / incumbent["source"]),
                    "latest_candidate_id": latest["id"], "latest_code": read_text(self.directory / latest["source"]),
                    "latest_evaluation": latest["evaluations"][-1]}


def run_search(session: Session, propose, *, max_attempts: int) -> dict:
    """Each returned candidate is evaluated durably before propose is called again.

    propose(feedback) returns {code, parent_id?, note?}, or None to stop.
    The callback may wrap any API/agent. It cannot supply scores or pick a winner.
    """
    positive_number(max_attempts, "max_attempts", integer=True)
    for _ in range(max_attempts):
        candidate = propose(session.feedback())
        if candidate is None:
            break
        if not isinstance(candidate, dict) or "code" not in candidate:
            raise ValueError("Agent must return an object with code, or null to stop")
        session.checkpoint(candidate["code"], parent_id=candidate.get("parent_id"), note=candidate.get("note", ""))
    return session.finalize()
