"""Read role-based request receipts with the shared accounting calculator.

No model calls or experiment imports. Provider charges, price estimates and
reservation debits stay separate. An absent response is an incomplete request.
"""
from copy import deepcopy
from decimal import Decimal
import re

from . import accounting as a, models
from .artifacts import read, sha


def safe(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Usage source escapes run directory')
    return path


def total(values):
    return None if any(v is None for v in values) else str(sum((a.money(v) for v in values), Decimal(0)))


def report(root, *, max_calls=None):
    source = read(safe(root, 'usage-source.json'))
    if source.get('schema_version') != 1 or source.get('layout') not in ('role-calls-v1', 'role-suite-v1'):
        raise ValueError('Unsupported usage source')
    backend = source['backend']
    if backend not in ('openrouter', 'openai', 'fixture'):
        raise ValueError('Unsupported role usage backend')
    prices = read(safe(root, 'input/usage-prices.json'))
    a.validate_prices(prices)
    receipts, guards, sources = [], [], []

    def evidence(path):
        sources.append({'path': str(path.relative_to(root)), 'sha256': sha(path.read_bytes())})

    evidence(root/'usage-source.json')
    evidence(root/'input/usage-prices.json')
    if source['layout'] == 'role-suite-v1':
        for relative in source['runs']:
            child = safe(root, relative)
            if not child.exists():
                continue
            value = report(child)
            if value['backend'] != backend or value['price_snapshot'] != prices:
                raise ValueError('Run usage differs from suite settings')
            receipts.extend(value['receipts'])
            guards.extend(value['budget_entries'])
            sources.extend({**row, 'path': relative+'/'+row['path']} for row in value['input_files'])
    else:
        folders = sorted((root/'calls').glob('[0-9]*'))
        if max_calls is not None:
            if type(max_calls) is not int or not 0 <= max_calls <= len(folders):
                raise ValueError('Invalid recorded call prefix')
            folders = folders[:max_calls]
        for index, folder in enumerate(folders, 1):
            if folder.name != f'{index:04d}':
                raise ValueError('Role call sequence differs')
            req_path = safe(root, str(folder.relative_to(root)/'request.json'))
            req = read(req_path)
            evidence(req_path)
            role, call_id = req['role'], req['call_id']
            if role not in ('planner', 'root', 'repair') or call_id != source['run_id']+f'/call-{index:03}':
                raise ValueError('Invalid role call identity')
            reserved = str(a.money(req['reserved_usd']))
            response_path = safe(root, str(folder.relative_to(root)/'response.json'))
            response = read(response_path) if response_path.exists() else None
            if response is not None:
                evidence(response_path)
            original = (response.get('openrouter_response' if backend == 'openrouter' else 'openai_response', {})
                        if backend != 'fixture' and response is not None else response)
            original = original if isinstance(original, dict) else {}
            actual = deepcopy(original)
            if backend == 'openai' and re.fullmatch(r'gpt-6\.1-sol(?:-\d{4}-\d{2}-\d{2})?', str(actual.get('model', ''))):
                # Same model-family price policy as main's direct adapter. Keep
                # the provider's exact snapshot below and in the raw receipt.
                actual['model'] = 'gpt-6.1-sol'
            if backend == 'fixture':
                # Scripted costs exercise the budget but are never API charges.
                actual = {**actual, 'usage': {'cost': '0'}, 'model': 'fixture-v1'}
            event = {'run_id': source['run_id'], 'agent_id': role, 'event_id': call_id,
                     'model': actual.get('model') or req['model'], 'usage_scope': 'exclusive_delta',
                     'status': 'incomplete' if response is None else 'failed' if original.get('error') or original.get('transport_error') else 'completed',
                     'response': actual}
            receipt = a.make_receipt(event, 'api', prices)
            if backend == 'openai':
                receipt['provider_model'] = original.get('model')
            receipts.append(receipt)
            if backend == 'fixture':
                debit = models.receipt(response)['cost_usd']
            else:
                usage = receipt['usage']
                complete = usage is not None and all(usage[k] is not None for k in
                    ('input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_write_tokens', 'reasoning_tokens'))
                billed, estimated = receipt['reported_cost_usd'], receipt['estimated_token_cost_usd']
                priced = complete and estimated is not None and response is not None and not response.get('accounting_error')
                debit = (estimated if priced else None) if backend == 'openai' else (
                    str(max(a.money(billed), a.money(estimated))) if priced and billed is not None else None)
                if response is not None and models.receipt(response)['cost_usd'] != debit:
                    # Decimal strings may have different trailing zeroes.
                    saved = models.receipt(response)['cost_usd']
                    if saved is None or debit is None or a.money(saved) != a.money(debit):
                        raise ValueError('Recorded budget debit differs from original receipt')
            state = 'reserved' if response is None else 'uncertain' if debit is None else 'bound_violated' if a.money(debit) > a.money(reserved) else 'settled'
            guards.append({'run_id': source['run_id'], 'call_id': call_id, 'role': role,
                           'reserved_usd': reserved, 'cost_usd': debit, 'status': state})

    summary = a.summarize(receipts, allow_empty=True)
    debits = [row['cost_usd'] for row in guards]
    unsettled = sum(row['status'] != 'settled' for row in guards)
    known = str(sum((a.money(v) for v in debits if v is not None), Decimal(0)))
    summary.update(actual_api_calls=len(receipts) if backend != 'fixture' else 0,
                   actual_api_cost_usd=summary['reported_cost_usd'] if backend == 'openrouter' else None if backend == 'openai' and receipts else '0',
                   estimated_api_cost_usd=total(debits) if backend == 'openai' else None,
                   budget_debit_usd=total(debits), budget_known_subtotal_usd=known,
                   reserved_usd=total([row['reserved_usd'] for row in guards]), unsettled_calls=unsettled,
                   budget_limit_usd=source['budget_usd'],
                   remaining_guard_usd=None if unsettled else str(max(Decimal(0), a.money(source['budget_usd'])-a.money(known))),
                   simulated_cost_usd=total(debits) if backend == 'fixture' else None)
    result = {'schema_version': 1, 'calculator': a.VERSION, 'backend': backend, 'price_snapshot': prices,
              'summary': summary, 'receipts': receipts, 'budget_entries': guards,
              'scope': 'role_requests; fixture budget debits are simulated; reservations are not charges',
              'input_files': sources, 'input_sha256': a.digest(sources)}
    result['by_agent_id'] = {role: a.summarize([r for r in receipts if r['agent_id'] == role], allow_empty=True)
                             for role in ('planner', 'root', 'repair')}
    result['by_model'] = {model: a.summarize([r for r in receipts if r['model'] == model])
                          for model in sorted({r['model'] for r in receipts})}
    return result
