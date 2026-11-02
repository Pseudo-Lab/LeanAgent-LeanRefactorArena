#!/usr/bin/env python3
"""Serial P02 comparison: actual-cost threshold by default; strict cap is explicit."""
import argparse
from collections import Counter
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time

from lean_agent import artifacts as a, budgeting, harness as h, models, prepared

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location("p02_transport", HERE.parent / "api-comparison/compare.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
MODEL = {"backend": "openrouter", "id": "openai/gpt-6.1-sol", "provider": "openai",
         "reasoning_effort": "high", "max_tokens": 4096, "timeout_seconds": 180,
         "seed": 42, "max_price": {"prompt": 2.5, "completion": 10}}
AUTH = {"total_usd": "0.30", "condition_cap_usd": "0.15", "max_calls": 12}


def authorization(mode="threshold", target="0.15"):
    amount = c.money(target)
    if amount <= 0:
        raise ValueError("Budget target must be positive")
    if mode == "strict":
        return {"total_usd": str(amount * 2), "condition_cap_usd": str(amount), "max_calls": 12}
    if mode != "threshold":
        raise ValueError("Unknown budget mode")
    return {"mode": "threshold", "stop_at_usd": str(amount), "total_target_usd": str(amount * 2),
            "last_call_may_overshoot": True, "max_calls": None}


def budget_conditions(config, auth):
    config["limits"].pop("cost_cap_usd", None)
    config["limits"].pop("cost_stop_usd", None)
    config["limits"]["max_calls"] = auth["max_calls"]
    threshold = auth.get("mode") == "threshold"
    config["limits"]["cost_stop_usd" if threshold else "cost_cap_usd"] = auth["stop_at_usd" if threshold else "condition_cap_usd"]
    if "agent" in config:
        config["agent"]["allow_finish"] = not threshold


def validate_endpoint(endpoint, body, bound):
    if endpoint.get("tag") != "openai" or endpoint.get("model_id") != MODEL["id"]:
        raise ValueError("Unexpected model/provider")
    if not {"max_tokens", "reasoning", "response_format", "seed"} <= set(endpoint["supported_parameters"]):
        raise ValueError("Endpoint lacks required parameters")
    if bound["input_token_bound"] + body["max_tokens"] > endpoint["context_length"]:
        raise ValueError("Context limit exceeded")
    if endpoint.get("max_completion_tokens", 0) < body["max_tokens"]:
        raise ValueError("Output limit exceeded")
    pricing = endpoint["pricing"]
    allowed = {"prompt", "completion", "input_cache_read", "input_cache_write", "web_search", "discount", "overrides"}
    if set(pricing) - allowed:
        raise ValueError("Unknown pricing component")
    tiers = [pricing]
    for override in pricing.get("overrides", []):
        threshold = override.get("min_prompt_tokens")
        if type(threshold) is not int or threshold < 0 or set(override) - allowed - {"min_prompt_tokens"}:
            raise ValueError("Unknown pricing override")
        if threshold <= bound["input_token_bound"]:
            tiers.append(override)
    inp = max(c.money(t.get(k, 0)) for t in tiers for k in ("prompt", "input_cache_read", "input_cache_write"))
    out = max(c.money(t["completion"]) for t in tiers)
    caps = body["provider"]["max_price"]
    if inp > Decimal(str(caps["prompt"])) / 1_000_000 or out > Decimal(str(caps["completion"])) / 1_000_000:
        raise ValueError("Current endpoint/cache price exceeds reserved ceilings")


def make_corpus(packet):
    headings = ["Expression constructors", "getVars", "HasVarsPure instance", "OldExpressions.IsOldPred",
                "OldExpressions.IsFvar", "OldExpressions.extractOldExprVars",
                "OldExpressions.NormalizedOldExpr", "Local helper declarations"]
    entries = []
    for index, heading in enumerate(headings):
        start = packet.index("\n" + heading + "\n") + 1
        end = packet.index("\n" + headings[index + 1] + "\n", start) if index + 1 < len(headings) else len(packet)
        entries.append({"name": heading, "source": "P02 original task packet / " + heading,
                        "text": packet[start:end].strip()})
    return {"schema_version": 1, "entries": entries}


def prepare(root, common, strata, toolchain, *, budget_mode="threshold", target="0.15"):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = root / "inputs"
    inputs.mkdir()
    auth = authorization(budget_mode, target)
    meta = a.read(common / "P02/metadata.json")
    source = (common / "P02/source.lean").read_text()
    if a.sha(source) != meta["file_sha256"] or a.sha(meta["src"]) != meta["src_sha256"]:
        raise ValueError("P02 original source hash mismatch")
    revision = meta["version_info"][0]["v4.26.0"]
    head = c.subprocess.check_output(["git", "-C", str(strata), "rev-parse", "HEAD"]).decode().strip()
    if head != revision:
        raise ValueError("Strata revision mismatch")
    a.write(inputs / "metadata.json", meta)
    (inputs / "source.lean").write_text(source)
    prefix = source[:source.index(meta["src"])]
    template = "{{HARNESS_IMPORT}}\n" + prefix + "\n{{DECLARATION}}\nend CallElimCorrect\n"
    lines = template.splitlines(keepends=True)
    last_import = max(i for i, line in enumerate(lines) if line.startswith("import "))
    lines.insert(last_import + 1, "{{HARNESS_COMMANDS}}\n")
    (inputs / "context.lean.in").write_text("".join(lines))
    packet = (common / "packet.txt").read_text()
    (inputs / "packet.txt").write_text(packet)
    a.write(inputs / "corpus.json", make_corpus(packet))
    a.write(inputs / "problem.json", {"id": "warmup-P02", "name": meta["name"],
        "statement": meta["statement"], "reference": meta["src"] + "\n"})
    project = inputs / "project"
    project.mkdir()
    for name in ("lean-toolchain", "lakefile.toml"):
        shutil.copyfile(REPO / "examples/first-harness/project" / name, project / name)
    prepared.freeze([strata / ".lake/build/lib/lean", toolchain / "lib/lean"], revision,
                    inputs / "prepared.json", sandbox="macos-readonly", verification="stat-cache")
    common_instruction = ("\nNamespace: CallElimCorrect. The verifier preserves the complete original source context.\n"
        + "Pinned source imports:\n" + "\n".join(line for line in prefix.splitlines() if line.startswith("import ")) + "\n" +
        "The following original task packet is the full generation context supplied to both conditions. "
        "No previous optimized proof is included.\n<task_packet>\n" + packet + "\n</task_packet>\n")
    for condition in ("whole", "actions-memory"):
        prompt_file = REPO / "examples/first-harness/prompt.txt" if condition == "whole" else HERE / "prompt.txt"
        (inputs / (condition + "-prompt.txt")).write_text(prompt_file.read_text() + common_instruction)
        config = a.read(REPO / "configs/smoke.json")
        config.update(problem="problem.json", template="context.lean.in", project="project",
                      prompt=condition + "-prompt.txt", model=MODEL)
        config["lean"].update(command=[str(toolchain / "bin/lean"), "-Dexperimental.module=true", "-j1", "-M2048", "-T200000"],
            timeout_seconds=120, repetitions=3, prepared_environment="prepared.json")
        config["limits"].update(max_proof_characters=12000, max_feedback_characters=6000, max_request_characters=100000)
        if condition == "actions-memory":
            config["agent"] = {"mode": "actions-v1", "corpus": "corpus.json", "history_limit": 4, "candidate_limit": 8}
        budget_conditions(config, auth)
        a.write(inputs / (condition + ".json"), config)
        h.load_config(inputs / (condition + ".json"))
    a.write(root / "authorization.json", auth)
    a.write(root / "budget.json", {**auth, "attempts": {}})
    (root / "adapter-code").mkdir()
    shutil.copyfile(__file__, root / "adapter-code/live_p02.py")
    shutil.copyfile(HERE.parent / "api-comparison/compare.py", root / "adapter-code/compare.py")
    a.write(root / "frozen.json", {str(p.relative_to(root)): a.sha(p.read_bytes())
        for p in [*inputs.rglob("*"), * (root / "adapter-code").iterdir(), root / "authorization.json"] if p.is_file()})
    print(json.dumps({"prepared": str(root), "model": MODEL, "authorization": auth,
                      "packet_characters": len(packet)}, ensure_ascii=False), flush=True)


def verify_frozen(root):
    for path, digest in a.read(root / "frozen.json").items():
        if a.sha((root / path).read_bytes()) != digest:
            raise ValueError("Prepared input changed: " + path)


class BudgetQuery:
    def __init__(self, root, condition):
        self.root, self.condition = root, condition

    def __call__(self, body, model, step, fixtures=None):
        root, condition = self.root, self.condition
        verify_frozen(root)
        for path in h.CODE_FILES:
            if (h.BASE / path).read_bytes() != (root / condition / "code/lean_agent" / path).read_bytes():
                raise ValueError("Harness code changed during execution")
        endpoints = c.http("models/" + MODEL["id"] + "/endpoints")
        endpoint = next(e for e in endpoints["data"]["endpoints"] if e["tag"] == "openai")
        config = a.read(root / "inputs" / (condition + ".json"))
        with c.locked(root):
            ledger = a.read(root / "budget.json")
            auth = a.read(root / "authorization.json")
            threshold = auth.get("mode") == "threshold"
            expected = authorization("threshold" if threshold else "strict", auth["stop_at_usd" if threshold else "condition_cap_usd"])
            if auth != expected or any(ledger.get(k) != v for k, v in auth.items()):
                raise ValueError("Budget authorization changed")
            if any(item["status"] != "settled" for item in ledger["attempts"].values()):
                raise ValueError("Unknown/pending charge prevents further dispatch")
            spent = sum((Decimal(row["cost_usd"]) for row in ledger["attempts"].values() if row["condition"] == condition), Decimal(0))
            if threshold:
                if config["limits"].get("cost_stop_usd") != auth["stop_at_usd"] or "cost_cap_usd" in config["limits"]:
                    raise ValueError("Threshold authorization/configuration differ")
                bound = {**budgeting.request_cost(body), "spent_usd": str(spent),
                         "target_usd": auth["stop_at_usd"], "allowed": spent < Decimal(auth["stop_at_usd"]),
                         "mode": "threshold"}
            else:
                if config["limits"].get("cost_cap_usd") != auth["condition_cap_usd"]:
                    raise ValueError("Strict authorization/configuration differ")
                bound = budgeting.reservation(body, {"cost_usd": str(spent)}, config)
            validate_endpoint(endpoint, body, bound)
            total = sum((Decimal(row["cost_usd"]) for row in ledger["attempts"].values()), Decimal(0))
            if not bound["allowed"] or not threshold and total + Decimal(bound["reserved_usd"]) > Decimal(auth["total_usd"]):
                raise ValueError("Strict budget reservation refused")
            attempt = condition + f"-{step:03}"
            if attempt in ledger["attempts"]:
                raise ValueError("Attempt ID already used; no retries")
            ledger["attempts"][attempt] = {"condition": condition, "status": "reserved",
                "reserved_usd": bound["reserved_usd"], "cost_usd": None}
            folder = root / "transport" / attempt
            a.write(folder / "endpoint.json", endpoints)
            a.write(folder / "reservation.json", bound)
            a.write(folder / "request.json", body)
            c.atomic(root / "budget.json", ledger)
        started = time.monotonic()
        raw = models.query(body, model, step, fixtures)
        a.write(folder / "response.json", raw)
        a.write(folder / "timing.json", {"seconds": time.monotonic() - started})
        with c.locked(root):
            ledger = a.read(root / "budget.json")
            settled = c.settle(ledger, attempt, raw)
            c.atomic(root / "budget.json", ledger)
        if settled == "bound_violated":
            raise ValueError("Provider exceeded reservation; no further dispatch")
        print(json.dumps({"condition": condition, "step": step, "cost_usd": models.receipt(raw)["cost_usd"],
                          "completion_tokens": (raw.get("usage") or {}).get("completion_tokens")}), flush=True)
        return raw


def run(root, key_path):
    root = root.resolve()
    verify_frozen(root)
    for condition in ("whole", "actions-memory"):
        h.run(root / "inputs" / (condition + ".json"), root / (condition + "-preflight"),
              check_only=True, dotenv=key_path)
    rows = []
    for condition in ("whole", "actions-memory"):
        started = time.monotonic()
        result = h.run(root / "inputs" / (condition + ".json"), root / condition,
                       query=BudgetQuery(root, condition), dotenv=key_path)
        replay = h.replay(root / condition)
        evaluator = prepared.PreparedLeanEvaluator(root / "inputs/prepared.json")
        meta = a.read(root / "inputs/metadata.json")
        source = (root / "inputs/source.lean").read_text()
        selected = (root / condition / "selected.lean").read_text()
        full = root / (condition + "-full-module")
        full.mkdir()
        path = full / "selected.lean"
        path.write_text(source.replace(meta["src"], selected.rstrip(), 1))
        command = a.read(root / condition / "preflight.json")["effective_command"]
        checked = evaluator.execute([*command, "--root=" + str(full), str(path)], root / "inputs/project", 120)
        (full / "compile.log").write_text(checked.pop("output"))
        a.write(full / "result.json", checked)
        steps, actions = [], Counter()
        for folder in sorted((root / condition / "steps").iterdir()):
            event = a.read(folder / "event.json")
            action = (event.get("action") or {}).get("action", "proof" if condition == "whole" else "rejected")
            actions[action] += 1
            evpath = folder / "evaluation/result.json"
            ev = a.read(evpath) if evpath.exists() else None
            steps.append({"step": int(folder.name), "action": action, "rejection": event["rejection"],
                "candidate_valid": ev["valid"] if ev else None, "metrics": h.metrics(ev) if ev else None,
                "cost_usd_after": event["state_after"]["cost_usd"],
                "best_tokens": event["state_after"]["best"]["tokens"],
                "best_raw_heartbeats": event["state_after"]["best"]["raw_heartbeats"]})
        baseline, final = result["state"]["baseline"], result["final"]
        score = (Decimal(final["tokens"]) / baseline["tokens"] + Decimal(final["raw_heartbeats"]) / baseline["raw_heartbeats"]) / 2
        rows.append({"condition": condition, "status": result["status"], "calls": result["state"]["calls"],
            "cost_usd": result["state"]["cost_usd"], "stop_reason": result["stop_reason"],
            "baseline": baseline, "final": final, "local_ratio_score": str(score),
            "candidate_evaluations": sum(row["candidate_valid"] is not None for row in steps),
            "valid_candidates": sum(row["candidate_valid"] is True for row in steps),
            "actions": dict(actions), "steps": steps, "replay_passed": replay["record_replay_passed"],
            "full_module_passed": checked["returncode"] == 0 and not checked["timed_out"],
            "wall_seconds": round(time.monotonic() - started, 3)})
        a.write(root / (condition + "-report.json"), rows[-1])
        print(json.dumps({k: rows[-1][k] for k in ("condition", "calls", "cost_usd", "stop_reason", "final", "full_module_passed")}), flush=True)
        if result["state"]["unknown_cost"]:
            raise ValueError("Unknown billing; second condition will not be dispatched")
    ledger = a.read(root / "budget.json")
    auth = a.read(root / "authorization.json")
    threshold = auth.get("mode") == "threshold"
    total = sum((Decimal(item["cost_usd"]) for item in ledger["attempts"].values()), Decimal(0))
    safe = all(item["status"] == "settled" and Decimal(item["cost_usd"]) <= Decimal(item["reserved_usd"])
               for item in ledger["attempts"].values())
    if threshold:
        for condition in ("whole", "actions-memory"):
            spent = Decimal(0)
            for name, item in sorted(ledger["attempts"].items(), key=lambda pair: (pair[1]["condition"], int(pair[0].rsplit("-", 1)[-1]))):
                if item["condition"] != condition:
                    continue
                safe = safe and spent < Decimal(auth["stop_at_usd"])
                spent += Decimal(item["cost_usd"])
    else:
        safe = safe and total <= Decimal(auth["total_usd"])
    key = models.load_key(key_path)
    leaked = any(key.encode() in p.read_bytes() for p in root.rglob("*") if p.is_file())
    report = {"schema_version": 1, "problem": "P02", "base_main": "ba3de4f", "model": MODEL,
        "authorization": auth, "reported_total_usd": str(total), "budget_ok": safe,
        "secret_in_evidence": leaked, "generation_context": "same original short task packet; no optimized proofs",
        "source_sha256": a.read(root / "inputs/metadata.json")["file_sha256"],
        "conditions": rows, "limitations": "One run per condition. Threshold permits the final call to overshoot; strict caps may leave budget unused. Not an official score."}
    a.write(root / "report.json", report)
    a.write(root / "artifacts.json", a.inventory(root))
    if not safe or leaked or not all(row["replay_passed"] and row["full_module_passed"] for row in rows):
        raise ValueError("Comparison audit failed")
    print(json.dumps({"total_usd": str(total), "budget_ok": safe, "report": str(root / "report.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--common", type=Path)
    parser.add_argument("--strata", type=Path)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--dotenv", type=Path)
    parser.add_argument("--budget-mode", choices=["threshold", "strict"], default="threshold")
    parser.add_argument("--target-usd", default="0.15")
    args = parser.parse_args()
    if args.command == "prepare":
        if not all((args.common, args.strata, args.toolchain)):
            parser.error("prepare requires --common, --strata and --toolchain")
        prepare(args.output, args.common, args.strata, args.toolchain,
                budget_mode=args.budget_mode, target=args.target_usd)
    else:
        if args.dotenv is None:
            parser.error("run requires --dotenv")
        run(args.output, args.dotenv)
