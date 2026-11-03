#!/usr/bin/env python3
"""Durable final60 actions-v1 runner. A settled $1 threshold permits one overshoot.

No implicit retries: an unresolved dispatch prevents every further model call.
The driver reuses the common harness state/action policy, while checkpointing
responses before Lean work so a restart never repeats a billed request.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
import traceback

from lean_agent import accounting, actions, artifacts as a, diagnostics, harness as h, models

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
import openai_transport as transport
from evaluation_cache import VERIFICATION_POLICY
DATASET_SHA = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"
MODEL = {"backend": "openai", "id": "gpt-6.1-sol", "provider": "openai",
         "reasoning_effort": "high", "max_tokens": 8192, "timeout_seconds": 900,
         "seed": 42}
TARGET = Decimal("1.00")
DEFAULT_PORTFOLIO = {"scout_evaluations": 6, "merger_evaluations": 22, "progress_guard": "bounded-v1"}
# Omitted policy means new-run defaults, while explicit None preserves legacy
# single-context inputs during validation and supports --no-portfolio.
UNSPECIFIED_PORTFOLIO = object()
UNSPECIFIED_STRATEGY = object()


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    with temporary.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def locked(path, *, blocking=True):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def evaluator_class():
    spec = importlib.util.spec_from_file_location("final_batch_evaluator", HERE / "evaluator.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.FinalEvaluator


def evaluator(root):
    return evaluator_class()(repo_root=REPO, global_lock_path=REPO / "sources/final/final-batch-compiler.lock",
                             cache_root=Path(root) / "evaluation-cache")


def folder(root, row):
    return Path(root) / "problems" / f"F{row:03}"


def rows_from(args):
    values = args.rows or list(range(1, 61))
    if len(set(values)) != len(values) or any(value < 1 or value > 60 for value in values):
        raise ValueError("Expected unique final problem rows 1..60")
    return values


def implementation_files():
    files = [h.BASE / name for name in h.CODE_FILES]
    files.extend(path for path in HERE.glob("*.py"))
    files.append(REPO / "experiments/proof-analyze/proof_tokens.py")
    return sorted(set(path.resolve() for path in files))


def verify_frozen(root):
    require_policy(root)
    manifest = a.read(Path(root) / "frozen.json")
    for path, digest in manifest.items():
        if a.sha(Path(path).read_bytes()) != digest:
            raise ValueError("Frozen input/implementation changed: " + path)


def require_policy(root):
    authorization = Path(root) / "authorization.json"
    if authorization.exists() and a.read(authorization).get("verification_policy") != VERIFICATION_POLICY:
        raise ValueError("Different verification policy: use a new batch root; never migrate an active run")


def prompt_text(context):
    base = (REPO / "examples/actions/prompt.txt").read_text()
    return base + "\n" + (
        "Optimization guidance: first look for existing lemmas, assumptions, or witnesses that remove proof steps. "
        "Then reduce repeated whole-context simplification or broad search using recorded evidence. "
        "Judge complete proof-token and heartbeat ratios together; a shorter proof can be worse. "
        "propose: state a short concrete approach in strategy and supply the complete replacement proof. "
        "repair: fix the reported errors in the named rejected parent, preserving working branches. "
        "search/inspect: retrieve a specific missing definition or theorem rather than repeatedly browsing. "
        "After repeated failure of the same approach, branch from another candidate or change the proof structure. "
        "Search is lexical evidence only, not a theorem-prover or availability guarantee. "
        "Every action consumes paid model budget. The controller stops at the configured settled-cost threshold in budget.stop_at_usd. "
        "The exact statement and original full source context are preserved by the evaluator. "
        "Exploration feedback verifies only the primary version; it does not establish cross-version compatibility. "
        "At final selection the controller checks candidates in score order against every required version, "
        "falling back to another candidate if needed. All listed versions must accept the final candidate. "
        "No extra imports or helper declarations.\n"
        "<original_context>\n" + context + "\n</original_context>\n")


def make_request(state, problem, config, prompt):
    # Assemble without truncating the live archive; compact only the wire copy.
    assembly = {**config, "limits": {**config["limits"], "max_request_characters": 2000000}}
    common = h.make_request(state, problem, assembly, prompt)
    body = transport.payload(common["messages"], config["model"])
    def fits():
        if len(a.canonical(body)) > config["limits"]["max_request_characters"]:
            return False
        try:
            transport.request_cost(body)
            return True
        except ValueError:
            return False
    if fits():
        return body
    packet = json.loads(body["messages"][1]["content"])
    changes = []
    if "code" in packet["best"]:
        packet["best"].pop("code")
        packet["best"]["code_ref"] = {"action": "read_candidate", "candidate_id": packet["exploration"]["best_candidate_id"]}
        changes.append("best source available through read_candidate")
        packet["request_compaction"] = changes
        body["messages"][1]["content"] = a.canonical(packet)
        if fits():
            return body
    if "reference" in packet["problem"]:
        packet["problem"].pop("reference")
        packet["problem"]["reference_ref"] = {"action": "read_candidate", "candidate_id": "c000"}
        changes.append("original source available as c000 through read_candidate")
        packet["request_compaction"] = changes
        body["messages"][1]["content"] = a.canonical(packet)
        if fits():
            return body
    raise ValueError("Request exceeds bounded wire size after source-reference compaction; archive and repair source preserved")


def evaluate_cached(ev, code, problem, destination, **kwargs):
    """A crash during Lean work can be retried without repeating the API call."""
    destination = Path(destination)
    path = destination / "result.json"
    receipt = destination / "evaluation-request.json"
    expected = {"candidate_sha256": a.sha(code), "problem": problem, "options": kwargs}
    if path.exists():
        if not receipt.exists() or a.read(receipt) != expected:
            raise ValueError("Saved evaluation belongs to a different candidate/problem/policy")
        return a.read(path)
    if destination.exists():
        destination.rename(destination.with_name(destination.name + "-incomplete-" + str(time.time_ns())))
    result = ev.evaluate(code, problem, destination, **kwargs)
    atomic(receipt, expected)
    atomic(path, result)
    return result


def guard_compiler_signal(result):
    value = json.loads(a.canonical(result))
    for environment in value.get("environments", {}).values():
        message = (environment.get("error") or {}).get("message", "").lower()
        failed_runs = [run for run in environment.get("runs", [])
                       if type(run.get("returncode")) is int and run["returncode"] < 0]
        # A diagnosed Lean allocator limit is candidate feedback, not evidence
        # of a broken machine. Keep the frozen 4 GiB bound; never retry it here.
        bounded_allocator_abort = (
            "lean::memory_exception" in message
            and "excessive memory consumption detected" in message
            and len(failed_runs) == 1
            and failed_runs[0]["returncode"] == -signal.SIGABRT
            and "-M4096" in failed_runs[0].get("command", [])
        )
        if bounded_allocator_abort:
            error = {"kind": "resource", "message": (environment.get("error") or {})["message"],
                     "resource": "lean_allocator_limit", "limit_mib": 4096}
            environment.update(valid=False, error=error)
            value.update(valid=False, error=error)
            continue
        resource_error = any(phrase in (environment.get("error") or {}).get("message", "").lower()
                             for phrase in ("maximum memory consumption reached", "out of memory", "allocation failed"))
        if resource_error or any(type(run.get("returncode")) is int and run["returncode"] < 0 for run in environment.get("runs", [])):
            error = {"kind": "environment", "message": "Compiler terminated by signal; stop model dispatch and inspect memory/process state."}
            environment.update(valid=False, error=error)
            value.update(valid=False, error=error)
    return value


INPUT_FILES = ("problem.json", "config.json", "action-corpus.json", "context-metadata.json", "prompt.txt")


def configuration(problem, portfolio_settings=UNSPECIFIED_PORTFOLIO, strategy_settings=None):
    if portfolio_settings is UNSPECIFIED_PORTFOLIO:
        portfolio_settings = DEFAULT_PORTFOLIO
    model = {**MODEL, "max_tokens": 16384 if len(problem["reference"]) > 12000 else 8192}
    config = {"schema_version": 1, "model": model,
        "limits": {"max_calls": None, "cost_stop_usd": str(TARGET),
                   "max_proof_characters": max(24000, len(problem["reference"]) * 3),
                   "max_feedback_characters": 7000, "max_request_characters": 190000},
        "agent": {"mode": "actions-v1", "corpus": "action-corpus.json", "history_limit": 4,
                  "candidate_limit": 8, "allow_finish": False}}
    if portfolio_settings is not None:
        h.portfolio.validate(portfolio_settings)
        config["agent"].update(portfolio=dict(portfolio_settings), approach_policy="exchange-v1")
    if strategy_settings is not None:
        h.strategy_bank.validate_settings(strategy_settings)
        config["agent"]["strategy_bank"] = json.loads(a.canonical(strategy_settings))
    return config


def validate_inputs(root, row):
    inputs = folder(root, row) / "input"
    missing = [name for name in INPUT_FILES if not (inputs / name).is_file()]
    if missing:
        raise ValueError(f"F{row:03} missing complete inputs: " + ", ".join(missing))
    problem = a.read(inputs / "problem.json")
    original = a.read(REPO / "sources/final/problems" / f"F{row:03}.json")
    if problem != original or problem.get("dataset_sha256") != DATASET_SHA:
        raise ValueError(f"F{row:03} frozen problem identity differs")
    config = a.read(inputs / "config.json")
    expected = configuration(problem, config.get("agent", {}).get("portfolio"),
                             config.get("agent", {}).get("strategy_bank"))
    timeout = config.get("model", {}).get("timeout_seconds")
    if timeout not in (300, 900):
        raise ValueError(f"F{row:03} unexpected prelaunch timeout")
    expected["model"]["timeout_seconds"] = timeout
    if config != expected:
        raise ValueError(f"F{row:03} input configuration differs from the fixed policy")
    corpus = a.read(inputs / "action-corpus.json")
    actions.validate_corpus(corpus)
    if not isinstance(a.read(inputs / "context-metadata.json"), dict):
        raise ValueError(f"F{row:03} context metadata must be an object")
    prompt = (inputs / "prompt.txt").read_text()
    if not prompt or len(prompt) > 60000:
        raise ValueError(f"F{row:03} missing or oversized prompt")
    h.portfolio.validate_shared_inputs(config, problem["reference"], prompt, corpus)
    return problem


def prepare_inputs(root, rows, workers=1, portfolio_settings=UNSPECIFIED_PORTFOLIO,
                   strategy_settings=UNSPECIFIED_STRATEGY):
    """Prepare disjoint row inputs only; no authorization, API ledger or seal."""
    if workers not in (1, 2):
        raise ValueError("Input preparation workers must be 1 or 2")
    root = Path(root).resolve()
    require_policy(root)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "frozen.json").exists():
        raise ValueError("Batch inputs are already sealed")
    ev = evaluator(root)
    def write_row(row):
        with locked(folder(root, row) / "input.lock"):
            if (root / "frozen.json").exists():
                raise ValueError("Batch became sealed before input preparation")
            output = folder(root, row)
            inputs = output / "input"
            if all((inputs / name).is_file() for name in INPUT_FILES):
                validate_inputs(root, row)
                if portfolio_settings is not UNSPECIFIED_PORTFOLIO and a.read(inputs / "config.json")["agent"].get("portfolio") != portfolio_settings:
                    raise ValueError("Existing inputs have a different policy; use a fresh batch root")
                if strategy_settings is not UNSPECIFIED_STRATEGY and a.read(inputs / "config.json")["agent"].get("strategy_bank") != strategy_settings:
                    raise ValueError("Existing inputs have a different Bank; use a fresh batch root")
                return {"row": row, "input_status": "reused"}
            inputs.mkdir(parents=True, exist_ok=True)
            problem = ev.load_problem(row)
            if problem.get("dataset_sha256") != DATASET_SHA:
                raise ValueError("Unexpected final dataset identity")
            context = ev.source_context(problem)
            corpus = context["corpus"]
            actions.validate_corpus(corpus)
            text = context["prompt_context"]
            if len(text) > 40000:
                raise ValueError("Initial context exceeds bounded 40000 characters")
            atomic(inputs / "problem.json", problem)
            atomic(inputs / "config.json", configuration(problem, portfolio_settings,
                   None if strategy_settings is UNSPECIFIED_STRATEGY else strategy_settings))
            atomic(inputs / "action-corpus.json", corpus)
            atomic(inputs / "context-metadata.json", context.get("metadata", {}))
            (inputs / "prompt.txt").write_text(prompt_text(text))
            validate_inputs(root, row)
            return {"row": row, "input_status": "prepared"}
    if workers == 1:
        for row in rows:
            print(json.dumps(write_row(row)), flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(rows), workers):
                for result in pool.map(write_row, rows[start:start + workers]):
                    print(json.dumps(result), flush=True)


def seal_inputs(root, rows):
    """Seal already complete row inputs without repeating source retrieval."""
    root = Path(root).resolve()
    require_policy(root)
    root.mkdir(parents=True, exist_ok=True)
    with locked(root / "prepare.lock"), ExitStack() as stack:
        if (root / "frozen.json").exists():
            verify_frozen(root)
            if a.read(root / "authorization.json")["rows"] != rows:
                raise ValueError("Sealed rows differ from requested authorization")
            return
        for row in rows:
            stack.enter_context(locked(folder(root, row) / "input.lock", blocking=False))
            validate_inputs(root, row)
        ledger = root / "ledger.json"
        if ledger.exists() and a.read(ledger)["attempts"]:
            raise ValueError("Cannot seal after any API dispatch")
        authorization = {"dataset_sha256": DATASET_SHA, "rows": rows, "problem_count": len(rows),
                         "per_problem_target_usd": str(TARGET), "nominal_total_usd": str(TARGET * len(rows)),
                         "last_call_may_overshoot": True, "max_api_parallel": 2, "max_lean_parallel": 1,
                         "no_automatic_retries": True, "created_at": now(),
                         "verification_policy": VERIFICATION_POLICY}
        authorization.update(provider="OpenAI direct", api_endpoint=transport.ENDPOINT,
                             budget_cost_basis="provider-token-usage-times-frozen-public-list-prices")
        atomic(root / "authorization.json", authorization)
        atomic(root / "pricing.json", transport.PRICING)
        if not (root / "ledger.json").exists():
            atomic(root / "ledger.json", {"schema_version": 1, "attempts": {}})
        code = root / "code"
        code.mkdir(exist_ok=True)
        for path in implementation_files():
            destination = code / path.relative_to(REPO)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        files = [*implementation_files(), root / "authorization.json", root / "pricing.json"]
        files.extend(path for path in (root / "problems").glob("*/input/*") if path.is_file())
        atomic(root / "frozen.json", {str(path): a.sha(path.read_bytes()) for path in files})
    print(json.dumps({"prepared": str(root), "rows": rows, "api_calls": 0}), flush=True)


def prepare(root, rows, workers=2, portfolio_settings=UNSPECIFIED_PORTFOLIO,
            strategy_settings=UNSPECIFIED_STRATEGY):
    if (Path(root) / "frozen.json").exists():
        if portfolio_settings is not UNSPECIFIED_PORTFOLIO:
            for row in rows:
                config = a.read(folder(root, row) / "input/config.json")
                if config.get("agent", {}).get("portfolio") != portfolio_settings:
                    raise ValueError("Sealed policy differs; use a fresh batch root")
        if strategy_settings is not UNSPECIFIED_STRATEGY:
            for row in rows:
                config = a.read(folder(root, row) / "input/config.json")
                if config.get("agent", {}).get("strategy_bank") != strategy_settings:
                    raise ValueError("Sealed Bank differs; use a fresh batch root")
        seal_inputs(root, rows)
        return
    prepare_inputs(root, rows, workers=workers, portfolio_settings=portfolio_settings,
                   strategy_settings=strategy_settings)
    seal_inputs(root, rows)


def ensure_baseline(root, row, ev):
    output = folder(root, row)
    problem = a.read(output / "input/problem.json")
    config = a.read(output / "input/config.json")
    baseline_file = output / "baseline/result.json"
    if not baseline_file.exists():
        evaluate_cached(ev, problem["reference"], problem, output / "baseline",
                        repetitions=3, trusted_reference=True)
    result = guard_compiler_signal(a.read(baseline_file))
    state = h.initial_state(problem, result, config)
    if not (output / "initial-state.json").exists():
        atomic(output / "initial-state.json", state)
    if not (output / "state.json").exists():
        atomic(output / "state.json", state)
    return state


def preflight(root, rows):
    root = Path(root).resolve()
    verify_frozen(root)
    ev = evaluator(root)
    failed = []
    for row in rows:
        output = folder(root, row)
        with locked(output / "problem.lock"):
            try:
                ensure_baseline(root, row, ev)
                problem = a.read(output / "input/problem.json")
                path = output / "reference-compatibility/result.json"
                if not path.exists():
                    evaluate_cached(ev, problem["reference"], problem, path.parent,
                                    repetitions=1, all_versions=True, trusted_reference=True)
                compatibility = a.read(path)
                if not compatibility["valid"]:
                    raise ValueError("Reference all-version compatibility failed")
                atomic(output / "preflight.json", {"status": "ready", "row": row, "at": now(),
                                                       "baseline": h.metrics(a.read(output / "baseline/result.json"))})
                print(json.dumps({"row": row, "preflight": "ready"}), flush=True)
            except Exception as exc:
                failed.append(row)
                atomic(output / "preflight.json", {"status": "failed", "row": row,
                                                      "error_type": type(exc).__name__, "message": str(exc)[:2000]})
                print(json.dumps({"row": row, "preflight": "failed", "error_type": type(exc).__name__}), flush=True)
    if failed:
        raise ValueError("Preflight failed rows: " + str(failed))


def reseal(root):
    """Prelaunch-only timeout correction; preserve the previous seal and code."""
    root = Path(root).resolve()
    require_policy(root)
    with locked(root / "prepare.lock"), ExitStack() as stack:
        authorization = a.read(root / "authorization.json")
        for row in authorization["rows"]:
            stack.enter_context(locked(folder(root, row) / "problem.lock", blocking=False))
        for number in range(2):
            stack.enter_context(locked(root / f"api-slot-{number}.lock", blocking=False))
        stack.enter_context(locked(root / "ledger.lock"))
        if a.read(root / "ledger.json")["attempts"]:
            raise ValueError("Resealing is forbidden after any API dispatch")
        old_path = root / "frozen.json"
        previous_bytes = old_path.read_bytes()
        previous = a.read(old_path)
        implementation = {str(path) for path in implementation_files()}
        for path, digest in previous.items():
            if path not in implementation and a.sha(Path(path).read_bytes()) != digest:
                raise ValueError("Prelaunch immutable input changed before reseal: " + path)
        configs = {}
        for row in authorization["rows"]:
            path = folder(root, row) / "input/config.json"
            value = a.read(path)
            if value["model"]["timeout_seconds"] not in (300, 900):
                raise ValueError("Unexpected timeout before prelaunch correction")
            configs[path] = (path.read_bytes(), value)
        receipt = root / "prelaunch-reseals" / str(time.time_ns())
        receipt.mkdir(parents=True)
        (receipt / "previous-frozen.json").write_bytes(previous_bytes)
        for path, (original, _) in configs.items():
            dest = receipt / "config-before" / path.parent.parent.name / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(original)
        code = root / "code"
        if code.exists():
            code.rename(receipt / "code-before")
        try:
            for path, (_, value) in configs.items():
                value["model"]["timeout_seconds"] = 900
                atomic(path, value)
            for path in implementation_files():
                destination = code / path.relative_to(REPO)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
            current_files = {Path(path) for path in previous} | set(implementation_files())
            atomic(old_path, {str(path): a.sha(path.read_bytes()) for path in sorted(current_files)})
            atomic(receipt / "receipt.json", {"at": now(), "reason": "Uniform 900-second prelaunch transport timeout",
                "api_attempts": 0, "changed_setting": "model.timeout_seconds", "final_value": 900,
                "previous_seal_sha256": a.sha(previous_bytes), "final_seal_sha256": a.sha(old_path.read_bytes()),
                "rows": authorization["rows"], "other_inputs_unchanged": True})
        except BaseException:
            for path, (original, _) in configs.items():
                path.write_bytes(original)
            old_path.write_bytes(previous_bytes)
            if code.exists():
                shutil.rmtree(code)
            if (receipt / "code-before").exists():
                (receipt / "code-before").rename(code)
            raise
    verify_frozen(root)
    print(json.dumps({"resealed": str(root), "timeout_seconds": 900, "api_attempts": 0}), flush=True)


@contextmanager
def api_slot(root):
    # This also bounds independent subagent-run worker processes to two calls.
    while True:
        for number in range(2):
            stream = (root / f"api-slot-{number}.lock").open("a+")
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                stream.close()
                continue
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
                stream.close()
            return
        time.sleep(0.25)


def problem_spend(ledger, row):
    return sum((Decimal(item["cost_usd"]) for item in ledger["attempts"].values()
                if item["row"] == row and item.get("cost_usd") is not None), Decimal(0))


def check_dispatchable(root, ledger):
    """Known live requests may overlap; lost/unknown requests stop the batch."""
    if (root / "stop-unknown-cost.json").exists():
        raise ValueError("Global unresolved-charge marker prevents API dispatch")
    for attempt, item in ledger["attempts"].items():
        if item["status"] == "settled":
            continue
        if item["status"] != "pending":
            raise ValueError("Unsettled charge globally prevents further API dispatch")
        try:
            with locked(root / "dispatch-locks" / (attempt + ".lock"), blocking=False):
                # A real in-flight dispatcher holds this lock until settlement.
                raise ValueError("Lost pending dispatcher globally prevents further API dispatch")
        except BlockingIOError:
            pass


def dispatch(root, row, step, body, model, step_dir):
    verify_frozen(root)
    bound = transport.request_cost(body)
    data = transport.model_metadata()
    attempt = f"F{row:03}-{step:04}"
    with api_slot(root), locked(root / "dispatch-locks" / (attempt + ".lock"), blocking=False):
        with locked(root / "ledger.lock"):
            ledger = a.read(root / "ledger.json")
            check_dispatchable(root, ledger)
            if problem_spend(ledger, row) >= TARGET:
                raise ValueError("Actual-cost threshold already reached")
            if attempt in ledger["attempts"]:
                raise ValueError("Attempt already dispatched; refusing duplicate API call")
            ledger["attempts"][attempt] = {"row": row, "step": step, "status": "pending", "cost_usd": None,
                                           "owner_pid": os.getpid(),
                                           "request_sha256": a.sha(a.canonical(body)), "started_at": now(),
                                           "maximum_request_cost_usd": bound["reserved_usd"]}
            atomic(step_dir / "endpoint.json", data)
            atomic(step_dir / "cost-bound.json", bound)
            atomic(step_dir / "request.json", body)
            atomic(root / "ledger.json", ledger)
        start = time.monotonic()
        provider_raw = transport.query(body, model, step)
        atomic(step_dir / "provider-response.json", provider_raw)
        raw = transport.normalize(provider_raw)
        atomic(step_dir / "response.json", raw)
        atomic(step_dir / "cost-receipt.json", raw["_cost_receipt"])
        atomic(step_dir / "timing.json", {"seconds": time.monotonic() - start})
        receipt = models.receipt(raw)
        with locked(root / "ledger.lock"):
            ledger = a.read(root / "ledger.json")
            item = ledger["attempts"][attempt]
            if receipt["cost_usd"] is None:
                item.update(status="unknown", response_id=receipt["id"], finished_at=now())
                atomic(root / "stop-unknown-cost.json", {"attempt": attempt, "at": now()})
            else:
                item.update(status="settled", cost_usd=receipt["cost_usd"], response_id=receipt["id"], finished_at=now(),
                            cost_basis=raw["_cost_receipt"]["basis"], invoice_verified=False,
                            provider_response_sha256=raw["_cost_receipt"]["provider_response_sha256"])
                if Decimal(receipt["cost_usd"]) > Decimal(bound["reserved_usd"]):
                    item["status"] = "bound_violated"
                    atomic(root / "stop-unknown-cost.json", {"attempt": attempt, "reason": "cost_bound_violated", "at": now()})
            atomic(root / "ledger.json", ledger)
        if item["status"] != "settled":
            raise ValueError("Unknown or excessive charge; all further dispatch stopped")
        print(json.dumps({"row": row, "step": step, "call_cost_usd": receipt["cost_usd"]}), flush=True)
        return raw


def recover_pending(root, row, step, step_dir):
    attempt = f"F{row:03}-{step:04}"
    with locked(root / "ledger.lock"):
        ledger = a.read(root / "ledger.json")
        item = ledger["attempts"].get(attempt)
        if item is None:
            return
        provider_path = step_dir / "provider-response.json"
        if not provider_path.exists():
            raise ValueError("Dispatched call has no durable original provider response; refusing retry")
        normalized = transport.normalize(a.read(provider_path))
        expected_receipt = normalized["_cost_receipt"]
        expected_hash = expected_receipt["provider_response_sha256"]
        if item.get("provider_response_sha256") is not None and item["provider_response_sha256"] != expected_hash:
            raise ValueError("Original provider response differs from ledger hash")
        if item["status"] == "settled" and item.get("provider_response_sha256") is None:
            raise ValueError("Settled receipt lacks original provider response hash")
        if (step_dir / "response.json").exists():
            if a.read(step_dir / "response.json") != normalized:
                raise ValueError("Normalized response differs from recomputed provider usage/content")
        else:
            atomic(step_dir / "response.json", normalized)
        cost_path = step_dir / "cost-receipt.json"
        if cost_path.exists() and a.read(cost_path) != expected_receipt:
            raise ValueError("Saved cost receipt differs from original provider usage")
        if not cost_path.exists():
            atomic(cost_path, expected_receipt)
        raw = normalized
        receipt = models.receipt(raw)
        if item["status"] == "settled" and (receipt["cost_usd"] is None or
                Decimal(item["cost_usd"]) != Decimal(receipt["cost_usd"]) or item.get("response_id") != receipt["id"]):
            raise ValueError("Settled ledger cost/identity differs from original provider response")
        if item["status"] == "pending" and receipt["cost_usd"] is not None:
            item.update(status="settled", cost_usd=receipt["cost_usd"], response_id=receipt["id"], recovered_at=now())
            if raw.get("_cost_receipt"):
                item.update(cost_basis=raw["_cost_receipt"]["basis"], invoice_verified=False,
                            provider_response_sha256=raw["_cost_receipt"]["provider_response_sha256"])
            bound = a.read(step_dir / "cost-bound.json")
            if Decimal(receipt["cost_usd"]) > Decimal(bound["reserved_usd"]):
                item["status"] = "bound_violated"
            atomic(root / "ledger.json", ledger)
        if item["status"] != "settled":
            raise ValueError("Unresolved billed call requires charge reconciliation")


def check_improvement_compatibility(ev, problem, code, result, state, baseline, step_dir):
    """Mark primary-only exploration honestly; defer other versions to selection."""
    result = json.loads(a.canonical(result))
    result["compatibility_check"] = {"status": "deferred_until_final_selection", "valid": None}
    return result


def candidate_diagnosis(raw, rejection, result, step_dir, output, config):
    compatible = (result or {}).get("compatibility_check")
    if compatible and compatible.get("valid") is False:
        path = Path(compatible["path"])
        # Diagnose the failed version's actual source/log, not the successful
        # primary measurement retained for ranking.
        return diagnostics.evaluation(a.read(path), path.parent, output, "candidate")
    return h.step_diagnosis(raw, rejection, result, step_dir, output, config)


def compact_worker_failure(exc):
    """Release failed worker frames that can otherwise retain library maps."""
    report = {"error_type": type(exc).__name__, "message": str(exc)[:1000]}
    pending, seen = [exc], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        pending.extend(value for value in (current.__context__, current.__cause__) if value is not None)
        traceback.clear_frames(current.__traceback__)
        current.__traceback__ = None
        current.__context__ = None
        current.__cause__ = None
    return report


def run_problem(root, row):
    root = Path(root)
    require_policy(root)
    output = folder(root, row)
    with locked(output / "problem.lock", blocking=False):
        verify_frozen(root)
        if a.read(output / "preflight.json")["status"] != "ready":
            raise ValueError("Problem lacks ready preflight")
        if (output / "summary.json").exists():
            return a.read(output / "summary.json")
        ev = evaluator(root)
        problem = a.read(output / "input/problem.json")
        config = a.read(output / "input/config.json")
        prompt = (output / "input/prompt.txt").read_text()
        state = a.read(output / "state.json")
        baseline = a.read(output / "baseline/result.json")
        atomic(output / "progress.json", {"status": "running", "at": now(), "row": row})
        try:
            initial_fingerprints = ev.verify_environments(problem, full=True)
            initial_receipt = output / "initial-environment-fingerprints.json"
            if initial_receipt.exists():
                initial_receipt.rename(initial_receipt.with_name("initial-environment-fingerprints-before-resume-" + str(time.time_ns()) + ".json"))
            atomic(initial_receipt, {"full_content_verification": True, "verified_at": now(),
                                     "environments": initial_fingerprints})
            while not h.cost_threshold_reached(state, config) and not h.portfolio.finished(state):
                step = state["step"] + 1
                step_dir = output / "steps" / f"{step:04}"
                step_dir.mkdir(parents=True, exist_ok=True)
                recover_pending(root, row, step, step_dir)
                body = make_request(state, problem, config, prompt)
                if (not (step_dir / "response.json").exists() and h.portfolio.enabled(config)
                        and h.portfolio.budget_phase(state["portfolio"], config)):
                    # Budget-ended merger: never start a call whose worst-case cost could cross the cap.
                    bound = Decimal(transport.request_cost(body)["reserved_usd"])
                    if Decimal(state["cost_usd"]) + bound > Decimal(str(config["limits"]["cost_stop_usd"])):
                        try:
                            step_dir.rmdir()
                        except OSError:
                            pass
                        break
                if (step_dir / "response.json").exists():
                    if a.read(step_dir / "request.json") != body:
                        raise ValueError("Saved pending request differs from reconstructed state")
                    raw = a.read(step_dir / "response.json")
                else:
                    raw = dispatch(root, row, step, body, config["model"], step_dir)
                atomic(step_dir / "usage.json", accounting.response_record(raw))
                action, code, observation, rejection = h.prepare_response(raw, state, problem, config, output)
                result = None
                if code is not None:
                    (step_dir / "candidate.lean").write_text(code)
                    evaluation = step_dir / "evaluation/result.json"
                    if not evaluation.exists():
                        evaluate_cached(ev, code, problem, evaluation.parent, repetitions=1)
                    result = guard_compiler_signal(a.read(evaluation))
                    result = check_improvement_compatibility(ev, problem, code, result, state, baseline, step_dir)
                    atomic(step_dir / "selection-result.json", result)
                diagnosis = candidate_diagnosis(raw, rejection, result, step_dir, output, config)
                previous_sha = a.sha(a.canonical(state))
                state = h.advance(state, raw, code, result, rejection, h.metrics(baseline), config,
                                  str(output), diagnosis, action=action, observation=observation)
                atomic(step_dir / "event.json", {"step": step, "previous_state_sha256": previous_sha,
                    "state_sha256": a.sha(a.canonical(state)), "action": {k: v for k, v in (action or {}).items() if k != "proof"},
                    "rejection": rejection, "cost_usd_after": state["cost_usd"], "best_sha256": state["best"]["sha256"]})
                atomic(output / "state.json", state)
                atomic(output / "progress.json", {"status": "running", "row": row, "step": step,
                    "cost_usd": state["cost_usd"], "best": {k: v for k, v in state["best"].items() if k != "code"}, "at": now()})
                if state["unknown_cost"] or (result and h.environment_failed(result)):
                    raise ValueError("Unknown model cost or evaluator environment failure")
            # Score/compatibility selection happens after exploration without additional API spend.
            unique = {value["sha256"]: value for value in state["exploration"]["candidates"].values() if value["valid"]}
            ranked = sorted(unique.values(), key=h.ranking)
            selected, checked = None, None
            for rank, value in enumerate(ranked):
                check = output / "compatibility" / value["sha256"] / "result.json"
                if not check.exists():
                    evaluate_cached(ev, value["code"], problem, check.parent, repetitions=1,
                                    all_versions=True, trusted_reference=value["sha256"] == a.sha(problem["reference"]))
                result = guard_compiler_signal(a.read(check))
                if h.environment_failed(result) or any((value.get("error") or {}).get("kind") == "timeout"
                                                      for value in result.get("environments", {}).values()):
                    raise ValueError("Final compatibility environment/resource failure; inspect before retry")
                if result["valid"]:
                    selected, checked = value, result
                    break
            if selected is None:
                raise ValueError("No all-version compatible final candidate")
            (output / "selected.lean").write_text(selected["code"])
            final = output / "final/result.json"
            if not final.exists():
                evaluate_cached(ev, selected["code"], problem, final.parent, repetitions=3,
                                trusted_reference=selected["sha256"] == a.sha(problem["reference"]), fresh=True)
            measured = h.metrics(a.read(final))
            if measured is None:
                raise ValueError("Selected candidate failed fresh final verification/measurement")
            fingerprints = ev.verify_environments(problem, full=True)
            atomic(output / "final/environment-fingerprints.json", {"full_content_verification": True,
                    "verified_at": now(), "environments": fingerprints})
            summary = {"row": row, "id": problem["id"], "name": problem["name"], "status": "completed",
                       "stop_reason": (h.portfolio.stop_reason(state, config) if h.portfolio.finished(state) else
                                       "portfolio_budget_complete" if h.portfolio.enabled(config)
                                       and h.portfolio.completed(state, config) else "cost_limit"),
                       "cost_usd": state["cost_usd"], "calls": state["calls"],
                       "baseline": h.metrics(baseline), "selected": {k: v for k, v in selected.items() if k != "code"},
                       "final": measured, "all_versions_valid": checked["valid"], "official_evaluation": False,
                       "finished_at": now(), "verification_policy": VERIFICATION_POLICY}
            if h.portfolio.enabled(config):
                summary["portfolio"] = h.portfolio.summary(state, config)
                if not summary["portfolio"]["complete"]:
                    summary["status"] = "stopped"
            summary.update(cost_basis="provider-token-usage-times-frozen-public-list-prices", invoice_verified=False,
                           provider="OpenAI direct", model=MODEL["id"])
            atomic(output / "summary.json", summary)
            atomic(output / "progress.json", {"row": row, "status": summary["status"], "cost_usd": state["cost_usd"], "at": now()})
            print(json.dumps({"row": row, "status": summary["status"], "cost_usd": state["cost_usd"], "calls": state["calls"]}), flush=True)
            return summary
        except Exception as exc:
            atomic(output / "progress.json", {"row": row, "status": "stopped", "error_type": type(exc).__name__,
                                               "message": str(exc)[:2000], "cost_usd": state["cost_usd"], "at": now()})
            raise


def run_with_preflight(root, row, ensure=False):
    if ensure:
        path = folder(root, row) / "preflight.json"
        if not path.exists() or a.read(path).get("status") != "ready":
            preflight(root, [row])
    return run_problem(root, row)


def status(root):
    root = Path(root).resolve()
    ledger = a.read(root / "ledger.json")
    rows = []
    for row in a.read(root / "authorization.json")["rows"]:
        output = folder(root, row)
        path = output / "progress.json"
        item = a.read(path) if path.exists() else {"status": "prepared"}
        rows.append({"row": row, "status": item["status"], "cost_usd": str(problem_spend(ledger, row)),
                     **({"step": item["step"]} if "step" in item else {})})
    report = {"rows": rows, "total_known_usd": str(sum((problem_spend(ledger, row["row"]) for row in rows), Decimal(0))),
              "completed": sum(row["status"] == "completed" for row in rows), "attempts": len(ledger["attempts"]),
              "unsettled": {key: value for key, value in ledger["attempts"].items() if value["status"] != "settled"}}
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "inputs", "seal", "preflight", "run", "status", "reseal"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rows", nargs="+", type=int)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=None)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--ensure-preflight", action="store_true",
                        help="Finish each problem's no-API baseline checks before its first paid request")
    policy = parser.add_mutually_exclusive_group()
    policy.add_argument("--portfolio", dest="portfolio", action="store_true", default=None,
                        help="Use isolated scouts then merger (default for new inputs)")
    policy.add_argument("--no-portfolio", dest="portfolio", action="store_false",
                        help="Prepare legacy single-context inputs instead of scouts/merger")
    parser.add_argument("--scout-evaluations", type=int, default=None)
    parser.add_argument("--merger-evaluations", type=int, default=None)
    parser.add_argument("--rounds", type=int, default=None,
                        help="Repeat scouts then merger this many times; later scouts start from the incumbent")
    parser.add_argument("--merger-until-budget", action="store_true",
                        help="Let the last merger run until the per-problem budget instead of its evaluation count")
    parser.add_argument("--strategy-bank", type=Path,
                        help="Freeze an optional Bank JSON in new prepare/inputs configurations")
    parser.add_argument("--strategy-top-k", type=int, choices=(1, 2, 3), default=None)
    parser.add_argument("--strategy-contextual", action="store_true")
    parser.add_argument("--strategy-search-policy", choices=("guided", "alternating-v1"), default=None)
    args = parser.parse_args()
    bank_settings = UNSPECIFIED_STRATEGY
    if args.strategy_bank or args.strategy_top_k is not None or args.strategy_contextual or args.strategy_search_policy:
        if args.command not in ("prepare", "inputs") or args.strategy_bank is None:
            parser.error("Bank settings require --strategy-bank and fresh prepare/inputs")
        bank_settings = {"bank": a.read(args.strategy_bank),
                         "top_k": 3 if args.strategy_top_k is None else args.strategy_top_k,
                         "contextual": args.strategy_contextual,
                         "search_policy": args.strategy_search_policy or "guided"}
        h.strategy_bank.validate_settings(bank_settings)
    settings = UNSPECIFIED_PORTFOLIO
    custom_quotas = (args.scout_evaluations is not None or args.merger_evaluations is not None
                     or args.rounds is not None or args.merger_until_budget)
    if args.portfolio is not None or custom_quotas:
        if args.command not in ("prepare", "inputs"):
            parser.error("Portfolio settings apply only to prepare/inputs on a fresh root")
        if args.portfolio is False and custom_quotas:
            parser.error("Scout/merger quotas, rounds and budget merging cannot be used with --no-portfolio")
    if args.portfolio is False:
        settings = None
    elif args.portfolio is True or custom_quotas:
        settings = {"progress_guard": "bounded-v1",
                    "scout_evaluations": 6 if args.scout_evaluations is None else args.scout_evaluations,
                    "merger_evaluations": 22 if args.merger_evaluations is None else args.merger_evaluations}
        if args.rounds is not None:
            settings["rounds"] = args.rounds
        if args.merger_until_budget:
            settings["merger_until_budget"] = True
        h.portfolio.validate(settings)
    root = args.root.resolve()
    require_policy(root)
    rows = rows_from(args)
    if args.command == "prepare":
        prepare(root, rows, workers=args.workers or 2, portfolio_settings=settings,
                strategy_settings=bank_settings)
    elif args.command == "inputs":
        prepare_inputs(root, rows, workers=args.workers or 1, portfolio_settings=settings,
                       strategy_settings=bank_settings)
    elif args.command == "seal":
        seal_inputs(root, rows)
    elif args.command == "preflight":
        preflight(root, rows)
    elif args.command == "status":
        status(root)
    elif args.command == "reseal":
        reseal(root)
    else:
        verify_frozen(root)
        if args.key_file:
            os.environ["OPENAI_API_KEY"] = transport.load_key(args.key_file)
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("Missing explicitly configured OpenAI credentials")
        failed = []
        with ThreadPoolExecutor(max_workers=args.workers or 1) as pool:
            futures = {pool.submit(run_with_preflight, root, row, args.ensure_preflight): row for row in rows}
            for future in as_completed(futures):
                row = futures.pop(future)
                try:
                    if future.result()["status"] != "completed":
                        failed.append(row)
                except Exception as exc:
                    failed.append(row)
                    print(json.dumps({"row": row, "status": "stopped", **compact_worker_failure(exc)}), flush=True)
        status(root)
        if failed:
            raise ValueError("Stopped rows: " + str(failed))


if __name__ == "__main__":
    main()
