"""Completion and cost adapters for the shared harness readers."""
from decimal import Decimal
import re

from common import canonical, inventory, read, sha, shared
from lean_agent import accounting, harness, openai_direct, recorded_usage, status


def price_card(protocol):
    if protocol['backend'] == 'fixture':
        return accounting.NO_PRICES
    if protocol['backend'] == 'openai':
        prices = protocol['pricing']
        if prices != openai_direct.PRICING:
            raise ValueError('Unrecognized direct-API price snapshot')
        rates = {key: prices[key] for key in ('input_per_million', 'output_per_million',
                                            'cached_input_per_million', 'cache_write_per_million')}
        return {'schema_version': 1, 'currency': 'USD', 'rate_card_id': sha(canonical(prices)),
                'source': prices['source'], 'as_of': prices['as_of'], 'models': {prices['model']: rates}}
    endpoint = protocol['endpoint']
    prices = endpoint['pricing']
    rates = {dest: str(Decimal(prices[src])*1000000) for src, dest in
             [('prompt', 'input_per_million'), ('completion', 'output_per_million'),
              ('input_cache_read', 'cached_input_per_million'), ('input_cache_write', 'cache_write_per_million')]}
    model = endpoint['model_id']
    aliases = {model, *re.findall(re.escape(model)+r'-\d{8}\b', endpoint.get('name', ''))}
    for alias in list(aliases):
        match = re.fullmatch(re.escape(model)+r'-(\d{4})(\d{2})(\d{2})', alias)
        if match:
            aliases.add(model+'-'+'-'.join(match.groups()))
    return {'schema_version': 1, 'currency': 'USD', 'rate_card_id': sha(canonical(endpoint)),
            'source': 'Frozen OpenRouter standard endpoint metadata', 'as_of': '2026-11-01',
            'models': {alias: rates for alias in sorted(aliases)}}


def usage_inputs(root, protocol, *, suite=False):
    source = {'schema_version': 1, 'layout': 'role-suite-v1' if suite else 'role-calls-v1',
              'backend': protocol['backend'], 'budget_usd': protocol['suite_budget_usd'] if suite else protocol['run_budget_usd']}
    source.update({'runs': ['runs/'+row[0] for row in protocol['condition_order']]} if suite else
                  {'run_id': protocol['run_id']})
    return {'usage-source.json': source, 'input/usage-prices.json': price_card(protocol)}


def record(root, relative, value, replay=False):
    path = root/relative
    if replay:
        if read(path) != value:
            raise ValueError('Recorded request, receipt or input differs: '+relative)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        shared.atomic(path, value)


def reconcile(rt, *, prefix=False):
    entries = rt.own_entries()
    report = recorded_usage.report(rt.root, max_calls=len(entries)) if prefix else accounting.native_report(rt.root)
    if len(entries) != len(report['budget_entries']):
        raise ValueError('Cost report call count differs from ledger')
    for guard in report['budget_entries']:
        saved = rt.ledger['attempts'][guard['call_id']]
        if saved['role'] != guard['role'] or saved['status'] != guard['status']:
            raise ValueError('Cost report role/status differs from ledger')
        for key in ('reserved_usd', 'cost_usd'):
            lhs, rhs = guard[key], saved[key]
            if (lhs is None) != (rhs is None) or lhs is not None and Decimal(lhs) != Decimal(rhs):
                raise ValueError('Cost report amount differs from ledger')
    return report


def save_execution(rt, result):
    shared.atomic(rt.root/'summary.json', result)
    if result.get('selected_code'):
        (rt.root/'selected.lean').write_text(result['selected_code'])
    shared.atomic(rt.root/'usage-cost.json', reconcile(rt))


def verify_execution(rt, result):
    rt.tape.assert_complete()
    if result != read(rt.root/'summary.json'):
        raise ValueError('Run replay differs: '+rt.protocol['run_id'])
    if result.get('selected_code') and (rt.root/'selected.lean').read_text() != result['selected_code']:
        raise ValueError('Selected source differs from replay')
    if reconcile(rt) != read(rt.root/'usage-cost.json'):
        raise ValueError('Usage/cost report differs from original receipts')


def lifecycle(result):
    return {**result, 'replay': {'record_replay_passed': True, 'usage_cost_replay_passed': True,
                               'model_called': False, 'lean_called': False,
                               'selected_sha256': result.get('selected_sha256')}}


def seal_execution(rt, result):
    # Called only after the whole suite has passed record replay.
    stage = rt.tape.journal.start('replay', {})
    rt.tape.journal.finish(stage, 'passed', ['summary.json', 'usage-cost.json'])
    shared.atomic(rt.root/'result.json', lifecycle(result))
    rt.tape.journal.seal(result['status'])
    harness.seal(rt.root)


def verify_seal(rt, result):
    harness.check_artifacts(rt.root)
    if read(rt.root/'result.json') != lifecycle(result):
        raise ValueError('Lifecycle differs from replay')
    view = status.inspect(rt.root)
    if not view['sealed'] or view['record_error'] or view.get('usage_cost_error'):
        raise ValueError('Unsealed or inconsistent status/cost records')
    if result['status'] == 'completed' and result.get('final_valid'):
        if not view['final_result'] or view['final_result']['sha256'] != result['selected_sha256']:
            raise ValueError('Final source is not confirmed by the shared status reader')
