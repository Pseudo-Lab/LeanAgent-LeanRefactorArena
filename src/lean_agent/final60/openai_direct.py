"""OpenAI-direct development wire for final60 (never a submission path).

Same shape as ``transport`` (the OpenRouter wire) so ``money.dispatch_guarded``,
``CostLedger.recover`` and ``transport.audit_step`` run unchanged with ``wire=`` this
module: one POST per sub-attempt, the same worst-case pre-request bound against the
same $2.99 per-problem cap, the same SQLite/ledger.json schema, every receipt stamped
``provider "OpenAI direct"`` and ``api_endpoint https://api.openai.com/v1/chat/completions``.

Payload, bound and list-price receipt are reused from
``experiments/final-batch-next/openai_transport.py`` (pinned ``gpt-6.1-sol``, frozen
public prices). OpenAI has no generation API, so a lost response is settled at its
full bound. Everything produced through this wire is development data: the
provenance checker and submission assembly refuse it (``transports.is_submittable``),
and ``dev_proofs`` lists its proof texts so they can be fed to ``--non-openrouter``.

Credentials are never logged, printed or stored.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import http.client
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from urllib import error, request

from lean_agent.artifacts import canonical, read, sha

from . import transport as t
from .contracts import CAP_USD, SCHEMA, Bound, ModelSpec

PROVIDER = "OpenAI direct"
TRANSPORT = "openai"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
HOST = "api.openai.com"
MODEL_ID = "gpt-6.1-sol"
BACKEND = "openai"
PINNED_PROVIDER = "openai"
UNBILLED_HTTP = t.UNBILLED_HTTP          # 400/401/403/404/429 are refused before billing
DISABLE_HTTP = t.DISABLE_HTTP            # 401 (key) / 402 disable the API globally
GENERATION_API = False                   # no exact settlement of lost responses
LOST_ID_PREFIX = t.LOST_ID_PREFIX
KEY_ENV = "OPENAI_API_KEY"
_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")
LEAK_MARKERS = (re.compile(rb"sk-[A-Za-z0-9_\-]{20,}"),)
REDACTED = t.REDACTED
COST_BASIS = "provider-token-usage-times-frozen-public-list-prices"
DEBIT_RULE = "cache-aware frozen public list price of the returned token usage (OpenAI reports no usage.cost)"
BOUND_BASIS = "public-list-price upper bound; all input conservatively charged as 30m cache writes"
ALLOWED_MODEL_KEYS = frozenset({"backend", "id", "provider", "max_tokens", "timeout_seconds", "reasoning_effort",
                                "seed"})
usd = t.usd
classify = t.classify
http_status_of = t.http_status_of


# ---------------------------------------------------------------- reuse of openai_transport.py

def batch_module():
    """``experiments/final-batch-next/openai_transport.py`` (importable on the driver path,
    else loaded from this checkout; never from a machine-specific location)."""
    module = sys.modules.get("openai_transport")
    if module is not None:
        return module
    try:
        import openai_transport as module   # noqa: F811 - the driver directory is on sys.path
        return module
    except ImportError:
        pass
    path = Path(__file__).resolve().parents[3] / "experiments" / "final-batch-next" / "openai_transport.py"
    if not path.is_file():
        raise ImportError("openai_transport.py is not available (expected experiments/final-batch-next)")
    spec = importlib.util.spec_from_file_location("openai_transport", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["openai_transport"] = module
    spec.loader.exec_module(module)
    return module


def pricing() -> dict:
    return dict(batch_module().PRICING)


def _base_spec() -> ModelSpec:
    price = pricing()
    return ModelSpec(key="gen_primary", model_id=MODEL_ID, provider=PINNED_PROVIDER,
                     prompt_usd_per_mtok=Decimal(price["input"]), completion_usd_per_mtok=Decimal(price["output_including_reasoning"]),
                     cache_read_usd_per_mtok=Decimal(price["cached_input"]), cache_write_usd_per_mtok=Decimal(price["cache_write_30m"]),
                     max_tokens=8192, reasoning_effort="high", timeout_s=900, seed=42)


def prices(spec: ModelSpec | None = None) -> dict:
    spec = spec or _base_spec()
    return {"prompt": str(spec.prompt_usd_per_mtok), "completion": str(spec.completion_usd_per_mtok),
            "cache_read": str(spec.cache_read_usd_per_mtok), "cache_write": str(spec.cache_write_usd_per_mtok),
            "unit": "USD per million tokens"}


# ---------------------------------------------------------------- keys

def require_key(key) -> str:
    if (not isinstance(key, str) or not key.startswith("sk-") or key.startswith("sk-or-") or len(key) < 20):
        raise ValueError("Missing OpenAI API key (expected an sk- key that is not an OpenRouter key; never shown)")
    return key


def load_key(path) -> str:
    """OPENAI_API_KEY from an explicit dotenv file; never logs or echoes it."""
    return require_key(batch_module().load_key(Path(path)))


def scrub(value, key: str | None = None, *, strict: bool = True):
    """Copy of ``value`` with the key and anything key-shaped replaced (see transport.scrub)."""
    if isinstance(value, dict):
        return {name: scrub(item, key, strict=strict) for name, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, key, strict=strict) for item in value]
    if isinstance(value, str):
        if isinstance(key, str) and len(key) >= 20:
            value = value.replace(key, REDACTED)
        if "sk-" in value:
            value = _KEY_PATTERN.sub(REDACTED, value)
        if strict and "earer" in value:
            value = t._BEARER_PATTERN.sub(REDACTED, value)
        return value
    return value


# ---------------------------------------------------------------- specs, payload and bound

def driver_model(*, max_tokens: int | None = None, timeout_s: int | None = None) -> dict:
    """The final-batch-next ``config["model"]`` dict of the pinned direct model."""
    base = _base_spec()
    return {"backend": BACKEND, "id": MODEL_ID, "provider": PINNED_PROVIDER,
            "reasoning_effort": base.reasoning_effort, "max_tokens": base.max_tokens if max_tokens is None else max_tokens,
            "timeout_seconds": base.timeout_s if timeout_s is None else timeout_s, "seed": base.seed}


def spec_for_model(model: dict) -> ModelSpec:
    """Driver ``config["model"]`` dict -> ModelSpec; refuses anything but the pinned direct model."""
    if not isinstance(model, dict) or model.get("backend") != BACKEND or model.get("id") != MODEL_ID:
        raise ValueError("Expected the pinned direct OpenAI model dict (backend openai, id " + MODEL_ID + ")")
    if set(model) - ALLOWED_MODEL_KEYS:
        raise ValueError("Unexpected OpenAI model settings: " + ", ".join(sorted(set(model) - ALLOWED_MODEL_KEYS)))
    if model.get("provider", PINNED_PROVIDER) != PINNED_PROVIDER:
        raise ValueError("Direct OpenAI model provider must be 'openai'")
    base = _base_spec()
    tokens = model.get("max_tokens", base.max_tokens)
    timeout = model.get("timeout_seconds", base.timeout_s)
    if type(tokens) is not int or not 0 < tokens <= 65_536 or type(timeout) is not int or not 0 < timeout <= 900:
        raise ValueError("Expected positive integer max_tokens <= 65536 and timeout_seconds <= 900")
    effort, seed = model.get("reasoning_effort"), model.get("seed")
    if effort not in ("low", "medium", "high") or (seed is not None and type(seed) is not int):
        raise ValueError("Direct OpenAI model needs reasoning_effort low|medium|high and an integer or null seed")
    return replace(base, max_tokens=tokens, timeout_s=timeout, reasoning_effort=effort, seed=seed)


def _model_dict(spec: ModelSpec) -> dict:
    return {"backend": BACKEND, "id": spec.model_id, "max_tokens": spec.max_tokens,
            "reasoning_effort": spec.reasoning_effort, "seed": spec.seed}


def payload(messages: list[dict], spec: ModelSpec) -> dict:
    """Pinned direct body (openai_transport.payload): JSON mode, default tier, no store."""
    body = deepcopy(batch_module().payload(messages, _model_dict(spec)))
    validate_body(body, spec)
    return body


def validate_body(body: dict, spec: ModelSpec) -> None:
    batch_module().request_cost(body)   # ValueError unless the pinned direct shape
    if body.get("max_completion_tokens") != spec.max_tokens or body.get("reasoning_effort") != spec.reasoning_effort:
        raise ValueError("Request max_completion_tokens/reasoning_effort differ from the model spec")
    if body.get("seed") != spec.seed:
        raise ValueError("Request seed differs from its model spec")


def spec_for_body(body: dict) -> ModelSpec:
    """Wire body -> spec (tokens, effort and seed taken from the pinned body)."""
    batch_module().request_cost(body)
    base = _base_spec()
    tokens, effort, seed = body["max_completion_tokens"], body["reasoning_effort"], body["seed"]
    if type(tokens) is not int or not 0 < tokens <= 65_536 or effort not in ("low", "medium", "high"):
        raise ValueError("Request max_completion_tokens/reasoning_effort are not pinned values")
    if seed is not None and type(seed) is not int:
        raise ValueError("Request seed must be an integer or null")
    return replace(base, max_tokens=tokens, reasoning_effort=effort, seed=seed)


def fallback_spec(model_id) -> ModelSpec:
    return _base_spec()


def request_bound(body: dict, spec: ModelSpec) -> Bound:
    """Worst-case cost of one request (openai_transport.request_cost); ValueError if unpinned."""
    validate_body(body, spec)
    cost = batch_module().request_cost(body)
    return Bound(input_token_bound=cost["input_token_bound"], output_token_bound=cost["output_token_bound"],
                 reserved_usd=Decimal(cost["reserved_usd"]), basis=cost["basis"])


def bound_json(bound: Bound, body: dict, spec: ModelSpec) -> dict:
    return {"request_sha256": sha(canonical(body)), "input_token_bound": bound.input_token_bound,
            "output_token_bound": bound.output_token_bound, "reserved_usd": usd(bound.reserved_usd),
            "basis": bound.basis, "catalog_key": spec.key, "model": spec.model_id, "provider": spec.provider,
            "transport": TRANSPORT, "prices": prices(spec)}


def endpoint_evidence(spec: ModelSpec) -> dict:
    price = pricing()
    return {"schema": SCHEMA, "api_endpoint": ENDPOINT, "host": HOST, "provider": PROVIDER, "transport": TRANSPORT,
            "catalog_key": spec.key, "model": spec.model_id, "service_tier": price.get("service_tier", "default"),
            "prices": prices(spec), "prices_verified_date": price.get("verified_date"),
            "source": "frozen openai_transport.PRICING (development transport)", "submittable": False}


def wire_bytes(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------- HTTP

def query(body: dict, spec: ModelSpec, *, key: str, timeout_s: int | None = None) -> dict:
    """ONE POST to api.openai.com; no redirect, no retry, never raises for HTTP/network."""
    require_key(key)
    data = wire_bytes(body)
    try:
        status, text = t._open(ENDPOINT, key=key, data=data, timeout=timeout_s or spec.timeout_s)
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
        retry_after = t._retry_after(getattr(exc, "headers", None))
        if retry_after is not None:
            result["retry_after_s"] = retry_after
        return scrub(result, key)
    except (error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
        return {"transport_error": type(exc).__name__, "http_status": None, "billing_hint": "unknown"}
    try:
        value = t._json(text)
    except (ValueError, UnicodeDecodeError):
        return {"transport_error": "InvalidJSON", "http_status": status, "billing_hint": "unknown",
                "body_sha256": sha(text), "body_bytes": len(text)}
    if not isinstance(value, dict):
        return {"transport_error": "InvalidJSONType", "http_status": status, "billing_hint": "unknown"}
    return scrub(value, key, strict=classify(value) != "ok")


def _error_info(text) -> dict | None:
    try:
        doc = t._json(text)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    failure = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(failure, dict):
        return None
    info = {}
    for name in ("type", "code", "param"):
        if isinstance(failure.get(name), (int, str)):
            info[name] = failure[name] if isinstance(failure[name], int) else failure[name][:200]
    if isinstance(failure.get("message"), str):
        info["message"] = failure["message"][:500]
    return info


def generation_id_of(raw) -> str | None:
    if not isinstance(raw, dict) or "transport_error" in raw:
        return None
    value = raw.get("id")
    return value if isinstance(value, str) and value else None


# ---------------------------------------------------------------- receipts

def compute_cost(raw: dict, spec: ModelSpec) -> dict:
    """Deterministic list-price debit (openai_transport.compute_cost); ValueError if unusable."""
    if classify(raw) != "ok":
        raise ValueError("Missing successful provider response")
    detail = batch_module().compute_cost(raw)
    usage = raw["usage"]
    prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
    if detail["reasoning_tokens_already_included"] > completion:
        raise ValueError("Reasoning tokens exceed total completion tokens")
    return {"cost_usd": usd(Decimal(detail["cost_usd"])), "basis": "cache-aware-list-price", "debit_rule": DEBIT_RULE,
            "usage_cost": None, "list_price_cost": usd(Decimal(detail["cost_usd"])),
            "prompt_tokens": prompt, "ordinary_prompt_tokens": detail["ordinary_input_tokens"],
            "cached_tokens": detail["cached_input_tokens"], "cache_write_tokens": detail["cache_write_30m_tokens"],
            "completion_tokens": completion, "reasoning_tokens": detail["reasoning_tokens_already_included"],
            "catalog_key": spec.key, "requested_model": spec.model_id, "pinned_provider": spec.provider,
            "returned_model": raw.get("model"), "returned_provider": PROVIDER, "service_tier": raw.get("service_tier"),
            "generation_id": raw.get("id"), "prices": prices(spec), "invoice_verified": False,
            "provider_response_sha256": sha(canonical(raw))}


def sub_attempt_cost(raw, spec: ModelSpec, bound: Bound, generation: dict | None = None) -> dict:
    """Receipt for one HTTP sub-attempt (same keys as transport.sub_attempt_cost)."""
    kind = classify(raw)
    status = http_status_of(raw)
    record = {"outcome": kind, "http_status": status, "generation_id": generation_id_of(raw),
              "returned_model": raw.get("model") if isinstance(raw, dict) and kind == "ok" else None,
              "returned_provider": PROVIDER if kind == "ok" else None,
              "bound_usd": usd(bound.reserved_usd), "provider_response_sha256": sha(canonical(raw))}
    if kind == "unbilled":
        return {**record, "status": "unbilled", "cost_usd": "0", "basis": f"unbilled-http-{status}",
                "settlement_basis": "unbilled", "bound_violated": False}
    if kind == "ok":
        try:
            detail = compute_cost(raw, spec)
        except (ValueError, TypeError, KeyError) as exc:
            return {**record, "status": "settled", "cost_usd": usd(bound.reserved_usd),
                    "basis": "conservative-bound-unusable-usage", "settlement_basis": "lost-bound",
                    "usage_error": str(exc)[:300], "bound_violated": False}
        cost = Decimal(detail["cost_usd"])
        violated = (cost > bound.reserved_usd or detail["completion_tokens"] > bound.output_token_bound
                    or detail["prompt_tokens"] > bound.input_token_bound)
        return {**record, "status": "settled", "cost_usd": detail["cost_usd"], "basis": detail["basis"],
                "settlement_basis": "list-price", "detail": detail, "bound_violated": violated}
    return {**record, "status": "lost_conservative", "cost_usd": usd(bound.reserved_usd),
            "basis": "lost-response-conservative-bound", "settlement_basis": "lost-bound", "bound_violated": False}


def normalize(raw, spec: ModelSpec, bound: Bound, *, sub_attempts=(), attempt_id: str | None = None,
              final_id: str | None = None, generation: dict | None = None) -> dict:
    """Step response with usage.cost and _cost_receipt stamped OpenAI direct / api.openai.com."""
    return t.normalize(raw, spec, bound, sub_attempts=sub_attempts, attempt_id=attempt_id, final_id=final_id,
                       generation=generation, wire=_self())


def audit_step(step_dir: Path, ledger_item: dict) -> list[str]:
    """Recompute one OpenAI-direct driver step from its evidence; [] means clean."""
    return t.audit_step(Path(step_dir), ledger_item, wire=_self())


def _self():
    return sys.modules[__name__]


def pricing_json() -> dict:
    """run_root/pricing.json for a development root."""
    base = _base_spec()
    price = pricing()
    return {"schema": SCHEMA, "provider": PROVIDER, "transport": TRANSPORT, "api_endpoint": ENDPOINT,
            "currency": "USD", "unit": "per_million_tokens", "source": price.get("source"),
            "verified_date": price.get("verified_date"), "per_problem_cap_usd": str(CAP_USD),
            "models": {base.key: {"model_id": base.model_id, "provider": base.provider, "max_tokens": base.max_tokens,
                                  "reasoning_effort": base.reasoning_effort, "seed": base.seed,
                                  "timeout_s": base.timeout_s, **prices(base)}},
            "bound_rule": BOUND_BASIS, "debit_rule": DEBIT_RULE,
            "lost_response_rule": "full request bound (OpenAI has no generation API)",
            "unbilled_http_statuses": sorted(UNBILLED_HTTP), "submittable": False,
            "note": "development data only: never submitted, never a seed, carry or prompt content for OpenRouter runs"}


def dev_proofs(root) -> list[dict]:
    """Every proof text a development root produced ({name, proof, path}); feed them to
    the provenance checker's --non-openrouter so they can never seed an OpenRouter run."""
    root = Path(root)
    found = []
    for folder in sorted((root / "problems").glob("F[0-9][0-9][0-9]")):
        problem = folder / "input" / "problem.json"
        name = None
        if problem.is_file():
            try:
                name = read(problem).get("name")
            except (OSError, ValueError):
                name = None
        for path in sorted(folder.rglob("*.lean")):
            if "input" in path.relative_to(folder).parts:
                continue   # frozen inputs (the original) are not model output
            try:
                found.append({"name": name or folder.name, "proof": path.read_text(encoding="utf-8"),
                              "path": str(path.relative_to(root))})
            except (OSError, UnicodeDecodeError):
                continue
    return found


# ---------------------------------------------------------------- fixture transport

class MockOpenAI(t.MockOpenRouter):
    """Deterministic fixture with OpenAI-shaped completions (no network, no generation API)."""

    generation_lookup = None

    def __init__(self, responder, *, prompt_tokens: int = 100, completion_tokens: int = 50, cached_tokens: int = 0,
                 reasoning_tokens: int = 0, model: str = MODEL_ID, service_tier: str = "default"):
        super().__init__(responder, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        self.cached_tokens, self.reasoning_tokens = cached_tokens, reasoning_tokens
        self.model, self.service_tier = model, service_tier

    def response(self, content: str, spec: ModelSpec, body: dict) -> dict:
        t.MockOpenRouter._sequence += 1
        identity = f"chatcmpl-mock-{time.time_ns():x}-{t.MockOpenRouter._sequence:06d}-{sha(canonical(body))[:10]}"
        prompt, completion = self.prompt_tokens, self.completion_tokens
        return {"id": identity, "object": "chat.completion", "created": 0, "model": self.model,
                "service_tier": self.service_tier,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
                          "prompt_tokens_details": {"cached_tokens": self.cached_tokens},
                          "completion_tokens_details": {"reasoning_tokens": self.reasoning_tokens}}}
