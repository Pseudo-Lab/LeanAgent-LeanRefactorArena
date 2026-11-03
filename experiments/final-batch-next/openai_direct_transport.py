"""OpenAI-direct development adapter for final-batch-next (final60 ``--transport openai``).

Development data only: roots sealed with this adapter record provider "OpenAI direct"
and api_endpoint https://api.openai.com/v1/chat/completions on every call, run
through the same guarded money path and shared ledger schema as OpenRouter (same
$2.99 worst-case pre-request cap, retries included), and are refused by
scripts/check_submission_provenance.py and by submission assembly. Their proofs
must never seed, carry into or appear in the prompts of an OpenRouter run
(``dev_proofs`` lists them for ``--non-openrouter``).

It exposes the names driver.py and report.py use from ``openai_transport`` plus the
final60 hooks, all bound to ``lean_agent.final60.openai_direct``; the hooks are the
profile-aware ones of ``openrouter_transport`` (the sealed root selects the wire).
"""
from __future__ import annotations

import json
from pathlib import Path

from lean_agent import artifacts as a
from lean_agent.final60 import openai_direct as wire, transports

import openrouter_transport as base

PROFILE = transports.profile("openai")
MODEL_ID = wire.MODEL_ID
ENDPOINT = wire.ENDPOINT
PROVIDER = wire.PROVIDER
TRANSPORT = wire.TRANSPORT
PRICING = wire.pricing_json()
COST_BASIS = wire.COST_BASIS
KEY_ENV = wire.KEY_ENV
SUBMITTABLE = False
BudgetExceeded = base.BudgetExceeded
ApiDisabled = base.ApiDisabled
MockOpenAI = wire.MockOpenAI

# Hooks shared with the OpenRouter adapter (they read the sealed transport of the root).
dispatch = base.dispatch
recover_pending = base.recover_pending
audit_root = base.audit_root
smoke_summary = base.smoke_summary
use_transport = base.use_transport
ledger_for_root = base.ledger_for_root
ledger_path = base.ledger_path
config_cap = base.config_cap
summary_fields = base.summary_fields
dev_proofs = wire.dev_proofs


def load_key(path):
    """OPENAI_API_KEY from an explicit dotenv file (never OpenRouter keys; never echoed)."""
    return wire.load_key(path)


def payload(messages, model):
    return wire.payload(messages, wire.spec_for_model(model))


def request_cost(body):
    """Same shape as openai_transport.request_cost: the worst-case reservation of one request."""
    spec = wire.spec_for_body(body)
    return wire.bound_json(wire.request_bound(body, spec), body, spec)


def model_metadata(model=None):
    """Static endpoint evidence (no network)."""
    spec = wire.spec_for_model(model) if model is not None else wire.fallback_spec(None)
    return wire.endpoint_evidence(spec)


def query(body, model, step):
    """One POST, no retry (driver signature). Use ``dispatch`` for guarded, ledgered calls."""
    spec = wire.spec_for_model(model)
    fixture = base.fixture()
    if fixture is not None:
        return fixture.query(body, spec, key=None)
    return wire.query(body, spec, key=base.current_key(PROFILE))


def compute_cost(raw):
    return wire.compute_cost(raw, wire.fallback_spec(raw.get("model") if isinstance(raw, dict) else None))


def normalize(raw, bound=None):
    """Single-response normalization. Without a bound an unusable bill stays unknown (None)."""
    spec = wire.fallback_spec(raw.get("model") if isinstance(raw, dict) else None)
    if bound is not None:
        return wire.normalize(raw, spec, bound)
    normalized = json.loads(a.canonical(raw)) if isinstance(raw, dict) else {
        "invalid_provider_response_type": type(raw).__name__}
    try:
        receipt = wire.compute_cost(raw, spec)
    except (ValueError, TypeError, KeyError) as exc:
        receipt = {"cost_usd": None, "basis": "unknown", "invoice_verified": False, "error": str(exc)[:300],
                   "provider_response_sha256": a.sha(a.canonical(raw))}
    if not isinstance(normalized.get("usage"), dict):
        normalized["usage"] = {}
    normalized["usage"]["cost"] = receipt["cost_usd"]
    normalized["provider"] = PROVIDER
    normalized["_cost_receipt"] = receipt
    return normalized


def audit_step(step_dir, ledger_item):
    return wire.audit_step(Path(step_dir), ledger_item)


def seal_fields(**options):
    """Authorization fields of an OpenAI-direct development root (never submittable)."""
    return PROFILE.seal_fields(**options)
