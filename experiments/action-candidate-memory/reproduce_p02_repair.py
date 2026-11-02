#!/usr/bin/env python3
"""Reproduce both failed API candidates, then check a minimal manual repair.

Uses fixture responses and the original pinned Lean environment. No API calls.
The manual repair is debugging evidence, not a model-performance result.
"""
import argparse
import json
from pathlib import Path
import shutil

from lean_agent import artifacts as a, diagnostics, harness as h, prepared
from lean_agent.evaluator.tokens import proof_body


def run(original, output):
    original, output = original.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    hashes = a.read(original / "artifacts.json")
    def source(relative):
        path = original / relative
        if a.sha(path.read_bytes()) != hashes[relative]:
            raise ValueError("Original evidence changed: " + relative)
        return path.read_text()
    failed = [source(f"actions-memory/steps/{step}/candidate.lean") for step in ("002", "003")]
    old = """    simp_all [Imperative.HasVarsPure.getVars, extractOldExprVars,
      Lambda.LExpr.LExpr.getVars, List.Subset, List.mem_append]
    intro x hx
    cases hx <;> simp_all
    all_goals
      rename_i hx
      cases hx <;> simp_all"""
    new = """    simp_all [Imperative.HasVarsPure.getVars, extractOldExprVars,
      Lambda.LExpr.LExpr.getVars, List.Subset, List.mem_append] <;>
      (intro x hx
       cases hx <;> try simp_all
       all_goals
         rename_i hx
         cases hx <;> simp_all)"""
    if failed[1].count(old) != 1:
        raise ValueError("Recorded failed proof differs from expected repair site")
    fixed = failed[1].replace(old, new, 1)
    inputs = output / "inputs"
    inputs.mkdir()
    for name in ("problem.json", "context.lean.in", "prepared.json", "source.lean", "metadata.json", "corpus.json"):
        (inputs / name).write_text(source("inputs/" + name))
    shutil.copytree(original / "inputs/project", inputs / "project")
    (inputs / "prompt.txt").write_text((Path(__file__).parent / "prompt.txt").read_text())
    problem = a.read(inputs / "problem.json")
    responses = []
    for index, code in enumerate([*failed, fixed], 1):
        responses.append(json.dumps({"action": "propose" if index == 1 else "repair",
            "parent_id": "c000" if index == 1 else f"c{index - 1:03}",
            "strategy": "recorded API failure" if index < 3 else "manual tactic scoping repair",
            "proof": proof_body(code, problem["statement"]).strip()}))
    responses.append('{"action":"finish"}')
    a.write(inputs / "responses.json", responses)
    config = a.read(original / "inputs/actions-memory.json")
    config.update(prompt="prompt.txt", model={"backend": "fixture", "responses": "responses.json"})
    config["limits"].pop("cost_cap_usd", None)
    config["limits"].pop("cost_stop_usd", None)
    config["limits"]["max_calls"] = 4
    a.write(inputs / "config.json", config)
    result = h.run(inputs / "config.json", output / "harness")
    replay = h.replay(output / "harness")
    steps = []
    for index in range(1, 4):
        folder = output / "harness/steps" / f"{index:03}"
        ev = a.read(folder / "evaluation/result.json")
        report = a.read(output / "harness/diagnostics" / f"candidate-{index:03}.json")
        steps.append({"step": index, "valid": ev["valid"], "metrics": h.metrics(ev),
                      "issues": report.get("issues", []), "warning_count": report.get("warning_count", 0)})
    full = output / "full-module"
    full.mkdir()
    meta = a.read(inputs / "metadata.json")
    path = full / "repaired.lean"
    path.write_text((inputs / "source.lean").read_text().replace(meta["src"], fixed.rstrip(), 1))
    evaluator = prepared.PreparedLeanEvaluator(inputs / "prepared.json")
    command = a.read(output / "harness/preflight.json")["effective_command"]
    checked = evaluator.execute([*command, "--root=" + str(full), str(path)], inputs / "project", 120)
    (full / "compile.log").write_text(checked.pop("output"))
    a.write(full / "result.json", checked)
    summary = {"schema_version": 1, "purpose": "Offline reproduction and manual repair; not a new API/model result",
        "paid_requests": 0, "cost_usd": "0", "steps": steps, "manual_repair_metrics": steps[2]["metrics"],
        "selected_is_manual_repair": result["state"]["best"]["sha256"] == a.sha(fixed), "final": result["final"],
        "replay_passed": replay["record_replay_passed"],
        "full_module_passed": checked["returncode"] == 0 and not checked["timed_out"],
        "repair": "Scope follow-up tactics to remaining goals; guard optional simp_all cleanup."}
    a.write(output / "report.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if [step["valid"] for step in steps] != [False, False, True] or not summary["full_module_passed"]:
        raise ValueError("Failure reproduction / manual repair did not pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.original_run, args.output)
