"""Serial propose/verify/select experiment. Replay calls neither the model nor Lean."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys

from . import diagnostics, models, status
from .artifacts import canonical, inventory, read, sha as digest, write
from .evaluator.lean import LeanEvaluator, validate_template
from .evaluator.tokens import TOKENIZER_ID, proof_body

BASE = Path(__file__).resolve().parent
CODE_FILES = ("__init__.py", "__main__.py", "harness.py", "models.py", "provenance.json",
              "artifacts.py", "preflight.py", "diagnostics.py", "status.py",
              "evaluator/__init__.py", "evaluator/lean.py", "evaluator/tokens.py", "evaluator/provenance.json")
SELECTION = "ratio-sum-v1: tokens*baseline_raw + raw*baseline_tokens; then tokens, declaration SHA256"


def positive(value):
    return type(value) is int and value > 0


def load_config(path):
    config = read(path)
    if config.get("schema_version") != 1:
        raise ValueError("Expected config schema_version 1")
    limits, lean, model = config["limits"], config["lean"], config["model"]
    if set(model) - {"backend", "responses", "id", "provider", "max_tokens", "temperature", "seed", "timeout_seconds"}:
        raise ValueError("Unexpected model setting; credentials belong in environment variables")
    for key in ("max_calls", "max_proof_characters", "max_feedback_characters", "max_request_characters"):
        if not positive(limits[key]):
            raise ValueError("Expected positive integer: " + key)
    if not positive(lean["repetitions"]) or lean["repetitions"] % 2 != 1:
        raise ValueError("Lean repetitions must be a positive odd integer")
    if not positive(lean["timeout_seconds"]):
        raise ValueError("Expected positive Lean timeout")
    if not lean["command"] or not all(isinstance(x, str) and x for x in lean["command"]):
        raise ValueError("Lean command must be an argument list")
    if model["backend"] not in ("fixture", "openrouter"):
        raise ValueError("Unknown model backend")
    if model["backend"] == "openrouter":
        for key in ("id", "provider"):
            if not isinstance(model[key], str) or not model[key] or "REPLACE" in model[key]:
                raise ValueError("Set explicit model " + key)
        if not positive(model["max_tokens"]) or not positive(model["timeout_seconds"]):
            raise ValueError("Set positive model token and timeout limits")
        if type(model["temperature"]) not in (int, float) or not 0 <= model["temperature"] <= 2:
            raise ValueError("Invalid temperature")
    paths = {key: (path.parent / config[key]).resolve() for key in ("problem", "template", "project", "prompt")}
    if model["backend"] == "fixture":
        paths["responses"] = (path.parent / model["responses"]).resolve()
        responses = read(paths["responses"])
        if not isinstance(responses, list) or len(responses) < limits["max_calls"] or not all(isinstance(s, str) for s in responses):
            raise ValueError("Fixture requires one response string for every call")
    validate_template(paths["template"].read_text())
    problem = read(paths["problem"])
    for key in ("id", "name", "statement", "reference"):
        if not isinstance(problem[key], str) or not problem[key]:
            raise ValueError("Missing problem field: " + key)
    proof_body(problem["reference"], problem["statement"])
    # v1 intentionally supports core Lean only. Do not pretend an uncopied
    # dependency tree is frozen; add a proper prepared-environment adapter later.
    if (paths["project"] / "lake-manifest.json").exists():
        if read(paths["project"] / "lake-manifest.json").get("packages"):
            raise ValueError("v1 supports dependency-free Lean projects only")
    return config, paths


def git_metadata(directory):
    """Record checkout provenance when available; installed packages need no Git checkout."""
    def git(*args):
        return subprocess.check_output(["git", "-C", str(directory), *args], stderr=subprocess.DEVNULL)
    try:
        return {"head": git("rev-parse", "HEAD").decode().strip(),
                "branch": git("branch", "--show-current").decode().strip(),
                "tracked_diff_sha256": digest(git("diff", "HEAD", "--", "."))}
    except (OSError, subprocess.CalledProcessError):
        return None


def snapshot_code(output):
    for relative in CODE_FILES:
        dest = output / "code/lean_agent" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / relative, dest)
    shutil.copyfile(BASE / "__main__.py", output / "code/replay.py")


def snapshot(output, config_path, paths):
    for key, filename in {"problem": "problem.json", "template": "context.lean.in", "prompt": "prompt.txt",
                          "responses": "responses.json"}.items():
        if key in paths:
            dest = output / "input" / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paths[key], dest)
    shutil.copyfile(config_path, output / "input/config.json")
    project = output / "input/project"
    project.mkdir()
    for name in ("lean-toolchain", "lakefile.toml", "lakefile.lean", "lake-manifest.json"):
        if (paths["project"] / name).exists():
            shutil.copyfile(paths["project"] / name, project / name)
    manifest = {"schema_version": 2, "created_at": datetime.now(timezone.utc).isoformat(),
                "run_directory": str(output),
                "backend": read(output / "input/config.json")["model"]["backend"],
                "git": git_metadata(BASE),
                "host": {"python": sys.version, "platform": platform.platform()},
                "tokenizer": TOKENIZER_ID, "selection": SELECTION,
                "files": {name: value for name, value in inventory(output).items()
                          if name.startswith(("code/", "input/"))}}
    return manifest


def metrics(result):
    if not result["valid"]:
        return None
    rows = list(result["environments"].values())
    if len(rows) != 1 or not rows[0]["valid"]:
        raise ValueError("Expected one valid environment")
    raw = [r["measurement"]["raw"] for r in rows[0]["runs"] if "measurement" in r]
    if not raw or any(type(x) is not int or x < 0 for x in raw):
        raise ValueError("Missing raw heartbeat measurements")
    if not positive(result["tokens"]):
        raise ValueError("Invalid proof-token measurement")
    return {"tokens": result["tokens"], "raw_heartbeats": int(statistics.median(raw)), "raw_samples": raw}


def environment_failed(result):
    return any(row.get("error", {}).get("kind") == "environment"
               for row in result.get("environments", {}).values() if row.get("error"))


def candidate(code, result, baseline):
    value = metrics(result)
    if value is None:
        return None
    return {"code": code, "sha256": digest(code), **value,
            "rank_numerator": value["tokens"] * baseline["raw_heartbeats"] + value["raw_heartbeats"] * baseline["tokens"]}


def ranking(value):
    return value["rank_numerator"], value["tokens"], value["sha256"]


def initial_state(problem, result):
    baseline = metrics(result)
    if baseline is None or baseline["raw_heartbeats"] <= 0:
        raise ValueError("Original must verify with positive baseline measurements")
    return {"step": 0, "calls": 0, "cost_usd": "0", "unknown_cost": False,
            "baseline": {k: baseline[k] for k in ("tokens", "raw_heartbeats")},
            "best": candidate(problem["reference"], result, baseline), "latest": None}


def make_request(state, problem, config, prompt):
    latest = json.loads(canonical(state["latest"]))
    if latest and latest["feedback"].get("metrics"):
        latest["feedback"]["metrics"].pop("raw_samples", None)
    packet = {"problem": problem, "baseline": state["baseline"],
              "best": {k: v for k, v in state["best"].items() if k != "raw_samples"}, "latest": latest,
              "step": state["step"] + 1,
              "remaining_calls": config["limits"]["max_calls"] - state["calls"]}
    body = models.payload([{"role": "system", "content": prompt},
                           {"role": "user", "content": canonical(packet)}], config["model"])
    if len(canonical(body)) > config["limits"]["max_request_characters"]:
        raise ValueError("Request exceeds max_request_characters")
    return body


def parse_proof(raw, problem, limit):
    content = models.receipt(raw)["content"]
    if content is None or len(content) > limit * 2:
        raise ValueError("Missing or oversized model content")
    diagnostics.validate_response_text(content)
    # Use the same strict JSON parser for model output and saved configuration.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate model key")
            result[key] = value
        return result
    try:
        value = json.loads(content, object_pairs_hook=unique)
    except RecursionError as exc:
        raise ValueError("Model JSON exceeds parser nesting capacity") from exc
    if not isinstance(value, dict) or set(value) != {"proof"}:
        raise ValueError("Expected exactly one proof field")
    proof = value["proof"]
    if not isinstance(proof, str) or not proof.strip() or len(proof) > limit:
        raise ValueError("Invalid or oversized proof")
    try:
        proof.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Proof contains invalid Unicode") from exc
    return problem["statement"] + " := " + proof.strip() + "\n"


def feedback(result, rejection, limit, run_directory):
    if rejection:
        return {"status": "response_rejected", "valid": False, "details": rejection[:limit]}
    details = {"error": result.get("error"), "environments": {
        key: row.get("error") for key, row in result.get("environments", {}).items()}}
    return {"status": "environment_failed" if environment_failed(result) else "verified" if result["valid"] else "proof_rejected",
            "valid": result["valid"], "metrics": metrics(result),
            "details": canonical(details).replace(run_directory, "<RUN>")[:limit]}


def advance(state, raw, code, result, rejection, baseline, config, run_directory, diagnosis=None):
    state = json.loads(canonical(state))
    bill = models.receipt(raw)
    state["step"] += 1
    state["calls"] += 1
    state["unknown_cost"] = bill["cost_usd"] is None
    if bill["cost_usd"] is not None:
        state["cost_usd"] = str(Decimal(state["cost_usd"]) + Decimal(bill["cost_usd"]))
    proposal = candidate(code, result, baseline) if result else None
    if proposal and ranking(proposal) < ranking(state["best"]):
        state["best"] = proposal
    limit = config["limits"]["max_feedback_characters"]
    state["latest"] = {"code": code, "feedback": diagnostics.enrich(
        feedback(result, rejection, limit, run_directory), diagnosis, limit, run_directory)}
    return state


def seal(output):
    write(output / "artifacts.json", inventory(output))


def stopping_reason(state, problem, config, prompt):
    if state["unknown_cost"]:
        return "unknown_cost"
    if state["latest"] and state["latest"]["feedback"]["status"] == "environment_failed":
        return "environment_failed"
    if state["calls"] >= config["limits"]["max_calls"]:
        return "call_limit"
    try:
        make_request(state, problem, config, prompt)
    except ValueError:
        return "context_limit"
    raise ValueError("Recorded run ended before a stopping condition")


def summarize(state, baseline, final, config, stop):
    measured = metrics(final)
    return {"status": "completed" if final["valid"] and stop in ("call_limit", "context_limit") else "stopped",
            "stop_reason": stop, "backend": config["model"]["backend"],
            "state": state, "baseline": baseline, "final": measured,
            "final_valid": final["valid"], "official_evaluation": False,
            "final_median_matches_selection": measured is not None and all(
                measured[k] == state["best"][k] for k in ("tokens", "raw_heartbeats")),
            "final_samples_match_selection": measured is not None and measured["raw_samples"] == state["best"]["raw_samples"]}


def run(config_path, output, evaluator=None, *, check_only=False, query=None):
    if output.exists() or output.is_symlink():
        raise FileExistsError("Refusing to reuse an existing run directory: " + str(output))
    config_path, output = config_path.resolve(), output.resolve()
    output.mkdir(parents=True)
    progress = status.Progress(status.Journal(output))
    recorder = diagnostics.Recorder(output)
    evaluator = evaluator or LeanEvaluator()
    outcome = {"schema_version": 1, "status": "failed", "model_requests": 0}

    def evaluate(code, folder, stage, source, **details):
        progress.enter(stage, **details)
        result = evaluator.evaluate(code, problem, [environment], folder, config["lean"]["repetitions"])
        write(folder / "result.json", result)
        recorder.evaluated(result, folder)
        report = recorder.records[-1]["path"]
        progress.failure_report = report
        paths = [folder / "result.json", report]
        verified = None
        if result["valid"]:
            paths.append(source)
            verified = {"sha256": digest(code), "source": str(source.relative_to(output)), "stage": stage}
        progress.finish("passed" if result["valid"] else "failed", paths, verified)
        return result

    try:
        progress.enter("setup")
        snapshot_code(output)
        progress.finish()
        progress.enter("config")
        config, paths = load_config(config_path)
        if config["model"]["backend"] == "openrouter":
            import os
            if not os.environ.get("OPENROUTER_API_KEY"):
                raise ValueError("Export OPENROUTER_API_KEY before running a live experiment")
        manifest = snapshot(output, config_path, paths)
        config = read(output / "input/config.json")
        problem = read(output / "input/problem.json")
        prompt = (output / "input/prompt.txt").read_text()
        environment = {"id": "fixed", "project": str(output / "input/project"),
                       "template": (output / "input/context.lean.in").read_text(),
                       **{key: config["lean"][key] for key in ("toolchain", "command", "timeout_seconds")}}
        fixtures = read(output / "input/responses.json") if config["model"]["backend"] == "fixture" else None
        outcome["backend"] = config["model"]["backend"]
        progress.finish(paths=["input/config.json"])
        checked = evaluator.preflight(environment, output, progress)
        outcome["preflight_report"] = "preflight.json"
        report = diagnostics.preflight_diagnosis(checked, output)
        if report:
            recorder.save("preflight", report)
            progress.failure_report = recorder.records[-1]["path"]
        if checked["status"] != "passed":
            outcome["error"] = checked["error"]
            raise ValueError(checked["error"]["message"])
        environment["command"] = checked["effective_command"]
        manifest["environment"] = checked["environment"]
        write(output / "manifest.json", manifest)
        if check_only:
            outcome.update(status="ready", stage="context")
            return outcome
        reference = output / "baseline.lean"
        reference.write_text(problem["reference"], encoding="utf-8")
        baseline_result = evaluate(problem["reference"], output / "baseline", "baseline", reference)
        state = initial_state(problem, baseline_result)
        baseline = metrics(baseline_result)
        write(output / "initial-state.json", state)
        stop = "call_limit"
        for step in range(1, config["limits"]["max_calls"] + 1):
            folder = output / "steps" / f"{step:03}"
            try:
                body = make_request(state, problem, config, prompt)
            except ValueError:
                stop = "context_limit"
                break
            progress.enter("model", attempt=step)
            write(folder / "request.json", body)
            progress.calls += 1  # A dispatched call may have an unknown outcome.
            raw = (query or models.query)(body, config["model"], step, fixtures)
            write(folder / "response.json", raw)
            receipt_error = diagnostics.response(raw, None, folder / "response.json", output)
            progress.finish("failed" if receipt_error else "passed", [folder / "request.json", folder / "response.json"])
            progress.enter("response", attempt=step)
            code, result, rejection = None, None, None
            try:
                code = parse_proof(raw, problem, config["limits"]["max_proof_characters"])
            except (ValueError, TypeError) as exc:
                rejection = str(exc)
            progress.finish("failed" if rejection else "passed", [folder / "response.json"])
            if code is not None:
                source = folder / "candidate.lean"
                source.write_text(code, encoding="utf-8")
                result = evaluate(code, folder / "evaluation", "candidate", source, attempt=step)
            report = diagnostics.step(raw, rejection, result, folder, output)
            if report and report["stage"] == "model":
                recorder.save(f"model-{step:03}", report)
            state = advance(state, raw, code, result, rejection, baseline, config, str(output), report)
            write(folder / "event.json", {"state_after": state, "rejection": rejection})
            if state["unknown_cost"]:
                stop = "unknown_cost"
                break
            if result and environment_failed(result):
                stop = "environment_failed"
                break
        selected = output / "selected.lean"
        selected.write_text(state["best"]["code"], encoding="utf-8")
        final = evaluate(state["best"]["code"], output / "final", "final", selected)
        progress.enter("environment", phase="harness_end")
        if evaluator.fingerprint(environment) != manifest["environment"]:
            raise ValueError("Lean environment changed during the run")
        progress.finish(paths=["environment.json"])
        summary = summarize(state, baseline, final, config, stop)
        write(output / "summary.json", summary)
        progress.enter("replay")
        replayed = replay_records(output)
        progress.finish(paths=["summary.json"])
        outcome.update(status=summary["status"], stage="harness", replay=replayed,
                       selected_sha256=state["best"]["sha256"])
        return summary
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        interrupted = isinstance(exc, (KeyboardInterrupt, SystemExit))
        outcome.update(status="interrupted" if interrupted else "failed", stage=progress.stage,
                       error=outcome.get("error", {"exception_type": type(exc).__name__, "message": str(exc)}))
        write(output / "failure.json", {"status": outcome["status"], "error_type": type(exc).__name__})
        (output / "diagnostic.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8", errors="backslashreplace")
        if not progress.failure_report:
            recorder.save("failure", diagnostics.diagnosis(progress.stage, "unknown", "execution_interrupted" if interrupted else "execution_failed",
                evidence=[diagnostics.evidence(output, output / "diagnostic.log")], excerpt=str(exc)))
        progress.finish("interrupted" if interrupted else "failed", ["failure.json", "diagnostic.log"])
        raise
    finally:
        outcome.update(model_requests=progress.calls, diagnostics=recorder.records)
        write(output / "result.json", outcome)
        progress.journal.seal(outcome["status"])
        seal(output)


def check_artifacts(output):
    files = read(output / "artifacts.json")
    actual = set(inventory(output))
    if set(files) != actual:
        raise ValueError("Artifact inventory differs")
    for name, expected in files.items():
        path = output / name
        if not path.resolve().is_relative_to(output.resolve()) or path.is_symlink() or digest(path.read_bytes()) != expected:
            raise ValueError("Artifact mismatch: " + name)
    if (output / "failure.json").exists():
        raise ValueError("Incomplete run: inspect failure.json and any pending request")


def replay(output):
    output = output.resolve()
    check_artifacts(output)
    if read(output / "result.json")["status"] not in ("completed", "stopped"):
        raise ValueError("Run has no completed execution to replay")
    replayed = replay_records(output)
    lifecycle = read(output / "result.json")
    if (lifecycle["status"] != read(output / "summary.json")["status"]
            or lifecycle.get("selected_sha256") != replayed["selected_sha256"]
            or lifecycle.get("replay") != replayed):
        raise ValueError("Lifecycle result differs from replay")
    observed = status.inspect(output)
    if observed["record_error"] or not observed["sealed"]:
        raise ValueError("Stage journal is inconsistent or unsealed")
    return replayed


def replay_records(output):
    manifest = read(output / "manifest.json")
    for name, expected in manifest["files"].items():
        if digest((output / name).read_bytes()) != expected:
            raise ValueError("Frozen input mismatch: " + name)
    for name in CODE_FILES:
        if digest((BASE / name).read_bytes()) != manifest["files"]["code/lean_agent/" + name]:
            raise ValueError(f"Replay code differs. Use: python3 -B {output}/code/replay.py replay {output}")
    config = read(output / "input/config.json")
    problem = read(output / "input/problem.json")
    prompt = (output / "input/prompt.txt").read_text()
    baseline_result = read(output / "baseline/result.json")
    state = initial_state(problem, baseline_result)
    baseline = metrics(baseline_result)
    if read(output / "initial-state.json") != state:
        raise ValueError("Initial state differs")
    steps = sorted((output / "steps").iterdir()) if (output / "steps").exists() else []
    for index, folder in enumerate(steps, 1):
        if (folder.name != f"{index:03}" or state["unknown_cost"] or index > config["limits"]["max_calls"]
                or state["latest"] and state["latest"]["feedback"]["status"] == "environment_failed"):
            raise ValueError("Invalid step sequence")
        if read(folder / "request.json") != make_request(state, problem, config, prompt):
            raise ValueError("Request does not match the recorded state")
        raw = read(folder / "response.json")
        code, result, rejection = None, None, None
        try:
            code = parse_proof(raw, problem, config["limits"]["max_proof_characters"])
        except (ValueError, TypeError) as exc:
            rejection = str(exc)
        if code is not None:
            if (folder / "candidate.lean").read_text() != code:
                raise ValueError("Candidate differs from model response")
            result = read(folder / "evaluation/result.json")
        report = diagnostics.step(raw, rejection, result, folder, output)
        state = advance(state, raw, code, result, rejection, baseline, config, manifest["run_directory"], report)
        if read(folder / "event.json") != {"state_after": state, "rejection": rejection}:
            raise ValueError("State transition differs")
    summary = read(output / "summary.json")
    if state != summary["state"] or (output / "selected.lean").read_text() != state["best"]["code"]:
        raise ValueError("Final selection differs")
    final = read(output / "final/result.json")
    expected = summarize(state, baseline, final, config, stopping_reason(state, problem, config, prompt))
    if summary != expected:
        raise ValueError("Final summary differs")
    return {"record_replay_passed": True, "model_called": False, "lean_called": False,
            "steps": len(steps), "selected_sha256": state["best"]["sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "check"):
        start = commands.add_parser(name)
        start.add_argument("--config", type=Path, required=True)
        start.add_argument("--output", type=Path, required=True)
    observe = commands.add_parser("status")
    observe.add_argument("run_directory", type=Path)
    observe.add_argument("--json", action="store_true")
    again = commands.add_parser("replay")
    again.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = status.inspect(args.run_directory)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else status.describe(result))
            return 0
        result = (run(args.config, args.output, check_only=args.command == "check")
                  if args.command in ("run", "check") else replay(args.run_directory))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("record_replay_passed") or result.get("status") in ("completed", "ready") else 1


if __name__ == "__main__":
    sys.exit(main())
