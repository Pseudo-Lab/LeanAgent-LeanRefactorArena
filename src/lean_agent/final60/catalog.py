"""Pinned OpenRouter model catalog for final60 (USD per million tokens).

Prices are OpenRouter list prices read from the public model list
(GET /api/v1/models, 2026-11-04 02:57 KST) and the per-model endpoint lists
(GET /api/v1/models/{id}/endpoints, 02:29 KST). They are frozen here: every
worst-case bound and every debit uses them, and OpenRouter's own usage.cost is
recorded beside them (the larger amount is debited).

Only ``gen_primary`` is used by default. The other entries are listed so that a
route can opt in after Smoke has checked them (design section 5, amendment A9):
``gen_alt`` has ``seed=None`` because no Claude endpoint supports ``seed`` and
``require_parameters`` would otherwise match no endpoint; ``gen_alt2`` stays off
until Smoke shows completion_tokens <= max_tokens.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal

from .contracts import CAP_USD, OPENROUTER_ENDPOINT, SCHEMA, ModelSpec

PRICES_FETCHED_AT = "2026-11-04T02:57:00+09:00"
PRICES_SOURCE = ("https://openrouter.ai/api/v1/models",
                 "https://openrouter.ai/api/v1/models/{id}/endpoints")
FRAMING_TOKENS = 4096            # chat framing allowance added to the UTF-8 byte count
MAX_REQUEST_BYTES = 240_000      # bytes + framing must stay below this (far under the 272K-token tier)
LONG_CONTEXT_TOKENS = 272_000    # OpenRouter price override threshold for the OpenAI models
MAX_COMPLETION_TOKENS = 65_536   # sanity ceiling for a request's max_tokens
MAX_TIMEOUT_S = 900
DEFAULT_KEY = "gen_primary"


def _usd(text):
    return Decimal(text)


CATALOG: dict[str, ModelSpec] = {
    "gen_primary": ModelSpec(
        key="gen_primary", model_id="openai/gpt-6.1-sol", provider="openai",
        prompt_usd_per_mtok=_usd("2"), completion_usd_per_mtok=_usd("10"),
        cache_read_usd_per_mtok=_usd("0.10"), cache_write_usd_per_mtok=_usd("2.50"),
        max_tokens=8192, reasoning_effort="high", timeout_s=900, seed=42),
    # Cache writes priced at Anthropic's 1-hour rate ($4/M), the most expensive
    # write tier OpenRouter lists for this model: over-reporting is allowed.
    "gen_alt": ModelSpec(
        key="gen_alt", model_id="anthropic/claude-sonnet-5.5", provider="anthropic",
        prompt_usd_per_mtok=_usd("2"), completion_usd_per_mtok=_usd("10"),
        cache_read_usd_per_mtok=_usd("0.10"), cache_write_usd_per_mtok=_usd("4.00"),
        max_tokens=16384, reasoning_effort="high", timeout_s=900, seed=None),
    "gen_alt2": ModelSpec(
        key="gen_alt2", model_id="google/gemini-4-argon", provider="google-ai-studio",
        prompt_usd_per_mtok=_usd("2"), completion_usd_per_mtok=_usd("10"),
        cache_read_usd_per_mtok=_usd("0.10"), cache_write_usd_per_mtok=_usd("0.1875"),
        max_tokens=16384, reasoning_effort="high", timeout_s=900, seed=42),
    "cheap": ModelSpec(
        key="cheap", model_id="openai/gpt-6-luna", provider="openai",
        prompt_usd_per_mtok=_usd("0.10"), completion_usd_per_mtok=_usd("0.50"),
        cache_read_usd_per_mtok=_usd("0.01"), cache_write_usd_per_mtok=_usd("0.125"),
        max_tokens=8192, reasoning_effort="low", timeout_s=900, seed=42),
}

STATUS = {"gen_primary": "default for every role",
          "gen_alt": "off by default; enable only after Smoke confirms JSON actions (no seed support)",
          "gen_alt2": "off by default; enable only after Smoke shows completion_tokens <= max_tokens",
          "cheap": "reserved; not used by default"}


def spec(key: str) -> ModelSpec:
    try:
        return CATALOG[key]
    except KeyError:
        raise ValueError("Unknown final60 catalog key: " + str(key)) from None


def number(value: Decimal):
    """JSON number for a price ceiling (int when integral, else float)."""
    value = Decimal(value)
    return int(value) if value == value.to_integral_value() else float(value)


def max_price(model_spec: ModelSpec) -> dict:
    return {"prompt": number(model_spec.prompt_usd_per_mtok),
            "completion": number(model_spec.completion_usd_per_mtok)}


def driver_model(key: str = DEFAULT_KEY, *, max_tokens: int | None = None, timeout_s: int | None = None) -> dict:
    """The final-batch-next ``config["model"]`` dict for a catalog entry."""
    base = spec(key)
    model = {"backend": "openrouter", "catalog_key": base.key, "id": base.model_id, "provider": base.provider,
             "max_tokens": base.max_tokens if max_tokens is None else max_tokens,
             "timeout_seconds": base.timeout_s if timeout_s is None else timeout_s,
             "max_price": max_price(base)}
    if base.reasoning_effort is not None:
        model["reasoning_effort"] = base.reasoning_effort
    if base.seed is not None:
        model["seed"] = base.seed
    spec_for_model(model)
    return model


def _positive(value, label, ceiling):
    if type(value) is not int or value <= 0 or value > ceiling:
        raise ValueError(f"Expected a positive integer {label} <= {ceiling}")
    return value


def spec_for_model(model: dict) -> ModelSpec:
    """Driver ``config["model"]`` dict -> ModelSpec (by ``catalog_key``), refusing any drift."""
    if not isinstance(model, dict) or model.get("backend") != "openrouter":
        raise ValueError("Expected an OpenRouter model dict")
    key = model.get("catalog_key")
    if key is None:
        matches = [value for value in CATALOG.values()
                   if value.model_id == model.get("id") and value.provider == model.get("provider")]
        if len(matches) != 1:
            raise ValueError("OpenRouter model dict needs a catalog_key")
        key = matches[0].key
    base = spec(key)
    if model.get("id") != base.model_id or model.get("provider") != base.provider:
        raise ValueError("Model id/provider differ from the pinned catalog entry " + base.key)
    if model.get("reasoning_effort") != base.reasoning_effort:
        raise ValueError("Reasoning effort differs from the pinned catalog entry " + base.key)
    if model.get("seed") != base.seed:
        raise ValueError("Seed differs from the pinned catalog entry " + base.key)
    if "max_price" in model and model["max_price"] != max_price(base):
        raise ValueError("Price ceiling differs from the pinned catalog entry " + base.key)
    extra = set(model) - {"backend", "catalog_key", "id", "provider", "max_tokens", "timeout_seconds",
                          "reasoning_effort", "seed", "max_price"}
    if extra:
        raise ValueError("Unexpected OpenRouter model settings: " + ", ".join(sorted(extra)))
    tokens = _positive(model.get("max_tokens", base.max_tokens), "max_tokens", MAX_COMPLETION_TOKENS)
    timeout = _positive(model.get("timeout_seconds", base.timeout_s), "timeout_seconds", MAX_TIMEOUT_S)
    return replace(base, max_tokens=tokens, timeout_s=timeout)


def spec_for_body(body: dict) -> ModelSpec:
    """Wire body -> the catalog entry it is pinned to (``max_tokens`` taken from the body)."""
    try:
        model_id, only = body["model"], body["provider"]["only"]
    except (KeyError, TypeError):
        raise ValueError("Request is not pinned to an OpenRouter provider") from None
    matches = [value for value in CATALOG.values() if value.model_id == model_id and only == [value.provider]]
    if len(matches) != 1:
        raise ValueError("Request model/provider is not a pinned final60 catalog entry")
    return replace(matches[0], max_tokens=_positive(body.get("max_tokens"), "max_tokens", MAX_COMPLETION_TOKENS))


def spec_for_returned_model(model_id) -> ModelSpec | None:
    """Best-effort lookup from a response's model field (OpenRouter may append a dated suffix)."""
    if not isinstance(model_id, str):
        return None
    for value in CATALOG.values():
        if model_id == value.model_id or model_id.startswith(value.model_id + "-"):
            return value
    return None


def prices(model_spec: ModelSpec) -> dict:
    return {"prompt": str(model_spec.prompt_usd_per_mtok), "completion": str(model_spec.completion_usd_per_mtok),
            "cache_read": str(model_spec.cache_read_usd_per_mtok),
            "cache_write": str(model_spec.cache_write_usd_per_mtok),
            "unit": "USD per million tokens"}


def pricing_json() -> dict:
    """Written to run_root/pricing.json: every spec, its source and the money rules."""
    models = {}
    for key, value in CATALOG.items():
        entry = asdict(value)
        for field in ("prompt_usd_per_mtok", "completion_usd_per_mtok", "cache_read_usd_per_mtok",
                      "cache_write_usd_per_mtok"):
            entry[field] = str(entry[field])
        entry["max_price"] = max_price(value)
        entry["status"] = STATUS[key]
        models[key] = entry
    return {"schema": SCHEMA, "provider": "OpenRouter", "api_endpoint": OPENROUTER_ENDPOINT,
            "currency": "USD", "unit": "per_million_tokens", "source": list(PRICES_SOURCE),
            "fetched_at": PRICES_FETCHED_AT, "per_problem_cap_usd": str(CAP_USD), "models": models,
            "bound_rule": ("(utf8_bytes(body) + 4096) * max(prompt, cache_write) + max_tokens * completion; "
                           "requests stay below 240,000 bytes so the 272K-token price tier is never reached"),
            "debit_rule": "max(openrouter usage.cost, cache-aware list price of the returned token usage)",
            "lost_response_rule": "generation API total if a generation id is known, else the full request bound",
            "unbilled_http_statuses": [400, 401, 402, 403, 404, 429]}
