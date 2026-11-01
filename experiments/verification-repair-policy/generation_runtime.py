"""One shared suite ledger for Planner, root Worker and recursive Worker calls."""
from copy import deepcopy
from decimal import Decimal
import time

from common import Stop, canonical, shared, sha
from generation_transport import plan_request
from openrouter_transport import plan_request as router_plan
from runtime import Runtime


class GenerationRuntime(Runtime):
    def __init__(self, root, protocol, ledger, transport=None, *, budget_path=None,
                 libraries=None, replay=False):
        super().__init__(root, protocol, transport, replay)
        self.ledger = deepcopy(ledger)
        self.budget_path, self.libraries = budget_path, libraries
        self.finalizing = False
        self.seen = {self.candidate_key(self.problem['reference'])}
        self.final_reserve = 8 * self.limits.lean_seconds
        if self.limits.run_seconds <= self.final_reserve:
            raise ValueError('Run deadline must leave time for final check and original fallback')

    @staticmethod
    def candidate_key(code):
        # Preserve indentation, literals and comments. Only line endings and
        # trailing file whitespace are normalized; this is not semantic dedup.
        return sha(code.replace('\r\n', '\n').rstrip())

    def duplicate(self, code):
        key = self.candidate_key(code)
        duplicate = key in self.seen
        self.seen.add(key)
        self.tape.event('candidate_seen', candidate_sha256=sha(code), normalized_sha256=key, duplicate=duplicate)
        return duplicate

    def own_entries(self, role=None):
        return [value for key, value in self.ledger['attempts'].items()
                if key.startswith(self.protocol['run_id']+'/') and (role is None or value['role'] == role)]

    def cost(self, entries):
        return sum((Decimal(e['cost_usd']) for e in entries if e['cost_usd'] is not None), Decimal(0))

    def check_time(self, repair=False):
        now = super().check_time(repair)
        if not self.finalizing and now >= self.limits.run_seconds-self.final_reserve:
            raise Stop('final_verification_reserve')
        return now

    def _execute(self, command, cwd, timeout):
        if self.libraries:
            self.libraries.verify(full=False)
        left = self.limits.run_seconds-(time.monotonic()-self.epoch)
        if not self.finalizing:
            left -= self.final_reserve
        return super()._execute(command, cwd, max(0, min(timeout, left)))

    def observe(self, code):
        self.check_time()
        self._repair_operation = False
        self.lean_calls += 1
        tag = 'controller-observe-'+sha(code)[:16]
        return self.tape.call('observe', {'code': code, 'label': tag},
            lambda: self.native.inspect(code, tag, self.limits.lean_seconds, self.limits.memory_mib))

    def dispatch(self, role, request):
        if self.finalizing:
            raise Stop('final_verification_no_dispatch')
        now = self.check_time(repair=role == 'repair')
        if any(e['status'] != 'settled' for e in self.ledger['attempts'].values()):
            raise Stop('unsettled_receipt')
        own = self.own_entries()
        if len(own) >= self.limits.run_calls:
            raise Stop('run_call_limit')
        if role == 'repair' and self.repair_calls >= self.limits.repair_calls:
            raise Stop('repair_call_limit')
        control = self.protocol['controller']
        if role == 'planner' and len(self.own_entries('planner')) >= control['planner_max_calls']:
            raise Stop('planner_call_limit')
        remaining = min(Decimal(self.protocol['run_budget_usd'])-self.cost(own),
                        Decimal(self.ledger['total_usd'])-self.cost(self.ledger['attempts'].values()))
        if role == 'planner':
            remaining = min(remaining, Decimal(control['planner_budget_usd'])-self.cost(self.own_entries('planner')))
        call_id = self.protocol['run_id']+f'/call-{len(own)+1:03}'
        packet = {**request, 'role': role, 'call_id': call_id}
        if self.protocol['backend'] == 'fixture':
            planned = {'reserved_usd': '0.02', 'body': None, 'input_token_upper_bound': 0}
            if Decimal(planned['reserved_usd']) > remaining:
                planned = None
        else:
            planner = router_plan if self.protocol['backend'] == 'openrouter' else plan_request
            planned = planner(self.protocol, packet, remaining)
        if planned is None:
            self.tape.event('dispatch_blocked', role=role, remaining_usd=str(remaining))
            raise Stop('planner_budget_limit' if role == 'planner' else 'budget_limit')
        timeout = min(control['api_timeout_seconds'], self.limits.run_seconds-self.final_reserve-now)
        if role == 'repair':
            timeout = min(timeout, self.limits.repair_seconds-(now-self.repair_start))
        if timeout <= 0:
            raise Stop('generation_time_limit')
        shared.reserve(self.ledger, call_id, Decimal(planned['reserved_usd']))
        self.ledger['attempts'][call_id].update(role=role, run_id=self.protocol['run_id'])
        if role == 'repair':
            self.repair_calls += 1
            self.total_repair_calls += 1
        # Both durable records exist before any billable operation.
        self.tape.event('reserved', call_id=call_id, ledger=self.ledger)
        if not self.tape.replay:
            shared.atomic(self.budget_path or self.root/'budget.json', self.ledger)
        raw = self.tape.call('worker', {'packet': packet, 'planned': planned, 'timeout': timeout},
                             lambda: self.worker(packet, planned, timeout))
        settlement = shared.settle(self.ledger, call_id, raw)
        if self.protocol['backend'] == 'openrouter':
            self.ledger['attempts'][call_id]['accounting'] = raw.get('openrouter_accounting', {})
        self.tape.event('settled', call_id=call_id, ledger=self.ledger)
        if not self.tape.replay:
            shared.atomic(self.budget_path or self.root/'budget.json', self.ledger)
        if settlement != 'settled':
            raise Stop('unsettled_receipt')
        return raw

    def cost_summary(self):
        entries = self.own_entries()
        unknown = any(e['status'] != 'settled' for e in entries)
        cost = None if unknown else str(self.cost(entries))
        live = self.protocol['backend'] != 'fixture'
        router = self.protocol['backend'] == 'openrouter'
        charged = (None if unknown else str(sum((Decimal(e['accounting']['provider_reported_usd'])
                    for e in entries), Decimal(0)))) if router else cost
        return {**super().cost_summary(), 'dispatches': len(entries),
                'actual_api_calls': len(entries) if live else 0,
                'actual_api_cost_usd': charged if live else '0',
                'budget_debit_usd': cost,
                'simulated_cost_usd': None if live else cost,
                'simulated_known_subtotal_usd': None if live else str(self.cost(entries)),
                'cost_basis': 'provider_reported_with_list_price_budget_guard' if router else 'usage_estimate' if live else 'simulated_fixture',
                'unknown_cost': unknown, 'known_cost_usd': str(self.cost(entries)),
                'role_cost_usd': {role: str(self.cost(self.own_entries(role))) for role in ('planner', 'root', 'repair')},
                'role_calls': {role: len(self.own_entries(role)) for role in ('planner', 'root', 'repair')}}
