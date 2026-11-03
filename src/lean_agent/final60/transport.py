"""OpenRouter transport for final60 (standard library only).

* ``payload`` builds a pinned Chat Completions body from ``lean_agent.models.payload``.
* ``request_bound`` is a true upper bound on what one request can cost.
* ``query`` sends exactly one POST (no redirects, no retries) and never raises for
  HTTP or network failures; failures come back tagged ``billing_hint`` unbilled/unknown.
* ``sub_attempt_cost``/``normalize`` turn a saved provider response into a
  deterministic receipt, and ``audit_step`` recomputes a whole driver step from its
  saved evidence.

Credentials are never logged, printed or stored: request headers are never saved,
error bodies are reduced to a few fields, and every value saved from the network
passes ``scrub``.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import http.client
import json
from pathlib import Path
import re
import time
from urllib import error, parse, request

from lean_agent import models as _models
from lean_agent.artifacts import canonical, read, sha

from . import catalog
from .contracts import SCHEMA, Bound, ModelSpec, OPENROUTER_ENDPOINT

ENDPOINT = OPENROUTER_ENDPOINT
API_BASE = "https://openrouter.ai/api/v1"
HOST = "openrouter.ai"
UNBILLED_HTTP = frozenset({400, 401, 402, 403, 404, 429})   # amendment A10
DISABLE_HTTP = frozenset({401, 402})                        # key or credits: global api-disabled
BODY_KEYS = frozenset({"model", "messages", "max_tokens", "stream", "response_format", "provider",
                       "plugins", "usage", "reasoning", "seed"})
REQUIRED_BODY_KEYS = frozenset({"model", "messages", "max_tokens", "stream", "response_format", "provider",
                                "plugins", "usage"})
PROVIDER_KEYS = frozenset({"only", "order", "allow_fallbacks", "require_parameters", "max_price"})
LOST_ID_PREFIX = "lost-"
BOUND_BASIS = ("public-list-price upper bound: (UTF-8 body bytes + 4096) at max(prompt, cache-write) price "
               "plus max_tokens at the completion price")
DEBIT_RULE = "max(openrouter usage.cost, cache-aware list price of the returned token usage)"
COST_BASIS = "max(openrouter-usage-cost, cache-aware-public-list-price)"
MILLION = Decimal(1_000_000)
_KEY_PATTERN = re.compile(r"sk-or-[A-Za-z0-9_\-]{4,}")
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{8,}")
_GENERATION_PATTERN = re.compile(rb'"id"\s*:\s*"(gen-[A-Za-z0-9_\-]{4,200})"')
_GENERATION_ID = re.compile(r"gen-[A-Za-z0-9_\-]{4,200}")
REDACTED = "<redacted-credential>"


# ---------------------------------------------------------------- helpers

def usd(value) -> str:
    """Exact decimal text without exponent notation (no rounding)."""
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("Expected a finite USD amount")
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "0") else text


def scrub(value, key: str | None = None, *, strict: bool = True):
    """Copy of ``value`` with the key and anything key-shaped replaced.

    ``strict`` also redacts bearer-token text; it is off for successful completions
    so model content is only touched if it literally contains a key.
    """
    if isinstance(value, dict):
        return {name: scrub(item, key, strict=strict) for name, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, key, strict=strict) for item in value]
    if isinstance(value, str):
        if key:
            value = value.replace(key, REDACTED)
        if "sk-or-" in value:
            value = _KEY_PATTERN.sub(REDACTED, value)
        if strict and "earer" in value:
            value = _BEARER_PATTERN.sub(REDACTED, value)
        return value
    return value


def require_key(key) -> str:
    if not isinstance(key, str) or not key.startswith("sk-or-") or len(key) < 20:
        raise ValueError("Missing OpenRouter-issued API key (expected an sk-or- key; the value is never shown)")
    return key


def load_key(path) -> str:
    """Read OPENROUTER_API_KEY / OPENROUTER from an explicit dotenv file; never logs or echoes it."""
    return require_key(_models.load_key(Path(path)))


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None   # never forward the Authorization header to another origin


def _open(url, *, key=None, data=None, timeout=30):
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if key is not None:
        headers["Authorization"] = "Bearer " + key
    call = request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with request.build_opener(_NoRedirect).open(call, timeout=timeout) as response:
        return response.status, response.read()


def _json(text):
    return json.loads(text, parse_constant=_reject_constant)


def _generation_from_bytes(text) -> str | None:
    match = _GENERATION_PATTERN.search(text or b"")
    return match.group(1).decode() if match else None


def _error_info(text) -> dict | None:
    try:
        doc = _json(text)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    failure = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(failure, dict):
        return None
    info = {}
    if isinstance(failure.get("code"), (int, str)):
        info["code"] = failure["code"]
    if isinstance(failure.get("message"), str):
        info["message"] = failure["message"][:500]
    metadata = failure.get("metadata")
    if isinstance(metadata, dict):
        if isinstance(metadata.get("provider_name"), str):
            info["provider_name"] = metadata["provider_name"][:100]
        info["metadata_keys"] = sorted(str(name) for name in metadata)[:20]
    return info


def _retry_after(headers) -> int | None:
    try:
        value = headers.get("Retry-After") if headers is not None else None
        return max(0, min(3600, int(float(value)))) if value is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- payload and bound

def _messages(messages):
    if (not isinstance(messages, list) or len(messages) != 2 or
            any(not isinstance(message, dict) or set(message) != {"role", "content"} or
                not isinstance(message["content"], str) for message in messages) or
            messages[0]["role"] != "system" or messages[1]["role"] != "user"):
        raise ValueError("Expected exactly two plain-text system/user messages")
    return [{"role": message["role"], "content": message["content"]} for message in messages]


def provider_preferences(spec: ModelSpec) -> dict:
    return {"only": [spec.provider], "order": [spec.provider], "allow_fallbacks": False,
            "require_parameters": True, "max_price": catalog.max_price(spec)}


def payload(messages: list[dict], spec: ModelSpec) -> dict:
    """Pinned body: provider only/order, no fallbacks, required parameters, price ceiling, usage."""
    model = {"backend": "openrouter", "id": spec.model_id, "provider": spec.provider,
             "max_tokens": spec.max_tokens, "max_price": catalog.max_price(spec)}
    if spec.reasoning_effort is not None:
        model["reasoning_effort"] = spec.reasoning_effort
    if spec.seed is not None:
        model["seed"] = spec.seed
    body = deepcopy(_models.payload(_messages(messages), model))
    body["provider"] = provider_preferences(spec)
    body["usage"] = {"include": True}
    validate_body(body, spec)
    return body


def validate_body(body: dict, spec: ModelSpec) -> None:
    if not isinstance(body, dict) or set(body) - BODY_KEYS or REQUIRED_BODY_KEYS - set(body):
        raise ValueError("Request carries fields outside the pinned OpenRouter contract")
    if body["model"] != spec.model_id:
        raise ValueError("Request model differs from its catalog entry")
    _messages(body["messages"])
    if (body["stream"] is not False or body["plugins"] != [] or body["usage"] != {"include": True}
            or body["response_format"] != {"type": "json_object"}):
        raise ValueError("Request must be non-streaming JSON mode with usage and no plugins")
    if body["provider"] != provider_preferences(spec):
        raise ValueError("Request is not pinned to its catalog provider and price ceiling")
    tokens = body["max_tokens"]
    if type(tokens) is not int or tokens <= 0 or tokens > catalog.MAX_COMPLETION_TOKENS or tokens != spec.max_tokens:
        raise ValueError("Request max_tokens differs from its model spec")
    expected_reasoning = None if spec.reasoning_effort is None else {"effort": spec.reasoning_effort}
    if body.get("reasoning") != expected_reasoning or ("reasoning" in body) != (expected_reasoning is not None):
        raise ValueError("Request reasoning differs from its model spec")
    if body.get("seed") != spec.seed or ("seed" in body) != (spec.seed is not None):
        raise ValueError("Request seed differs from its model spec")


def wire_bytes(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def request_bound(body: dict, spec: ModelSpec) -> Bound:
    """Worst-case cost of one request; ValueError if unpinned or too large for the bound."""
    validate_body(body, spec)
    count = len(wire_bytes(body)) + catalog.FRAMING_TOKENS
    if count >= catalog.MAX_REQUEST_BYTES:
        raise ValueError("Request must remain conservatively below the 272K pricing tier")
    input_price = max(spec.prompt_usd_per_mtok, spec.cache_write_usd_per_mtok)
    reserved = (Decimal(count) * input_price + Decimal(body["max_tokens"]) * spec.completion_usd_per_mtok) / MILLION
    return Bound(input_token_bound=count, output_token_bound=body["max_tokens"], reserved_usd=reserved,
                 basis=BOUND_BASIS)


def bound_json(bound: Bound, body: dict, spec: ModelSpec) -> dict:
    """cost-bound.json; the field names follow openai_transport.request_cost."""
    return {"request_sha256": sha(canonical(body)), "input_token_bound": bound.input_token_bound,
            "output_token_bound": bound.output_token_bound, "reserved_usd": usd(bound.reserved_usd),
            "basis": bound.basis, "catalog_key": spec.key, "model": spec.model_id, "provider": spec.provider,
            "prices": catalog.prices(spec)}


def endpoint_evidence(spec: ModelSpec) -> dict:
    """endpoint.json: where the request goes and what it is pinned to (static, no network)."""
    return {"schema": SCHEMA, "api_endpoint": ENDPOINT, "host": HOST, "provider": "OpenRouter",
            "catalog_key": spec.key, "model": spec.model_id, "provider_preferences": provider_preferences(spec),
            "prices": catalog.prices(spec), "prices_fetched_at": catalog.PRICES_FETCHED_AT,
            "source": "frozen final60 catalog"}


# ---------------------------------------------------------------- HTTP

def query(body: dict, spec: ModelSpec, *, key: str, timeout_s: int | None = None) -> dict:
    """ONE POST to the OpenRouter endpoint; no redirect, no retry, never raises for HTTP/network."""
    require_key(key)
    data = wire_bytes(body)
    try:
        status, text = _open(ENDPOINT, key=key, data=data, timeout=timeout_s or spec.timeout_s)
    except error.HTTPError as exc:
        code = exc.code if type(exc.code) is int else None
        result = {"transport_error": "HTTPError", "http_status": code,
                  "billing_hint": "unbilled" if code in UNBILLED_HTTP else "unknown"}
        try:
            text = exc.read()
        except Exception:   # noqa: BLE001 - an unreadable error body is just absent
            text = b""
        info = _error_info(text)
        if info:
            result["error"] = info
        generation = _generation_from_bytes(text)
        if generation:
            result["generation_id"] = generation
        retry_after = _retry_after(getattr(exc, "headers", None))
        if retry_after is not None:
            result["retry_after_s"] = retry_after
        return scrub(result, key)
    except (error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
        # Sent (or maybe sent) without a usable response: billing unknown, never retried here.
        return {"transport_error": type(exc).__name__, "http_status": None, "billing_hint": "unknown"}
    try:
        value = _json(text)
    except (ValueError, UnicodeDecodeError):
        result = {"transport_error": "InvalidJSON", "http_status": status, "billing_hint": "unknown",
                  "body_sha256": sha(text), "body_bytes": len(text)}
        generation = _generation_from_bytes(text)
        if generation:
            result["generation_id"] = generation
        return result
    if not isinstance(value, dict):
        return {"transport_error": "InvalidJSONType", "http_status": status, "billing_hint": "unknown"}
    return scrub(value, key, strict=classify(value) != "ok")


def classify(raw) -> str:
    """'ok' (a billed completion), 'unbilled' (4xx refused before billing) or 'lost' (billing unknown)."""
    if not isinstance(raw, dict):
        return "lost"
    if "transport_error" in raw:
        status = raw.get("http_status")
        return "unbilled" if type(status) is int and status in UNBILLED_HTTP else "lost"
    if isinstance(raw.get("error"), dict) and not raw.get("choices"):
        code = raw["error"].get("code")
        if type(code) is int and code in UNBILLED_HTTP and not raw.get("usage") and not raw.get("id"):
            return "unbilled"
        return "lost"
    choices = raw.get("choices")
    return "ok" if isinstance(choices, list) and choices else "lost"


def http_status_of(raw) -> int | None:
    if not isinstance(raw, dict):
        return None
    if "transport_error" in raw:
        status = raw.get("http_status")
        return status if type(status) is int else None
    if isinstance(raw.get("error"), dict) and not raw.get("choices"):
        code = raw["error"].get("code")
        return code if type(code) is int else None
    return 200


def generation_id_of(raw) -> str | None:
    if not isinstance(raw, dict):
        return None
    for value in (raw.get("id"), raw.get("generation_id")):
        if isinstance(value, str) and _GENERATION_ID.fullmatch(value):
            return value
    value = raw.get("id")
    return value if isinstance(value, str) and value and "transport_error" not in raw else None


# ---------------------------------------------------------------- receipts

def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("Missing/invalid token counter: " + label)
    return value


def _details(usage, key):
    value = usage.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Invalid token details: " + key)
    return value


def _optional(details, key, label):
    value = details.get(key)
    return 0 if value is None else _count(value, label)


def _reported_cost(raw) -> Decimal | None:
    usage = raw.get("usage") if isinstance(raw, dict) else None
    value = usage.get("cost") if isinstance(usage, dict) else None
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def compute_cost(raw: dict, spec: ModelSpec) -> dict:
    """Deterministic debit for a billed completion; ValueError if its usage is unusable."""
    if classify(raw) != "ok":
        raise ValueError("Missing successful provider response")
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("Provider usage missing")
    prompt = _count(usage.get("prompt_tokens"), "prompt_tokens")
    completion = _count(usage.get("completion_tokens"), "completion_tokens")
    if usage.get("total_tokens") is not None and _count(usage["total_tokens"], "total_tokens") != prompt + completion:
        raise ValueError("Provider usage totals disagree")
    prompt_details = _details(usage, "prompt_tokens_details")
    completion_details = _details(usage, "completion_tokens_details")
    cached = _optional(prompt_details, "cached_tokens", "cached_tokens")
    written = _optional(prompt_details, "cache_write_tokens", "cache_write_tokens")
    ordinary = prompt - cached - written
    if ordinary < 0:
        raise ValueError("Cache reads/writes exceed total input tokens")
    reasoning = _optional(completion_details, "reasoning_tokens", "reasoning_tokens")
    if reasoning > completion:
        raise ValueError("Reasoning tokens exceed total completion tokens")
    for label, details in (("prompt", prompt_details), ("completion", completion_details)):
        for modality in ("audio_tokens", "image_tokens", "video_tokens"):
            if _optional(details, modality, label + "." + modality):
                raise ValueError("Unexpected non-text token pricing")
    if prompt >= catalog.LONG_CONTEXT_TOKENS:
        raise ValueError("Unexpected long-context price tier")
    list_price = (Decimal(ordinary) * spec.prompt_usd_per_mtok + Decimal(cached) * spec.cache_read_usd_per_mtok
                  + Decimal(written) * spec.cache_write_usd_per_mtok
                  + Decimal(completion) * spec.completion_usd_per_mtok) / MILLION
    reported = _reported_cost(raw)
    if usage.get("cost") is not None and reported is None:
        raise ValueError("Invalid provider usage.cost")
    debit = list_price if reported is None or reported <= list_price else reported
    basis = "openrouter-usage-cost" if reported is not None and reported > list_price else "cache-aware-list-price"
    return {"cost_usd": usd(debit), "basis": basis, "debit_rule": DEBIT_RULE,
            "usage_cost": None if reported is None else usd(reported), "list_price_cost": usd(list_price),
            "prompt_tokens": prompt, "ordinary_prompt_tokens": ordinary, "cached_tokens": cached,
            "cache_write_tokens": written, "completion_tokens": completion, "reasoning_tokens": reasoning,
            "catalog_key": spec.key, "requested_model": spec.model_id, "pinned_provider": spec.provider,
            "returned_model": raw.get("model"), "returned_provider": raw.get("provider"),
            "generation_id": raw.get("id"), "prices": catalog.prices(spec), "invoice_verified": False,
            "provider_response_sha256": sha(canonical(raw))}


def _per_mtok(value) -> Decimal | None:
    try:
        amount = Decimal(str(value)) * MILLION
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def cost_from_generation(doc, spec: ModelSpec | None = None) -> Decimal | None:
    """Exact settlement from GET /api/v1/generation (never below the list price of its tokens)."""
    data = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(data, dict):
        return None
    total = data.get("total_cost")
    if total is None or isinstance(total, bool):
        return None
    try:
        amount = Decimal(str(total))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    if spec is not None:
        prompt = data.get("native_tokens_prompt", data.get("tokens_prompt"))
        completion = data.get("native_tokens_completion", data.get("tokens_completion"))
        cached = data.get("native_tokens_cached") or 0
        if all(type(value) is int and value >= 0 for value in (prompt, completion, cached)) and cached <= prompt:
            listed = (Decimal(prompt - cached) * spec.prompt_usd_per_mtok + Decimal(cached) * spec.cache_read_usd_per_mtok
                      + Decimal(completion) * spec.completion_usd_per_mtok) / MILLION
            amount = max(amount, listed)
    return amount


def sub_attempt_cost(raw, spec: ModelSpec, bound: Bound, generation: dict | None = None) -> dict:
    """Receipt for one HTTP sub-attempt, recomputable from saved evidence alone."""
    kind = classify(raw)
    status = http_status_of(raw)
    record = {"outcome": kind, "http_status": status, "generation_id": generation_id_of(raw),
              "returned_model": raw.get("model") if isinstance(raw, dict) and kind == "ok" else None,
              "returned_provider": raw.get("provider") if isinstance(raw, dict) and kind == "ok" else None,
              "bound_usd": usd(bound.reserved_usd), "provider_response_sha256": sha(canonical(raw))}
    if kind == "unbilled":
        return {**record, "status": "unbilled", "cost_usd": "0", "basis": f"unbilled-http-{status}",
                "settlement_basis": "unbilled", "bound_violated": False}
    if kind == "ok":
        try:
            detail = compute_cost(raw, spec)
        except (ValueError, TypeError, KeyError) as exc:
            reported = _reported_cost(raw)
            cost = bound.reserved_usd if reported is None else max(bound.reserved_usd, reported)
            return {**record, "status": "settled", "cost_usd": usd(cost),
                    "basis": "conservative-bound-unusable-usage", "settlement_basis": "lost-bound",
                    "usage_error": str(exc)[:300],
                    "bound_violated": reported is not None and reported > bound.reserved_usd}
        cost = Decimal(detail["cost_usd"])
        violated = (cost > bound.reserved_usd or detail["completion_tokens"] > bound.output_token_bound
                    or detail["prompt_tokens"] > bound.input_token_bound)
        return {**record, "status": "settled", "cost_usd": detail["cost_usd"], "basis": detail["basis"],
                "settlement_basis": "usage" if detail["basis"] == "openrouter-usage-cost" else "list-price",
                "detail": detail, "bound_violated": violated}
    exact = cost_from_generation(generation, spec) if generation is not None else None
    if exact is not None:
        return {**record, "status": "settled", "cost_usd": usd(exact), "basis": "generation-api-total-cost",
                "settlement_basis": "generation-api", "bound_violated": exact > bound.reserved_usd}
    return {**record, "status": "lost_conservative", "cost_usd": usd(bound.reserved_usd),
            "basis": "lost-response-conservative-bound", "settlement_basis": "lost-bound", "bound_violated": False}


def brief(record: dict) -> dict:
    """The ledger.json form of a sub-attempt (amendment A4)."""
    return {"id": record["id"], "http_status": record["http_status"], "status": record["status"],
            "cost_usd": record["cost_usd"], "basis": record["settlement_basis"]}


def normalize(raw, spec: ModelSpec, bound: Bound, *, sub_attempts=(), attempt_id: str | None = None,
              final_id: str | None = None, generation: dict | None = None) -> dict:
    """Step response: ALWAYS sets usage.cost (the step total) and _cost_receipt.

    ``sub_attempts`` are the earlier receipts of the same step (with ``id``). A lost
    final outcome yields a response without choices and id ``lost-<attempt>``; its
    content is never synthesized.
    """
    final = {"id": final_id or f"{attempt_id or 'attempt'}#r{len(sub_attempts)}",
             **sub_attempt_cost(raw, spec, bound, generation)}
    records = [*sub_attempts, final]
    total = sum((Decimal(item["cost_usd"]) for item in records), Decimal(0))
    if final["outcome"] == "ok":
        normalized = deepcopy(raw)
        if not isinstance(normalized.get("usage"), dict):
            normalized["usage"] = {}
    else:
        normalized = {"id": LOST_ID_PREFIX + (attempt_id or "attempt"), "object": "final60.lost-response",
                      "model": spec.model_id, "provider": None, "choices": [], "usage": {},
                      "transport_error": (raw.get("transport_error") if isinstance(raw, dict) else None) or "lost",
                      "http_status": final["http_status"]}
    basis = next((item["settlement_basis"] for item in reversed(records) if item["settlement_basis"] != "unbilled"),
                 "unbilled")
    normalized["usage"]["cost"] = usd(total)
    normalized["_cost_receipt"] = {
        "schema": SCHEMA, "attempt_id": attempt_id, "api_endpoint": ENDPOINT, "provider": "OpenRouter",
        "catalog_key": spec.key, "model": spec.model_id, "provider_pin": spec.provider,
        "returned_model": final["returned_model"], "returned_provider": final["returned_provider"],
        "cost_usd": usd(total), "step_cost_usd": usd(total), "settlement_basis": basis, "basis": final["basis"],
        "cost_basis": COST_BASIS, "debit_rule": DEBIT_RULE, "invoice_verified": False,
        "bound": {"reserved_usd": usd(bound.reserved_usd), "input_token_bound": bound.input_token_bound,
                  "output_token_bound": bound.output_token_bound},
        "bound_violated": any(item["bound_violated"] for item in records),
        "sub_attempts": [brief(item) for item in records], "final_sub_attempt": final,
        "provider_response_sha256": final["provider_response_sha256"]}
    return normalized


# ---------------------------------------------------------------- audit

def _sub_index(path: Path) -> int | None:
    name = path.name
    return int(name[1:]) if path.is_dir() and name.startswith("r") and name[1:].isdigit() else None


def step_records(step_dir: Path, spec: ModelSpec, bound: Bound, attempt_id: str):
    """Recompute every sent sub-attempt of a step: [(record, raw, generation)] in index order."""
    entries = []
    folders = sorted((path for path in (Path(step_dir) / "http").glob("r*") if _sub_index(path) is not None),
                     key=_sub_index)
    for folder in folders:
        if (folder / "void.json").exists():
            continue
        provider = folder / "provider-response.json"
        if not provider.exists():
            raise ValueError(f"{folder.name}: sent sub-attempt has no saved provider response")
        raw = read(provider)
        generation = read(folder / "generation.json") if (folder / "generation.json").exists() else None
        record = {"id": f"{attempt_id}#r{_sub_index(folder)}", **sub_attempt_cost(raw, spec, bound, generation)}
        entries.append((record, raw, generation, folder))
    return entries


def _credential_leaks(step_dir: Path) -> list[str]:
    found = []
    for path in sorted(Path(step_dir).rglob("*")):
        if path.is_file() and path.suffix in (".json", ".txt", ".log", ".jsonl", ""):
            try:
                if b"sk-or-" in path.read_bytes():
                    found.append(str(path.relative_to(step_dir)))
            except OSError:
                continue
    return found


def audit_step(step_dir: Path, ledger_item: dict) -> list[str]:
    """Recompute one OpenRouter driver step from its evidence; [] means it audits clean."""
    step_dir = Path(step_dir)
    errors = []
    try:
        attempt = f"F{int(ledger_item['row']):03}-{int(ledger_item['step']):04}"
        body = read(step_dir / "request.json")
        spec = catalog.spec_for_body(body)
        bound = request_bound(body, spec)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"request evidence invalid ({type(exc).__name__}: {str(exc)[:200]})"]
    if ledger_item.get("status") != "settled":
        errors.append("ledger attempt is not settled")
    if sha(canonical(body)) != ledger_item.get("request_sha256"):
        errors.append("request hash differs from ledger")
    try:
        if Decimal(str(ledger_item.get("maximum_request_cost_usd"))) != bound.reserved_usd:
            errors.append("reservation differs from the recomputed request bound")
    except InvalidOperation:
        errors.append("reservation amount is not a decimal")
    try:
        if read(step_dir / "cost-bound.json") != bound_json(bound, body, spec):
            errors.append("cost-bound.json differs from the recomputed bound")
        endpoint = read(step_dir / "endpoint.json")
        if endpoint != endpoint_evidence(spec) or parse.urlparse(endpoint.get("api_endpoint", "")).hostname != HOST:
            errors.append("endpoint evidence is not the pinned openrouter.ai endpoint")
        entries = step_records(step_dir, spec, bound, attempt)
        for record, _, _, folder in entries:
            if read(folder / "receipt.json") != record:
                errors.append(f"{folder.name}: saved receipt differs from its provider evidence")
        if not entries:
            return errors + ["no sent HTTP sub-attempt"]
        records = [record for record, _, _, _ in entries]
        final_record, final_raw, final_generation, _ = entries[-1]
        if any(record["outcome"] == "ok" for record in records[:-1]):
            errors.append("a successful sub-attempt was followed by another HTTP call")
        total = sum((Decimal(record["cost_usd"]) for record in records), Decimal(0))
        if Decimal(str(ledger_item.get("cost_usd"))) != total:
            errors.append("ledger cost differs from the sum of HTTP sub-attempts")
        if ledger_item.get("sub_attempts") != [brief(record) for record in records]:
            errors.append("ledger sub_attempts differ from the HTTP evidence")
        expected = normalize(final_raw, spec, bound, sub_attempts=records[:-1], attempt_id=attempt,
                             final_id=final_record["id"], generation=final_generation)
        response = read(step_dir / "response.json")
        if response != expected:
            errors.append("normalized response differs from raw provider evidence")
        if read(step_dir / "cost-receipt.json") != response.get("_cost_receipt"):
            errors.append("cost receipt differs from the normalized response")
        if read(step_dir / "provider-response.json") != final_raw:
            errors.append("provider-response.json differs from the final HTTP sub-attempt")
        if ledger_item.get("response_id") != response.get("id"):
            errors.append("response identity differs from ledger")
        if final_record["outcome"] == "ok":
            if not response.get("id") or final_raw.get("id") != response.get("id"):
                errors.append("raw provider response identity mismatch")
        elif response.get("id") != LOST_ID_PREFIX + attempt:
            errors.append("lost step must carry its lost-<attempt> id")
        if bool(ledger_item.get("bound_violated", False)) != expected["_cost_receipt"]["bound_violated"]:
            errors.append("bound violation flag differs from the evidence")
        if ledger_item.get("settlement_basis") != expected["_cost_receipt"]["settlement_basis"]:
            errors.append("settlement basis differs from the evidence")
        if ledger_item.get("api_endpoint", ENDPOINT) != ENDPOINT:
            errors.append("ledger endpoint is not openrouter.ai")
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
        errors.append(f"malformed evidence ({type(exc).__name__}: {str(exc)[:200]})")
    for path in _credential_leaks(step_dir):
        errors.append("credential-like string in evidence: " + path)
    return errors


# ---------------------------------------------------------------- free account and catalogue checks

def generation_lookup(generation_id: str, *, key: str, timeout_s: int = 30) -> dict:
    """GET /api/v1/generation?id=... (no charge); returns the scrubbed document or a failure record."""
    require_key(key)
    if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(generation_id):
        raise ValueError("Invalid generation id")
    url = API_BASE + "/generation?" + parse.urlencode({"id": generation_id})
    try:
        status, text = _open(url, key=key, timeout=timeout_s)
    except error.HTTPError as exc:
        return {"transport_error": "HTTPError", "http_status": exc.code if type(exc.code) is int else None}
    except (error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
        return {"transport_error": type(exc).__name__, "http_status": None}
    try:
        doc = _json(text)
    except (ValueError, UnicodeDecodeError):
        return {"transport_error": "InvalidJSON", "http_status": status}
    return scrub(doc, key) if isinstance(doc, dict) else {"transport_error": "InvalidJSONType", "http_status": status}


def generation_cost(generation_id: str, *, key: str, spec: ModelSpec | None = None, attempts: int = 3,
                    backoff_s=(2, 5), sleep=time.sleep) -> Decimal | None:
    for number in range(attempts):
        cost = cost_from_generation(generation_lookup(generation_id, key=key), spec)
        if cost is not None:
            return cost
        if number + 1 < attempts:
            sleep(backoff_s[min(number, len(backoff_s) - 1)])
    return None


def key_status(*, key: str, timeout_s: int = 30) -> dict:
    """GET /api/v1/key and /api/v1/credits (no charge). Numbers only: the key label is never kept."""
    require_key(key)
    result = {"api_base": API_BASE}
    fields = {"key": ("limit", "usage", "limit_remaining", "is_free_tier", "usage_daily", "usage_weekly",
                      "usage_monthly", "byok_usage"),
              "credits": ("total_credits", "total_usage")}
    for name, path in (("key", "/key"), ("credits", "/credits")):
        try:
            status, text = _open(API_BASE + path, key=key, timeout=timeout_s)
            doc = _json(text)
        except error.HTTPError as exc:
            result[name] = {"ok": False, "http_status": exc.code if type(exc.code) is int else None}
            continue
        except (error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
            result[name] = {"ok": False, "transport_error": type(exc).__name__}
            continue
        data = doc.get("data") if isinstance(doc, dict) else None
        data = data if isinstance(data, dict) else {}
        entry = {"ok": True, "http_status": status}
        for field in fields[name]:
            value = data.get(field)
            if value is None or isinstance(value, (bool, int, float)):
                entry[field] = value
        result[name] = entry
    credits = result.get("credits", {})
    if all(isinstance(credits.get(field), (int, float)) and not isinstance(credits.get(field), bool)
           for field in ("total_credits", "total_usage")):
        credits["remaining"] = usd(Decimal(str(credits["total_credits"])) - Decimal(str(credits["total_usage"])))
    result["valid"] = result.get("key", {}).get("ok") is True
    return scrub(result, key)


def check_endpoints(doc: dict, spec: ModelSpec) -> dict:
    """Pure check of an /endpoints document against a spec (live tag, prices, parameters)."""
    data = doc.get("data", doc) if isinstance(doc, dict) else {}
    endpoints = data.get("endpoints") if isinstance(data, dict) else None
    needed = {"max_tokens", "response_format"}
    if spec.reasoning_effort is not None:
        needed.add("reasoning")
    if spec.seed is not None:
        needed.add("seed")
    ceiling = catalog.max_price(spec)
    rows = []
    for endpoint in endpoints if isinstance(endpoints, list) else []:
        tag = endpoint.get("tag") if isinstance(endpoint, dict) else None
        if not isinstance(tag, str) or (tag != spec.provider and not tag.startswith(spec.provider + "/")):
            continue
        pricing = endpoint.get("pricing") if isinstance(endpoint.get("pricing"), dict) else {}
        prompt, completion = _per_mtok(pricing.get("prompt")), _per_mtok(pricing.get("completion"))
        cache_read, cache_write = _per_mtok(pricing.get("input_cache_read")), _per_mtok(pricing.get("input_cache_write"))
        within = (prompt is not None and completion is not None and prompt <= Decimal(str(ceiling["prompt"]))
                  and completion <= Decimal(str(ceiling["completion"])))
        missing = sorted(needed - set(endpoint.get("supported_parameters") or []))
        rows.append({"tag": tag, "status": endpoint.get("status"), "provider_name": endpoint.get("provider_name"),
                     "prompt_usd_per_mtok": None if prompt is None else usd(prompt),
                     "completion_usd_per_mtok": None if completion is None else usd(completion),
                     "cache_read_usd_per_mtok": None if cache_read is None else usd(cache_read),
                     "cache_write_usd_per_mtok": None if cache_write is None else usd(cache_write),
                     "within_max_price": within, "missing_parameters": missing, "eligible": within and not missing,
                     "max_completion_tokens": endpoint.get("max_completion_tokens")})
    exact = next((row for row in rows if row["tag"] == spec.provider), None)
    problems, warnings = [], []
    if exact is None:
        problems.append("pinned provider tag is not listed")
    else:
        if exact["missing_parameters"]:
            problems.append("pinned tag lacks parameters: " + ", ".join(exact["missing_parameters"]))
        if not exact["within_max_price"]:
            problems.append("pinned tag price is above the catalog ceiling")
        for field, limit in (("cache_read_usd_per_mtok", spec.cache_read_usd_per_mtok),
                             ("cache_write_usd_per_mtok", spec.cache_write_usd_per_mtok)):
            if exact[field] is not None and Decimal(exact[field]) > limit:
                problems.append("pinned tag " + field + " is above the catalog price")
        if exact["status"] not in (0, None):
            warnings.append(f"pinned tag status {exact['status']}")
        if type(exact["max_completion_tokens"]) is int and exact["max_completion_tokens"] < spec.max_tokens:
            problems.append("pinned tag max_completion_tokens is below max_tokens")
    variants = [row["tag"] for row in rows if row["eligible"] and row["tag"] != spec.provider]
    if variants:
        warnings.append("only=[" + spec.provider + "] can also reach: " + ", ".join(variants)
                        + " (debit stays max(usage.cost, catalog list price); check the served provider)")
    return {"model": spec.model_id, "pinned_tag": spec.provider, "endpoints": rows, "eligible_variants": variants,
            "problems": problems, "warnings": warnings, "ok": exact is not None and not problems}


def endpoint_check(spec: ModelSpec, *, timeout_s: int = 30) -> dict:
    """GET /api/v1/models/{id}/endpoints (public, no key): the pinned tag is live and priced <= spec."""
    url = API_BASE + "/models/" + parse.quote(spec.model_id, safe="/") + "/endpoints"
    try:
        _, text = _open(url, timeout=timeout_s)
        doc = _json(text)
    except error.HTTPError as exc:
        return {"model": spec.model_id, "ok": False, "problems": [f"endpoint list HTTP {exc.code}"]}
    except (error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
        return {"model": spec.model_id, "ok": False, "problems": ["endpoint list unavailable: " + type(exc).__name__]}
    return check_endpoints(doc if isinstance(doc, dict) else {}, spec)


# ---------------------------------------------------------------- fixture transport

class MockOpenRouter:
    """Deterministic fixture transport (tests, --dry-run): same query() signature, no network.

    ``responder`` is a string (always that content), a list (one outcome per call) or a
    callable ``(body, spec, index) -> outcome``. An outcome is model content (str), a
    complete raw response dict (e.g. ``MockOpenRouter.http_error(429)``), or an
    exception instance to raise from ``query`` (simulating a crash mid-call).
    """

    _sequence = 0

    def __init__(self, responder, *, cost_usd: Decimal = Decimal("0.01"), prompt_tokens: int = 100,
                 completion_tokens: int = 50, provider_name: str = "OpenAI", generations: dict | None = None):
        self.responder = responder
        self.cost_usd = Decimal(str(cost_usd))
        self.prompt_tokens, self.completion_tokens = prompt_tokens, completion_tokens
        self.provider_name = provider_name
        self.generations = dict(generations or {})   # generation id -> /generation document
        self.calls = []

    def generation_lookup(self, generation_id: str, *, key: str | None = None) -> dict | None:
        doc = self.generations.get(generation_id)
        return deepcopy(doc) if doc is not None else None

    @property
    def http_calls(self) -> int:
        return len(self.calls)

    def outcome(self, body, spec, index):
        if callable(self.responder):
            return self.responder(body, spec, index)
        if isinstance(self.responder, (list, tuple)):
            return self.responder[index]
        return self.responder

    def query(self, body: dict, spec: ModelSpec, *, key: str | None = None, timeout_s: int | None = None) -> dict:
        index = len(self.calls)
        self.calls.append(deepcopy(body))
        outcome = self.outcome(body, spec, index)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, dict):
            return deepcopy(outcome)
        if not isinstance(outcome, str):
            raise TypeError("Mock outcome must be content text, a raw response dict or an exception")
        return self.response(outcome, spec, body)

    def response(self, content: str, spec: ModelSpec, body: dict) -> dict:
        MockOpenRouter._sequence += 1
        identity = f"gen-mock-{time.time_ns():x}-{MockOpenRouter._sequence:06d}-{sha(canonical(body))[:10]}"
        prompt, completion = self.prompt_tokens, self.completion_tokens
        return {"id": identity, "object": "chat.completion", "created": 0, "model": spec.model_id,
                "provider": self.provider_name,
                "choices": [{"index": 0, "finish_reason": "stop", "native_finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
                          "cost": float(self.cost_usd), "prompt_tokens_details": {"cached_tokens": 0},
                          "completion_tokens_details": {"reasoning_tokens": 0}}}

    @staticmethod
    def http_error(status: int, message: str = "mock error") -> dict:
        return {"transport_error": "HTTPError", "http_status": status, "error": {"code": status, "message": message},
                "billing_hint": "unbilled" if status in UNBILLED_HTTP else "unknown"}

    @staticmethod
    def timeout() -> dict:
        return {"transport_error": "TimeoutError", "http_status": None, "billing_hint": "unknown"}
