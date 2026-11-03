"""Offline OpenRouter adapter. Network dispatch is deliberately unavailable."""
import os
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from lean_agent import artifacts as a, models

MODEL_ID = 'openai/gpt-6.1-sol'
ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'

def payload(messages, model):
    if model.get('backend') != 'openrouter' or model.get('id') != MODEL_ID:
        raise ValueError('Expected pinned OpenRouter model')
    if not model.get('provider'):
        raise ValueError('Explicit upstream provider required')
    return models.payload(messages, model)

def compute_cost(raw):
    if not isinstance(raw, dict) or raw.get('error') or raw.get('transport_error'):
        raise ValueError('Successful response required')
    if raw.get('model') != MODEL_ID or not raw.get('id'):
        raise ValueError('Unexpected model or missing response identity')
    if not isinstance(raw.get('usage'), dict):
        raise ValueError('Usage required')
    value = raw['usage'].get('cost')
    if value is None or isinstance(value, bool):
        raise ValueError('Explicit settled OpenRouter cost required')
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid cost') from None
    if not cost.is_finite() or cost < 0:
        raise ValueError('Invalid cost')
    return {'cost_usd': str(cost), 'basis': 'openrouter-response-usage-cost',
            'invoice_verified': False, 'provider_response_sha256': a.sha(a.canonical(raw))}

def normalize(raw):
    value = deepcopy(raw) if isinstance(raw, dict) else {"invalid_response": True}
    try:
        receipt = compute_cost(raw)
    except (ValueError, TypeError, KeyError):
        receipt = {"cost_usd": None, "basis": "unknown", "invoice_verified": False,
                   "provider_response_sha256": a.sha(a.canonical(raw))}
    if not isinstance(value.get("usage"), dict):
        value["usage"] = {}
    value["usage"]["cost"] = receipt["cost_usd"]
    value["_cost_receipt"] = receipt
    return value

def query(*args, **kwargs):
    if os.environ.get('LEANAGENT_ALLOW_API') != '1':
        raise RuntimeError('API dispatch disabled: offline preparation only')
    return models.query(*args, **kwargs)

def model_metadata(*args, **kwargs):
    if os.environ.get('LEANAGENT_ALLOW_API') != '1':
        raise RuntimeError('Model API lookup disabled: offline preparation only')
    return {'id': MODEL_ID, 'endpoint': ENDPOINT, 'provider': 'openai', 'availability_verified': False, 'source': 'local pinned configuration; no model-list API call'}

# The price ceilings are routing constraints, not claims about current prices.
PRICING = {"basis": "openrouter-response-usage-cost", "routing_max_price_per_million": {"prompt": 10, "completion": 30}, "online_verified": False}
from lean_agent.budgeting import request_cost
load_key = models.load_key
