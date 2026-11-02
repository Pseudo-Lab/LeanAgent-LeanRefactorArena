#!/usr/bin/env python3
"""Audit durable model receipts and export the completed local final batch."""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from policy import validate_declaration
from openai_transport import compute_cost, normalize
from evaluation_cache import EvaluationCache
from lean_agent import autosolver, harness as h, portfolio


def read(path):
    return json.loads(Path(path).read_text())


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def audit_portfolio(folder, summary, attempts):
    """Recount the routing barrier from saved requests and evaluation receipts."""
    config = read(folder / "input/config.json")
    if not portfolio.enabled(config):
        if "portfolio" in summary or summary.get("stop_reason") == "portfolio_complete":
            raise ValueError("Portfolio completion without configured portfolio")
        return False
    portfolio.validate(config["agent"]["portfolio"])
    state = {}
    portfolio.initialize(state, config)
    scope, quotas = state["portfolio"], portfolio.quotas(config)
    for _, item in attempts:
        branch = scope["active"]
        if branch == "complete":
            raise ValueError("Model dispatch after portfolio completion")
        step = folder / "steps" / f"{item['step']:04}"
        packet = json.loads(read(step / "request.json")["messages"][1]["content"])
        if packet["portfolio"]["branch"] != branch:
            raise ValueError("Scout/merger request crossed evaluation barrier")
        scope["calls"][branch] += 1
        if (step / "selection-result.json").exists():
            if not (step / "candidate.lean").is_file():
                raise ValueError("Portfolio evaluation missing candidate source")
            if type(read(step / "selection-result.json")["valid"]) is not bool:
                raise ValueError("Portfolio evaluation missing validity")
            scope["evaluations"][branch] += 1
        if scope["evaluations"][branch] == quotas[branch]:
            index = portfolio.BRANCHES.index(branch) + 1
            scope["active"] = portfolio.BRANCHES[index] if index < len(portfolio.BRANCHES) else "complete"
    expected = portfolio.summary(state, config)
    saved = read(folder / "state.json")
    if summary.get("portfolio") != expected or portfolio.summary(saved, config) != expected:
        raise ValueError("Portfolio summary/state differs from recorded routing")
    if saved["calls"] != len(attempts):
        raise ValueError("Portfolio state call count differs from ledger")
    if (summary["stop_reason"] == "portfolio_complete") != expected["complete"]:
        raise ValueError("Portfolio completion reason differs from recorded routing")
    if (summary["status"] == "completed") != expected["complete"]:
        raise ValueError("Incomplete portfolio reported as completed")
    return expected["complete"]


def audit_autosolver(folder, summary, attempts):
    config = read(folder / "input/config.json")
    if not autosolver.enabled(config):
        return
    state = read(folder / "state.json")
    totals = {"searches": 0, "attempts": 0, "inspections": 0, "verified_candidates": 0,
              "native_seconds": 0.0, "model_calls": 0}
    for _, item in attempts:
        step = folder / "steps" / f"{item['step']:04}"
        code = (step / "candidate.lean").read_text() if (step / "candidate.lean").exists() else None
        result = read(step / "selection-result.json") if (step / "selection-result.json").exists() else None
        automatic = h.read_automatic(config, read(step / "response.json"), code, result, step)
        if automatic is None:
            continue
        outcome = autosolver.replay_search(config, code, automatic["search"])
        parent = f"c{item['step']:03}"
        info = autosolver.summary(outcome, parent)
        totals["searches"] += 1
        for key in ("attempts", "inspections", "native_seconds"):
            totals[key] += info[key]
        if outcome["candidate_code"] is not None:
            child = state["exploration"]["candidates"][parent + "-auto"]
            measured = automatic["evaluation"]
            candidate = h.candidate(outcome["candidate_code"], measured, summary["baseline"])
            if (child["code"] != outcome["candidate_code"] or child["sha256"] != sha(child["code"])
                    or child["parent_id"] != parent or child["valid"] != bool(candidate)
                    or candidate and any(child[key] != value for key, value in candidate.items())):
                raise ValueError("Automatic candidate ancestry/measurement differs")
            totals["verified_candidates"] += candidate is not None
            if portfolio.enabled(config) and state["portfolio"]["owners"][parent] != state["portfolio"]["owners"][parent + "-auto"]:
                raise ValueError("Automatic candidate crossed scout scope")
    expected = totals if totals["searches"] else {"searches": 0, "model_calls": 0}
    if state.get("autosolver", expected) != expected or summary.get("autosolver") != expected:
        raise ValueError("AutoSolver accounting differs from saved inspections")


def build_report(root, *, require_complete=False):
    root = Path(root).resolve()
    authorization = read(root / "authorization.json")
    ledger = read(root / "ledger.json")
    errors, generations, by_row = [], set(), {}
    for attempt, item in ledger["attempts"].items():
        row = item["row"]
        by_row.setdefault(row, []).append((attempt, item))
        if item["status"] != "settled":
            errors.append(attempt + ": unsettled billing")
        if item.get("cost_usd") is None:
            continue
        step = root / "problems" / f"F{row:03}" / "steps" / f"{item['step']:04}"
        try:
            response = read(step / "response.json")
            provider_response = read(step / "provider-response.json")
            recalculated = compute_cost(provider_response)
            generation = response.get("id")
            if not generation or generation in generations:
                errors.append(attempt + ": missing/duplicate generation ID")
            generations.add(generation)
            if generation != item["response_id"]:
                errors.append(attempt + ": response identity differs from ledger")
            if Decimal(str(response["usage"]["cost"])) != Decimal(item["cost_usd"]):
                errors.append(attempt + ": response cost differs from ledger")
            if Decimal(recalculated["cost_usd"]) != Decimal(item["cost_usd"]):
                errors.append(attempt + ": provider token accounting differs from ledger")
            if provider_response.get("id") != generation:
                errors.append(attempt + ": raw provider response identity mismatch")
            if (recalculated["provider_response_sha256"] != item.get("provider_response_sha256") or
                    recalculated != response.get("_cost_receipt")):
                errors.append(attempt + ": raw provider receipt hash differs from ledger/normalized receipt")
            if normalize(provider_response) != response:
                errors.append(attempt + ": normalized response differs from raw provider evidence")
            request = read(step / "request.json")
            # Shared artifacts.canonical uses sorted keys, compact separators.
            canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            if sha(canonical) != item["request_sha256"]:
                errors.append(attempt + ": request hash differs from ledger")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(attempt + ": malformed evidence (" + type(exc).__name__ + ")")
    rows, statuses = [], Counter()
    for number in authorization["rows"]:
        folder = root / "problems" / f"F{number:03}"
        problem = read(folder / "input/problem.json")
        attempts = sorted(by_row.get(number, []), key=lambda value: value[1]["step"])
        spent = Decimal(0)
        for attempt, item in attempts:
            if spent >= Decimal(authorization["per_problem_target_usd"]):
                errors.append(attempt + ": dispatched after cost threshold")
            if item.get("cost_usd") is not None:
                spent += Decimal(item["cost_usd"])
        progress = read(folder / "progress.json") if (folder / "progress.json").exists() else {"status": "prepared"}
        row = {"row": number, "name": problem["name"], "source": problem["source"],
               "status": progress["status"], "known_cost_usd": str(spent), "calls": len(attempts)}
        if (folder / "summary.json").exists():
            summary = read(folder / "summary.json")
            portfolio_complete = False
            try:
                portfolio_complete = audit_portfolio(folder, summary, attempts)
                audit_autosolver(folder, summary, attempts)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"F{number:03}: invalid exploration evidence: {exc}")
            final = read(folder / "final/result.json")
            code = (folder / "selected.lean").read_text()
            try:
                validate_declaration(code, problem["statement"])
            except ValueError as exc:
                errors.append(f"F{number:03}: invalid exported declaration: {exc}")
            if sha(code) != summary["selected"]["sha256"]:
                errors.append(f"F{number:03}: selected source hash mismatch")
            if not final["valid"] or not summary["all_versions_valid"] or summary["final"] is None:
                errors.append(f"F{number:03}: final verification incomplete")
            compatibility = read(folder / "compatibility" / sha(code) / "result.json")
            if (not compatibility["valid"] or
                    set(compatibility["environments"]) != set(problem["environments"]) or
                    not all(value["valid"] for value in compatibility["environments"].values())):
                errors.append(f"F{number:03}: required-version evidence incomplete")
            for result_path in (folder / "final/result.json",
                                folder / "compatibility" / sha(code) / "result.json"):
                evidence = read(result_path)
                for environment, value in evidence["environments"].items():
                    if result_path.parent.name == "final" and value.get("cache"):
                        errors.append(f"F{number:03}: final measurement must be fresh")
                    try:
                        EvaluationCache(root / "evaluation-cache").audit_reuse(
                            value, problem=problem, code=code, environment=environment)
                    except ValueError as exc:
                        errors.append(f"F{number:03}: invalid reused evaluation: {exc}")
                    for record in value["runs"]:
                        evidence_dir = result_path.parent / environment
                        if sha((evidence_dir / record["source"]).read_text()) != record["source_sha256"]:
                            errors.append(f"F{number:03}: saved compiler source hash mismatch")
                        if sha((evidence_dir / record["log"]).read_text()) != record["log_sha256"]:
                            errors.append(f"F{number:03}: saved compiler log hash mismatch")
            if Decimal(summary["cost_usd"]) != spent or summary["calls"] != len(attempts):
                errors.append(f"F{number:03}: summary accounting mismatch")
            if (summary.get("status", "completed") == "completed" and not portfolio_complete
                    and spent < Decimal(authorization["per_problem_target_usd"])):
                errors.append(f"F{number:03}: completed below authorized cost threshold")
            baseline, selected = summary["baseline"], summary["final"]
            length_ratio = selected["tokens"] / baseline["tokens"]
            heartbeat_ratio = selected["raw_heartbeats"] / baseline["raw_heartbeats"]
            row.update(status=summary.get("status", "completed"), baseline=baseline, final=selected,
                       length_reduction_pct=100 * (1-length_ratio),
                       heartbeat_reduction_pct=100 * (1-heartbeat_ratio),
                       local_score_estimate=100 - 100 / 3 * (length_ratio + heartbeat_ratio),
                       selected_sha256=sha(code))
        statuses[row["status"]] += 1
        rows.append(row)
    complete = statuses["completed"] == len(authorization["rows"])
    if require_complete and not complete:
        errors.append("All authorized problems must complete before final export")
    costs = [Decimal(row["known_cost_usd"]) for row in rows]
    report = {"dataset_sha256": authorization["dataset_sha256"], "problem_count": len(rows),
              "completed": statuses["completed"], "statuses": dict(statuses),
              "known_total_usd": str(sum(costs, Decimal(0))),
              "known_mean_usd": str(sum(costs, Decimal(0)) / len(costs)),
              "known_max_usd": str(max(costs)), "attempts": len(ledger["attempts"]),
              "unique_generation_ids": len(generations), "audit_errors": errors,
              "api_cost_basis": "OpenAI response usage times frozen public list prices",
              "provider_invoice_verified": False,
              "all_completed": complete, "audit_passed": not errors,
              "official_evaluation": False, "rows": rows}
    if complete:
        report["mean_local_score_estimate"] = sum(row["local_score_estimate"] for row in rows) / len(rows)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    report = build_report(args.root, require_complete=args.require_complete or args.export)
    (args.root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.export and report["audit_passed"] and report["all_completed"]:
        lines = []
        for row in report["rows"]:
            code = (args.root / "problems" / f"F{row['row']:03}" / "selected.lean").read_text()
            lines.append(json.dumps({"name": row["name"], "proof": code}, ensure_ascii=False))
        (args.root / "submission.jsonl").write_text("\n".join(lines) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False))
    if not report["audit_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
