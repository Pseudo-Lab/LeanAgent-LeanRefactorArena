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


def read(path):
    return json.loads(Path(path).read_text())


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


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
                    for record in value["runs"]:
                        evidence_dir = result_path.parent / environment
                        if sha((evidence_dir / record["source"]).read_text()) != record["source_sha256"]:
                            errors.append(f"F{number:03}: saved compiler source hash mismatch")
                        if sha((evidence_dir / record["log"]).read_text()) != record["log_sha256"]:
                            errors.append(f"F{number:03}: saved compiler log hash mismatch")
            if Decimal(summary["cost_usd"]) != spent or summary["calls"] != len(attempts):
                errors.append(f"F{number:03}: summary accounting mismatch")
            if spent < Decimal(authorization["per_problem_target_usd"]):
                errors.append(f"F{number:03}: completed below authorized cost threshold")
            baseline, selected = summary["baseline"], summary["final"]
            length_ratio = selected["tokens"] / baseline["tokens"]
            heartbeat_ratio = selected["raw_heartbeats"] / baseline["raw_heartbeats"]
            row.update(status="completed", baseline=baseline, final=selected,
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
