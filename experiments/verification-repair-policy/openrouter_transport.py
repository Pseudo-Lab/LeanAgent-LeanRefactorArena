"""Competition model calls through OpenRouter only; no retries or fallback."""
from copy import deepcopy
from decimal import Decimal, ROUND_FLOOR
import json
import getpass
import re
import sys
import warnings
from urllib import request, error

from common import canonical, shared
from generation_transport import payload as direct_payload
from lean_agent import models

MODEL = 'openai/gpt-6.1-sol'
ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
METADATA_URL = 'https://openrouter.ai/api/v1/models/'+MODEL+'/endpoints'
INPUT_CAP = 200000
IP, OP = Decimal('0.0000025'), Decimal('0.00001')


def validate_endpoint(endpoint):
    if endpoint.get('tag') != 'openai' or endpoint.get('model_id') != MODEL or endpoint.get('service_tier') not in (None, 'default'):
        raise ValueError('Expected the standard OpenAI endpoint on OpenRouter')
    required = {'reasoning', 'max_tokens', 'response_format', 'structured_outputs'}
    if not required <= set(endpoint.get('supported_parameters', [])):
        raise ValueError('Endpoint lacks required parameters')
    prices = endpoint['pricing']
    allowed = {'prompt', 'completion', 'input_cache_read', 'input_cache_write', 'web_search', 'discount', 'overrides'}
    if set(prices)-allowed or shared.money(prices.get('discount', 0)) != 0:
        raise ValueError('Unaccounted or discounted endpoint pricing')
    tiers = [prices]
    for tier in prices.get('overrides', []):
        if set(tier)-allowed-{'min_prompt_tokens'}:
            raise ValueError('Unaccounted pricing override')
        if int(tier.get('min_prompt_tokens', 0)) < INPUT_CAP:
            tiers.append(tier)
    for tier in tiers:
        if max(shared.money(tier.get(k, 0)) for k in ('prompt', 'input_cache_read', 'input_cache_write')) > IP or shared.money(tier['completion']) > OP:
            raise ValueError('Endpoint price exceeds transmitted ceilings')
    if endpoint.get('context_length', 0) < INPUT_CAP+16384+256 or endpoint.get('max_completion_tokens', 0) < 16384:
        raise ValueError('Endpoint context/output capacity is too small')
    return endpoint


def fetch_endpoint():
    with request.build_opener(shared.NoRedirect).open(METADATA_URL, timeout=30) as stream:
        data = json.load(stream)
    matches = [e for e in data['data']['endpoints'] if e.get('tag') == 'openai']
    if len(matches) != 1:
        raise ValueError('Cannot resolve one standard OpenAI endpoint')
    return validate_endpoint(matches[0])


def payload(protocol, packet, output):
    old = direct_payload(protocol, packet, output)
    messages = deepcopy(old['input'])
    for message in messages:
        if isinstance(message['content'], list):
            for block in message['content']:
                block['type'] = 'text'
    schema = {k: v for k, v in old['text']['format'].items() if k != 'type'}
    return {'model': MODEL, 'messages': messages, 'max_tokens': output,
            'reasoning': {'effort': 'high'}, 'stream': False, 'tools': [], 'tool_choice': 'none',
            'plugins': [], 'service_tier': 'default',
            'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
            'response_format': {'type': 'json_schema', 'json_schema': schema},
            'provider': {'only': ['openai'], 'allow_fallbacks': False, 'require_parameters': True,
                         'max_price': {'prompt': 2.5, 'completion': 10}}}


def plan_request(protocol, packet, remaining):
    validate_endpoint(protocol['endpoint'])
    ceiling, minimum = (4096, 1024) if packet['role'] == 'planner' else (16384, 4096)
    body = payload(protocol, packet, ceiling)
    count = len(canonical(body).encode())+4096
    if count >= INPUT_CAP:
        raise ValueError('Request exceeds priced input bound')
    output = min(ceiling, int(((remaining-count*IP-Decimal('.005'))/OP).to_integral_value(rounding=ROUND_FLOOR))-256)
    if output < minimum:
        return None
    body['max_tokens'] = output
    return {'body': body, 'reserved_usd': str(count*IP+(output+256)*OP+Decimal('.005')),
            'input_token_upper_bound': count}


def normalize(raw, endpoint):
    """Keep the charged receipt and list-price estimate; debit their maximum."""
    result = deepcopy(raw) if isinstance(raw, dict) else {}
    reported = models.receipt(result)['cost_usd']
    list_cost = debit = None
    problem = None
    try:
        validate_endpoint(endpoint)
        if result.get('provider') not in ('OpenAI', 'openai') or not re.fullmatch(
                r'openai/gpt-6\.1-sol(?:-\d{8}|-\d{4}-\d{2}-\d{2})?', result.get('model', '')):
            raise ValueError('Unpriced response provider/model')
        usage = result['usage']
        if not isinstance(usage, dict):
            raise ValueError('Missing usage fields')
        def tokens(value):
            if type(value) is not int or value < 0:
                raise ValueError('Missing token usage')
            return value
        inp, out = tokens(usage.get('prompt_tokens')), tokens(usage.get('completion_tokens'))
        detail = usage['prompt_tokens_details']
        completion_detail = usage['completion_tokens_details']
        if not isinstance(detail, dict) or not isinstance(completion_detail, dict):
            raise ValueError('Missing usage fields')
        cached, written = tokens(detail.get('cached_tokens')), tokens(detail.get('cache_write_tokens'))
        reasoning = tokens(completion_detail.get('reasoning_tokens'))
        if inp >= INPUT_CAP or cached+written > inp or reasoning > out or usage.get('is_byok') is True:
            raise ValueError('Usage outside the priced scope')
        prices = endpoint['pricing']
        amount = ((inp-cached-written)*shared.money(prices['prompt'])
                  +cached*shared.money(prices['input_cache_read'])
                  +written*shared.money(prices['input_cache_write'])
                  +out*shared.money(prices['completion']))
        list_cost = str(amount)
        if reported is None:
            raise ValueError('No provider cost receipt')
        debit = str(max(shared.money(reported), amount))
    except (KeyError, TypeError, ValueError) as exc:
        problem = str(exc) if isinstance(exc, ValueError) else 'Missing usage fields'
    usage = dict(result['usage']) if isinstance(result.get('usage'), dict) else {}
    usage['cost'] = debit
    content = models.receipt(result)['content']
    choices = result.get('choices') or []
    if (not isinstance(choices, list) or not choices or not isinstance(choices[0], dict)
            or choices[0].get('finish_reason') != 'stop'):
        content = None
    return {**result, 'usage': usage, 'choices': [{'message': {'content': content}}],
            'openrouter_response': raw, 'cost_basis': 'max_provider_reported_and_list_price',
            'accounting_error': problem, 'openrouter_accounting': {
                'provider_reported_usd': reported, 'list_price_usd': list_cost, 'budget_debit_usd': debit}}


def terminal_key():
    if not sys.stdin.isatty():
        raise ValueError('Run in an interactive terminal to enter the API key securely')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            key = getpass.getpass('OpenRouter API key (hidden input): ')
        except (getpass.GetPassWarning, EOFError) as exc:
            raise ValueError('Hidden terminal input is unavailable') from exc
    if not key.startswith('sk-or-'):
        raise ValueError('Expected a regular OpenRouter inference key')
    return key


class OpenRouterTransport:
    def __init__(self, protocol, *, enabled=False, key=None):
        self.protocol, self.enabled, self._key = protocol, enabled, key

    def credentials(self):
        if not self.enabled:
            raise RuntimeError('Paid execution is disabled; --allow-paid is required')
        key = self._key
        if not key or not key.startswith('sk-or-'):
            raise ValueError('Provide a regular OpenRouter inference key through hidden terminal input')
        return key

    def __call__(self, packet, planned, timeout):
        key = self.credentials()
        body = planned['body']
        if body != payload(self.protocol, packet, body['max_tokens']):
            raise ValueError('Unexpected OpenRouter request')
        call = request.Request(ENDPOINT, data=canonical(body).encode(),
                               headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
        try:
            with request.build_opener(shared.NoRedirect).open(call, timeout=timeout) as stream:
                raw = json.load(stream)
        except (error.URLError, TimeoutError, OSError, ValueError) as exc:
            raw = {'transport_error': type(exc).__name__, 'http_status': getattr(exc, 'code', None)}
        # Never persist credentials, even if an upstream error echoes a header.
        raw = json.loads(json.dumps(raw).replace(key, '<REDACTED>'))
        return normalize(raw, self.protocol['endpoint'])
