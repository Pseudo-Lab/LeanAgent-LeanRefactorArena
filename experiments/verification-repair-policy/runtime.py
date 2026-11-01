"""Controller-owned resources and a durable, executable observation tape."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import time

from common import Limits, Stop, canonical, read, sha, shared
from native import NativeLean
from lean_agent import harness, models, preflight, status
from lean_agent.evaluator.lean import LeanEvaluator
from lean_agent.evaluator.lean import execute


class Tape:
    def __init__(self, root, replay=False):
        self.root, self.replay, self.index = Path(root), replay, 0
        self.directory = self.root/'tape'
        self.journal = None if replay else status.Journal(self.root)
        if not replay:
            self.directory.mkdir()

    def call(self, kind, payload, operation=lambda: None):
        self.index += 1
        tag = f'{self.index:05}'
        request, response = self.directory/(tag+'-request.json'), self.directory/(tag+'-response.json')
        expected = {'kind': kind, 'input': payload}
        if self.replay:
            if read(request) != expected:
                raise ValueError('Replay decision/input differs at ' + tag + ': ' + kind)
            record = read(response)
        else:
            shared.atomic(request, expected)
            stage_name = kind
            candidate_path = None
            if kind == 'evaluate':
                label = payload['label']
                stage_name = 'baseline' if label == 'baseline' else 'final' if label.startswith('final-') else 'candidate'
                candidate_path = self.root/'candidates'/(sha(payload['code'])+'.lean')
                candidate_path.parent.mkdir(exist_ok=True)
                if not candidate_path.exists():
                    candidate_path.write_text(payload['code'])
                elif candidate_path.read_text() != payload['code']:
                    raise ValueError('Candidate evidence changed')
            stage = self.journal.start(stage_name, {'tape_id': tag, 'input_sha256': sha(canonical(payload))}) if kind != 'clock' else None
            try:
                record = {'ok': True, 'value': operation()}
            except (OSError, ValueError, RuntimeError) as exc:
                record = {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}
            shared.atomic(response, record)
            if stage:
                passed = record['ok']
                candidate = None
                evidence = [request, response]
                if candidate_path:
                    evidence.append(candidate_path)
                    passed = passed and record['value']['valid']
                    if passed:
                        candidate = {'sha256': sha(payload['code']), 'source': str(candidate_path.relative_to(self.root))}
                self.journal.finish(stage, 'passed' if passed else 'failed', evidence, candidate=candidate)
        if not record['ok']:
            raise RuntimeError(record['error'])
        return deepcopy(record['value'])

    def event(self, kind, **value):
        self.call(kind, value)

    def assert_complete(self):
        if len(list(self.directory.glob('*-request.json'))) != self.index:
            raise ValueError('Unconsumed observations remain in replay')


def envelope(proof, cost='0.01'):
    return {'choices': [{'message': {'content': canonical({'proof': proof})}}],
            'usage': {} if cost is None else {'cost': cost}, 'cost_basis': 'simulated_fixture'}


class FixtureWorker:
    """An explicit offline transport, not an implementation of #37's Planner."""
    def __init__(self, case):
        self.case, self.index = case, 0

    def __call__(self, request):
        if request['role'] == 'root':
            return envelope(self.case['candidate'], self.case.get('root_cost', '0.01'))
        rows = self.case.get('responses', [])
        if self.index >= len(rows):
            raise ValueError('Fixture exhausted; no model fallback')
        row = rows[self.index]
        self.index += 1
        if 'target_contains' in row and row['target_contains'] not in request['goal']['target']:
            raise ValueError('Fixture response assigned to wrong native goal')
        return row.get('raw') or envelope(row['proof'], row.get('cost', '0.01'))


class Runtime:
    """One run owns the clock, shared budget, worker and duplicate set.

    A future #37 adapter supplies its worker and controller-owned state here.
    The public CLI supplies only FixtureWorker; no paid transport is exposed.
    """
    def __init__(self, root, protocol, worker=None, replay=False):
        self.root, self.protocol = Path(root), protocol
        self.limits = Limits(**protocol['limits'])
        self.tape = Tape(root, replay)
        self.epoch = time.monotonic()
        self.worker = worker
        self.problem, self.environment = protocol['problem'], protocol['environment']
        self.native = NativeLean(self.environment, self.problem, self.root/'native', invoke=self._execute) if not replay else None
        self.ledger = {'per_trial_usd': protocol['simulated_reservation_usd'],
                       'total_usd': protocol['simulated_budget_usd'], 'max_trials': self.limits.run_calls, 'attempts': {}}
        self.seen = {sha(self.problem['reference'])}
        self.lean_calls = 0
        self.repair_lean_calls = 0
        self.repair_calls = 0
        self.nodes = 0
        self.repair_start = None
        self.repair_serial = 0
        self.total_repair_calls = 0
        self.total_inspections = 0
        self.total_repair_evaluations = 0
        self._repair_operation = False
        self.preflight_commands = 0
        self.preflight_compilations = 0

    def preflight(self):
        self._repair_operation = False
        result = self.tape.call('preflight', {'environment': self.environment},
            lambda: preflight.check(self.environment, self.root/'preflight', LeanEvaluator(executor=self._execute)))
        self.preflight_commands += result['compiler_invocations']
        self.preflight_compilations += result['context_compilations']
        self.lean_calls += result['context_compilations']
        return result

    def availability(self):
        self.check_time()
        self._repair_operation = False
        result = self.tape.call('availability', {'tactics': self.protocol['tactics']},
            lambda: self.native.availability(self.protocol['tactics'], self.limits.lean_seconds, self.limits.memory_mib))
        self.lean_calls += 1
        return [r['tactic'] for r in result if r['available']]

    def now(self):
        return self.tape.call('clock', {}, lambda: round(time.monotonic() - self.epoch, 6))

    def check_time(self, repair=False):
        now = self.now()
        if now >= self.limits.run_seconds:
            raise Stop('run_time_limit')
        if repair and self.repair_start is not None and now - self.repair_start >= self.limits.repair_seconds:
            raise Stop('repair_time_limit')
        return now

    def _execute(self, command, cwd, timeout):
        # Evaluator may start several processes; each gets the remaining deadline.
        left = self.limits.run_seconds - (time.monotonic() - self.epoch)
        if self._repair_operation and self.repair_start is not None:
            left = min(left, self.limits.repair_seconds - (time.monotonic() - self.epoch - self.repair_start))
        if left <= 0:
            return {'command': command, 'returncode': -1, 'timed_out': True, 'seconds': 0,
                    'output': 'Controller deadline reached before subprocess', 'stderr': ''}
        return execute(command, cwd, min(timeout, left))

    def inspect(self, code):
        self.check_time(repair=True)
        if self.repair_lean_calls >= self.limits.lean_calls:
            raise Stop('lean_call_limit')
        self.repair_lean_calls += 1
        self.lean_calls += 1
        self.total_inspections += 1
        tag = f'inspect-{self.total_inspections:04}'
        payload = {'code': code, 'label': tag, 'timeout': self.limits.lean_seconds, 'memory': self.limits.memory_mib}
        self._repair_operation = True
        report = self.tape.call('inspect', payload, lambda: self.native.inspect(code, tag, self.limits.lean_seconds, self.limits.memory_mib))
        if report['kind'] == 'timeout':
            raise Stop('lean_timeout')
        return report

    def evaluate(self, code, label, repair=False):
        self.check_time(repair=repair)
        # Reserve enough room for the complete shared evaluation before starting
        # it; failed checks can use fewer processes, never more than this bound.
        if repair and self.repair_lean_calls + NativeLean.evaluation_processes > self.limits.lean_calls:
            raise Stop('lean_call_limit')
        self._repair_operation = repair
        result = self.tape.call('evaluate', {'code': code, 'label': label, 'repair': repair},
                                lambda: self.native.evaluate(code, label, self.limits.lean_seconds, self.limits.memory_mib))
        calls = sum(len(e['runs']) for e in result['environments'].values())
        self.lean_calls += calls
        if repair:
            self.repair_lean_calls += calls
            self.total_repair_evaluations += calls
        return result

    def dispatch(self, role, request):
        self.check_time(repair=role == 'repair')
        if role == 'repair' and self.repair_calls >= self.limits.repair_calls:
            raise Stop('repair_call_limit')
        call_id = f'call-{len(self.ledger["attempts"])+1:03}'
        bound = Decimal(self.protocol['simulated_reservation_usd'])
        try:
            shared.reserve(self.ledger, call_id, bound)
        except ValueError as exc:
            self.tape.event('dispatch_blocked', role=role, reason=str(exc))
            raise Stop('budget_or_call_limit') from exc
        if role == 'repair':
            self.repair_calls += 1
            self.total_repair_calls += 1
        self.tape.event('reserved', call_id=call_id, role=role, ledger=self.ledger)
        if not self.tape.replay:
            shared.atomic(self.root/'budget.json', self.ledger)
        packet = {**request, 'role': role, 'call_id': call_id}
        raw = self.tape.call('worker', packet, lambda: self.worker(packet))
        settlement = shared.settle(self.ledger, call_id, raw)
        self.tape.event('settled', call_id=call_id, ledger=self.ledger)
        if not self.tape.replay:
            shared.atomic(self.root/'budget.json', self.ledger)
        if settlement != 'settled':
            raise Stop('unsettled_receipt')
        return raw

    def duplicate(self, code):
        key = sha(code.replace('\r\n', '\n'))
        duplicate = key in self.seen
        self.seen.add(key)
        self.tape.event('candidate_seen', candidate_sha256=key, duplicate=duplicate)
        return duplicate

    def cost_summary(self):
        entries = list(self.ledger['attempts'].values())
        known = sum((Decimal(e['cost_usd']) for e in entries if e['cost_usd'] is not None), Decimal(0))
        unknown = any(e['status'] != 'settled' for e in entries)
        return {'actual_api_calls': 0, 'actual_api_cost_usd': '0', 'cost_basis': 'simulated_fixture',
                'simulated_cost_usd': None if unknown else str(known), 'simulated_known_subtotal_usd': str(known),
                'unknown_cost': unknown, 'dispatches': len(entries), 'repair_dispatches': self.total_repair_calls,
                'lean_calls': self.lean_calls,
                'repair_lean_calls': self.total_inspections + self.total_repair_evaluations,
                'compiler_commands': self.lean_calls + self.preflight_commands - self.preflight_compilations}
