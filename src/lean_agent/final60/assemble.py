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

from . import transports
from .contracts import CAP_USD
from .orchestrator import (REPO, Layout, atomic_bytes, atomic_json, load_dataset, load_non_openrouter,
                           normalized_sha, now_iso, read_json, row_spend, sha_bytes, sha_text)

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
    submittable, reason = transports.is_submittable(authorization)
    if not submittable and not (allow_dry_run and authorization.get("dry_run")):
        return None, reason
    return code, None


def development_proofs(layout):
    """(label, proof) of every proof a development-transport row root of this run produced.

    Such roots (OpenAI direct) are never submitted; their proofs join the non-OpenRouter set so
    the provenance checker refuses them as submissions, seeds or prompt content (PR #70).
    """
    from . import openai_direct
    found = []
    for row in range(1, 61):
        root = layout.row_root(row)
        path = root / "authorization.json"
        if not path.exists():
            continue
        try:
            authorization = read_json(path)
        except (OSError, ValueError):
            continue
        if authorization.get("transport") == "openai" or authorization.get("provider") == "OpenAI direct":
            found.extend((f"openai-direct#{item['name']}", item["proof"]) for item in openai_direct.dev_proofs(root))
    return found


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


def failing_names(rules, provenance, static=None):
    names = set(rules.get("problems", {}))
    for line in provenance.get("errors", []):
        names.add(line.split(": ", 1)[0])
    names.update((static or {}).get("problems", {}))
    return names


def static_rules():
    """The golf component's rules module (verbatim app.py filter + check_static), or None when absent."""
    try:
        rules = importlib.import_module(__package__ + ".rules")   # honours sys.modules (tests unset it)
    except ImportError:
        return None
    return rules if hasattr(rules, "official_rejection") and hasattr(rules, "check_static") else None


def static_issues(rules, proof, statement):
    """Research item 3: the Space's verbatim intake filter plus check_static on one submitted proof."""
    issues = []
    try:
        verdict = rules.official_rejection(proof)
    except Exception as exc:
        verdict = "official filter error: " + type(exc).__name__
    if verdict:
        issues.append("official: " + str(verdict))
    try:
        issues += [str(item) for item in rules.check_static(proof, statement) if str(item) not in issues]
    except Exception as exc:
        issues.append("check_static error: " + type(exc).__name__)
    return issues


def official_filter(rules, data):
    """The verbatim app.py filter over every original (item 3): a hit would reject the whole upload."""
    rejected = {}
    for item in data:
        try:
            verdict = rules.official_rejection(item["src"])
        except Exception as exc:
            verdict = "official filter error: " + type(exc).__name__
        if verdict:
            rejected[item["name"]] = str(verdict)
    return rejected


def proof_rejections(code, statement, *, outside_hashes, rules_checker, static_checker):
    """Per-proof pre-checks an alternate must pass before it is re-published (no run-root checks)."""
    issues = []
    if normalized_sha(code) in outside_hashes:
        issues.append("equals a non-OpenRouter proof")
    try:
        issues += [str(item) for item in rules_checker.check_row(statement, code)]
    except Exception as exc:
        issues.append("rules checker error: " + type(exc).__name__)
    if static_checker is not None:
        issues += static_issues(static_checker, code, statement)
    return issues


# Alternates tried per row before it reverts to its original (select_final keeps at most two).
MAX_ALTERNATES = 4


def alternate_for(layout, row, item, reason, *, outside_hashes, rules_checker, static_checker, enabled=True):
    """Re-publish the row's best untried validated alternate (rowworker.fallback_to_alternate).

    Returns (code, info) when an alternate was published as an OpenRouter-run proof, else
    (None, why). Never raises: a failure here means the row keeps its original this round.
    """
    if not enabled:
        return None, "alternates disabled"
    try:
        from . import rowworker
        return rowworker.fallback_to_alternate(
            layout, row, reason=reason, rejects=lambda code: proof_rejections(
                code, item["statement"], outside_hashes=outside_hashes, rules_checker=rules_checker,
                static_checker=static_checker))
    except Exception as exc:
        return None, f"alternates unavailable: {type(exc).__name__}: {exc}"[:300]


def assemble(run_dir, *, final, dataset=None, allow_dry_run=False, alternates=True):
    layout = Layout(run_dir)
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    if dataset is None and layout.plan.exists():
        dataset = read_json(layout.plan).get("dataset")
    data = load_dataset(dataset)
    rules_checker, rules_path = checker("check_submission_rules")
    provenance_checker, provenance_path = checker("check_submission_provenance")
    outside = [(f"{row['source']}#{row['name']}", row["proof"]) for row in load_non_openrouter(layout)]
    outside.extend(development_proofs(layout))
    outside_hashes = {normalized_sha(proof) for _, proof in outside}
    static_checker = static_rules()
    choice, reasons, facts, swapped = {}, {}, {}, {}

    def try_alternate(row, reason):
        """A rejected row: its next validated alternate (published into the root), else the original."""
        swaps = swapped.setdefault(row, [])
        code, info = (None, "alternate limit reached") if len(swaps) >= MAX_ALTERNATES else alternate_for(
            layout, row, data[row - 1], reason, outside_hashes=outside_hashes, rules_checker=rules_checker,
            static_checker=static_checker, enabled=alternates)
        if code is None:
            reasons[row] = reason + (" | alternates: " + str(info) if info else "")
            return None
        swaps.append({"label": info["alternate"]["label"], "sha256": info["selected_sha256"],
                      "local_score_estimate": info["local_score_estimate"], "replaced": reason[:300]})
        facts[row] = row_facts(layout, row)
        reasons.pop(row, None)
        return code

    for row in range(1, 61):
        facts[row] = row_facts(layout, row)
        code, reason = published_proof(layout, row, allow_dry_run=allow_dry_run)
        if code is not None and Decimal(facts[row]["total_spend_usd"]) > CAP_USD:
            code, reason = None, "recorded spend exceeds the 2.99 cap"
        if code is not None and facts[row].get("ledger_mirror_agrees") is False:
            code, reason = None, "SQLite mirror spend exceeds ledger.json plus declared prior"
        if code is None and str(reason).startswith("row audit failed"):
            # The worker's audit rejected its chosen proof: a validated alternate may still pass.
            code = try_alternate(row, reason)
            reason = reasons.get(row)
        choice[row] = code
        if reason:
            reasons[row] = reason
    benchmark = [{"name": item["name"], "statement": item["statement"], "reference": item["src"]} for item in data]
    by_name = {item["name"]: index + 1 for index, item in enumerate(data)}
    checks = {}
    # Each failing round reverts at least one improved row to its original or swaps it for one
    # of its never-tried alternates (at most MAX_ALTERNATES per row), so the last round always
    # checks exactly the submission that is written.
    for round_number in range(1, 62 + 60 * MAX_ALTERNATES):
        submission = [{"name": item["name"], "proof": choice[index + 1] if choice[index + 1] is not None else item["src"]}
                      for index, item in enumerate(data)]
        rules = rules_checker.check(data, submission)
        roots = [cached_run_root(provenance_checker, layout.row_root(row)) for row in range(1, 61) if choice[row] is not None]
        manifest = [{"name": data[row - 1]["name"], "prior_cost_usd": facts[row]["prior_cost_usd"]}
                    for row in range(1, 61) if choice[row] is not None and Decimal(facts[row]["prior_cost_usd"]) > 0]
        provenance = provenance_checker.check(benchmark, submission, roots, manifest, outside, OFFICIAL_CAP)
        # Third checker (item 3): the verbatim app.py intake filter and check_static on every improved row.
        static = {"checker": "lean_agent.final60.rules" if static_checker else "unavailable", "problems": {}}
        if static_checker is not None:
            for row in range(1, 61):
                if choice[row] is not None:
                    issues = static_issues(static_checker, choice[row], data[row - 1]["statement"])
                    if issues:
                        static["problems"][data[row - 1]["name"]] = issues
        checks = {"round": round_number, "rules": rules, "provenance": provenance, "static": static}
        bad = [by_name[name] for name in failing_names(rules, provenance, static)
               if name in by_name and choice[by_name[name]] is not None]
        if not bad:
            break
        for row in bad:
            messages = rules.get("problems", {}).get(data[row - 1]["name"], []) + [
                line for line in provenance.get("errors", []) if line.startswith(data[row - 1]["name"] + ": ")] + \
                static["problems"].get(data[row - 1]["name"], [])
            # The next validated alternate (re-published into the row root and re-checked in the
            # next round), the original only when none is left.
            choice[row] = try_alternate(row, "checker rejected the published proof: " + "; ".join(messages)[:600])
    # The loop never reverts an original, so the official filter runs over all 60 originals too:
    # one rejected original would reject the whole upload ("Rejected - fix these and re-upload").
    originals_rejected = official_filter(static_checker, data) if static_checker is not None else {}
    official = {"checker": checks["static"]["checker"], "originals_checked": 60 if static_checker else 0,
                "originals_rejected": originals_rejected,
                "submission_rejected": {name: verdict for name, verdict in
                                        (official_filter(static_checker, [{"name": entry["name"], "src": entry["proof"]}
                                                                          for entry in submission]).items()
                                         if static_checker else ())}}
    atomic_json(layout.run_dir / "checks/official.json", official)
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
        elif entry.get("local_score_estimate") is None:
            published = read_json(layout.row_root(row) / "published.json")
            entry["local_score_estimate"] = float(published.get("local_score_estimate") or 100 / 3)
        if swapped.get(row):
            entry["alternates_used"] = swapped[row]
        rows.append(entry)
    spend = [Decimal(entry["total_spend_usd"]) for entry in rows]
    issues = len(checks["rules"].get("problems", {})) + len(checks["rules"].get("missing", [])) + \
        len(checks["provenance"].get("errors", [])) + len(checks["provenance"].get("missing", [])) + \
        len(checks["static"].get("problems", {})) + len(official["submission_rejected"])
    report = {"at": now_iso(), "final": final, "rows_submitted": len(submission),
              "improved": sum(entry["origin"] == "openrouter-run" for entry in rows),
              "checker_issues": issues, "checks_passed": issues == 0,
              "official_filter": official,
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
        "passed": issues == 0, "issues": issues, "round": checks["round"], "static_checker": official["checker"],
        "originals_rejected": sorted(originals_rejected)},
        "mean_local_score_estimate": report["mean_local_score_estimate"],
        "submission": str(layout.run_dir / "submission.jsonl")}


def render_markdown(report):
    official = report.get("official_filter") or {}
    lines = [f"# final60 run report ({'final' if report['final'] else 'rolling'})", "",
             f"- Generated: {report['at']}",
             f"- Rows submitted: {report['rows_submitted']}; improved (OpenRouter run): {report['improved']}",
             f"- Checkers: {'passed' if report['checks_passed'] else str(report['checker_issues']) + ' issue(s)'}",
             f"- Official intake filter ({official.get('checker', 'n/a')}): "
             f"{len(official.get('submission_rejected') or {})} submitted row(s) rejected, "
             f"{len(official.get('originals_rejected') or {})} original(s) rejected",
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
    rejected = (report.get("official_filter") or {}).get("submission_rejected") or {}
    lines = ["final60 submission ready" if not rejected else "final60 submission NOT ready: DO NOT UPLOAD",
             f"generated_at: {report['at']}",
             f"file: {layout.run_dir / 'submission.jsonl'}", f"sha256: {report['submission_sha256']}",
             f"rows: {report['rows_submitted']}  improved: {report['improved']}  checks_passed: {report['checks_passed']}",
             f"mean_local_score_estimate: {report['mean_local_score_estimate']:.2f} (local, not official)"]
    if rejected:
        lines.append("official intake filter rejects: " + "; ".join(f"{name}: {why}" for name, why in sorted(rejected.items()))[:1000])
    lines += ["Upload this file once, before 20:45 KST. The leaderboard keeps only the latest submission.", "",
              "row\torigin\tlast_validated_at\tnote"]
    for entry in report["rows"]:
        published = layout.row_root(entry["row"]) / "published.json"
        at = read_json(published).get("at") if published.exists() else "-"
        lines.append(f"F{entry['row']:03}\t{entry['origin']}\t{at}\t{entry.get('fallback_reason', '')[:100]}")
    return "\n".join(lines) + "\n"
