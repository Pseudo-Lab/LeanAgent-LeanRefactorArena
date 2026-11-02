"""OpenAI direct Chat Completions transport and auditable public-price receipts.

The untouched provider JSON is archived separately by the driver. A normalized
copy supplies the common harness's usage.cost field; this is a calculation from
provider token usage and frozen public list prices, not an invoice receipt.
"""
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import shlex
from urllib import error, request

from lean_agent import artifacts as a

MODEL_ID = "gpt-6.1-sol"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
PRICING = {"model": MODEL_ID, "provider": "OpenAI", "service_tier": "default",
           "currency": "USD", "unit": "per_million_tokens", "input": "2", "cached_input": "0.10",
           "cache_write_30m": "2.50", "output_including_reasoning": "10", "long_context_threshold": 272000,
           "source": "https://developers.openai.com/api/docs/pricing",
           "usage_source": "https://developers.openai.com/api/docs/guides/prompt-caching",
           "verified_date": "2026-11-01"}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_key(path):
    values = []
    for line in Path(path).read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "OPENAI_API_KEY":
            parts = shlex.split(value, comments=True)
            if len(parts) != 1 or not parts[0]:
                raise ValueError("Invalid OpenAI dotenv entry")
            values.append(parts[0])
    if not values or len(set(values)) != 1:
        raise ValueError("Missing or conflicting OpenAI dotenv entries")
    return values[0]


def payload(messages, model):
    if model["id"] != MODEL_ID or model["backend"] != "openai":
        raise ValueError("Expected pinned direct OpenAI model")
    if (not isinstance(messages, list) or len(messages) != 2 or
            any(not isinstance(message, dict) or set(message) != {"role", "content"} or
                not isinstance(message["content"], str) for message in messages) or
            messages[0]["role"] != "system" or messages[1]["role"] != "user"):
        raise ValueError("Expected exactly two plain-text system/user messages")
    wire_messages = [{"role": "system", "content": [{"type": "text", "text": messages[0]["content"],
                        "prompt_cache_breakpoint": {"mode": "explicit"}}]},
                     {"role": "user", "content": messages[1]["content"]}]
    return {"model": MODEL_ID, "messages": wire_messages,
            "max_completion_tokens": model["max_tokens"], "reasoning_effort": model["reasoning_effort"],
            "seed": model["seed"], "response_format": {"type": "json_object"},
            "service_tier": "default", "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
            "n": 1, "stream": False, "store": False}


def request_cost(body):
    allowed = {"model", "messages", "max_completion_tokens", "reasoning_effort", "seed", "response_format",
               "service_tier", "prompt_cache_options", "n", "stream", "store"}
    messages = body.get("messages")
    valid_messages = (isinstance(messages, list) and len(messages) == 2 and
        all(isinstance(message, dict) and set(message) == {"role", "content"} for message in messages))
    if valid_messages:
        system, user = messages
        parts = system["content"]
        valid_messages = (system["role"] == "system" and user["role"] == "user" and isinstance(user["content"], str) and
            isinstance(parts, list) and len(parts) == 1 and isinstance(parts[0], dict) and
            set(parts[0]) == {"type", "text", "prompt_cache_breakpoint"} and parts[0]["type"] == "text" and
            isinstance(parts[0]["text"], str) and parts[0]["prompt_cache_breakpoint"] == {"mode": "explicit"})
    if (set(body) != allowed or body["model"] != MODEL_ID or body["service_tier"] != "default" or
            body["prompt_cache_options"] != {"mode": "explicit", "ttl": "30m"} or
            body["stream"] is not False or body["n"] != 1 or not valid_messages):
        raise ValueError("Cost bound requires pinned direct OpenAI plain-text request")
    count = len(json.dumps(body, ensure_ascii=False).encode()) + 4096
    if count >= 240000:
        raise ValueError("Request must remain conservatively below the 272K pricing tier")
    maximum = (Decimal(count) * Decimal(PRICING["cache_write_30m"]) +
               Decimal(body["max_completion_tokens"]) * Decimal(PRICING["output_including_reasoning"])) / 1000000
    return {"request_sha256": a.sha(a.canonical(body)), "input_token_bound": count,
            "output_token_bound": body["max_completion_tokens"], "reserved_usd": str(maximum),
            "basis": "public-list-price upper bound; all input conservatively charged as 30m cache writes"}


def model_metadata():
    call = request.Request("https://api.openai.com/v1/models/" + MODEL_ID,
                           headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
    with request.build_opener(NoRedirect).open(call, timeout=30) as response:
        data = json.loads(response.read())
    if data.get("id") != MODEL_ID:
        raise ValueError("Pinned direct OpenAI model unavailable")
    return data


def query(body, model, step):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Missing explicitly configured OpenAI credentials")
    call = request.Request(ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode(),
                           headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with request.build_opener(NoRedirect).open(call, timeout=model["timeout_seconds"]) as response:
            return json.loads(response.read())
    except error.HTTPError as exc:
        result = {"transport_error": "HTTPError", "http_status": exc.code}
        try:
            failure = json.loads(exc.read()).get("error", {})
            result["error"] = {key: failure.get(key) for key in ("type", "code", "param")}
        except (ValueError, TypeError, AttributeError):
            pass
        return result
    except (error.URLError, TimeoutError, OSError, ValueError) as exc:
        # No retry, no exception strings or headers that could expose credentials.
        return {"transport_error": type(exc).__name__, "http_status": getattr(exc, "code", None)}


def integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("Missing/invalid token counter: " + label)
    return value


def compute_cost(raw):
    if not isinstance(raw, dict) or raw.get("error") or raw.get("transport_error"):
        raise ValueError("Missing successful provider response")
    if raw.get("model") != MODEL_ID or raw.get("service_tier") != "default":
        raise ValueError("Unexpected returned model/service tier")
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("Provider usage missing")
    prompt = integer(usage.get("prompt_tokens"), "prompt_tokens")
    completion = integer(usage.get("completion_tokens"), "completion_tokens")
    if integer(usage.get("total_tokens"), "total_tokens") != prompt + completion:
        raise ValueError("Provider usage totals disagree")
    if prompt > PRICING["long_context_threshold"]:
        raise ValueError("Unexpected long-context price tier")
    details = usage.get("prompt_tokens_details")
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise ValueError("Invalid prompt token details")
    cached = integer(details.get("cached_tokens", 0), "cached_tokens")
    written = integer(details.get("cache_write_tokens", 0), "cache_write_tokens")
    ordinary = prompt - cached - written
    if ordinary < 0:
        raise ValueError("Cache reads/writes exceed total input tokens")
    lifetimes = details.get("cache_write_tokens_details")
    if lifetimes is not None:
        if not isinstance(lifetimes, dict) or integer(lifetimes.get("ttl_12h_tokens", 0), "ttl_12h_tokens") != 0:
            raise ValueError("Unexpected non-30m cache writes")
        if integer(lifetimes.get("ttl_30m_tokens", 0), "ttl_30m_tokens") != written:
            raise ValueError("Cache-write lifetime counts disagree")
    completion_details = usage.get("completion_tokens_details")
    if completion_details is None:
        completion_details = {}
    if not isinstance(completion_details, dict):
        raise ValueError("Invalid completion token details")
    reasoning = integer(completion_details.get("reasoning_tokens", 0), "reasoning_tokens")
    if reasoning > completion:
        raise ValueError("Reasoning tokens exceed total completion tokens")
    for label, counters in (("prompt", details), ("completion", completion_details)):
        for modality in ("audio_tokens", "image_tokens"):
            if integer(counters.get(modality, 0), label + "." + modality):
                raise ValueError("Unexpected non-text token pricing")
    cost = (Decimal(ordinary) * Decimal(PRICING["input"]) +
            Decimal(cached) * Decimal(PRICING["cached_input"]) +
            Decimal(written) * Decimal(PRICING["cache_write_30m"]) +
            Decimal(completion) * Decimal(PRICING["output_including_reasoning"])) / 1000000
    return {"cost_usd": str(cost), "basis": "provider-token-usage-times-frozen-public-list-prices",
            "invoice_verified": False, "ordinary_input_tokens": ordinary, "cached_input_tokens": cached,
            "cache_write_30m_tokens": written, "completion_tokens_including_reasoning": completion,
            "reasoning_tokens_already_included": reasoning, "pricing": PRICING,
            "provider_response_sha256": a.sha(a.canonical(raw))}


def normalize(raw):
    normalized = deepcopy(raw) if isinstance(raw, dict) else {"invalid_provider_response_type": type(raw).__name__}
    try:
        receipt = compute_cost(raw)
    except (ValueError, TypeError, KeyError) as exc:
        receipt = {"cost_usd": None, "basis": "unknown", "invoice_verified": False,
                   "error": str(exc), "provider_response_sha256": a.sha(a.canonical(raw))}
    if not isinstance(normalized.get("usage"), dict):
        normalized["usage"] = {}
    normalized["usage"]["cost"] = receipt["cost_usd"]
    normalized["provider"] = "OpenAI"
    normalized["_cost_receipt"] = receipt
    return normalized
