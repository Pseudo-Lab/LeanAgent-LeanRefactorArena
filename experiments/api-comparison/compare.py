#!/usr/bin/env python3
"""One frozen problem, independent one-proposal trials, serial parent-owned Lean.

No automatic retries. OpenRouter spends are reserved durably before dispatch.
Subagents run as fresh Codex CLI sessions with per-turn runtime usage. Manual
imports remain available and explicitly leave unobserved usage unknown.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib import request, error

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from lean_agent import harness as h, models
from lean_agent.artifacts import canonical, inventory, read, sha, write
from lean_agent.evaluator.lean import LeanEvaluator

API = "https://openrouter.ai/api/v1/"
MODEL = "openai/gpt-6.1-sol"
MAX_OUTPUT = 16384
PRICE_CAPS = {"prompt": "5", "completion": "15"}  # includes long-context/cache-write ceiling
MAX_INPUT_BOUND = 120000  # UTF-8 bytes plus framing allowance, below 272K pricing tier
COMMON = REPO.parent / "LeanAgent/docs/research/refactoring/warmup/권주원/evidence/2026-10-15-controlled-harness-p02/common"


def money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing monetary amount")
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError("Invalid monetary amount")
    return n


load_key = models.load_key


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http(route, *, key=None, body=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = request.Request(API + route, headers=headers,
                          data=canonical(body).encode() if body is not None else None)
    try:
        with request.build_opener(NoRedirect).open(req, timeout=120) as stream:
            raw = stream.read()
    except error.HTTPError as exc:
        # Preserve structured API errors, never credentials or exception strings.
        try:
            raw = exc.read()
            result = json.loads(raw)
        except (ValueError, OSError):
            result = {"error": {"http_status": exc.code}}
        if key:
            result = json.loads(json.dumps(result).replace(key, "<REDACTED>"))
        return result
    result = json.loads(raw)
    if key:
        result = json.loads(json.dumps(result).replace(key, "<REDACTED>"))
    return result


def wire_request(messages):
    return {"model": MODEL, "messages": messages, "max_tokens": MAX_OUTPUT,
            "reasoning": {"effort": "high"}, "stream": False,
            "response_format": {"type": "json_object"}, "plugins": [],
            "provider": {"only": ["openai"], "allow_fallbacks": False,
                         "require_parameters": True,
                         "max_price": {k: float(v) for k, v in PRICE_CAPS.items()}}}


def input_bound(body, *, limit=MAX_INPUT_BOUND):
    # OpenAI's byte-level text tokenizer cannot produce more content tokens than
    # UTF-8 bytes. Reserve an additional 4096 for two-message JSON/chat framing.
    # This is specific to the pinned text-only endpoint, with no tools/plugins.
    if body != wire_request(body["messages"]):
        raise ValueError("Unexpected request options")
    if len(body["messages"]) != 2 or any(not isinstance(m.get("content"), str) for m in body["messages"]):
        raise ValueError("Expected two plain-text messages")
    if type(limit) is not int or not 0 < limit <= 240000:
        raise ValueError("Input reservation limit must remain below the pricing tier threshold")
    count = len(canonical(body).encode("utf-8")) + 4096
    if count > limit:
        raise ValueError("Input exceeds conservative token reservation limit")
    return count


def reservation(endpoint, body, *, max_input_bound=MAX_INPUT_BOUND):
    """Reserve byte-bounded text input and all visible/reasoning output.

    Includes the highest cache-write and long-context rates in endpoint metadata.
    No tool/plugin charges, no retries, and no parallel paid requests are allowed.
    This local bound assumes the provider honors its documented prices/limits;
    the existing inference key cannot create provider-enforced $2 child keys.
    """
    if endpoint.get("tag") != "openai" or endpoint.get("model_id") != MODEL:
        raise ValueError("Only the pinned OpenAI endpoint is supported")
    context = endpoint.get("context_length")
    if type(context) is not int or context <= 0:
        raise ValueError("Missing context length")
    pricing = endpoint["pricing"]
    allowed = {"prompt", "completion", "input_cache_read", "input_cache_write", "web_search", "discount", "overrides"}
    if set(pricing) - allowed:
        raise ValueError("Unaccounted pricing fields")
    required = {"max_tokens", "reasoning", "response_format"}
    if not required <= set(endpoint.get("supported_parameters", [])):
        raise ValueError("Endpoint lacks required parameters")
    tiers = [pricing, *pricing.get("overrides", [])]
    for tier in tiers:
        if set(tier) - allowed - {"min_prompt_tokens"}:
            raise ValueError("Unknown conditional pricing field")
    inp = max(money(t.get(k, 0)) for t in tiers for k in ("prompt", "input_cache_read", "input_cache_write"))
    out = max(money(t["completion"]) for t in tiers)
    if inp > money(PRICE_CAPS["prompt"]) / 1_000_000 or out > money(PRICE_CAPS["completion"]) / 1_000_000:
        raise ValueError("Endpoint price exceeds configured ceiling")
    if endpoint.get("max_completion_tokens", 0) < MAX_OUTPUT:
        raise ValueError("Endpoint output limit too small")
    # Use the transmitted ceilings, even if the current endpoint price is lower.
    count = input_bound(body, limit=max_input_bound)
    if count + MAX_OUTPUT > context:
        raise ValueError("Request exceeds model context window")
    return (count * money(PRICE_CAPS["prompt"]) + MAX_OUTPUT * money(PRICE_CAPS["completion"])) / 1_000_000


def atomic(path, value):
    temp = path.with_suffix(".tmp")
    with temp.open("w") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def locked(root):
    with (root / ".budget.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def reserve(ledger, trial, bound):
    if trial in ledger["attempts"]:
        raise ValueError("Attempt already reserved; never retry/reuse an ID")
    if any(a["status"] != "settled" for a in ledger["attempts"].values()):
        raise ValueError("An unsettled/uncertain charge blocks further paid calls")
    if ledger["max_trials"] is not None and len(ledger["attempts"]) >= ledger["max_trials"]:
        raise ValueError("Paid trial limit reached")
    total = sum((money(a["cost_usd"]) for a in ledger["attempts"].values()), Decimal(0))
    if bound > money(ledger["per_trial_usd"]) or total + bound > money(ledger["total_usd"]):
        raise ValueError("Budget reservation refused")
    ledger["attempts"][trial] = {"status": "reserved", "reserved_usd": str(bound), "cost_usd": None}


def settle(ledger, trial, raw):
    item = ledger["attempts"][trial]
    cost = models.receipt(raw)["cost_usd"]
    item["cost_usd"] = cost
    item["status"] = "uncertain" if cost is None else "settled"
    if cost is not None and money(cost) > money(item["reserved_usd"]):
        item["status"] = "bound_violated"
    return item["status"]


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    h.snapshot_code(root)
    shutil.copyfile(__file__, root / "code/compare.py")
    # Reuse the prepared Strata environment and the original warm-up P02, with
    # no previously optimized proof or team result exposed to generators.
    metadata = read(COMMON / "P02/metadata.json")
    source = (COMMON / "P02/source.lean").read_text()
    if sha(source) != metadata["file_sha256"] or source.count(metadata["src"]) != 1:
        raise ValueError("Original warm-up source/hash mismatch")
    config = read(REPO / "configs/smoke.json")
    inputs = root / "input"
    inputs.mkdir()
    problem = {"id": "warmup-P02", "name": metadata["name"], "statement": metadata["statement"],
               "reference": metadata["src"] + "\n"}
    write(inputs / "problem.json", problem)
    write(inputs / "metadata.json", metadata)
    (inputs / "source.lean").write_text(source)
    packet = (COMMON / "packet.txt").read_text()
    (inputs / "packet.txt").write_text(packet)
    prompt = (REPO / "examples/first-harness/prompt.txt").read_text()
    (inputs / "prompt.txt").write_text(prompt)
    config["limits"]["max_calls"] = 1
    config["lean"].update(timeout_seconds=120)
    env = read(REPO / "runs/warmup-team-results/20261022-verify-01/P01/v4.26.0/environment.json")
    # Existing verified sandbox command already pins compiler and LEAN_PATH.
    template = source.replace(metadata["src"], "{{DECLARATION}}", 1)
    lines = template.splitlines(keepends=True)
    last_import = max(i for i, line in enumerate(lines) if line.startswith("import "))
    lines.insert(last_import + 1, "{{HARNESS_COMMANDS}}\n")
    env["template"] = "{{HARNESS_IMPORT}}\n" + "".join(lines)
    env["timeout_seconds"] = 120
    evaluator = LeanEvaluator()
    write(root / "environment.json", evaluator.fingerprint(env))
    write(root / "environment-spec.json", env)
    dependency_files = {}
    lean_path = next(x.split("=", 1)[1] for x in env["command"] if x.startswith("LEAN_PATH="))
    for directory in lean_path.split(os.pathsep):
        for path in Path(directory).rglob("*"):
            if path.is_file() and path.suffix in {".olean", ".so", ".dylib"}:
                dependency_files[str(path)] = sha(path.read_bytes())
    if not dependency_files:
        raise ValueError("No prepared Lean dependency artifacts found")
    write(root / "dependencies.json", dependency_files)
    baseline = evaluator.evaluate(problem["reference"], problem, [env], root / "baseline", 3)
    write(root / "baseline/result.json", baseline)
    state = h.initial_state(problem, baseline)
    messages = [{"role": "system", "content": prompt},
                {"role": "user", "content": canonical({"task_packet": packet, "baseline": h.metrics(baseline),
                  "step": 1, "remaining_calls": 1})}]
    write(root / "messages.json", messages)
    write(root / "wire-request.json", wire_request(messages))
    endpoint_data = http("models/" + MODEL + "/endpoints")
    endpoint = next(e for e in endpoint_data["data"]["endpoints"] if e["tag"] == "openai")
    bound = reservation(endpoint, wire_request(messages))
    if bound > Decimal("2"):
        raise ValueError("One request could exceed $2")
    write(root / "endpoint.json", endpoint_data)
    write(root / "price-snapshot.json", {"input_per_million": str(money(endpoint["pricing"]["prompt"]) * 1_000_000),
          "cached_input_per_million": str(money(endpoint["pricing"]["input_cache_read"]) * 1_000_000),
          "cache_write_per_million": str(money(endpoint["pricing"]["input_cache_write"]) * 1_000_000),
          "output_per_million": str(money(endpoint["pricing"]["completion"]) * 1_000_000)})
    write(root / "protocol.json", {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
          "problem": problem, "config": config, "git": h.git_metadata(REPO),
          "api_model": MODEL, "api_provider": "openai", "subagent_model": "gpt-6.1-sol", "reasoning_effort": "high",
          "subagent_trials": 3, "openrouter_trials": 5, "candidates_per_trial": 1,
          "comparison": "first 3 per backend; API 4-5 supplementary",
          "reservation_usd": str(bound), "per_trial_usd": "2", "total_usd": "10",
          "input_identity_scope": "identical explicit messages, rendered as role-labelled CLI stdin; subagent ambient system/tools not controlled",
          "input_token_bound": input_bound(wire_request(messages)), "max_output_tokens": MAX_OUTPUT,
          "dependency_files": len(dependency_files),
          "scope": "Warm-up P02, Strata 451e5f0, Lean 4.26.0; original full source context",
          "limits": "local reservation plus provider price/output caps; not a provider-side dollar lock"})
    write(root / "budget.json", {"per_trial_usd": "2", "total_usd": "10", "max_trials": 5, "attempts": {}})
    frozen = {k: v for k, v in inventory(root).items() if k != "budget.json"}
    write(root / "frozen.json", frozen)
    print(canonical({"prepared": str(root), "reservation_per_request_usd": str(bound)}), end="")


def check_frozen(root):
    for name, expected in read(root / "frozen.json").items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError("Frozen experiment changed: " + name)
    verify_dependencies(root)


def verify_dependencies(root):
    path = root / "dependencies.json"
    if path.exists():
        for name, expected in read(path).items():
            if sha(Path(name).read_bytes()) != expected:
                raise ValueError("Prepared Lean dependency changed: " + name)


def evaluate_trial(root, folder, raw, backend, elapsed, agent_id=None):
    protocol = read(root / "protocol.json")
    problem = protocol["problem"]
    env = read(root / "environment-spec.json")
    evaluator = LeanEvaluator()
    before = evaluator.fingerprint(env)
    if before != read(root / "environment.json"):
        raise ValueError("Environment changed before candidate evaluation")
    baseline = read(root / "baseline/result.json")
    bm = h.metrics(baseline)
    rejection, result, code = None, None, None
    try:
        code = h.parse_proof(raw, problem, protocol["config"]["limits"]["max_proof_characters"])
    except (ValueError, TypeError) as exc:
        rejection = str(exc)
    if code:
        (folder / "candidate.lean").write_text(code)
        result = evaluator.evaluate(code, problem, [env], folder / "evaluation", 3)
        write(folder / "evaluation/result.json", result)
    selected = h.candidate(problem["reference"], baseline, bm)
    proposed = h.candidate(code, result, bm) if result else None
    adopted = proposed is not None and h.ranking(proposed) < h.ranking(selected)
    if adopted:
        selected = proposed
    (folder / "selected.lean").write_text(selected["code"])
    final = evaluator.evaluate(selected["code"], problem, [env], folder / "final", 3)
    write(folder / "final/result.json", final)
    if evaluator.fingerprint(env) != before:
        raise ValueError("Environment changed during trial")
    verify_dependencies(root)
    usage = raw.get("usage")
    cost = models.receipt(raw)["cost_usd"] if backend == "openrouter" else None
    from lean_agent import accounting
    rates = read(root / "price-snapshot.json")
    normalized = accounting.normalize_usage(usage)
    estimate, assumptions, estimate_error = accounting.estimate(normalized, rates)
    summary = {"trial": folder.name, "backend": backend, "agent_id": agent_id,
               "model": raw.get("model"), "provider": raw.get("provider"),
               "messages_sha256": sha(canonical(read(root / "messages.json"))),
               "candidate_valid": bool(result and result["valid"]), "rejection": rejection,
               "candidate_metrics": h.metrics(result) if result else None, "improved": adopted,
               "baseline": bm, "selected": selected, "final_valid": final["valid"],
               "final_metrics": h.metrics(final), "usage": usage, "cost_usd": cost,
               "generation_seconds": elapsed, "subagent_usage_status": "available" if backend == "subagent" and usage else "unavailable" if backend == "subagent" else None,
               "estimated_token_cost_usd": estimate, "cost_estimate_assumptions": assumptions,
               "cost_estimate_error": estimate_error, "runtime_tool_items": raw.get("runtime_tool_items"),
               "finish_reason": raw.get("choices", [{}])[0].get("finish_reason"),
               "official_evaluation": False}
    write(folder / "summary.json", summary)
    write(folder / "artifacts.json", inventory(folder))
    return summary


def run_subagent(root, trial):
    """Fresh CLI subagent with ChatGPT auth and real per-turn JSONL usage."""
    check_frozen(root)
    if trial not in range(1, 4):
        raise ValueError("Subagent trial must be 1..3")
    folder = root / f"subagent-{trial:02}"
    folder.mkdir(exist_ok=False)
    # Empty scratch working directory avoids loading this repo or past solutions.
    scratch = Path(os.environ["PROJECT_CACHE_DIR"]) / "api-comparison" / root.name / folder.name
    scratch.mkdir(parents=True, exist_ok=False)
    messages = read(root / "messages.json")
    prompt = "\n\n".join(m["role"].upper() + "\n" + m["content"] for m in messages)
    write(folder / "request.json", {"messages": messages})
    command = ["codex", "exec", "--ignore-user-config", "--ephemeral", "--json",
               "--sandbox", "read-only", "--skip-git-repo-check", "--model", "gpt-6.1-sol",
               "-c", 'model_reasoning_effort="high"', "--cd", str(scratch),
               "--output-last-message", str(folder / "agent-final.txt"), "-"]
    write(folder / "launch.json", {"command": command, "timeout_seconds": 600,
          "auth": "existing Codex ChatGPT login; API credential env vars removed",
          "prompt_sha256": sha(prompt)})
    env = {k: v for k, v in os.environ.items() if k in {"HOME", "PATH", "CODEX_HOME", "TMPDIR", "LANG", "LC_ALL"}}
    started = time.monotonic()
    with (folder / "runtime.jsonl").open("w") as out, (folder / "runtime-stderr.txt").open("w") as err:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                   env=env, start_new_session=True)
        try:
            process.communicate(input=prompt.encode(), timeout=600)
        except (subprocess.TimeoutExpired, BaseException):
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            write(folder / "runtime-interrupted.json", {"no_retry": True})
            raise
    elapsed = time.monotonic() - started
    events = [json.loads(line) for line in (folder / "runtime.jsonl").read_text().splitlines() if line.strip()]
    completed = [e for e in events if e.get("type") == "turn.completed"]
    tools = [e["item"] for e in events if e.get("type") == "item.completed"
             and e.get("item", {}).get("type") not in {"agent_message", "reasoning"}]
    usage = completed[0].get("usage") if len(completed) == 1 else None
    final_path = folder / "agent-final.txt"
    raw_text = final_path.read_text() if final_path.exists() else ""
    thread = next((e.get("thread_id") for e in events if e.get("type") == "thread.started"), None)
    raw = {"id": thread, "model": "gpt-6.1-sol", "provider": "Codex CLI subagent (ChatGPT)",
           "choices": [{"message": {"content": raw_text}}], "usage": usage,
           "runtime_tool_items": tools, "runtime_exit_code": process.returncode}
    write(folder / "response.json", raw)
    summary = evaluate_trial(root, folder, raw, "subagent", elapsed, thread)
    print(canonical({k: summary[k] for k in ["trial", "candidate_valid", "improved", "cost_usd", "usage", "estimated_token_cost_usd"]}), end="")


def run_api(root, trial, dotenv):
    check_frozen(root)
    if trial not in range(1, 6):
        raise ValueError("API trial must be 1..5")
    name = f"openrouter-{trial:02}"
    key = load_key(dotenv)
    # Network metadata/account reads are not generation attempts.
    current = http("models/" + MODEL + "/endpoints")
    endpoint = next(e for e in current["data"]["endpoints"] if e["tag"] == "openai")
    bound = reservation(endpoint, read(root / "wire-request.json"))
    if bound != money(read(root / "protocol.json")["reservation_usd"]):
        raise ValueError("Endpoint context/price changed; prepare a new suite")
    credits = http("credits", key=key)["data"]
    available = money(credits["total_credits"]) - money(credits["total_usage"])
    if available < bound:
        raise ValueError("Account balance cannot cover reservation")
    folder = root / name
    with locked(root):
        ledger = read(root / "budget.json")
        reserve(ledger, name, bound)
        folder.mkdir(exist_ok=False)
        write(folder / "endpoint-before.json", current)
        write(folder / "balance-before.json", {"available_usd": str(available)})
        write(folder / "request.json", read(root / "wire-request.json"))
        atomic(root / "budget.json", ledger)
    started = time.monotonic()
    try:
        raw = http("chat/completions", key=key, body=read(root / "wire-request.json"))
    except (OSError, ValueError) as exc:
        raw = {"transport_error": type(exc).__name__}
    elapsed = time.monotonic() - started
    write(folder / "response.json", raw)
    with locked(root):
        ledger = read(root / "budget.json")
        state = settle(ledger, name, raw)
        atomic(root / "budget.json", ledger)
    if state != "settled":
        write(folder / "charge-uncertain.json", {"status": state, "no_retry": True})
        raise ValueError("Charge uncertain or exceeds reservation; all paid calls blocked")
    summary = evaluate_trial(root, folder, raw, "openrouter", elapsed)
    print(canonical({k: summary[k] for k in ["trial", "candidate_valid", "improved", "cost_usd", "usage"]}), end="")


def ingest(root, trial, response_file, agent_id):
    check_frozen(root)
    if trial not in range(1, 4):
        raise ValueError("Subagent trial must be 1..3")
    folder = root / f"subagent-{trial:02}"
    folder.mkdir(exist_ok=False)
    raw_text = response_file.read_text()
    # Preserve malformed responses too; parsing happens in the shared evaluator.
    (folder / "agent-final.txt").write_text(raw_text)
    write(folder / "request.json", {"messages": read(root / "messages.json")})
    raw = {"id": agent_id, "model": "gpt-6.1-sol (requested; runtime snapshot not exposed)", "provider": "Codex subagent",
           "choices": [{"message": {"content": raw_text}}], "usage": None}
    write(folder / "response.json", raw)
    summary = evaluate_trial(root, folder, raw, "subagent", None, agent_id)
    print(canonical({k: summary[k] for k in ["trial", "candidate_valid", "improved", "cost_usd"]}), end="")


def replay(root):
    """Offline integrity and selection replay; no Lean or network access."""
    check_frozen(root)
    protocol = read(root / "protocol.json")
    base_result = read(root / "baseline/result.json")
    bm = h.metrics(base_result)
    rows = []
    for folder in sorted(root.glob("*-0[1-5]")):
        if not (folder / "summary.json").exists():
            continue
        expected = read(folder / "artifacts.json")
        if expected != inventory(folder):
            raise ValueError("Trial artifacts changed: " + folder.name)
        summary, raw = read(folder / "summary.json"), read(folder / "response.json")
        problem = protocol["problem"]
        selected = h.candidate(problem["reference"], base_result, bm)
        try:
            code = h.parse_proof(raw, problem, protocol["config"]["limits"]["max_proof_characters"])
        except (ValueError, TypeError):
            code = None
        result = read(folder / "evaluation/result.json") if code else None
        proposed = h.candidate(code, result, bm) if result else None
        improved = proposed is not None and h.ranking(proposed) < h.ranking(selected)
        if improved:
            selected = proposed
        if summary["selected"] != selected or summary["improved"] != improved:
            raise ValueError("Selection replay mismatch")
        if summary["messages_sha256"] != sha(canonical(read(root / "messages.json"))):
            raise ValueError("Message identity mismatch")
        if summary["backend"] == "openrouter":
            item = read(root / "budget.json")["attempts"][folder.name]
            if item["status"] != "settled" or item["cost_usd"] != models.receipt(raw)["cost_usd"]:
                raise ValueError("Ledger/response cost mismatch")
            if read(folder / "request.json") != read(root / "wire-request.json"):
                raise ValueError("Wire request mismatch")
        rows.append(summary)
    return {"record_replay_passed": True, "trials": rows,
            "reported_openrouter_total_usd": str(sum((money(r["cost_usd"]) for r in rows if r["backend"] == "openrouter"), Decimal(0))),
            "subagent_total_cost_usd": None,
            "comparison_limit": "Same requested model/effort; ambient subagent context differs; one warm-up problem; no general performance claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "openrouter", "subagent", "ingest", "report"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trial", type=int)
    parser.add_argument("--dotenv", type=Path, default=REPO / ".env")
    parser.add_argument("--response", type=Path)
    parser.add_argument("--agent-id")
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == "prepare":
        prepare(root)
    elif args.command == "openrouter":
        run_api(root, args.trial, args.dotenv)
    elif args.command == "ingest":
        ingest(root, args.trial, args.response, args.agent_id)
    elif args.command == "subagent":
        run_subagent(root, args.trial)
    else:
        result = replay(root)
        print(canonical(result), end="")


if __name__ == "__main__":
    main()
