"""One small opt-in OpenRouter call and offline replay of its cost receipt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from urllib import request
import uuid

import accounting

MODEL = "openai/gpt-6.1-sol"
PROVIDER = "openai"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
METADATA_URL = "https://openrouter.ai/api/v1/models/" + MODEL + "/endpoints"
MAX_OUTPUT = 256
MAX_CHECK_USD = Decimal("0.05")
CODE_FILES = ("accounting.py", "live_check.py")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return {str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob("*"))
            if p.is_file() and p != root / "artifacts.json" and "__pycache__" not in p.parts}


def load_key(dotenv):
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    if dotenv is None:
        raise ValueError("Set OPENROUTER_API_KEY or pass an explicit --dotenv path")
    values = []
    for line in dotenv.read_text().splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() in ("OPENROUTER", "OPENROUTER_API_KEY"):
            value = value.strip()
            if value[:1] in ("'", '"'):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError("Malformed credential entry")
                value = value[1:-1]
            if not value or any(char.isspace() for char in value):
                raise ValueError("Malformed credential entry")
            values.append(value)
    if not values or len(set(values)) != 1:
        raise ValueError("Missing or conflicting OpenRouter credentials")
    return values[0]


def fetch(url, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None if body is None else json.dumps(body).encode()
    req = request.Request(url, data=data, headers=headers)
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    with request.build_opener(NoRedirect).open(req, timeout=60) as response:
        return response.read()


def price_snapshot(metadata, request_body):
    endpoints = [row for row in metadata["data"]["endpoints"] if row.get("tag") == PROVIDER]
    if len(endpoints) != 1:
        raise ValueError("Expected one explicit standard OpenAI endpoint")
    endpoint = endpoints[0]
    if endpoint.get("provider_name") != "OpenAI":
        raise ValueError("Unexpected provider identity")
    pricing = endpoint["pricing"]
    allowed = {"prompt", "completion", "input_cache_read", "input_cache_write", "web_search", "discount", "overrides"}
    if set(pricing) - allowed or pricing.get("discount", 0) != 0:
        raise ValueError("Unsupported pricing fields or discount")
    tiers = [pricing, *pricing.get("overrides", [])]
    for tier in tiers[1:]:
        if set(tier) - {"min_prompt_tokens", "prompt", "completion", "input_cache_read", "input_cache_write"}:
            raise ValueError("Unsupported conditional pricing")
    # A conservative local guard for this fixed tiny text request, not a general billing guarantee.
    input_bound = len(json.dumps(request_body["messages"]).encode()) + 4096
    if any(type(tier.get("min_prompt_tokens")) is not int or tier["min_prompt_tokens"] <= input_bound for tier in tiers[1:]):
        raise ValueError("The check may enter an unsupported pricing tier")
    max_in = max(accounting.money(tier.get(key, pricing.get(key, 0)))
                 for tier in tiers for key in ("prompt", "input_cache_read", "input_cache_write"))
    max_out = max(accounting.money(tier.get("completion", pricing["completion"])) for tier in tiers)
    bound = input_bound * max_in + MAX_OUTPUT * max_out
    if bound > MAX_CHECK_USD:
        raise ValueError("Public price guard exceeds the $0.05 small-check limit")
    rates = {target: format(accounting.money(pricing[source]) * 1_000_000, "f")
             for source, target in (("prompt", "input_per_million"), ("completion", "output_per_million"),
                                    ("input_cache_read", "cached_input_per_million"), ("input_cache_write", "cache_write_per_million"))
             if source in pricing}
    snapshot = {"schema_version": 1, "currency": "USD", "rate_card_id": "openrouter-standard-openai-" + uuid.uuid4().hex,
                "source": METADATA_URL, "as_of": datetime.now(timezone.utc).isoformat(), "models": {MODEL: rates}}
    accounting.validate_prices(snapshot)
    return snapshot, {"max_output_tokens": MAX_OUTPUT, "input_tokens_guard": input_bound,
                      "estimated_guard_usd": format(bound, "f"), "ceiling_usd": str(MAX_CHECK_USD),
                      "automatic_retry": False, "scope": "one fixed text request; no tools; not an account-wide spending cap"}


def recorded_report(root):
    attempt = accounting.read_json((root / "attempt.json").read_text())
    response_path = root / "response.json"
    response = accounting.read_json(response_path.read_text()) if response_path.is_file() else {}
    result_path = root / "call-result.json"
    result = accounting.read_json(result_path.read_text()) if result_path.is_file() else {"status": "incomplete"}
    event = {key: attempt[key] for key in ("run_id", "agent_id", "event_id", "model", "usage_scope")}
    event.update(status=result["status"], response=response)
    return accounting.build_report([event], "api", accounting.read_json((root / "prices.json").read_text()))


def run(root, dotenv=None, *, network=fetch):
    key = load_key(dotenv)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    calls = 0
    try:
        for name in CODE_FILES:
            dest = root / "code" / name
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(Path(__file__).parent / name, dest)
        body = {"model": MODEL, "messages": [{"role": "user", "content": 'Return only this JSON object: {"ok":true}'}],
                "max_tokens": MAX_OUTPUT, "stream": False, "reasoning": {"effort": "low"},
                "response_format": {"type": "json_object"},
                "provider": {"only": [PROVIDER], "allow_fallbacks": False, "require_parameters": True}}
        metadata_bytes = network(METADATA_URL)
        metadata = accounting.read_json(metadata_bytes.decode())
        write(root / "metadata.json", metadata)
        prices, guard = price_snapshot(metadata, body)
        write(root / "prices.json", prices)
        write(root / "guard.json", guard)
        write(root / "request.json", body)
        attempt = {"run_id": uuid.uuid4().hex, "agent_id": "api-check", "event_id": "attempt-1", "model": MODEL,
                   "usage_scope": "exclusive_delta", "status": "dispatched",
                   "request_sha256": file_hash(root / "request.json"), "price_sha256": file_hash(root / "prices.json")}
        write(root / "attempt.json", attempt)  # durable before the potentially billable call
        try:
            calls = 1
            raw = network(ENDPOINT, body, key)
            with (root / "response.raw").open("xb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            response = accounting.read_json(raw.decode())
            if not isinstance(response, dict):
                raise ValueError("Expected API response object")
            write(root / "response.json", response)
            write(root / "call-result.json", {"status": "failed" if response.get("error") else "completed"})
        except (Exception, KeyboardInterrupt, SystemExit) as exc:
            if not (root / "call-result.json").exists():
                write(root / "call-result.json", {"status": "incomplete", "error_type": type(exc).__name__,
                                                  "http_status": getattr(exc, "code", None), "automatic_retry": False})
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        report = recorded_report(root)
        write(root / "report.json", report)
        return report
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        write(root / "failure.json", {"error_type": type(exc).__name__, "generation_requests": calls})
        raise
    finally:
        write(root / "artifacts.json", inventory(root))


def replay(root):
    root = root.resolve()
    expected = accounting.read_json((root / "artifacts.json").read_text())
    if inventory(root) != expected:
        raise ValueError("Artifact integrity mismatch")
    for name in expected:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Artifact escapes run directory")
    for name in CODE_FILES:
        if file_hash(Path(__file__).parent / name) != expected["code/" + name]:
            raise ValueError("Use the archived code to replay this run")
    attempt = accounting.read_json((root / "attempt.json").read_text())
    if (attempt["request_sha256"] != file_hash(root / "request.json") or
            attempt["price_sha256"] != file_hash(root / "prices.json")):
        raise ValueError("Dispatched request or prices changed")
    report = recorded_report(root)
    if report != accounting.read_json((root / "report.json").read_text()):
        raise ValueError("Cost report differs from recorded evidence")
    return {"replay_passed": True, "model_called": False, "summary": report["summary"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("run")
    start.add_argument("--output", type=Path, required=True)
    start.add_argument("--dotenv", type=Path)
    again = sub.add_parser("replay")
    again.add_argument("run_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.output, args.dotenv) if args.command == "run" else replay(args.run_directory)
        print(json.dumps(result.get("summary", result), indent=2))
        return 0 if args.command == "replay" or result["summary"]["reported_cost_usd"] is not None else 1
    except Exception as exc:
        # Do not print request/HTTP exception text, which may contain credentials.
        print(type(exc).__name__ + ": inspect local artifacts; no automatic retry", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
