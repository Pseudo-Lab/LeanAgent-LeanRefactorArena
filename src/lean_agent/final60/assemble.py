"""Assemble the 60-row submission: published rows or originals, both checkers, fallback.

A row's proof is used only when rows/F0NN/published.json names its selected.lean
and report.json by hash, the row audit passed, the root is an OpenRouter root
(never a dry run) and both checkers accept it. Every other row is the dataset
original, which scores 33.33 rather than 0. No model call and no Lean here.
"""
from __future__ import annotations

from decimal import Decimal
import importlib.util
import json
from pathlib import Path

from .contracts import CAP_USD
from .orchestrator import (REPO, Layout, atomic_bytes, atomic_json, load_dataset, load_non_openrouter,
                           now_iso, read_json, row_spend, sha_bytes, sha_text)

OFFICIAL_CAP = Decimal("3")


def checker(name):
    """The repo script (PR #64/#70) when present, else the vendored copy in final60/checks."""
    path = REPO / "scripts" / (name + ".py")
    if not path.exists():
        path = Path(__file__).with_name("checks") / (name + ".py")
    spec = importlib.util.spec_from_file_location("final60_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def cached_run_root(module, root):
    """PR #70 RunRoot whose requests() is read once per folder (the checker re-reads them per outside proof).

    The check logic is the checker's own; only file reads are cached (one folder at a time,
    which matches check()'s access order and bounds memory to one row's requests).
    """
    class CachedRunRoot(module.RunRoot):
        def requests(self, folder):
            if getattr(self, "_final60_folder", None) != folder:
                self._final60_folder, self._final60_requests = folder, list(super().requests(folder))
            return iter(self._final60_requests)
    return CachedRunRoot(root)


def published_proof(layout, row, *, allow_dry_run=False):
    """(code, None) for a publishable OpenRouter row, else (None, reason)."""
    root = layout.row_root(row)
    path = root / "published.json"
    if not path.exists():
        return None, "not published yet"
    entry = read_json(path)
    if entry.get("origin") != "openrouter-run":
        return None, entry.get("reason") or "no improvement over the original"
    try:
        code = (layout.row_folder(row) / "selected.lean").read_text(encoding="utf-8")
        report_bytes = (root / "report.json").read_bytes()
        authorization = read_json(root / "authorization.json")
        read_json(root / "ledger.json")
    except (OSError, ValueError) as exc:
        return None, "missing run evidence: " + type(exc).__name__
    if sha_text(code) != entry.get("selected_sha256") or sha_bytes(report_bytes) != entry.get("report_sha256"):
        return None, "selected.lean or report.json changed after publication"
    if not json.loads(report_bytes).get("audit_passed"):
        return None, "row audit failed"
    if authorization.get("provider") != "OpenRouter" or not str(authorization.get("api_endpoint", "")).startswith("https://openrouter.ai/"):
        return None, "not an OpenRouter run root"
    if authorization.get("dry_run") and not allow_dry_run:
        return None, "dry-run root (mock transport) is never submitted"
    return code, None


def sqlite_spend(layout, row):
    """SQLite mirror spend for the row when the transport ledger is available (critic A1/A11)."""
    if not layout.sqlite.exists():
        return None
    try:
        from .ledger import CostLedger
        return Decimal(str(CostLedger(layout.sqlite).spent(f"F{row:03}")))
    except Exception:
        return None


def prior_cost(layout, row):
    path = layout.row_folder(row) / "input/final60.json"
    try:
        return Decimal(read_json(path)["prior_cost_usd"])
    except (OSError, ValueError, KeyError):
        return Decimal(0)


def row_facts(layout, row):
    """Calls, spend, models and providers recorded in the row's ledger.json and report."""
    root = layout.row_root(row)
    facts = {"calls": 0, "spent_usd": str(row_spend(layout, row)), "prior_cost_usd": str(prior_cost(layout, row)),
             "served_providers": [], "served_models": []}
    if (root / "ledger.json").exists():
        attempts = read_json(root / "ledger.json").get("attempts", {}).values()
        facts["calls"] = len(attempts)
        facts["served_providers"] = sorted({str(item.get("served_provider")) for item in attempts if item.get("served_provider")})
        facts["served_models"] = sorted({str(item.get("served_model")) for item in attempts if item.get("served_model")})
    if (root / "authorization.json").exists():
        authorization = read_json(root / "authorization.json")
        facts.update(api_endpoint=authorization.get("api_endpoint"), provider=authorization.get("provider"),
                     dry_run=bool(authorization.get("dry_run")))
    config = layout.row_folder(row) / "input/config.json"
    if config.exists():
        model = read_json(config).get("model", {})
        facts.update(model=model.get("id"), model_provider_pin=model.get("provider"),
                     reasoning_effort=model.get("reasoning_effort"))
    report = root / "report.json"
    if report.exists():
        rows = [entry for entry in read_json(report).get("rows", []) if entry.get("row") == row]
        if rows and "final" in rows[0]:
            facts.update(baseline=rows[0]["baseline"], final=rows[0]["final"],
                         local_score_estimate=rows[0]["local_score_estimate"],
                         length_reduction_pct=rows[0]["length_reduction_pct"],
                         heartbeat_reduction_pct=rows[0]["heartbeat_reduction_pct"])
    total = Decimal(facts["spent_usd"]) + Decimal(facts["prior_cost_usd"])
    facts["total_spend_usd"] = str(total)
    mirror = sqlite_spend(layout, row)
    if mirror is not None:
        facts["sqlite_spend_usd"] = str(mirror)
        facts["ledger_mirror_agrees"] = mirror <= total
    return facts


def failing_names(rules, provenance):
    names = set(rules.get("problems", {}))
    for line in provenance.get("errors", []):
        names.add(line.split(": ", 1)[0])
    return names


def assemble(run_dir, *, final, dataset=None, allow_dry_run=False):
    layout = Layout(run_dir)
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    if dataset is None and layout.plan.exists():
        dataset = read_json(layout.plan).get("dataset")
    data = load_dataset(dataset)
    rules_checker, rules_path = checker("check_submission_rules")
    provenance_checker, provenance_path = checker("check_submission_provenance")
    outside = [(f"{row['source']}#{row['name']}", row["proof"]) for row in load_non_openrouter(layout)]
    choice, reasons, facts = {}, {}, {}
    for row in range(1, 61):
        facts[row] = row_facts(layout, row)
        code, reason = published_proof(layout, row, allow_dry_run=allow_dry_run)
        if code is not None and Decimal(facts[row]["total_spend_usd"]) > CAP_USD:
            code, reason = None, "recorded spend exceeds the 2.99 cap"
        if code is not None and facts[row].get("ledger_mirror_agrees") is False:
            code, reason = None, "SQLite mirror spend exceeds ledger.json plus declared prior"
        choice[row] = code
        if reason:
            reasons[row] = reason
    benchmark = [{"name": item["name"], "statement": item["statement"], "reference": item["src"]} for item in data]
    by_name = {item["name"]: index + 1 for index, item in enumerate(data)}
    checks = {}
    # Each failing round reverts at least one improved row, so the last round always checks
    # exactly the submission that is written (at most 61 rounds).
    for round_number in range(1, 62):
        submission = [{"name": item["name"], "proof": choice[index + 1] if choice[index + 1] is not None else item["src"]}
                      for index, item in enumerate(data)]
        rules = rules_checker.check(data, submission)
        roots = [cached_run_root(provenance_checker, layout.row_root(row)) for row in range(1, 61) if choice[row] is not None]
        manifest = [{"name": data[row - 1]["name"], "prior_cost_usd": facts[row]["prior_cost_usd"]}
                    for row in range(1, 61) if choice[row] is not None and Decimal(facts[row]["prior_cost_usd"]) > 0]
        provenance = provenance_checker.check(benchmark, submission, roots, manifest, outside, OFFICIAL_CAP)
        checks = {"round": round_number, "rules": rules, "provenance": provenance}
        bad = [by_name[name] for name in failing_names(rules, provenance) if name in by_name and choice[by_name[name]] is not None]
        if not bad:
            break
        for row in bad:
            messages = rules.get("problems", {}).get(data[row - 1]["name"], []) + [
                line for line in provenance.get("errors", []) if line.startswith(data[row - 1]["name"] + ": ")]
            reasons[row] = "checker rejected the published proof: " + "; ".join(messages)[:600]
            choice[row] = None
    lines = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in submission)
    atomic_bytes(layout.run_dir / "submission.jsonl", lines.encode("utf-8"))
    atomic_bytes(layout.run_dir / "provenance-benchmark.jsonl",
                 "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in benchmark).encode("utf-8"))
    atomic_json(layout.run_dir / "checks/rules.json", {**checks["rules"], "checker": str(rules_path)})
    atomic_json(layout.run_dir / "checks/provenance.json", {**checks["provenance"], "checker": str(provenance_path),
                                                            "non_openrouter_proofs": len(outside)})
    rows = []
    for row in range(1, 61):
        item = data[row - 1]
        improved = choice[row] is not None
        entry = {"row": row, "name": item["name"], "source": item["source"],
                 "origin": "openrouter-run" if improved else "original",
                 "proof_sha256": sha_text(submission[row - 1]["proof"]), **facts[row]}
        if not improved:
            entry["local_score_estimate"] = 100 / 3
            entry["fallback_reason"] = reasons.get(row, "original")
            entry.pop("final", None)
        rows.append(entry)
    spend = [Decimal(entry["total_spend_usd"]) for entry in rows]
    issues = len(checks["rules"].get("problems", {})) + len(checks["rules"].get("missing", [])) + \
        len(checks["provenance"].get("errors", [])) + len(checks["provenance"].get("missing", []))
    report = {"at": now_iso(), "final": final, "rows_submitted": len(submission),
              "improved": sum(entry["origin"] == "openrouter-run" for entry in rows),
              "checker_issues": issues, "checks_passed": issues == 0,
              "mean_local_score_estimate": sum(entry["local_score_estimate"] for entry in rows) / 60,
              "score_note": "local estimate: (L + H + C)/3 with C = 100 for all-version-validated proofs; not official",
              "spend": {"total_usd": str(sum(spend, Decimal(0))), "mean_per_problem_usd": str(sum(spend, Decimal(0)) / 60),
                        "max_per_problem_usd": str(max(spend)), "cap_per_problem_usd": str(CAP_USD),
                        "calls": sum(entry["calls"] for entry in rows),
                        "basis": "ledger.json per row (every call, including retries and discarded candidates) plus declared prior spend"},
              "models": sorted({json.dumps({"model": entry.get("model"), "provider_pin": entry.get("model_provider_pin"),
                                            "served_providers": entry.get("served_providers"),
                                            "endpoint": entry.get("api_endpoint")}, sort_keys=True)
                                for entry in rows if entry.get("model")}),
              "submission_sha256": sha_text(lines), "rows": rows}
    report["models"] = [json.loads(value) for value in report["models"]]
    atomic_json(layout.run_dir / "report.json", report)
    atomic_bytes(layout.run_dir / "report.md", render_markdown(report).encode("utf-8"))
    if final:
        atomic_bytes(layout.run_dir / "SUBMIT-READY.txt", submit_ready(layout, report).encode("utf-8"))
    return {"rows": len(submission), "improved": report["improved"], "checks": {
        "passed": issues == 0, "issues": issues, "round": checks["round"]},
        "mean_local_score_estimate": report["mean_local_score_estimate"],
        "submission": str(layout.run_dir / "submission.jsonl")}


def render_markdown(report):
    lines = [f"# final60 run report ({'final' if report['final'] else 'rolling'})", "",
             f"- Generated: {report['at']}",
             f"- Rows submitted: {report['rows_submitted']}; improved (OpenRouter run): {report['improved']}",
             f"- Checkers: {'passed' if report['checks_passed'] else str(report['checker_issues']) + ' issue(s)'}",
             f"- Mean local score estimate (not official): {report['mean_local_score_estimate']:.2f}",
             f"- Spend: total ${report['spend']['total_usd']}, mean ${report['spend']['mean_per_problem_usd'][:8]} per problem, "
             f"max ${report['spend']['max_per_problem_usd']} (cap ${report['spend']['cap_per_problem_usd']}), "
             f"{report['spend']['calls']} calls",
             "", "## Models", ""]
    for model in report["models"]:
        lines.append(f"- {model['model']} (provider pin {model['provider_pin']}; served by "
                     f"{', '.join(model['served_providers'] or ['n/a'])}; endpoint {model['endpoint']})")
    lines += ["", "## Rows", "", "| Row | Source | Origin | Score est. | Calls | Spend $ | Note |", "|---|---|---|---|---|---|---|"]
    for entry in report["rows"]:
        lines.append(f"| F{entry['row']:03} | {entry['source']} | {entry['origin']} | {entry['local_score_estimate']:.2f} | "
                     f"{entry['calls']} | {entry['total_spend_usd']} | {entry.get('fallback_reason', '')[:80]} |")
    return "\n".join(lines) + "\n"


def submit_ready(layout, report):
    lines = ["final60 submission ready", f"generated_at: {report['at']}",
             f"file: {layout.run_dir / 'submission.jsonl'}", f"sha256: {report['submission_sha256']}",
             f"rows: {report['rows_submitted']}  improved: {report['improved']}  checks_passed: {report['checks_passed']}",
             f"mean_local_score_estimate: {report['mean_local_score_estimate']:.2f} (local, not official)",
             "Upload this file once, before 20:45 KST. The leaderboard keeps only the latest submission.", "",
             "row\torigin\tlast_validated_at\tnote"]
    for entry in report["rows"]:
        published = layout.row_root(entry["row"]) / "published.json"
        at = read_json(published).get("at") if published.exists() else "-"
        lines.append(f"F{entry['row']:03}\t{entry['origin']}\t{at}\t{entry.get('fallback_reason', '')[:100]}")
    return "\n".join(lines) + "\n"
