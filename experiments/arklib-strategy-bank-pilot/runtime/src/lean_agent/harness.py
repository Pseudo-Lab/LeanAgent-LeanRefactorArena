"""Serial propose/verify/select experiment. Replay calls neither the model nor Lean."""
from __future__ import annotations

import argparse
from itertools import count
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys

from . import accounting, actions, budgeting, diagnostics, models, portfolio, prepared, search_policy, status, strategy_bank
from .artifacts import canonical, inventory, read, sha as digest, write
from .evaluator.lean import LeanEvaluator, validate_template
from .evaluator.tokens import TOKENIZER_ID, proof_body

BASE = Path(__file__).resolve().parent
CODE_FILES = ("__init__.py", "__main__.py", "harness.py", "models.py", "provenance.json",
              "artifacts.py", "actions.py", "strategy_bank.py", "strategy_signals.py", "portfolio.py", "search_policy.py", "budgeting.py", "preflight.py", "diagnostics.py", "status.py", "accounting.py", "prepared.py", "usage_cost.py", "openai_direct.py",
              "evaluator/__init__.py", "evaluator/lean.py", "evaluator/tokens.py", "evaluator/provenance.json")
SELECTION = "ratio-sum-v1: tokens*baseline_raw + raw*baseline_tokens; then tokens, declaration SHA256"


def positive(value):
    return type(value) is int and value > 0


def load_config(path):
    config = read(path)
    if config.get("schema_version") != 1:
        raise ValueError("Expected config schema_version 1")
    limits, lean, model = config["limits"], config["lean"], config["model"]
    if "max_calls" not in limits:
        raise ValueError("Set max_calls explicitly (null requires cost_stop_usd)")
    if set(model) - {"backend", "responses", "id", "provider", "max_tokens", "temperature", "seed", "timeout_seconds", "reasoning_effort", "max_price"}:
        raise ValueError("Unexpected model setting; credentials belong in environment variables")
    for key in ("max_proof_characters", "max_feedback_characters", "max_request_characters"):
        if not positive(limits[key]):
            raise ValueError("Expected positive integer: " + key)
    threshold = limits.get("cost_stop_usd")
    if threshold is not None:
        if isinstance(threshold, bool):
            raise ValueError("Expected a positive finite cost_stop_usd")
        try:
            amount = Decimal(str(threshold))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Expected a positive finite cost_stop_usd") from exc
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Expected a positive finite cost_stop_usd")
    if limits.get("max_calls") is None:
        if model["backend"] not in ("openrouter", "openai") or threshold is None:
            raise ValueError("Unlimited calls require an OpenRouter cost_stop_usd")
    elif not positive(limits["max_calls"]):
        raise ValueError("Expected positive integer max_calls or null with cost_stop_usd")
    if "cost_cap_usd" in limits:
        try:
            cap = Decimal(str(limits["cost_cap_usd"]))
        except InvalidOperation as exc:
            raise ValueError("Expected positive finite cost_cap_usd") from exc
        if not cap.is_finite() or cap <= 0 or model.get("backend") not in ("openrouter", "openai") or "max_price" not in model:
            raise ValueError("cost_cap_usd requires positive finite cap and OpenRouter price ceilings")
    if not positive(lean["repetitions"]) or lean["repetitions"] % 2 != 1:
        raise ValueError("Lean repetitions must be a positive odd integer")
    if not positive(lean["timeout_seconds"]):
        raise ValueError("Expected positive Lean timeout")
    if not lean["command"] or not all(isinstance(x, str) and x for x in lean["command"]):
        raise ValueError("Lean command must be an argument list")
    if model["backend"] not in ("fixture", "openrouter", "openai"):
        raise ValueError("Unknown model backend")
    if model["backend"] in ("openrouter", "openai"):
        for key in ("id", "provider"):
            if not isinstance(model[key], str) or not model[key] or "REPLACE" in model[key]:
                raise ValueError("Set explicit model " + key)
        if not positive(model["max_tokens"]) or not positive(model["timeout_seconds"]):
            raise ValueError("Set positive model token and timeout limits")
        if "temperature" in model and (type(model["temperature"]) not in (int, float) or not 0 <= model["temperature"] <= 2):
            raise ValueError("Invalid temperature")
        if "reasoning_effort" in model and model["reasoning_effort"] not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Invalid reasoning effort")
        if "max_price" in model:
            prices = model["max_price"]
            if (not isinstance(prices, dict) or set(prices) != {"prompt", "completion"}
                    or any(type(v) not in (int, float) or not Decimal(str(v)).is_finite() or v < 0 for v in prices.values())):
                raise ValueError("Expected finite prompt/completion price ceilings")
    paths = {key: (path.parent / config[key]).resolve() for key in ("problem", "template", "project", "prompt")}
    if "agent" in config:
        actions.validate_config(config["agent"])
        paths["action_corpus"] = (path.parent / config["agent"]["corpus"]).resolve()
        actions.validate_corpus(read(paths["action_corpus"]))
    if "prepared_environment" in lean:
        if not isinstance(lean["prepared_environment"], str) or not lean["prepared_environment"]:
            raise ValueError("Set a prepared_environment manifest path")
        paths["prepared_environment"] = (path.parent / lean["prepared_environment"]).resolve()
        prepared.PreparedLeanEvaluator(paths["prepared_environment"])
    if model["backend"] == "fixture":
        paths["responses"] = (path.parent / model["responses"]).resolve()
        responses = read(paths["responses"])
        if not isinstance(responses, list) or len(responses) < limits["max_calls"] or not all(isinstance(s, str) for s in responses):
            raise ValueError("Fixture requires one response string for every call")
    cost_config = config.get("usage_cost", {})
    if not isinstance(cost_config, dict) or set(cost_config) - {"prices"}:
        raise ValueError("usage_cost accepts only an optional prices file")
    if "prices" in cost_config:
        paths["prices"] = (path.parent / cost_config["prices"]).resolve()
        accounting.validate_prices(read(paths["prices"]))
    validate_template(paths["template"].read_text())
    problem = read(paths["problem"])
    for key in ("id", "name", "statement", "reference"):
        if not isinstance(problem[key], str) or not problem[key]:
            raise ValueError("Missing problem field: " + key)
    proof_body(problem["reference"], problem["statement"])
    if portfolio.enabled(config):
        portfolio.validate_shared_inputs(config, problem["reference"], paths["prompt"].read_text(),
                                         read(paths["action_corpus"]))
    if (paths["project"] / "lake-manifest.json").exists():
        if read(paths["project"] / "lake-manifest.json").get("packages") and "prepared_environment" not in paths:
            raise ValueError("External dependencies require a prepared_environment manifest")
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
                          "responses": "responses.json", "prepared_environment": "prepared-environment.json",
                          "action_corpus": "action-corpus.json"}.items():
        if key in paths:
            dest = output / "input" / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paths[key], dest)
    shutil.copyfile(config_path, output / "input/config.json")
    prices = read(paths["prices"]) if "prices" in paths else accounting.NO_PRICES
    accounting.validate_prices(prices)
    write(output / "input/usage-prices.json", prices)
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


def initial_state(problem, result, config=None):
    baseline = metrics(result)
    if baseline is None or baseline["raw_heartbeats"] <= 0:
        raise ValueError("Original must verify with positive baseline measurements")
    state = {"step": 0, "calls": 0, "cost_usd": "0", "unknown_cost": False,
            "baseline": {k: baseline[k] for k in ("tokens", "raw_heartbeats")},
            "best": candidate(problem["reference"], result, baseline), "latest": None}
    if actions.enabled(config or {}):
        actions.initialize(state)
        portfolio.initialize(state, config)
    return state


def make_request(state, problem, config, prompt):
    whole_state = state
    if portfolio.enabled(config):
        state = portfolio.scoped_state(state, config)
    hidden = portfolio.hidden_original(state, config)
    reference = problem["reference"]
    problem = dict(problem)
    if hidden:
        problem.pop("reference", None)
    latest = json.loads(canonical(state["latest"]))
    if latest and latest["feedback"].get("metrics"):
        latest["feedback"]["metrics"].pop("raw_samples", None)
    packet = {"problem": problem, "baseline": state["baseline"],
              "best": {k: v for k, v in state["best"].items() if k != "raw_samples"}, "latest": latest,
              "step": state["step"] + 1,
              "remaining_calls": None if config["limits"]["max_calls"] is None else config["limits"]["max_calls"] - state["calls"]}
    if actions.enabled(config):
        packet["exploration"] = actions.view(state, config)
        repair = packet["exploration"].get("repair_context")
        if repair and latest and latest["code"] == repair["code"]:
            packet["latest"] = {"candidate_id": repair["candidate_id"],
                                "feedback_ref": "exploration.repair_context.feedback"}
        elif latest:
            packet["latest"]["feedback"] = actions.compact_feedback(latest["feedback"])
        if packet["best"]["code"] == reference:
            packet["best"].pop("code")
            packet["best"]["code_ref"] = "hidden original" if hidden else "problem.reference"
        if hidden:
            packet["exploration"]["notes"] += " The original proof is hidden. read_candidate/analyze may only read your own candidates."
    context = portfolio.packet(whole_state, config) if portfolio.enabled(config) else None
    if context:
        packet["portfolio"] = context
    if search_policy.enabled(config):
        packet["approach_policy"] = search_policy.packet(state, config, context)
        prompt += "\n" + search_policy.GUIDANCE
    bank_settings = config.get("agent", {}).get("strategy_bank")
    if bank_settings is not None:
        packet["strategy_bank"] = strategy_bank.for_request(problem, bank_settings, packet, hidden=hidden)
    threshold = config["limits"].get("cost_stop_usd")
    if threshold is not None:
        spent = Decimal(state["cost_usd"])
        packet["budget"] = {"stop_at_usd": str(threshold), "spent_usd": str(spent),
                            "remaining_usd": str(max(Decimal(0), Decimal(str(threshold)) - spent)),
                            "mode": "stop after the response reaching the threshold; last call may overshoot"}
    if "cost_cap_usd" in config["limits"]:
        packet["hard_budget"] = {"cap_usd": str(config["limits"]["cost_cap_usd"]),
                                 "spent_usd": state["cost_usd"], "mode": "next maximum request must fit; no overshoot"}
    body = models.payload([{"role": "system", "content": prompt},
                           {"role": "user", "content": canonical(packet)}], config["model"])
    if len(canonical(body)) > config["limits"]["max_request_characters"]:
        raise ValueError("Request exceeds max_request_characters")
    if "cost_cap_usd" in config["limits"]:
        # Treat an unreservable request as a context boundary before dispatch.
        budgeting.request_cost(body)
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


def prepare_response(raw, state, problem, config, output):
    action, code, observation, rejection = None, None, None, None
    try:
        if actions.enabled(config):
            visible = portfolio.scoped_state(state, config)
            action, code, observation = actions.prepare(raw, visible, problem, config,
                read(output / "input/action-corpus.json"), parse_proof)
            if portfolio.enabled(config) and code is not None and any(
                    digest(code) == row["sha256"] for row in visible["exploration"]["candidates"].values()):
                raise ValueError("Duplicate candidate in this context; propose a new source")
        else:
            code = parse_proof(raw, problem, config["limits"]["max_proof_characters"])
    except (ValueError, TypeError) as exc:
        code, observation = None, None
        rejection = str(exc)
    return action, code, observation, rejection


def step_event(state, rejection, config, action, observation):
    event = {"state_after": state, "rejection": rejection}
    if actions.enabled(config):
        event.update(action=action, observation=observation)
    return event


def step_diagnosis(raw, rejection, result, folder, output, config):
    report = diagnostics.step(raw, rejection, result, folder, output)
    if report and rejection and actions.enabled(config):
        report["guidance"] = "Return one supported JSON action object using exploration.actions and known candidate IDs."
    return report


def advance(state, raw, code, result, rejection, baseline, config, run_directory, diagnosis=None,
            *, action=None, observation=None):
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
    if action and code is None and rejection is None:
        response_feedback = {"status": "tool_result", "valid": None,
                             "details": canonical(observation)[:limit]}
    else:
        response_feedback = diagnostics.enrich(
            feedback(result, rejection, limit, run_directory), diagnosis, limit, run_directory)
    state["latest"] = {"code": code, "feedback": response_feedback}
    if actions.enabled(config):
        actions.advance(state, action, code, proposal, rejection, observation)
        portfolio.advance(state, config, code, result, ranking)
    return state


def seal(output):
    write(output / "artifacts.json", inventory(output))


def stopping_reason(state, problem, config, prompt, output=None):
    if state["unknown_cost"]:
        return "unknown_cost"
    if state["latest"] and state["latest"]["feedback"]["status"] == "environment_failed":
        return "environment_failed"
    if portfolio.finished(state):
        return "portfolio_complete"
    if actions.finished(state):
        return "agent_finished"
    if cost_threshold_reached(state, config):
        return "cost_limit"
    if config["limits"]["max_calls"] is not None and state["calls"] >= config["limits"]["max_calls"]:
        return "call_limit"
    try:
        body = make_request(state, problem, config, prompt)
    except ValueError:
        return "context_limit"
    reserved = budgeting.reservation(body, state, config)
    if reserved is not None and not reserved["allowed"]:
        if output is None or read(output / "budget-stop.json") != reserved:
            raise ValueError("Budget stop differs from replayed reservation")
        return "budget_reservation"
    raise ValueError("Recorded run ended before a stopping condition")


def cost_threshold_reached(state, config):
    threshold = config["limits"].get("cost_stop_usd")
    return threshold is not None and Decimal(state["cost_usd"]) >= Decimal(str(threshold))


def summarize(state, baseline, final, config, stop):
    measured = metrics(final)
    result = {"status": "completed" if final["valid"] and stop in ("call_limit", "context_limit", "cost_limit", "agent_finished", "budget_reservation", "portfolio_complete") else "stopped",
            "stop_reason": stop, "backend": config["model"]["backend"],
            "state": state, "baseline": baseline, "final": measured,
            "final_valid": final["valid"], "official_evaluation": False,
            "final_median_matches_selection": measured is not None and all(
                measured[k] == state["best"][k] for k in ("tokens", "raw_heartbeats")),
            "final_samples_match_selection": measured is not None and measured["raw_samples"] == state["best"]["raw_samples"]}
    if portfolio.enabled(config):
        result["portfolio"] = portfolio.summary(state, config)
        if not result["portfolio"]["complete"]:
            result["status"] = "stopped"
    return result


def run(config_path, output, evaluator=None, *, check_only=False, query=None, dotenv=None):
    if output.exists() or output.is_symlink():
        raise FileExistsError("Refusing to reuse an existing run directory: " + str(output))
    config_path, output = config_path.resolve(), output.resolve()
    output.mkdir(parents=True)
    progress = status.Progress(status.Journal(output))
    recorder = diagnostics.Recorder(output)
    outcome = {"schema_version": 1, "status": "failed", "model_requests": 0}
    previous_key = os.environ.get("OPENROUTER_API_KEY")
    key_loaded = False

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
        evaluator = evaluator or (prepared.PreparedLeanEvaluator(paths["prepared_environment"])
                                  if "prepared_environment" in paths else LeanEvaluator())
        key_name = "OPENAI_API_KEY" if config["model"]["backend"] == "openai" else "OPENROUTER_API_KEY"
        previous_key = os.environ.get(key_name)
        if config["model"]["backend"] in ("openrouter", "openai"):
            if dotenv is not None:
                names = ("OPENAI_API_KEY", "OPENROUTER_API_KEY") if key_name == "OPENAI_API_KEY" else ("OPENROUTER", "OPENROUTER_API_KEY")
                os.environ[key_name] = models.load_key(dotenv, names)
                key_loaded = True
            if not os.environ.get(key_name):
                raise ValueError("Export " + key_name + " before running a live experiment")
        manifest = snapshot(output, config_path, paths)
        if "prepared_environment" in paths and isinstance(evaluator, prepared.PreparedLeanEvaluator):
            evaluator = prepared.PreparedLeanEvaluator(output / "input/prepared-environment.json", evaluator._executor)
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
        state = initial_state(problem, baseline_result, config)
        baseline = metrics(baseline_result)
        write(output / "initial-state.json", state)
        stop = "call_limit"
        usage_records = []
        for step in count(1):
            if portfolio.finished(state):
                stop = "portfolio_complete"
                break
            if cost_threshold_reached(state, config):
                stop = "cost_limit"
                break
            if config["limits"]["max_calls"] is not None and step > config["limits"]["max_calls"]:
                stop = "call_limit"
                break
            folder = output / "steps" / f"{step:03}"
            try:
                body = make_request(state, problem, config, prompt)
            except ValueError:
                stop = "context_limit"
                break
            reserved = budgeting.reservation(body, state, config)
            if reserved is not None and not reserved["allowed"]:
                write(output / "budget-stop.json", reserved)
                stop = "budget_reservation"
                break
            progress.enter("model", attempt=step)
            write(folder / "request.json", body)
            progress.calls += 1  # A dispatched call may have an unknown outcome.
            raw = (query or models.query)(body, config["model"], step, fixtures)
            write(folder / "response.json", raw)
            usage = accounting.response_record(raw)
            write(folder / "usage.json", usage)
            usage_records.append(usage)
            receipt_error = diagnostics.response(raw, None, folder / "response.json", output)
            progress.finish("failed" if receipt_error else "passed", [folder / "request.json", folder / "response.json"])
            progress.enter("response", attempt=step)
            action, code, observation, rejection = prepare_response(raw, state, problem, config, output)
            result = None
            progress.finish("failed" if rejection else "passed", [folder / "response.json"])
            if code is not None:
                source = folder / "candidate.lean"
                source.write_text(code, encoding="utf-8")
                result = evaluate(code, folder / "evaluation", "candidate", source, attempt=step)
            report = step_diagnosis(raw, rejection, result, folder, output, config)
            if report and report["stage"] == "model":
                recorder.save(f"model-{step:03}", report)
            state = advance(state, raw, code, result, rejection, baseline, config, str(output), report,
                            action=action, observation=observation)
            write(folder / "event.json", step_event(state, rejection, config, action, observation))
            if state["unknown_cost"]:
                stop = "unknown_cost"
                break
            if result and environment_failed(result):
                stop = "environment_failed"
                break
            if portfolio.finished(state):
                stop = "portfolio_complete"
                break
            if actions.finished(state):
                stop = "agent_finished"
                break
        selected = output / "selected.lean"
        selected.write_text(state["best"]["code"], encoding="utf-8")
        final = evaluate(state["best"]["code"], output / "final", "final", selected)
        progress.enter("environment", phase="harness_end")
        if evaluator.fingerprint(environment) != manifest["environment"]:
            raise ValueError("Lean environment changed during the run")
        progress.finish(paths=["environment.json"])
        summary = summarize(state, baseline, final, config, stop)
        write(output / "usage-summary.json", accounting.response_summary(usage_records))
        write(output / "summary.json", summary)
        write(output / "usage-cost.json", accounting.native_report(output))
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
        # Keep pending calls visible without hiding an earlier execution error.
        if (output / "input/usage-prices.json").exists() and not (output / "usage-cost.json").exists():
            try:
                write(output / "usage-cost.json", accounting.native_report(output))
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                write(output / "usage-cost-error.json", {"error_type": type(exc).__name__,
                                                       "reason": "usage_report_unavailable"})
        if key_loaded:
            if previous_key is None:
                os.environ.pop(key_name, None)
            else:
                os.environ[key_name] = previous_key
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
    state = initial_state(problem, baseline_result, config)
    baseline = metrics(baseline_result)
    if read(output / "initial-state.json") != state:
        raise ValueError("Initial state differs")
    steps = sorted((output / "steps").iterdir(), key=lambda p: int(p.name)) if (output / "steps").exists() else []
    usage_records = []
    for index, folder in enumerate(steps, 1):
        if (folder.name != f"{index:03}" or state["unknown_cost"] or actions.finished(state) or portfolio.finished(state) or cost_threshold_reached(state, config)
                or config["limits"]["max_calls"] is not None and index > config["limits"]["max_calls"]
                or state["latest"] and state["latest"]["feedback"]["status"] == "environment_failed"):
            raise ValueError("Invalid step sequence")
        if read(folder / "request.json") != make_request(state, problem, config, prompt):
            raise ValueError("Request does not match the recorded state")
        reserved = budgeting.reservation(read(folder / "request.json"), state, config)
        if reserved is not None and not reserved["allowed"]:
            raise ValueError("Recorded request exceeded cost reservation")
        raw = read(folder / "response.json")
        usage = accounting.response_record(raw)
        if read(folder / "usage.json") != usage:
            raise ValueError("Usage receipt differs from saved response")
        usage_records.append(usage)
        action, code, observation, rejection = prepare_response(raw, state, problem, config, output)
        result = None
        if code is not None:
            if (folder / "candidate.lean").read_text() != code:
                raise ValueError("Candidate differs from model response")
            result = read(folder / "evaluation/result.json")
        report = step_diagnosis(raw, rejection, result, folder, output, config)
        state = advance(state, raw, code, result, rejection, baseline, config, manifest["run_directory"], report,
                        action=action, observation=observation)
        if read(folder / "event.json") != step_event(state, rejection, config, action, observation):
            raise ValueError("State transition differs")
    summary = read(output / "summary.json")
    if read(output / "usage-summary.json") != accounting.response_summary(usage_records):
        raise ValueError("Usage summary differs from saved responses")
    if state != summary["state"] or (output / "selected.lean").read_text() != state["best"]["code"]:
        raise ValueError("Final selection differs")
    final = read(output / "final/result.json")
    expected = summarize(state, baseline, final, config, stopping_reason(state, problem, config, prompt, output))
    if summary != expected:
        raise ValueError("Final summary differs")
    if read(output / "usage-cost.json") != accounting.native_report(output):
        raise ValueError("Usage/cost report differs from recorded attempts")
    return {"usage_cost_replay_passed": True, "record_replay_passed": True, "model_called": False, "lean_called": False,
            "steps": len(steps), "selected_sha256": state["best"]["sha256"]}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "usage-cost":
        return accounting.main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("usage-cost", help="Offline API/subagent usage and cost accounting")
    freeze = commands.add_parser("freeze-environment", help="Pin already-built Lean libraries; no downloads")
    freeze.add_argument("--library-path", type=Path, action="append", required=True)
    freeze.add_argument("--revision", required=True)
    freeze.add_argument("--sandbox", choices=["none", "macos-readonly"], default="none")
    freeze.add_argument("--verification", choices=["full", "stat-cache"], default="full",
                        help="Full content checks by default; opt into per-process file-stat hash reuse")
    freeze.add_argument("--output", type=Path, required=True)
    for name in ("run", "check"):
        start = commands.add_parser(name)
        start.add_argument("--config", type=Path, required=True)
        start.add_argument("--output", type=Path, required=True)
        start.add_argument("--dotenv", type=Path, help="Explicit dotenv file; never copied into run artifacts")
    observe = commands.add_parser("status")
    observe.add_argument("run_directory", type=Path)
    observe.add_argument("--json", action="store_true")
    again = commands.add_parser("replay")
    again.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "freeze-environment":
            result = prepared.freeze(args.library_path, args.revision, args.output,
                                     sandbox=args.sandbox, verification=args.verification)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "status":
            result = status.inspect(args.run_directory)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else status.describe(result))
            return 0
        result = (run(args.config, args.output, check_only=args.command == "check", dotenv=args.dotenv)
                  if args.command in ("run", "check") else replay(args.run_directory))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("record_replay_passed") or result.get("status") in ("completed", "ready") else 1


if __name__ == "__main__":
    sys.exit(main())
