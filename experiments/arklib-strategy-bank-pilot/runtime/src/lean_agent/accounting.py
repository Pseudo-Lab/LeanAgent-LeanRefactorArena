"""Offline API/subagent cost receipts. No model calls, retries or hidden log access."""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import sys
from statistics import mean, median

MILLION = Decimal(1_000_000)
VERSION = "usage-cost-v2"


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON")))


def money(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Expected a nonnegative USD amount")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid USD amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("Expected finite nonnegative USD amount")
    return amount


def text_id(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing " + field)
    return value


def count(value, field):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError(field + " must be a nonnegative integer or null")
    return value


def normalize_usage(raw):
    """Accept Responses, Chat Completions and Codex turn usage; never tokenize visible text."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("usage must be an object or null")
    def pick(field, *values):
        present = [count(v, field) for v in values if v is not None]
        if present and any(v != present[0] for v in present):
            raise ValueError("Conflicting usage fields: " + field)
        return present[0] if present else None
    def details(key):
        value = raw.get(key)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("Token details must be objects")
        return value
    inp_details = [details(k) for k in ("input_tokens_details", "prompt_tokens_details")]
    out_details = [details(k) for k in ("output_tokens_details", "completion_tokens_details")]
    usage = {
        "input_tokens": pick("input_tokens", raw.get("input_tokens"), raw.get("prompt_tokens")),
        "output_tokens": pick("output_tokens", raw.get("output_tokens"), raw.get("completion_tokens")),
        "cached_input_tokens": pick("cached_input_tokens", raw.get("cached_input_tokens"),
                                    *(d.get("cached_tokens") for d in inp_details)),
        "cache_write_tokens": pick("cache_write_tokens", raw.get("cache_write_input_tokens"),
                                   *(d.get("cache_write_tokens") for d in inp_details)),
        "reasoning_tokens": pick("reasoning_tokens", raw.get("reasoning_output_tokens"),
                                 *(d.get("reasoning_tokens") for d in out_details)),
    }
    usage["unsupported_modalities"] = sorted({key for detail in [raw, *inp_details, *out_details]
        for key in ("audio_tokens", "image_tokens", "video_tokens")
        if count(detail.get(key), key) not in (None, 0)})
    inp, out = usage["input_tokens"], usage["output_tokens"]
    cache, writes = usage["cached_input_tokens"], usage["cache_write_tokens"]
    if inp is not None and (cache or 0) + (writes or 0) > inp:
        raise ValueError("Cached read/write tokens exceed total input tokens")
    if out is not None and usage["reasoning_tokens"] is not None and usage["reasoning_tokens"] > out:
        raise ValueError("Reasoning tokens must be included in total output tokens")
    total = count(raw.get("total_tokens"), "total_tokens")
    if total is not None and inp is not None and out is not None and total != inp + out:
        raise ValueError("total_tokens differs from input + output")
    return usage


def response_record(raw):
    """Normalize one saved response without pricing missing billing as zero.

    Malformed usage remains in response.json. It must not prevent the harness
    from recording a valid provider cost or handling the proof independently.
    """
    from .models import receipt
    bill = receipt(raw)
    try:
        usage, usage_error = normalize_usage(bill["usage"]), None
    except (ValueError, TypeError) as exc:
        usage, usage_error = None, str(exc)
    return {"schema_version": 1, "source": "model_response_usage",
            "response_id": bill["id"], "model": bill["model"], "provider": bill["provider"],
            "reported_cost_usd": bill["cost_usd"], "usage": usage, "usage_error": usage_error}

def response_summary(records):
    """All dispatched responses, including rejected proofs and repeated sources."""
    totals = {}
    for field in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens", "reasoning_tokens"):
        values = [(r["usage"] or {}).get(field) for r in records]
        known = [v for v in values if v is not None]
        complete = bool(values) and len(known) == len(values)
        totals[field] = {"known_records": len(known), "missing_records": len(values)-len(known),
                         "known_subtotal": sum(known), "total": sum(known) if complete else None,
                         "mean": mean(known) if complete else None, "median": median(known) if complete else None}
    costs = [r["reported_cost_usd"] for r in records]
    subtotal = sum((money(v) for v in costs if v is not None), Decimal(0))
    return {"schema_version": 1, "source": "model_response_usage", "responses": len(records),
            "reported_cost_usd": str(subtotal) if all(v is not None for v in costs) else None,
            "reported_cost_known_subtotal_usd": str(subtotal),
            "unknown_cost_responses": sum(v is None for v in costs), "tokens": totals,
            "token_scope": "cache reads/writes included in input; reasoning included in output; not added twice"}


def validate_prices(prices):
    if prices.get("schema_version") != 1 or prices.get("currency") != "USD":
        raise ValueError("Expected price schema_version 1 and USD currency")
    for key in ("rate_card_id", "source", "as_of"):
        text_id(prices.get(key), key)
    if not isinstance(prices.get("models"), dict):
        raise ValueError("Expected per-model prices")
    for model, rates in prices["models"].items():
        text_id(model, "model")
        if not isinstance(rates, dict):
            raise ValueError("Expected model rate object")
        allowed = {"input_per_million", "cached_input_per_million", "cache_write_per_million", "output_per_million"}
        if set(rates) - allowed:
            raise ValueError("Unknown price field")
        for key in ("input_per_million", "output_per_million"):
            money(rates.get(key))
        for value in rates.values():
            money(value)


def estimate(usage, rates):
    """Return text-token API-equivalent cost, not a subscription invoice or tool fee."""
    if usage is None or usage["input_tokens"] is None or usage["output_tokens"] is None:
        return None, [], "missing_usage"
    if usage.get("unsupported_modalities"):
        return None, [], "unsupported_multimodal_usage"
    if rates is None:
        return None, [], "missing_model_rates"
    assumptions = []
    cached = usage["cached_input_tokens"]
    writes = usage["cache_write_tokens"]
    if cached is None:
        cached = 0
        assumptions.append("unreported_cache_reads_priced_as_uncached")
    if writes is None:
        writes = 0
        assumptions.append("no_separate_cache_write_usage_reported")
    if cached and "cached_input_per_million" not in rates:
        return None, assumptions, "missing_cached_input_rate"
    if writes and "cache_write_per_million" not in rates:
        return None, assumptions, "missing_cache_write_rate"
    # Reasoning is already in output_tokens. Do not charge it a second time.
    ordinary = usage["input_tokens"] - cached - writes
    with localcontext() as ctx:
        ctx.prec = 50
        amount = (ordinary * money(rates["input_per_million"])
                  + cached * money(rates.get("cached_input_per_million", 0))
                  + writes * money(rates.get("cache_write_per_million", 0))
                  + usage["output_tokens"] * money(rates["output_per_million"])) / MILLION
    return format(amount, "f"), assumptions, None


def make_receipt(event, mode, prices):
    """One record per API request or exclusive subagent turn, including failed attempts.

    The caller supplies trusted runtime usage, never a model's self-reported estimate.
    Session cumulative totals and inclusive parent totals must not enter this ledger.
    """
    if mode not in ("api", "subagent"):
        raise ValueError("mode must be api or subagent")
    validate_prices(prices)
    ids = {key: text_id(event.get(key), key) for key in ("run_id", "agent_id", "event_id", "model")}
    if event.get("usage_scope") != "exclusive_delta":
        raise ValueError("Require exclusive_delta usage; do not mix cumulative or parent rollup totals")
    status = event.get("status")
    if status not in ("completed", "failed", "incomplete"):
        raise ValueError("Expected completed, failed or incomplete status")
    if mode == "api":
        response = event.get("response")
        if not isinstance(response, dict):
            raise ValueError("API event requires a response object (empty if unavailable)")
        if response.get("model") is not None and response["model"] != ids["model"]:
            raise ValueError("Response model differs from the priced model")
        raw_usage = response.get("usage")
    else:
        raw_usage = event.get("usage")
    usage_error = reported_cost_error = None
    try:
        usage = normalize_usage(raw_usage)
    except ValueError as exc:
        usage, usage_error = None, str(exc)
    reported = None
    if mode == "api" and isinstance(raw_usage, dict) and raw_usage.get("cost") is not None:
        try:
            reported = format(money(raw_usage["cost"]), "f")
        except ValueError as exc:
            reported_cost_error = str(exc)
    estimated, assumptions, unknown = estimate(usage, prices["models"].get(ids["model"]))
    # A partial turn's tokens remain useful evidence but cannot price the whole turn.
    if status == "incomplete":
        estimated, unknown = None, "incomplete_usage_scope"
        reported = None
    effective = reported if reported is not None else estimated
    basis = "provider_reported" if reported is not None else "token_estimate" if estimated is not None else "unknown"
    return {"schema_version": 1, "calculator": VERSION, **ids, "mode": mode,
            "status": status, "usage_scope": "exclusive_delta", "usage": usage,
            "usage_error": usage_error, "reported_cost_error": reported_cost_error,
            "provider_request_id": event.get("response", {}).get("id") if mode == "api" else None,
            "reported_cost_usd": reported, "estimated_token_cost_usd": estimated,
            "accounted_cost_usd": effective, "accounting_basis": basis,
            "estimate_assumptions": assumptions, "estimate_unavailable_reason": unknown,
            "rate_card_sha256": digest(prices), "evidence_sha256": digest(event)}


def summarize(receipts, budget_usd=None, *, allow_empty=False):
    """Dedupe identical delivery, reject conflicting revisions, never hide unknown spend."""
    unique = {}
    for receipt in receipts:
        key = tuple(receipt[k] for k in ("run_id", "agent_id", "event_id"))
        if key in unique and unique[key] != receipt:
            raise ValueError("Conflicting usage for the same event: " + repr(key))
        unique[key] = receipt
    rows = list(unique.values())
    if not rows and not allow_empty:
        raise ValueError("No attempt records; empty input does not establish zero spend")
    request_ids = set()
    for row in rows:
        request_id = row.get("provider_request_id")
        if request_id is not None:
            text_id(request_id, "provider_request_id")
            identity = (row["run_id"], request_id)
            if identity in request_ids:
                raise ValueError("Same provider request appears under different event identities")
            request_ids.add(identity)
    modes = {r["mode"] for r in rows}
    if len(modes) > 1:
        raise ValueError("Report API and subagent modes separately")
    if len({r["rate_card_sha256"] for r in rows}) > 1:
        raise ValueError("Cannot mix rate cards in one comparison")
    unknowns = sum(r["accounted_cost_usd"] is None for r in rows)
    totals = {}
    for key in ("reported_cost_usd", "estimated_token_cost_usd", "accounted_cost_usd"):
        values = [r[key] for r in rows]
        with localcontext() as ctx:
            ctx.prec = 50
            subtotal = sum((money(v) for v in values if v is not None), Decimal(0))
        totals[key] = format(subtotal, "f") if all(v is not None for v in values) else None
        totals[key.removesuffix("_usd") + "_known_subtotal_usd"] = format(subtotal, "f")
    tokens = {}
    for key in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens", "reasoning_tokens"):
        values = [(r.get("usage") or {}).get(key) for r in rows]
        tokens[key] = {"total": sum(values) if all(v is not None for v in values) else None,
                       "known_subtotal": sum(v for v in values if v is not None),
                       "unknown_entries": sum(v is None for v in values)}
    budget = money(budget_usd) if budget_usd is not None else None
    known = money(totals["accounted_cost_known_subtotal_usd"])
    state = "not_configured" if budget is None else (
        "exhausted" if known >= budget else "unknown" if unknowns else "below_limit")
    return {"entries": len(rows), "mode": next(iter(modes), None), "unknown_cost_entries": unknowns,
            "estimated_entries": sum(r["accounting_basis"] == "token_estimate" for r in rows),
            **totals, "tokens": tokens, "budget_usd": None if budget is None else format(budget, "f"),
            "budget_status": state,
            "remaining_accounted_usd": None if budget is None or unknowns else format(max(Decimal(0), budget - known), "f"),
            "budget_scope": "observed_records_only; not a reservation or a hard cap on the next call"}


def codex_turn_records(events, *, run_id, agent_id, model, partial_tail=False):
    """Import one exclusive agent's ordered Codex exec JSONL stream.

    Assign distinct run/agent IDs across executions. The model must be supplied from
    frozen execution configuration: turn.completed usage itself does not identify it.
    """
    records, pending, turn, threads = [], False, 0, set()
    def emit(status, usage=None):
        records.append({"run_id": run_id, "agent_id": agent_id, "model": model,
                        "event_id": f"turn-{turn:04d}", "usage_scope": "exclusive_delta",
                        "status": status, "usage": usage})
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Expected a Codex event object")
        kind = event.get("type")
        if kind == "thread.started":
            threads.add(text_id(event.get("thread_id"), "thread_id"))
            if len(threads) > 1:
                raise ValueError("Multiple threads require separate agent records")
        item = event.get("item") or {}
        if isinstance(item, dict) and "collab" in str(item.get("type", "")):
            raise ValueError("Child-agent rollup scope is unknown; supply exclusive per-agent usage")
        if event.get("model") is not None and event["model"] != model:
            raise ValueError("Runtime model differs from the fixed model")
        if kind == "turn.started":
            if pending:
                emit("incomplete")
            turn += 1
            pending = True
        elif kind in ("turn.completed", "turn.failed"):
            if not pending:
                raise ValueError("Terminal turn event without turn.started; provide a complete ordered stream")
            emit("completed" if kind == "turn.completed" else "failed", event.get("usage"))
            pending = False
    if pending:
        emit("incomplete")
    elif partial_tail:
        turn += 1
        emit("incomplete")
    if not records:
        # Empty/crashed exports do not prove zero usage.
        turn = 1
        emit("incomplete")
    return records


def parse_codex_jsonl(data):
    events, partial = [], False
    for line in data.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            partial = bool(line.strip())
            break
        if line.strip():
            events.append(read_json(line.decode("utf-8")))
    return events, partial


def harness_records(root, *, run_id, agent_id):
    """Import only explicit native-harness request/response files, including pending calls."""
    records, sources = [], []
    for folder in sorted((root / "steps").glob("[0-9]*")):
        request_path, response_path = folder / "request.json", folder / "response.json"
        if not request_path.is_file():
            continue
        request = read_json(request_path.read_text(encoding="utf-8"))
        response = read_json(response_path.read_text(encoding="utf-8")) if response_path.is_file() else {}
        malformed = not isinstance(response, dict)
        if malformed:
            # The original envelope is retained and hashed in input_files.
            response = {}
        status = ("incomplete" if not response_path.is_file() else
                  "failed" if malformed or response.get("transport_error") or response.get("error") else "completed")
        records.append({"run_id": run_id, "agent_id": agent_id, "event_id": "attempt-" + folder.name,
                        "model": response.get("model") or request.get("model"), "status": status,
                        "usage_scope": "exclusive_delta", "response": response})
        for path in (request_path, response_path):
            if path.is_file():
                sources.append({"path": str(path.relative_to(root)),
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if not records:
        raise ValueError("No recorded model attempts in harness run")
    return records, sources


def build_report(records, mode, prices, budget_usd=None):
    receipts = [make_receipt(event, mode, prices) for event in records]
    report = {"schema_version": 1, "calculator": VERSION, "price_snapshot": prices,
              "summary": summarize(receipts, budget_usd), "receipts": receipts}
    for field in ("agent_id", "model"):
        report["by_" + field] = {key: summarize([r for r in receipts if r[field] == key])
                                  for key in sorted({r[field] for r in receipts})}
    return report



# Absence of a rate card is explicit. Provider-reported costs still accumulate.
NO_PRICES = {"schema_version": 1, "currency": "USD", "rate_card_id": "not-configured",
             "source": "no token rates configured", "as_of": "not-configured", "models": {}}


def native_report(root):
    """Recompute a native run from durable attempts; safe to inspect during a call.

    The input snapshot marks a native run, so zero recorded attempts means no
    recorded dispatch yet. External empty exports remain invalid/unknown.
    No process-liveness or provider-invoice completeness claim is made.
    """
    prices = read_json((root / "input/usage-prices.json").read_text(encoding="utf-8"))
    validate_prices(prices)
    config = read_json((root / "input/config.json").read_text(encoding="utf-8"))
    manifest_path = root / "manifest.json"
    manifest = read_json(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if any((root / "steps").glob("*/request.json")):
        records, sources = harness_records(root, run_id=manifest.get("run_directory", str(root)), agent_id="harness")
        report = build_report(records, "api", prices)
    else:
        sources = []
        report = {"schema_version": 1, "calculator": VERSION, "price_snapshot": prices,
                  "summary": summarize([], allow_empty=True), "receipts": [],
                  "by_agent_id": {}, "by_model": {}}
        report["summary"]["mode"] = "api"
    report.update(backend=config["model"]["backend"], input_files=sources, input_sha256=digest(sources),
                  scope="recorded_native_attempts; fixture calls are simulated")
    return report

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["api", "subagent"], required=True)
    ap.add_argument("--format", choices=["records", "codex-jsonl", "harness-run"], default="records")
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--prices", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--budget-usd")
    ap.add_argument("--run-id")
    ap.add_argument("--agent-id")
    ap.add_argument("--model")
    args = ap.parse_args(argv)
    try:
        prices = read_json(args.prices.read_text(encoding="utf-8"))
        validate_prices(prices)
        sources = None
        partial = False
        data = b"" if args.format == "harness-run" else args.input.read_bytes()
        if args.format == "harness-run":
            if args.mode != "api":
                raise ValueError("harness-run requires api mode")
            text_id(args.run_id, "run_id")
            text_id(args.agent_id, "agent_id")
            records, sources = harness_records(args.input, run_id=args.run_id, agent_id=args.agent_id)
        elif args.format == "codex-jsonl":
            if args.mode != "subagent":
                raise ValueError("codex-jsonl requires subagent mode")
            for key in ("run_id", "agent_id", "model"):
                text_id(getattr(args, key), key)
            events, partial = parse_codex_jsonl(data)
            records = codex_turn_records(events, run_id=args.run_id, agent_id=args.agent_id,
                                         model=args.model, partial_tail=partial)
        else:
            records = read_json(data.decode())
            if not isinstance(records, list) or not records:
                raise ValueError("Expected a nonempty list of attempt records, including missing/failed calls")
        report = build_report(records, args.mode, prices, args.budget_usd)
        report["input_sha256"] = digest(sources) if sources is not None else hashlib.sha256(data).hexdigest()
        if args.format == "codex-jsonl":
            report["partial_trailing_record"] = partial
        if sources is not None:
            report["input_files"] = sources
        output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output)
        else:
            print(output, end="")
        return 0
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
