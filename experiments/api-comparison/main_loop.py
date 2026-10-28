#!/usr/bin/env python3
"""P02 experiment settings and budget guard around the native common harness."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
import os
from pathlib import Path
import shutil
import sys
import time

import compare as c
from lean_agent import harness as h, models
from lean_agent.prepared import PreparedLeanEvaluator

REPO = c.REPO


def prepare(root, cost_stop=None, *, common, prepared_manifest, conditions_path):
    threshold = c.money(cost_stop) if cost_stop is not None else None
    if threshold is not None and threshold <= 0:
        raise ValueError("Cost threshold must be positive")
    conditions = c.read(conditions_path)
    if conditions.get("schema_version") != 1 or conditions.get("problem_id") != "warmup-P02":
        raise ValueError("Expected P02 comparison conditions")
    # This adapter's byte/price reservation was validated for the pinned wire.
    # Other model settings can use the native runner with their own budget guard.
    if models.payload([], conditions["model"]) != c.wire_request([]):
        raise ValueError("P02 budget adapter requires the pinned GPT-6.1 Sol request settings")
    evaluator = PreparedLeanEvaluator(prepared_manifest)
    evaluator.verify()
    if evaluator.settings["revision"] != conditions["library_revision"]:
        raise ValueError("Prepared library revision differs from comparison conditions")
    common = common.resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = root / "inputs"
    inputs.mkdir()
    meta = c.read(common / "P02/metadata.json")
    source = (common / "P02/source.lean").read_text()
    if c.sha(source) != meta["file_sha256"] or source.count(meta["src"]) != 1:
        raise ValueError("P02 original source mismatch")
    prefix = source[:source.index(meta["src"])]
    # P02's original lexical scope is one namespace, with no open section.
    # Preserve every preceding declaration; later declarations are not visible
    # when Lean elaborates the target and are checked separately at the end.
    template = "{{HARNESS_IMPORT}}\n" + prefix + "\n{{DECLARATION}}\nend CallElimCorrect\n"
    lines = template.splitlines(keepends=True)
    last_import = max(i for i, line in enumerate(lines) if line.startswith("import "))
    lines.insert(last_import + 1, "{{HARNESS_COMMANDS}}\n")
    (inputs / "context.lean.in").write_text("".join(lines))
    (inputs / "source.lean").write_text(source)
    c.write(inputs / "metadata.json", meta)
    shutil.copyfile(conditions_path, inputs / "comparison-conditions.json")
    shutil.copyfile(prepared_manifest, inputs / "prepared-environment.json")
    problem = {"id": "warmup-P02", "name": meta["name"], "statement": meta["statement"],
               "reference": meta["src"] + "\n"}
    c.write(inputs / "problem.json", problem)
    instruction = (REPO / "examples/first-harness/prompt.txt").read_text()
    if threshold is None:
        instruction += "\nYou have up to " + str(conditions["limits"]["max_calls"]) + " proposals. Use the latest Lean feedback to repair errors before optimizing.\n"
    else:
        instruction += ("\nThere is no proposal-count limit. The controller stops after cumulative API cost reaches $"
                        + str(threshold) + ". Continue improving the current best; use the latest Lean feedback to repair failures.\n")
    instruction += "The following is the complete original source preceding the target declaration.\n<source_before_target>\n" + prefix + "\n</source_before_target>\n"
    instruction += "Imported expression definitions and local helper signatures follow.\n<task_packet>\n"
    instruction += (common / "packet.txt").read_text() + "\n</task_packet>\n"
    (inputs / "prompt.txt").write_text(instruction)
    project = inputs / "project"
    project.mkdir()
    for name in ("lean-toolchain", "lakefile.toml"):
        shutil.copyfile(REPO / "examples/first-harness/project" / name, project / name)
    config = c.read(REPO / "configs/smoke.json")
    config.update(problem="problem.json", template="context.lean.in", project="project", prompt="prompt.txt")
    config["model"] = conditions["model"]
    config["lean"].update(conditions["lean"], prepared_environment="prepared-environment.json")
    config["limits"].update(conditions["limits"])
    if threshold is not None:
        config["limits"].update(max_calls=None, cost_stop_usd=str(threshold))
    c.write(inputs / "config.json", config)
    h.load_config(inputs / "config.json")
    if threshold is None:
        authorization = conditions["authorization"]
    else:
        # A response can cross the requested threshold once. Reserve no more
        # than one maximum request beyond it; native main stops before another.
        maximum_request = (200000 * c.money(c.PRICE_CAPS["prompt"]) + c.MAX_OUTPUT * c.money(c.PRICE_CAPS["completion"])) / 1_000_000
        authorization = {"per_trial_usd": str(maximum_request), "total_usd": str(threshold + maximum_request),
                         "max_trials": None, "stop_at_usd": str(threshold), "mode": "threshold"}
    c.write(root / "authorization.json", authorization)
    c.write(root / "budget.json", {**authorization, "attempts": {}})
    code = root / "adapter-code"
    code.mkdir()
    for filename in ("main_loop.py", "compare.py"):
        shutil.copyfile(Path(__file__).with_name(filename), code / filename)
    c.write(root / "prepared-files.json", {str(p.relative_to(root)): c.sha(p.read_bytes())
            for p in [*inputs.rglob("*"), *code.iterdir(), root / "authorization.json"] if p.is_file()})
    print(c.canonical({"prepared": str(root), "source_prefix_characters": len(prefix),
                       "system_prompt_characters": len(instruction), "max_calls": config["limits"]["max_calls"],
                       "budget_usd": str(threshold) if threshold is not None else "2"}), end="")


def verify_prepared(root):
    for filename, expected in c.read(root / "prepared-files.json").items():
        if c.sha((root / filename).read_bytes()) != expected:
            raise ValueError("Prepared experiment file changed: " + filename)


class BudgetQuery:
    def __init__(self, root, *, http=c.http, query=models.query):
        self.root, self.http, self.query = root, http, query

    def __call__(self, body, model, step, fixtures=None):
        # main has already snapshotted its exact code and recorded this request.
        verify_prepared(self.root)
        for name in h.CODE_FILES:
            if (self.root / "harness/code/lean_agent" / name).read_bytes() != (h.BASE / name).read_bytes():
                raise ValueError("Main harness source changed during execution")
        current = self.http("models/" + c.MODEL + "/endpoints")
        endpoint = next(e for e in current["data"]["endpoints"] if e["tag"] == "openai")
        bound = c.reservation(endpoint, body, max_input_bound=200000)
        folder = self.root / "transport" / f"{step:03}"
        name = f"step-{step:03}"
        with c.locked(self.root):
            ledger = c.read(self.root / "budget.json")
            # Enforce the authorized limit even if the mutable ledger was edited.
            auth_path = self.root / "authorization.json"
            authorization = c.read(auth_path) if auth_path.exists() else {"total_usd": "2", "per_trial_usd": "2", "max_trials": 3}
            if any(ledger.get(k) != v for k, v in authorization.items()):
                raise ValueError("Budget configuration changed")
            if "stop_at_usd" in authorization:
                spent = sum((c.money(a["cost_usd"]) for a in ledger["attempts"].values() if a["cost_usd"] is not None), Decimal(0))
                if spent >= c.money(authorization["stop_at_usd"]):
                    raise ValueError("Cost threshold already reached; another dispatch is forbidden")
            c.reserve(ledger, name, bound)
            c.write(folder / "endpoint.json", current)
            c.write(folder / "request.json", body)
            c.atomic(self.root / "budget.json", ledger)
        started = time.monotonic()
        raw = self.query(body, model, step, fixtures)
        c.write(folder / "response.json", raw)
        c.write(folder / "timing.json", {"seconds": time.monotonic() - started})
        with c.locked(self.root):
            ledger = c.read(self.root / "budget.json")
            state = c.settle(ledger, name, raw)
            c.atomic(self.root / "budget.json", ledger)
        if state == "bound_violated":
            raise ValueError("Provider exceeded reserved amount; no further calls allowed")
        usage = raw.get("usage") or {}
        print(c.canonical({"step": step, "cost_usd": models.receipt(raw)["cost_usd"],
              "cumulative_usd": str(sum((c.money(a["cost_usd"]) for a in ledger["attempts"].values() if a["cost_usd"] is not None), Decimal(0))),
              "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}), end="", flush=True)
        # Unknown cost is passed to main, which records it and stops itself.
        return raw


def run(root, check_only=False):
    verify_prepared(root)
    key = c.load_key(REPO / ".env")
    prior = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = key
    evaluator = PreparedLeanEvaluator(root / "inputs/prepared-environment.json")
    try:
        result = h.run(root / "inputs/config.json", root / ("check" if check_only else "harness"),
                       check_only=check_only, query=BudgetQuery(root))
    finally:
        if prior is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = prior
    if check_only:
        print(c.canonical(result), end="")
        return
    replay = h.replay(root / "harness")
    # Confirm the selected proof also works with the original complete module.
    meta = c.read(root / "inputs/metadata.json")
    source = (root / "inputs/source.lean").read_text()
    selected = (root / "harness/selected.lean").read_text()
    full = root / "full-module"
    full.mkdir()
    target = full / "selected.lean"
    target.write_text(source.replace(meta["src"], selected.rstrip(), 1))
    command = c.read(root / "harness/preflight.json")["effective_command"]
    checked = evaluator.execute([*command, "--root=" + str(full), str(target)],
                                root / "inputs/project", 120)
    (full / "compile.log").write_text(checked["output"])
    c.write(full / "result.json", checked)
    steps = []
    previous_best = None
    for folder in sorted((root / "harness/steps").iterdir(), key=lambda p: int(p.name)):
        req, raw = c.read(folder / "request.json"), c.read(folder / "response.json")
        packet = json.loads(req["messages"][1]["content"])
        evaluation = folder / "evaluation/result.json"
        ev = c.read(evaluation) if evaluation.exists() else None
        state = c.read(folder / "event.json")["state_after"]
        candidate_path = folder / "candidate.lean"
        candidate_hash = c.sha(candidate_path.read_bytes()) if candidate_path.exists() else None
        steps.append({"step": int(folder.name), "feedback_present": packet["latest"] is not None,
                      "feedback": packet["latest"]["feedback"] if packet["latest"] else None,
                      "usage": raw.get("usage"), "candidate_valid": bool(ev and ev["valid"]),
                      "candidate_metrics": h.metrics(ev) if ev else None,
                      "candidate_sha256": candidate_hash, "selected_sha256": state["best"]["sha256"],
                      "selected_metrics": {k: state["best"][k] for k in ("tokens", "raw_heartbeats", "rank_numerator")},
                      "selection_changed": state["best"]["sha256"] != previous_best if previous_best else state["best"]["code"] != c.read(root / "inputs/problem.json")["reference"]})
        previous_best = state["best"]["sha256"]
    ledger = c.read(root / "budget.json")
    safe = all(a["status"] == "settled" and c.money(a["cost_usd"]) <= c.money(a["reserved_usd"]) for a in ledger["attempts"].values())
    total = sum((c.money(a["cost_usd"]) for a in ledger["attempts"].values() if a["cost_usd"] is not None), Decimal(0))
    config = c.read(root / "inputs/config.json")
    threshold = config["limits"].get("cost_stop_usd")
    target = c.money(threshold) if threshold is not None else c.money(c.read(root / "authorization.json")["total_usd"])
    threshold_ok, spent_before = True, Decimal(0)
    for name in sorted(ledger["attempts"], key=lambda name: int(name.rsplit("-", 1)[-1])):
        if spent_before >= target:
            threshold_ok = False
        amount = ledger["attempts"][name]["cost_usd"]
        if amount is None:
            threshold_ok = False
        else:
            spent_before += c.money(amount)
    report = {"main_commit": h.git_metadata(REPO)["head"], "entrypoint": "lean_agent.harness.run",
              "status": result["status"], "calls": result["state"]["calls"], "cost_usd": str(total) if safe else None,
              "budget_usd": str(target), "mode": "threshold" if threshold is not None else "strict_cap",
              "stop_reason": result["stop_reason"], "overshoot_usd": str(max(Decimal(0), total-target)),
              "budget_ok": safe and (total <= target if threshold is None else threshold_ok),
              "steps": steps, "replay": replay,
              "final_valid": result["final_valid"], "full_original_module_passed": checked["returncode"] == 0 and not checked["timed_out"],
              "baseline": result["baseline"], "selected_metrics": result["final"],
              "improved": result["state"]["best"]["code"] != c.read(root / "inputs/problem.json")["reference"],
              "secret_in_evidence": any(key.encode() in p.read_bytes() for p in root.rglob("*") if p.is_file())}
    c.write(root / "report.json", report)
    c.write(root / "artifacts.json", c.inventory(root))
    print(c.canonical({k: report[k] for k in ["status", "calls", "cost_usd", "budget_ok", "final_valid", "full_original_module_passed", "improved", "replay"]}), end="")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "check", "run"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cost-stop-usd", help="Prepare without a call limit; stop after a response reaches this cumulative cost")
    parser.add_argument("--common", type=Path, help="P02 source packet directory (P02/metadata.json, source.lean, packet.txt)")
    parser.add_argument("--prepared-environment", type=Path, help="Manifest made by lean-agent freeze-environment")
    parser.add_argument("--conditions", type=Path, default=Path(__file__).with_name("configs") / "p02-main-loop.json")
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == "prepare":
        if args.common is None or args.prepared_environment is None:
            parser.error("prepare requires --common and --prepared-environment")
        prepare(root, args.cost_stop_usd, common=args.common,
                prepared_manifest=args.prepared_environment, conditions_path=args.conditions)
    else:
        run(root, check_only=args.command == "check")


if __name__ == "__main__":
    main()
