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
import warm_start
import prompt_variants
DATASET_SHA = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"
MODEL = {"backend": "openai", "id": "gpt-6.1-sol", "provider": "openai",
         "reasoning_effort": "high", "max_tokens": 8192, "timeout_seconds": 900,
         "seed": 42}
TARGET = Decimal("1.00")
VERIFICATION_POLICY = warm_start.POLICY
DEFAULT_PORTFOLIO = {"scout_evaluations": 6, "merger_evaluations": 22, "progress_guard": "bounded-v1"}
# Omitted policy uses new-run defaults but preserves already prepared inputs.
# Explicit None selects the single-context path (--no-portfolio) and
# preserves legacy single-context inputs during validation.
UNSPECIFIED_PORTFOLIO = object()
UNSPECIFIED_STRATEGY = object()
MAX_COMPILER_PARALLELISM = 8
# Re-evaluations evaluate_cached may run after a machine-produced failure (ARENA_EVALUATION_RETRIES
# overrides), and the pause before each one.
EVALUATION_RETRIES = 2
EVALUATION_RETRY_PAUSE_SECONDS = 15
# Lean's allocator bound (-M) ends a run with lean::memory_exception; bubblewrap reports the abort as exit 134.
ALLOCATOR_ABORT_MARKERS = ("lean::memory_exception", "memory exception", "excessive memory consumption")

# final60 hooks (lean_agent.final60 orchestrator; one OpenRouter root per row).
# Every final60 branch is taken only for a model with backend "openrouter", a row
# whose inputs carry input/final60.json, or a root sealed with provider OpenRouter.
# OpenAI-direct roots keep the code paths above and below unchanged.
FINAL60_PROVIDER = "OpenRouter"
# Sealed transports of a final60 root (lean_agent.final60.transports.NAMES): openrouter (the entry),
# mock (dry runs) and openai (the OpenAI-direct development wire). Legacy OpenAI roots seal no transport.
FINAL60_TRANSPORTS = ("openrouter", "openai", "mock")
FINAL60_SCHEMA = "final60-v1"
FINAL60_MAX_CAP = Decimal("2.99")
FINAL60_MONEY_FILES = ("contracts.py", "catalog.py", "transport.py", "ledger.py", "money.py")
FINAL60_STOP_REASONS = ("skip_llm", "stop_exploration", "api_disabled", "row_api_frozen",
                        "ledger_budget_exceeded", "salvage")
FINAL60_COST_BASIS = "max(openrouter-usage-cost, cache-aware-public-list-price); lost responses at their bound"


class Final60Stop(Exception):
    """A clean end of paid exploration for one row; final selection still runs."""

    def __init__(self, reason, detail=None):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def transport_for(config):
    """final60 hook 1: the frozen model backend selects the transport module.

    OpenRouter models use openrouter_transport (real HTTP or the sealed dry-run mock). An OpenAI
    model of a final60 row sealed with transport ``openai`` (FINAL60_TRANSPORT, which the
    orchestrator sets per row worker) uses the OpenAI-direct development adapter, whose proofs
    are never submitted; legacy OpenAI roots keep openai_transport.
    """
    model = config.get("model", config) if isinstance(config, dict) else {}
    if isinstance(model, dict) and model.get("backend") == "openrouter":
        import openrouter_transport
        return openrouter_transport
    if isinstance(model, dict) and model.get("backend") == "openai" and os.environ.get("FINAL60_TRANSPORT") == "openai":
        import openai_direct_transport
        return openai_direct_transport
    return transport


def final60_transport_name(settings):
    """The sealed transport of final60 settings/authorization: openrouter, openai or mock (dry runs)."""
    name = settings.get("transport")
    if name is None:
        name = "mock" if settings.get("dry_run") else "openrouter"
    if name == "openrouter" and settings.get("dry_run"):
        name = "mock"
    return name


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
                             cache_root=Path(root) / "evaluation-cache",
                             compiler_parallelism=compiler_parallelism(root))


def validated_parallelism(value, source):
    if type(value) is bool or not str(value).strip().isdigit() or not 1 <= int(value) <= MAX_COMPILER_PARALLELISM:
        raise ValueError(f"{source} must be a whole number of compiler slots from 1 to {MAX_COMPILER_PARALLELISM}")
    return int(value)


def final60_root(root):
    """A root sealed by the final60 branch of seal_inputs, whatever its sealed transport.

    OpenRouter (real or mock) and OpenAI-direct development roots all take the final60 paths
    (hooks 2, 3 and 7: ledgered dispatch, stop reasons, no-resend recovery). Keying on the
    provider name alone sent OpenAI-direct roots down the legacy path, where a worker restart
    crashed forever in recover_pending and the row clock/salvage flags were never read (smoke).
    """
    path = Path(root) / "authorization.json"
    if not path.exists():
        return False
    authorization = a.read(path)
    return (authorization.get("provider") == FINAL60_PROVIDER
            or authorization.get("final60_schema") == FINAL60_SCHEMA
            or authorization.get("transport") in FINAL60_TRANSPORTS)


def final60_inputs(root):
    return final60_root(root) or any(Path(root).glob("problems/F[0-9][0-9][0-9]/input/final60.json"))


FINAL60_POOL_RULE = "final60 roots require 2..8 shared compiler slots (FINAL60_COMPILER_SLOTS or sealed compiler_slots)"


def compiler_parallelism(root):
    """Compiler-pool size for this root (final60 hook 5).

    Precedence: ARENA_COMPILER_PARALLELISM, then FINAL60_COMPILER_SLOTS (the orchestrator's name
    for the same operator override; a frozen authorization cannot change on a restart), then the
    sealed authorization (compiler_slots on a final60 root, max_lean_parallel on a legacy root),
    then the final60 row settings' compiler_slots. Legacy roots keep the serial default (1). A
    final60 process never falls back to the exclusive legacy lock: one exclusive holder would
    stall every pooled compiler on the shared lock file, so such roots fail closed below 2. The
    value only sizes the pool: resources.compiler_slot admits every compiler, and in particular
    a fourth or later one, through its memory gate.
    """
    final60 = final60_inputs(root)
    value = source = None
    for name in ("ARENA_COMPILER_PARALLELISM", "FINAL60_COMPILER_SLOTS"):
        raw = os.environ.get(name)
        if raw not in (None, ""):
            value, source = raw, name
            break
    authorization = Path(root) / "authorization.json"
    if value is None and authorization.exists():
        field = "compiler_slots" if final60 else "max_lean_parallel"
        value, source = a.read(authorization).get(field), f"authorization.json {field}"
    if value is None and final60:
        settings = sorted(Path(root).glob("problems/F[0-9][0-9][0-9]/input/final60.json"))
        value, source = (a.read(settings[0]).get("compiler_slots") if settings else None), "final60.json compiler_slots"
    if value is None:
        if final60:
            raise ValueError(FINAL60_POOL_RULE)
        return 1
    try:
        slots = validated_parallelism(value, source)
    except ValueError:
        if final60:
            raise ValueError(FINAL60_POOL_RULE + f" ({source} is {value!r})")
        raise
    if final60 and slots < 2:
        raise ValueError(FINAL60_POOL_RULE + f" ({source} is {value!r})")
    return slots


def compiler_pool_size(root):
    """Alias of compiler_parallelism for callers whose keyword of that name shadows the function."""
    return compiler_parallelism(root)


def sealed_compiler_parallelism(requested=None):
    """The pool size to seal: the explicit request, else ARENA_COMPILER_PARALLELISM, else 1."""
    if requested is not None:
        return validated_parallelism(requested, "--compiler-parallelism")
    override = os.environ.get("ARENA_COMPILER_PARALLELISM")
    return validated_parallelism(override, "ARENA_COMPILER_PARALLELISM") if override not in (None, "") else 1


def folder(root, row):
    return Path(root) / "problems" / f"F{row:03}"


def rows_from(args):
    values = args.rows or list(range(1, 61))
    if len(set(values)) != len(values) or any(value < 1 or value > 60 for value in values):
        raise ValueError("Expected unique final problem rows 1..60")
    return values


def implementation_files(final60=False):
    files = [h.BASE / name for name in h.CODE_FILES]
    files.extend(path for path in HERE.glob("*.py"))
    files.append(REPO / "experiments/proof-analyze/proof_tokens.py")
    if final60:
        # The OpenRouter money path is frozen with the run (missing files fail the seal).
        files.extend(h.BASE / "final60" / name for name in FINAL60_MONEY_FILES)
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


def prompt_text(context, variant="baseline", strict_cap=False, addendum=""):
    prompt_variants.policy(variant, strict_cap)
    base = (REPO / "examples/actions/prompt.txt").read_text()
    budget = ("Every action consumes paid model budget. The controller reserves each request and stops before exceeding the configured hard_budget.cap_usd. "
              if strict_cap else "Every action consumes paid model budget. The controller stops at the configured settled-cost threshold in budget.stop_at_usd. ")
    # final60 hook 4: frozen routing hints (empty for every legacy root, so its prompt is unchanged).
    hints = addendum.rstrip("\n") + "\n" if addendum else ""
    return base + "\n" + prompt_variants.VARIANTS[variant] + (
        "Search is lexical evidence only, not a theorem-prover or availability guarantee. ") + budget + (
        "The exact statement and original full source context are preserved by the evaluator. "
        "Exploration feedback verifies only the primary version; it does not establish cross-version compatibility. "
        "At final selection the controller checks candidates in score order against every required version, "
        "falling back to another candidate if needed. All listed versions must accept the final candidate. "
        "No extra imports or helper declarations.\n" + hints +
        "<original_context>\n" + context + "\n</original_context>\n")


def make_request(state, problem, config, prompt):
    # Assemble without truncating the live archive; compact only the wire copy.
    assembly = {**config, "limits": {**config["limits"], "max_request_characters": 2000000}}
    common = h.make_request(state, problem, assembly, prompt)
    wire = transport_for(config)
    body = wire.payload(common["messages"], config["model"])
    def fits():
        if len(a.canonical(body)) > config["limits"]["max_request_characters"]:
            return False
        try:
            wire.request_cost(body)
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


def evaluation_retries():
    raw = os.environ.get("ARENA_EVALUATION_RETRIES")
    if raw in (None, ""):
        return EVALUATION_RETRIES
    if not raw.isdigit() or int(raw) > 10:
        raise ValueError("ARENA_EVALUATION_RETRIES must be a whole number from 0 to 10")
    return int(raw)


def retryable_evaluation(result, options):
    """Whether a result was produced by the machine rather than by the candidate, so it is retried.

    Environment failures are retried: a missing sandbox, an allocator abort, a signal death, a
    memory-gate timeout. A compile the driver timed out is retried only for the trusted
    reference, whose compile time is known; for a candidate it is the candidate's feedback.
    """
    guarded = guard_compiler_signal(result)
    rows = list(guarded.get("environments", {}).values())
    if any((row.get("error") or {}).get("kind") == "timeout" for row in rows):
        return bool(options.get("trusted_reference"))
    return h.environment_failed(guarded)


def evaluate_cached(ev, code, problem, destination, **kwargs):
    """A crash during Lean work can be retried without repeating the API call.

    A saved result the machine produced (retryable_evaluation) is never reused: it is archived next
    to the destination as <name>-environment-failed-<ns> and measured again, so a restarted worker
    retries it. A fresh failure of the same kind is retried in-process up to ARENA_EVALUATION_RETRIES
    (default 2) more times, pausing in between. A result without its receipt is an interrupted
    evaluation and is measured again. Candidate verdicts are reused as before.
    """
    destination = Path(destination)
    path = destination / "result.json"
    receipt = destination / "evaluation-request.json"
    expected = {"candidate_sha256": a.sha(code), "problem": problem, "options": kwargs}
    retries, fresh = evaluation_retries(), False
    while True:
        if path.exists() and receipt.exists():
            if a.read(receipt) != expected:
                raise ValueError("Saved evaluation belongs to a different candidate/problem/policy")
            result = a.read(path)
            if not retryable_evaluation(result, kwargs) or (fresh and retries < 1):
                return result
            destination.rename(destination.with_name(destination.name + "-environment-failed-" + str(time.time_ns())))
            if fresh:
                retries -= 1
                time.sleep(EVALUATION_RETRY_PAUSE_SECONDS)
        elif destination.exists():
            destination.rename(destination.with_name(destination.name + "-incomplete-" + str(time.time_ns())))
        result = ev.evaluate(code, problem, destination, **kwargs)
        fresh = True
        atomic(receipt, expected)
        atomic(path, result)


def environment_abort(environment):
    """A saved per-environment result the machine ended (allocator abort, signal death); else None.

    The on-disk twin of evaluator.compiler_abort, so results written by older evaluators as
    "compile" failures are reclassified too. Lean's -M bound raises lean::memory_exception and
    aborts: returncode -SIGABRT when lean is the direct child, exit 134 under bubblewrap. Such a
    run says nothing about the proof: it is an environment failure that evaluate_cached retries,
    the cache refuses and the model never sees as feedback. A run the driver timed out keeps the
    evaluator's "timeout" verdict.
    """
    error = environment.get("error") or {}
    runs = [run for run in environment.get("runs", [])
            if type(run.get("returncode")) is int and not run.get("timed_out")]
    killed = [run for run in runs if run["returncode"] < 0 or run["returncode"] > 128]
    message = str(error.get("message", "")).lower()
    allocator = (any(marker in message for marker in ALLOCATOR_ABORT_MARKERS)
                 or any(run["returncode"] in (134, -signal.SIGABRT) for run in killed))
    if not allocator and not killed:
        return None
    failed = [run for run in runs if run["returncode"]]
    bounds = [part[2:] for part in (failed[-1].get("command", []) if failed else [])
              if isinstance(part, str) and part.startswith("-M") and part[2:].isdigit()]
    limit = int(bounds[0]) if len(bounds) == 1 else None
    signal_number = None
    if killed:
        signal_number = -killed[0]["returncode"] if killed[0]["returncode"] < 0 else killed[0]["returncode"] - 128
    description = ("Lean allocator abort" + (f" under -M{limit}" if limit else "") if allocator
                   else f"compiler terminated by signal {signal_number}")
    return {"kind": "environment", "resource": "lean_allocator_limit" if allocator else "compiler_signal",
            "retryable": True, "signal": signal_number, "limit_mib": limit,
            "message": f"Environment abort ({description}): retry; never candidate feedback.\n"
                       + str(error.get("message", ""))}


def guard_compiler_signal(result):
    """Re-read a saved result so that a machine event never passes as a verdict on the candidate."""
    value = json.loads(a.canonical(result))
    for environment in value.get("environments", {}).values():
        error = environment.get("error") or {}
        if error.get("kind") == "environment":
            continue  # already classified by the evaluator (sandbox, allocator abort, host failure)
        # environment_abort covers the bwrap sandbox's exit 134 (128 + SIGABRT) as well as -6 (lesson 4).
        abort = environment_abort(environment)
        if abort is None:
            resource_error = any(phrase in str(error.get("message", "")).lower()
                                 for phrase in ("maximum memory consumption reached", "out of memory", "allocation failed"))
            if not resource_error:
                continue
            abort = {"kind": "environment", "resource": "memory", "retryable": True,
                     "message": "Compiler ran out of memory: retry; never candidate feedback.\n" + str(error.get("message", ""))}
        environment.update(valid=False, error=abort)
        value.update(valid=False, error=abort)
    return value


def evaluate_automatic(ev, code, problem, destination):
    """Apply the batch's existing process/resource policy to derived proofs too."""
    measured = evaluate_cached(ev, code, problem, destination, repetitions=1)
    guarded = guard_compiler_signal(measured)
    if guarded != measured:
        atomic(destination / "compiler-result.json", measured)
        atomic(destination / "result.json", guarded)
    return guarded


INPUT_FILES = ("problem.json", "config.json", "action-corpus.json", "context-metadata.json", "prompt.txt", "warm-start.json", "prompt-policy.json")


def configuration(problem, portfolio_settings=UNSPECIFIED_PORTFOLIO, autosolver_settings=None,
                  strategy_settings=None, *, strict_cap=False):
    if portfolio_settings is UNSPECIFIED_PORTFOLIO:
        portfolio_settings = DEFAULT_PORTFOLIO
    model = {**MODEL, "max_tokens": 16384 if len(problem["reference"]) > 12000 else 8192}
    config = {"schema_version": 1, "model": model,
        "limits": {"max_calls": None, "cost_stop_usd": str(TARGET),
                   "max_proof_characters": max(24000, len(problem["reference"]) * 3),
                   "max_feedback_characters": 7000, "max_request_characters": 190000},
        "agent": {"mode": "actions-v1", "corpus": "action-corpus.json", "history_limit": 4,
                  "candidate_limit": 8, "allow_finish": False, "persistent_memory": True}}
    if strict_cap:
        config["limits"]["cost_cap_usd"] = str(TARGET)
    if portfolio_settings is not None:
        h.portfolio.validate(portfolio_settings)
        config["agent"].update(portfolio=dict(portfolio_settings), approach_policy="exchange-v1")
    if autosolver_settings is not None:
        h.autosolver.validate(autosolver_settings)
        config["agent"]["autosolver"] = dict(autosolver_settings)
    if strategy_settings is not None:
        h.strategy_bank.validate_settings(strategy_settings)
        config["agent"]["strategy_bank"] = json.loads(a.canonical(strategy_settings))
    return config


def final60_settings(root, row):
    path = folder(root, row) / "input/final60.json"
    return a.read(path) if path.is_file() else None


def final60_configuration(problem, settings):
    """final60 hook 4: the frozen route replaces the module defaults ($1 target, OpenAI model)."""
    model = dict(settings["model"])
    if len(problem["reference"]) > 12000:
        model["max_tokens"] = max(model["max_tokens"], 16384)
    cap = str(Decimal(settings["effective_cap_usd"]))
    config = {"schema_version": 1, "model": model,
        "limits": {"max_calls": None, "cost_stop_usd": cap, "cost_cap_usd": cap,
                   "max_proof_characters": max(24000, len(problem["reference"]) * 3),
                   "max_feedback_characters": 7000, "max_request_characters": 190000},
        "agent": {"mode": "actions-v1", "corpus": "action-corpus.json", "history_limit": 4,
                  "candidate_limit": 8, "allow_finish": False, "persistent_memory": True}}
    if settings.get("portfolio") is not None:
        h.portfolio.validate(settings["portfolio"])
        config["agent"].update(portfolio=dict(settings["portfolio"]), approach_policy="exchange-v1")
    return config


def final60_validate(inputs, settings, problem, policy):
    """Reject any final60 input that could seed, overspend or leave OpenRouter."""
    if settings.get("schema") != FINAL60_SCHEMA or settings.get("row") != problem["row"]:
        raise ValueError("Unexpected final60 input schema or row")
    route = inputs / "route.json"
    if not route.is_file() or a.sha(route.read_bytes()) != settings.get("route_sha256"):
        raise ValueError("final60 route.json is missing or differs from final60.json")
    cap, prior = Decimal(settings["cap_usd"]), Decimal(settings["prior_cost_usd"])
    effective = Decimal(settings["effective_cap_usd"])
    if not (0 < cap <= FINAL60_MAX_CAP) or prior < 0 or effective != cap - prior or effective <= 0:
        raise ValueError("final60 cap must be 0 < cap - declared prior spend <= 2.99")
    model = settings["model"]
    name = final60_transport_name(settings)
    if name not in ("openrouter", "openai", "mock"):
        raise ValueError("final60 transport must be openrouter, openai or mock")
    if name == "openai":
        if model.get("backend") != "openai" or settings.get("dry_run"):
            raise ValueError("final60 transport openai requires the pinned OpenAI-direct model (development only)")
    elif model.get("backend") != "openrouter" or not model.get("provider") or "max_price" not in model:
        raise ValueError("final60 requires a pinned OpenRouter model with price ceilings")
    if not policy["strict_cap"]:
        raise ValueError("final60 requires the strict per-request budget reservation")
    if settings.get("skip_llm") is not (settings.get("portfolio") is None):
        raise ValueError("final60 skip_llm rows have no portfolio; LLM rows require one")
    addendum = settings.get("prompt_addendum", "")
    if not isinstance(addendum, str) or len(addendum) > 2000 or "original_context>" in addendum:
        raise ValueError("final60 prompt addendum is oversized or contains a context marker")
    if settings.get("screening", "check-and-measure") not in ("check-and-measure", "single-pass"):
        raise ValueError("final60 screening must be check-and-measure or single-pass")
    if a.read(inputs / "warm-start.json").get("candidate") is not None:
        raise ValueError("final60 never warm-starts from historical proofs")


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
    policy = a.read(inputs / "prompt-policy.json")
    if policy != prompt_variants.policy(**policy):
        raise ValueError("Invalid frozen prompt policy")
    settings = final60_settings(root, row)
    if settings is not None:
        final60_validate(inputs, settings, problem, policy)
        expected = final60_configuration(problem, settings)
    else:
        expected = configuration(problem, config.get("agent", {}).get("portfolio"), config.get("agent", {}).get("autosolver"),
                                 config.get("agent", {}).get("strategy_bank"), strict_cap=policy["strict_cap"])
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
    marker = "<original_context>\n"
    ending = "\n</original_context>\n"
    if marker not in prompt or not prompt.endswith(ending):
        raise ValueError("Prompt lacks frozen original context")
    context = prompt.split(marker, 1)[1][:-len(ending)]
    addendum = settings.get("prompt_addendum", "") if settings is not None else ""
    if prompt != prompt_text(context, policy["variant"], policy["strict_cap"], addendum):
        raise ValueError("Prompt differs from its frozen variant policy")
    h.portfolio.validate_shared_inputs(config, problem["reference"], prompt, corpus)
    seed = a.read(inputs / "warm-start.json")
    warm_start.validate(seed, problem)
    if h.portfolio.enabled(config):
        if seed["candidate"] is not None:
            raise ValueError("Warm-start cannot bypass portfolio isolation")
    return problem


def requested_prompt_policy(saved, variant, strict_cap):
    """Only explicit flags may change an existing preparation's prompt policy."""
    defaults = saved or prompt_variants.policy()
    return prompt_variants.policy(defaults["variant"] if variant is None else variant,
                                  defaults["strict_cap"] if strict_cap is None else strict_cap)


def prepare_inputs(root, rows, workers=1, portfolio_settings=UNSPECIFIED_PORTFOLIO, autosolver_settings=None,
                   strategy_settings=UNSPECIFIED_STRATEGY, *, warm_start_manifest=None, cold_start=False,
                   prompt_variant=None, strict_cap=None):
    """Prepare disjoint row inputs only; no authorization, API ledger or seal."""
    if workers not in (1, 2):
        raise ValueError("Input preparation workers must be 1 or 2")
    root = Path(root).resolve()
    new_policy = requested_prompt_policy(None, prompt_variant, strict_cap)
    requested_portfolio = portfolio_settings
    if portfolio_settings is UNSPECIFIED_PORTFOLIO:
        portfolio_settings = DEFAULT_PORTFOLIO
    require_policy(root)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "frozen.json").exists():
        raise ValueError("Batch inputs are already sealed")
    if warm_start_manifest is not None and (cold_start or portfolio_settings is not None):
        raise ValueError("Explicit warm-start cannot combine with cold-start or isolated portfolio")
    manifest = Path(warm_start_manifest) if warm_start_manifest is not None else REPO / "dashboard/public/data/final-results.json"
    if warm_start_manifest is not None and not manifest.is_file():
        raise ValueError("Explicit warm-start manifest is missing")
    seed_reason = "explicit_cold_start" if cold_start else "portfolio_isolation" if portfolio_settings is not None else None
    if seed_reason or not manifest.is_file():
        seed_reason = seed_reason or "manifest_unavailable"
        manifest = None
    ev = evaluator(root)
    def write_row(row):
        with locked(folder(root, row) / "input.lock"):
            if (root / "frozen.json").exists():
                raise ValueError("Batch became sealed before input preparation")
            output = folder(root, row)
            inputs = output / "input"
            if all((inputs / name).is_file() for name in INPUT_FILES):
                problem = validate_inputs(root, row)
                saved_policy = a.read(inputs / "prompt-policy.json")
                if saved_policy != requested_prompt_policy(saved_policy, prompt_variant, strict_cap):
                    raise ValueError("Existing prompt/budget policy differs; use a fresh batch root")
                if requested_portfolio is not UNSPECIFIED_PORTFOLIO and a.read(inputs / "config.json")["agent"].get("portfolio") != portfolio_settings:
                    raise ValueError("Existing inputs have a different policy; use a fresh batch root")
                if autosolver_settings is not None and a.read(inputs / "config.json")["agent"].get("autosolver") != autosolver_settings:
                    raise ValueError("Existing AutoSolver policy differs; use a fresh batch root")
                if (warm_start_manifest is not None or cold_start) and a.read(inputs / "warm-start.json") != warm_start.snapshot(manifest, problem, reason=seed_reason):
                    raise ValueError("Existing warm-start differs; use a fresh batch root")
                if strategy_settings is not UNSPECIFIED_STRATEGY and a.read(inputs / "config.json")["agent"].get("strategy_bank") != strategy_settings:
                    raise ValueError("Existing inputs have a different Bank; use a fresh batch root")
                return {"row": row, "input_status": "reused"}
            inputs.mkdir(parents=True, exist_ok=True)
            problem = ev.load_problem(row)
            if problem.get("dataset_sha256") != DATASET_SHA:
                raise ValueError("Unexpected final dataset identity")
            settings = final60_settings(root, row)
            if settings is not None and (not cold_start or not new_policy["strict_cap"]
                                         or autosolver_settings is not None
                                         or strategy_settings is not UNSPECIFIED_STRATEGY):
                raise ValueError("final60 inputs require cold start, the strict cap and no Bank/AutoSolver")
            context = ev.source_context(problem)
            corpus = context["corpus"]
            actions.validate_corpus(corpus)
            text = context["prompt_context"]
            if len(text) > 40000:
                raise ValueError("Initial context exceeds bounded 40000 characters")
            atomic(inputs / "problem.json", problem)
            atomic(inputs / "warm-start.json", warm_start.snapshot(manifest, problem, reason=seed_reason))
            atomic(inputs / "config.json", final60_configuration(problem, settings) if settings is not None else
                   configuration(problem, portfolio_settings, autosolver_settings,
                   None if strategy_settings is UNSPECIFIED_STRATEGY else strategy_settings,
                   strict_cap=new_policy["strict_cap"]))
            atomic(inputs / "prompt-policy.json", new_policy)
            atomic(inputs / "action-corpus.json", corpus)
            atomic(inputs / "context-metadata.json", context.get("metadata", {}))
            (inputs / "prompt.txt").write_text(prompt_text(text, new_policy["variant"], new_policy["strict_cap"],
                                                           settings.get("prompt_addendum", "") if settings else ""))
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


def seal_inputs(root, rows, *, compiler_parallelism=None):
    """Seal already complete row inputs without repeating source retrieval.

    The authorization records max_lean_parallel, the compiler-pool size this run is configured
    for (sealed_compiler_parallelism); driver.evaluator reads it back, ARENA_COMPILER_PARALLELISM
    overrides it at run time.
    """
    root = Path(root).resolve()
    slots = sealed_compiler_parallelism(compiler_parallelism)
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
        policies = [a.read(folder(root, row) / "input/prompt-policy.json") for row in rows]
        if any(policy != policies[0] for policy in policies):
            raise ValueError("A batch must use one prompt and budget policy")
        settings = [final60_settings(root, row) for row in rows]
        final60 = any(value is not None for value in settings)
        if final60 and (any(value is None for value in settings)
                        or len({value["effective_cap_usd"] for value in settings}) != 1):
            raise ValueError("A final60 root seals only final60 rows with one per-problem cap")
        target = Decimal(settings[0]["effective_cap_usd"]) if final60 else TARGET
        authorization = {"dataset_sha256": DATASET_SHA, "rows": rows, "problem_count": len(rows),
                         "per_problem_target_usd": str(target), "nominal_total_usd": str(target * len(rows)),
                         "last_call_may_overshoot": not policies[0]["strict_cap"], "max_api_parallel": 2, "max_lean_parallel": slots,
                         "prompt_variant": policies[0]["variant"],
                         "no_automatic_retries": True, "created_at": now(),
                         "verification_policy": VERIFICATION_POLICY}
        if final60:
            # final60 hook 1: the sealed transport fixes provider and endpoint (PR #70 reads api_endpoint).
            # openrouter is the entry; mock (dry runs) and openai (development) are never submitted.
            from lean_agent.final60 import transports
            profile = transports.profile(final60_transport_name(settings[0]))
            if profile.name == "openai":
                import openai_direct_transport as wire
            else:
                wire = transport_for(settings[0]["model"])
            if not policies[0]["strict_cap"] or wire.ENDPOINT != profile.api_endpoint:
                raise ValueError("final60 roots must use the strict cap and the endpoint of the sealed transport")
            if profile.name != "openai" and not wire.ENDPOINT.startswith("https://openrouter.ai/"):
                raise ValueError("final60 roots must use the strict cap and the OpenRouter endpoint")
            # The keyword shadows the module function: the pool size is the explicit request, else the
            # root's own rule (environment override, else the row settings' compiler_slots; 2..8).
            pool = slots if compiler_parallelism is not None else compiler_pool_size(root)
            if pool < 2:
                raise ValueError(FINAL60_POOL_RULE)
            authorization.update(provider=profile.provider, api_endpoint=wire.ENDPOINT, transport=profile.name,
                                 submittable=profile.submittable,
                                 budget_cost_basis=getattr(wire, "COST_BASIS", FINAL60_COST_BASIS),
                                 final60_schema=FINAL60_SCHEMA,
                                 cap_usd=settings[0]["cap_usd"], prior_cost_usd=settings[0]["prior_cost_usd"],
                                 cost_ledger=settings[0].get("cost_ledger"),
                                 dry_run=bool(settings[0].get("dry_run")) or profile.dry_run,
                                 compiler_slots=pool, max_lean_parallel=pool,
                                 no_automatic_retries=False,
                                 retry_policy="unbilled HTTP errors only, recorded as $0 sub-attempts; billed or unknown outcomes are never re-sent")
            if not profile.submittable:
                authorization["development_only"] = ("proofs, candidates and prompts of this root are never submitted "
                                                     "and never seed, carry into or appear in an OpenRouter run")
        else:
            wire = transport
            authorization.update(provider="OpenAI direct", api_endpoint=transport.ENDPOINT,
                                 budget_cost_basis="provider-token-usage-times-frozen-public-list-prices")
        atomic(root / "authorization.json", authorization)
        atomic(root / "pricing.json", wire.PRICING)
        if not (root / "ledger.json").exists():
            atomic(root / "ledger.json", {"schema_version": 1, "attempts": {}})
        code = root / "code"
        code.mkdir(exist_ok=True)
        for path in implementation_files(final60):
            destination = code / path.relative_to(REPO)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        files = [*implementation_files(final60), root / "authorization.json", root / "pricing.json"]
        files.extend(path for path in (root / "problems").glob("*/input/*") if path.is_file())
        atomic(root / "frozen.json", {str(path): a.sha(path.read_bytes()) for path in files})
    print(json.dumps({"prepared": str(root), "rows": rows, "api_calls": 0}), flush=True)


def prepare(root, rows, workers=2, portfolio_settings=UNSPECIFIED_PORTFOLIO, autosolver_settings=None,
            strategy_settings=UNSPECIFIED_STRATEGY, *, warm_start_manifest=None, cold_start=False,
            prompt_variant=None, strict_cap=None, compiler_parallelism=None):
    require_policy(root)
    if (Path(root) / "frozen.json").exists():
        for row in rows:
            saved_policy = a.read(folder(root, row) / "input/prompt-policy.json")
            if saved_policy != requested_prompt_policy(saved_policy, prompt_variant, strict_cap):
                raise ValueError("Sealed prompt/budget policy differs; use a fresh batch root")
        if warm_start_manifest is not None or cold_start:
            raise ValueError("Warm-start options require a fresh unsealed root")
        if autosolver_settings is not None:
            for row in rows:
                config = a.read(folder(root, row) / "input/config.json")
                if config.get("agent", {}).get("autosolver") != autosolver_settings:
                    raise ValueError("Sealed AutoSolver policy differs; use a fresh batch root")
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
        seal_inputs(root, rows, compiler_parallelism=compiler_parallelism)
        return
    prepare_inputs(root, rows, workers=workers, portfolio_settings=portfolio_settings,
                   autosolver_settings=autosolver_settings, strategy_settings=strategy_settings,
                   warm_start_manifest=warm_start_manifest, cold_start=cold_start,
                   prompt_variant=prompt_variant, strict_cap=strict_cap)
    seal_inputs(root, rows, compiler_parallelism=compiler_parallelism)


def ensure_baseline(root, row, ev):
    output = folder(root, row)
    problem = a.read(output / "input/problem.json")
    config = a.read(output / "input/config.json")
    baseline_file = output / "baseline/result.json"
    # A saved baseline is reused, except one the machine failed (no sandbox, allocator abort):
    # on a restart evaluate_cached archives it and measures again instead of failing preflight forever.
    evaluate_cached(ev, problem["reference"], problem, output / "baseline",
                    repetitions=3, trusted_reference=True)
    result = guard_compiler_signal(a.read(baseline_file))
    state = h.initial_state(problem, result, config)
    seed_path = output / "input/warm-start.json"
    if seed_path.exists():
        seed = a.read(seed_path)
        warm_start.validate(seed, problem)
        if seed["candidate"] is not None:
            code = seed["candidate"]["code"]
            primary = guard_compiler_signal(evaluate_cached(ev, code, problem, output / "warm-start/primary",
                                                           repetitions=3, fresh=True))
            compatibility = guard_compiler_signal(evaluate_cached(ev, code, problem, output / "warm-start/compatibility",
                                                                 repetitions=1, all_versions=True))
            warm_start.seed_state(state, seed, problem, primary, compatibility)
    if (output / "initial-state.json").exists() and a.read(output / "initial-state.json") != state:
        raise ValueError("Saved initial state differs from current baseline/warm-start evidence")
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
    if final60_root(root):
        raise ValueError("final60 roots are never resealed; prepare a fresh row root")
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


def request_fits_budget(ledger, row, bound, cap):
    reserved = sum((Decimal(item["maximum_request_cost_usd"]) for item in ledger["attempts"].values()
                    if item["row"] == row and item["status"] == "pending"), Decimal(0))
    return problem_spend(ledger, row) + reserved + Decimal(bound["reserved_usd"]) <= Decimal(cap)


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


def final60_run_dir(root, row):
    settings = final60_settings(root, row) or {}
    return (Path(root) / settings.get("run_dir", "../..")).resolve()


def final60_flag(path, value):
    """Write a stop marker once; the first reason is kept."""
    if not Path(path).exists():
        atomic(path, {**value, "at": now()})


def final60_stop_reason(root, row):
    """final60 hook 3: reasons that end paid exploration before the next request."""
    root, settings = Path(root), final60_settings(root, row) or {}
    if settings.get("skip_llm"):
        return "skip_llm"
    run_dir = final60_run_dir(root, row)
    if (root / "api-disabled.json").exists() or (run_dir / "api-disabled.json").exists():
        return "api_disabled"
    if (root / "api-frozen.json").exists():
        return "row_api_frozen"
    if (root / "salvage.json").exists():
        return "salvage"
    if (root / "stop-exploration.json").exists() or (run_dir / "stop-exploration.json").exists():
        return "stop_exploration"
    return None


def final60_ledger(root, row=None):
    """The run's shared SQLite ledger (a mirror; ledger.json stays the audited truth).

    FINAL60_COST_LEDGER overrides the sealed path (one ledger shared across run dirs), as in
    openrouter_transport.ledger_path. With ``row`` the sealed prior_cost_usd (spend for this
    problem outside this root, e.g. a Smoke run) is declared before any reservation, so every
    HTTP sub-attempt, retries after lost responses included, is bounded by cap - prior; the
    declaration is idempotent and refuses a prior that disagrees with the locked ledger.
    """
    from lean_agent.final60 import ledger as cost_ledger
    authorization = a.read(Path(root) / "authorization.json")
    override = os.environ.get("FINAL60_COST_LEDGER")
    if not authorization.get("cost_ledger") and not override:
        raise ValueError("final60 root lacks its shared cost ledger")
    path = Path(override).resolve() if override else (Path(root) / authorization["cost_ledger"]).resolve()
    ledger = cost_ledger.CostLedger(path, cap_usd=Decimal(authorization["cap_usd"]))
    if row is not None:
        prior = Decimal(str(authorization.get("prior_cost_usd") or "0"))
        if not prior.is_finite() or prior < 0:
            raise ValueError("Invalid sealed prior_cost_usd")
        if prior:
            ledger.declare_prior(f"F{row:03}", prior, note="sealed authorization prior_cost_usd")
    return ledger


def final60_release(root, attempt):
    """Drop a reservation that provably reached no billable send ($0 or refused)."""
    with locked(Path(root) / "ledger.lock"):
        ledger = a.read(Path(root) / "ledger.json")
        if ledger["attempts"].get(attempt, {}).get("status") == "pending":
            ledger["attempts"].pop(attempt)
            atomic(Path(root) / "ledger.json", ledger)


def final60_plain(value):
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict
        value = asdict(value)
    return json.loads(json.dumps(value, default=str))


def final60_settle(root, row, step, bound, normalized, result, model):
    """One settled ledger.json attempt per driver step (report.py and PR #70 shape)."""
    root, attempt = Path(root), f"F{row:03}-{step:04}"
    receipt = getattr(result, "receipt", None)
    cost = Decimal(str(normalized["usage"]["cost"]))
    settled = Decimal(str(getattr(receipt, "cost_usd", cost)))
    charged = max(cost, settled)
    usage = normalized.get("usage") or {}
    completion = usage.get("completion_tokens")
    cost_receipt = normalized.get("_cost_receipt") or {}
    if "bound_violated" in cost_receipt:
        # money.dispatch_guarded checks every HTTP sub-attempt (cost and completion tokens) against
        # the single-request bound and the audit compares this flag with that evidence. The step
        # total legitimately exceeds one bound after a lost sub-attempt charged at its bound, so
        # recomputing the flag from the total froze the row and failed its audit (verify3).
        violated = bool(cost_receipt["bound_violated"])
    else:
        violated = charged > Decimal(str(bound["reserved_usd"])) or (
            type(completion) is int and completion > int(model.get("max_tokens", completion)))
    with locked(root / "ledger.lock"):
        ledger = a.read(root / "ledger.json")
        item = ledger["attempts"][attempt]
        item.update(status="settled", cost_usd=str(charged), response_id=normalized.get("id") or "lost-" + attempt,
                    finished_at=now(), cost_basis=cost_receipt.get("basis"), invoice_verified=False,
                    provider_response_sha256=cost_receipt.get("provider_response_sha256"),
                    settlement_basis=getattr(receipt, "basis", cost_receipt.get("basis")),
                    served_model=getattr(receipt, "model", normalized.get("model")),
                    served_provider=getattr(receipt, "provider", normalized.get("provider")),
                    http_calls=getattr(result, "http_calls", None),
                    sub_attempts=final60_plain(getattr(result, "sub_attempts", None) or cost_receipt.get("sub_attempts") or []))
        if violated:
            item["bound_violated"] = True
        atomic(root / "ledger.json", ledger)
    if violated or charged != cost:
        # Never under-report: a mismatch freezes this row's API; its audit then decides publication.
        final60_flag(root / "api-frozen.json", {"reason": "bound_violated" if violated else "accounting_mismatch",
                                                "attempt": attempt, "charged_usd": str(charged), "usage_cost_usd": str(cost)})
    print(json.dumps({"row": row, "step": step, "call_cost_usd": str(charged)}), flush=True)
    return normalized


def final60_dry_responder(body, spec=None, index=None):
    """Dry-run model: searches, then re-proposes the visible original with a marker comment.

    MockOpenRouter calls a responder as ``(body, spec, index)``; older fixtures pass the body only.
    """
    packet = json.loads(body["messages"][-1]["content"])
    reference = packet.get("problem", {}).get("reference")
    statement = packet.get("problem", {}).get("statement", "")
    if reference and reference.startswith(statement) and packet.get("step", 1) % 3 == 0:
        proof = reference[len(statement):].strip()
        proof = proof[2:].strip() if proof.startswith(":=") else proof
        return json.dumps({"action": "propose", "parent_id": "c000", "strategy": "dry-run replay",
                           "proof": proof + "\n  -- dry run " + str(packet.get("step"))})
    return json.dumps({"action": "search", "query": statement.split(":", 1)[0][-60:] or "theorem"})


def final60_dispatch(root, row, step, body, model, step_dir):
    """final60 hook 2: reserve in ledger.json, then money.dispatch_guarded (SQLite mirror)."""
    from lean_agent.final60 import catalog, money
    from lean_agent.final60.ledger import BudgetExceeded
    root = Path(root)
    wire = transport_for(model)
    authorization = a.read(root / "authorization.json")
    name = final60_transport_name(authorization)
    options = {}
    spec = None
    if authorization.get("dry_run"):
        # Sealed dry-run roots only ever use the no-network mock; assembly never submits them.
        from lean_agent.final60 import transport as router
        options["transport"] = router.MockOpenRouter(final60_dry_responder)
        key = "dry-run"
    elif name == "openai":
        # Development transport: same cap, ledger and evidence layout through the OpenAI-direct wire.
        from lean_agent.final60 import openai_direct
        options["wire"] = openai_direct
        spec = openai_direct.spec_for_model(model)
        key = os.environ.get(openai_direct.KEY_ENV)
    else:
        key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("Missing explicitly configured " + ("OpenAI" if name == "openai" else "OpenRouter") + " credentials")
    if spec is None:
        spec = catalog.spec_for_model(model)
    bound = wire.request_cost(body)
    attempt = f"F{row:03}-{step:04}"
    cap = Decimal(a.read(root / "authorization.json")["per_problem_target_usd"])
    stops = tuple(getattr(money, name) for name in ("ApiDisabled", "RowApiDisabled", "RowApiFrozen")
                  if isinstance(getattr(money, name, None), type))
    with api_slot(root), locked(root / "dispatch-locks" / (attempt + ".lock"), blocking=False):
        with locked(root / "ledger.lock"):
            ledger = a.read(root / "ledger.json")
            check_dispatchable(root, ledger)
            if attempt in ledger["attempts"]:
                raise ValueError("Attempt already dispatched; refusing duplicate API call")
            if not request_fits_budget(ledger, row, bound, cap):
                raise Final60Stop("ledger_budget_exceeded", "ledger.json reservation does not fit the cap")
            ledger["attempts"][attempt] = {"row": row, "step": step, "status": "pending", "cost_usd": None,
                                           "owner_pid": os.getpid(), "api_endpoint": wire.ENDPOINT,
                                           "request_sha256": a.sha(a.canonical(body)), "started_at": now(),
                                           "maximum_request_cost_usd": bound["reserved_usd"]}
            atomic(root / "ledger.json", ledger)
        start = time.monotonic()
        try:
            # The shared ledger learns the sealed prior before its first reservation for this row.
            result = money.dispatch_guarded(body, spec, ledger=final60_ledger(root, row),
                                            problem=f"F{row:03}", attempt_id=attempt, run_root=root,
                                            step_dir=step_dir, key=key, **options)
        except BudgetExceeded as exc:
            final60_release(root, attempt)
            raise Final60Stop("ledger_budget_exceeded", str(exc)[:500]) from None
        except stops as exc:
            final60_release(root, attempt)
            name = "api-disabled.json" if type(exc).__name__ == "ApiDisabled" else "api-frozen.json"
            target = final60_run_dir(root, row) if name == "api-disabled.json" else root
            final60_flag(target / name, {"reason": type(exc).__name__, "attempt": attempt, "message": str(exc)[:500]})
            raise Final60Stop("api_disabled" if name == "api-disabled.json" else "row_api_frozen") from None
        atomic(step_dir / "timing.json", {"seconds": time.monotonic() - start})
        return final60_settle(root, row, step, bound, result.normalized, result, model)


def final60_recover(root, row, step, step_dir):
    """final60 hook 7: reconcile a step interrupted between reservation and settlement.

    Never re-sends a possibly billed request. Unsent or unbilled-only steps are released
    and dispatched again; billed steps without a usable response become one unevaluated
    call whose cost is the exact generation charge or the reserved bound.
    """
    root, attempt = Path(root), f"F{row:03}-{step:04}"
    with locked(root / "ledger.lock"):
        item = a.read(root / "ledger.json")["attempts"].get(attempt)
    if item is None:
        return
    if item["status"] == "settled":
        if not (step_dir / "response.json").exists():
            raise ValueError("Settled OpenRouter step lacks its saved response")
        return
    try:
        with locked(root / "dispatch-locks" / (attempt + ".lock"), blocking=False):
            pass
    except BlockingIOError:
        raise ValueError("A live dispatcher still owns this attempt; refusing concurrent recovery") from None
    model = a.read(folder(root, row) / "input/config.json")["model"]
    if (step_dir / "response.json").exists() and (step_dir / "cost-receipt.json").exists():
        # The saved step may hold several HTTP sub-attempts: its reservation is the step total or the bound.
        response = a.read(step_dir / "response.json")
        total = Decimal(str((response.get("usage") or {}).get("cost") or 0))
        final60_settle(root, row, step, {"reserved_usd": str(max(total, Decimal(item["maximum_request_cost_usd"])))},
                       response, None, model)
        return
    sqlite = final60_ledger(root, row)
    def ours(entry):
        return str(entry.get("attempt_id", entry.get("id", ""))).split("#", 1)[0] == attempt
    authorization = a.read(root / "authorization.json")
    recover_options = {}
    if final60_transport_name(authorization) == "openai":
        from lean_agent.final60 import openai_direct
        recover_options["wire"] = openai_direct
        key = os.environ.get(openai_direct.KEY_ENV)
    else:
        key = os.environ.get("OPENROUTER_API_KEY")
    recovered = [final60_plain(sqlite.recover(entry.get("attempt_id", entry.get("id")), step_dir=step_dir, key=key,
                                              **recover_options))
                 for entry in sqlite.open_attempts(run_root=str(root)) if ours(entry)]
    subs = [final60_plain(entry) for entry in sqlite.attempts(f"F{row:03}") if ours(entry)]
    total = sum((Decimal(str(entry.get("cost_usd") or 0)) for entry in subs), Decimal(0))
    if total == 0 and all(entry.get("status") in ("void", "unbilled") for entry in subs):
        archive = step_dir / ("unsent-" + str(time.time_ns()))
        for name in ("request.json", "cost-bound.json", "endpoint.json", "provider-response.json", "http"):
            if (step_dir / name).exists():
                archive.mkdir(parents=True, exist_ok=True)
                (step_dir / name).rename(archive / name)
        final60_release(root, attempt)
        return
    basis = "generation-api" if any("generation" in str(entry.get("basis", "")) for entry in recovered) else "lost-bound"
    lost = {"id": "lost-" + attempt, "object": "final60.lost_response", "model": model["id"],
            "provider": authorization.get("provider", FINAL60_PROVIDER), "choices": [], "final60_lost": True,
            "usage": {"cost": str(total)},
            "_cost_receipt": {"cost_usd": str(total), "basis": basis, "invoice_verified": False,
                              "provider_response_sha256": None, "sub_attempts": subs}}
    atomic(step_dir / "response.json", lost)
    atomic(step_dir / "cost-receipt.json", lost["_cost_receipt"])
    final60_settle(root, row, step, {"reserved_usd": str(max(total, Decimal(item["maximum_request_cost_usd"])))},
                   lost, None, model)


def dispatch(root, row, step, body, model, step_dir):
    verify_frozen(root)
    if model.get("backend") == "openrouter" or (model.get("backend") == "openai"
                                                 and os.environ.get("FINAL60_TRANSPORT") == "openai"):
        return final60_dispatch(root, row, step, body, model, step_dir)
    bound = transport.request_cost(body)
    data = transport.model_metadata()
    attempt = f"F{row:03}-{step:04}"
    with api_slot(root), locked(root / "dispatch-locks" / (attempt + ".lock"), blocking=False):
        with locked(root / "ledger.lock"):
            ledger = a.read(root / "ledger.json")
            check_dispatchable(root, ledger)
            config_path = folder(root, row) / "input/config.json"
            cap = a.read(config_path)["limits"].get("cost_cap_usd") if config_path.exists() else None
            if cap is not None and not request_fits_budget(ledger, row, bound, cap):
                raise ValueError("Request would exceed the strict per-problem budget")
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
    if final60_root(root):
        return final60_recover(root, row, step, step_dir)
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


def final_candidate_disposition(result):
    """Verdict on one ranked candidate's all-version compatibility result in run_problem.

    ``valid`` selects it. ``skip`` moves on to the next ranked candidate: a timeout or a compile
    failure on any required version, or a Lean allocator abort, means this candidate is not
    all-version compatible, which says nothing about the others (raising here sent whole rows
    back to the original although lower-ranked candidates were valid). ``environment`` is a host
    failure that persisted through evaluate_cached's retries; it stops the row for inspection.
    """
    if result.get("valid"):
        return "valid"
    errors = [(value.get("error") or {}) for value in result.get("environments", {}).values()]
    if h.environment_failed(result) and not any(error.get("resource") == "lean_allocator_limit" for error in errors):
        return "environment"
    if any(error.get("kind") == "timeout" for error in errors):
        return "timeout"
    return "skip"


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
        final60 = final60_root(root)
        wire = transport_for(config)
        # final60 (critic A7): sealed single-pass exploration screens; final selection keeps full checks.
        screening = ({"screen_single_pass": True} if final60 and
                     (final60_settings(root, row) or {}).get("screening") == "single-pass" else {})
        atomic(output / "progress.json", {"status": "running", "at": now(), "row": row})
        try:
            initial_fingerprints = ev.verify_environments(problem, full=True)
            initial_receipt = output / "initial-environment-fingerprints.json"
            if initial_receipt.exists():
                initial_receipt.rename(initial_receipt.with_name("initial-environment-fingerprints-before-resume-" + str(time.time_ns()) + ".json"))
            atomic(initial_receipt, {"full_content_verification": True, "verified_at": now(),
                                     "environments": initial_fingerprints})
            stop_reason = "cost_limit"
            while not h.cost_threshold_reached(state, config) and not h.portfolio.finished(state):
                step = state["step"] + 1
                step_dir = output / "steps" / f"{step:04}"
                step_dir.mkdir(parents=True, exist_ok=True)
                recover_pending(root, row, step, step_dir)
                if final60 and not (step_dir / "response.json").exists():
                    # final60 hook 3: skip_llm, deadline, API-disabled or salvage end paid work here.
                    reason = final60_stop_reason(root, row)
                    if reason:
                        stop_reason = reason
                        try:
                            step_dir.rmdir()
                        except OSError:
                            pass
                        break
                body = make_request(state, problem, config, prompt)
                if (not (step_dir / "response.json").exists() and h.portfolio.enabled(config)
                        and h.portfolio.budget_phase(state["portfolio"], config)):
                    # Budget-ended merger: never start a call whose worst-case cost could cross the cap.
                    bound = Decimal(wire.request_cost(body)["reserved_usd"])
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
                    cap = config["limits"].get("cost_cap_usd")
                    if cap is not None:
                        bound = wire.request_cost(body)
                        with locked(root / "ledger.lock"):
                            ledger = a.read(root / "ledger.json")
                            check_dispatchable(root, ledger)
                            fits = request_fits_budget(ledger, row, bound, cap)
                        if not fits:
                            stop_reason = "next_request_would_exceed_budget"
                            atomic(output / "budget-stop.json", {"at": now(), "spent_usd": str(problem_spend(ledger, row)),
                                "cap_usd": cap, "next_request_bound_usd": bound["reserved_usd"],
                                "next_request_sha256": a.sha(a.canonical(body))})
                            atomic(output / "budget-stop-request.json", body)
                            break
                    try:
                        raw = dispatch(root, row, step, body, config["model"], step_dir)
                    except Final60Stop as stop:
                        # Released reservation: nothing billable was recorded for this step.
                        stop_reason = stop.reason
                        atomic(output / "final60-stop.json", {"at": now(), "step": step, "reason": stop.reason,
                                                              "detail": stop.detail})
                        break
                atomic(step_dir / "usage.json", accounting.response_record(raw))
                action, code, observation, rejection = h.prepare_response(raw, state, problem, config, output)
                result = None
                if code is not None:
                    (step_dir / "candidate.lean").write_text(code)
                    evaluation = step_dir / "evaluation/result.json"
                    # Reused when saved; a machine-produced failure is archived and evaluated again.
                    evaluate_cached(ev, code, problem, evaluation.parent, repetitions=1, **screening)
                    result = guard_compiler_signal(a.read(evaluation))
                    result = check_improvement_compatibility(ev, problem, code, result, state, baseline, step_dir)
                    atomic(step_dir / "selection-result.json", result)
                automatic = h.automatic_candidate(config, raw, code, result, step_dir,
                    lambda source, destination, seconds, mib: ev.inspect_native(
                        source, problem, destination, timeout=seconds, memory=mib),
                    lambda source, destination, source_path: evaluate_automatic(
                        ev, source, problem, destination))
                diagnosis = candidate_diagnosis(raw, rejection, result, step_dir, output, config)
                previous_sha = a.sha(a.canonical(state))
                state = h.advance(state, raw, code, result, rejection, h.metrics(baseline), config,
                                  str(output), diagnosis, action=action, observation=observation, automatic=automatic)
                atomic(step_dir / "event.json", {"step": step, "previous_state_sha256": previous_sha,
                    "state_sha256": a.sha(a.canonical(state)), "action": {k: v for k, v in (action or {}).items() if k != "proof"},
                    "rejection": rejection, "cost_usd_after": state["cost_usd"], "best_sha256": state["best"]["sha256"]})
                atomic(output / "state.json", state)
                atomic(output / "progress.json", {"status": "running", "row": row, "step": step,
                    "cost_usd": state["cost_usd"], "best": {k: v for k, v in state["best"].items() if k != "code"}, "at": now()})
                if (state["unknown_cost"] or (result and h.environment_failed(result))
                        or automatic and automatic["evaluation"] and h.environment_failed(automatic["evaluation"])):
                    raise ValueError("Unknown model cost or evaluator environment failure")
            # Score/compatibility selection happens after exploration without additional API spend.
            unique = {value["sha256"]: value for value in state["exploration"]["candidates"].values() if value["valid"]}
            ranked = sorted(unique.values(), key=h.ranking)
            selected, checked = None, None
            for rank, value in enumerate(ranked):
                check = output / "compatibility" / value["sha256"] / "result.json"
                evaluate_cached(ev, value["code"], problem, check.parent, repetitions=1,
                                all_versions=True, trusted_reference=value["sha256"] == a.sha(problem["reference"]))
                result = guard_compiler_signal(a.read(check))
                disposition = final_candidate_disposition(result)
                if disposition == "environment":
                    raise ValueError("Final compatibility environment/resource failure; inspect before retry")
                if disposition == "valid":
                    selected, checked = value, result
                    break
                atomic(check.parent / "skipped.json", {"rank": rank, "sha256": value["sha256"], "at": now(),
                                                       "reason": "not all-version compatible (" + disposition + ")"})
            if selected is None:
                raise ValueError("No all-version compatible final candidate")
            (output / "selected.lean").write_text(selected["code"])
            final = output / "final/result.json"
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
                                       and h.portfolio.completed(state, config) else stop_reason),
                       "cost_usd": state["cost_usd"], "calls": state["calls"],
                       "baseline": h.metrics(baseline), "selected": {k: v for k, v in selected.items() if k != "code"},
                       "final": measured, "all_versions_valid": checked["valid"], "official_evaluation": False,
                       "finished_at": now(), "verification_policy": VERIFICATION_POLICY}
            if h.portfolio.enabled(config):
                summary["portfolio"] = h.portfolio.summary(state, config)
                if not summary["portfolio"]["complete"]:
                    summary["status"] = "stopped"
            if h.autosolver.enabled(config):
                summary["autosolver"] = state.get("autosolver", {"searches": 0, "model_calls": 0})
            summary.update(cost_basis="provider-token-usage-times-frozen-public-list-prices", invoice_verified=False,
                           provider="OpenAI direct", model=MODEL["id"])
            if final60:
                # The sealed provider: OpenRouter, or "OpenAI direct" on a development root.
                sealed = a.read(root / "authorization.json")
                summary.update(cost_basis=sealed.get("budget_cost_basis", FINAL60_COST_BASIS),
                               provider=sealed.get("provider", FINAL60_PROVIDER), model=config["model"]["id"],
                               model_provider=config["model"]["provider"], api_endpoint=wire.ENDPOINT)
                if summary["stop_reason"] in FINAL60_STOP_REASONS:
                    # A deliberate end before the portfolio/budget completed is never "completed".
                    summary["status"] = "stopped"
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
    if sys.argv[1:2] == ["route60"]:
        from route60 import main as run_full
        return run_full(sys.argv[2:])
    if sys.argv[1:2] == ["route20"]:
        from assigned_routes import main as run_assigned
        return run_assigned(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__, epilog="Proof search: route20 --help or route60 --help")
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
                        help="Prepare single-context inputs with verified historical warm start")
    parser.add_argument("--scout-evaluations", type=int, default=None)
    parser.add_argument("--merger-evaluations", type=int, default=None)
    parser.add_argument("--rounds", type=int, default=None,
                        help="Repeat scouts then merger this many times; later scouts start from the incumbent")
    parser.add_argument("--merger-until-budget", action="store_true",
                        help="Let the last merger run until the per-problem budget instead of its evaluation count")
    parser.add_argument("--autosolver", action="store_true", help="Prepare bounded native AutoSolver for failed candidates (no extra model calls)")
    parser.add_argument("--warm-start-manifest", type=Path,
                        help="Freeze historical best sources (default: dashboard/public/data/final-results.json)")
    parser.add_argument("--cold-start", action="store_true", help="Explicitly start from originals for a comparison run")
    parser.add_argument("--prompt-variant", choices=tuple(prompt_variants.VARIANTS), default=None)
    parser.add_argument("--strict-cap", action="store_true", default=None, help="Reserve every next request within the $1 cap")
    parser.add_argument("--strategy-bank", type=Path,
                        help="Freeze an optional Bank JSON in new prepare/inputs configurations")
    parser.add_argument("--strategy-top-k", type=int, choices=(1, 2, 3), default=None)
    parser.add_argument("--strategy-contextual", action="store_true")
    parser.add_argument("--strategy-search-policy", choices=("guided", "alternating-v1"), default=None)
    parser.add_argument("--compiler-parallelism", type=int, default=None,
                        help="Seal the shared compiler-pool size (1-8; default ARENA_COMPILER_PARALLELISM or 1). "
                             "At run time ARENA_COMPILER_PARALLELISM overrides the sealed value")
    args = parser.parse_args()
    if args.compiler_parallelism is not None and args.command not in ("prepare", "seal"):
        parser.error("--compiler-parallelism is sealed by prepare/seal; at run time set ARENA_COMPILER_PARALLELISM")
    if args.autosolver and args.command not in ("prepare", "inputs"):
        parser.error("--autosolver is a frozen prepare/inputs setting; use a fresh batch root")
    if (args.prompt_variant is not None or args.strict_cap is not None) and args.command not in ("prepare", "inputs"):
        parser.error("Prompt/budget policy flags apply only to prepare/inputs")
    if (args.warm_start_manifest or args.cold_start) and args.command not in ("prepare", "inputs"):
        parser.error("Warm-start options apply only to prepare/inputs on a fresh root")
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
    if args.command in ("preflight", "run"):
        # The same Linux sandbox check as route60/route20 (bundled bwrap fallback and probe).
        from route60 import preflight as sandbox_preflight
        sandbox_preflight(REPO)
    if args.command == "prepare":
        prepare(root, rows, workers=args.workers or 2, portfolio_settings=settings,
                autosolver_settings={} if args.autosolver else None, strategy_settings=bank_settings,
                warm_start_manifest=args.warm_start_manifest, cold_start=args.cold_start,
                prompt_variant=args.prompt_variant, strict_cap=args.strict_cap,
                compiler_parallelism=args.compiler_parallelism)
    elif args.command == "inputs":
        prepare_inputs(root, rows, workers=args.workers or 1, portfolio_settings=settings,
                       autosolver_settings={} if args.autosolver else None, strategy_settings=bank_settings,
                       warm_start_manifest=args.warm_start_manifest, cold_start=args.cold_start,
                       prompt_variant=args.prompt_variant, strict_cap=args.strict_cap)
    elif args.command == "seal":
        seal_inputs(root, rows, compiler_parallelism=args.compiler_parallelism)
    elif args.command == "preflight":
        preflight(root, rows)
    elif args.command == "status":
        status(root)
    elif args.command == "reseal":
        reseal(root)
    else:
        verify_frozen(root)
        if final60_root(root):
            from lean_agent.final60 import transports
            authorization = a.read(root / "authorization.json")
            profile = transports.profile(final60_transport_name(authorization))
            if profile.name == "openai":
                os.environ["FINAL60_TRANSPORT"] = "openai"
            if args.key_file:
                os.environ[profile.key_env] = profile.wire.load_key(args.key_file)
            if not authorization.get("dry_run") and not os.environ.get(profile.key_env):
                raise ValueError("Missing explicitly configured " + profile.provider + " credentials")
        else:
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
