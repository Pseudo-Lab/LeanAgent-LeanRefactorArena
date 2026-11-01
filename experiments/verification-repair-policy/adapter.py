"""Offline experiment hooks for the existing budget runner.

The fixture transport is the only dispatch path exposed by this experiment.
Compiler evaluation, proof parsing, receipt parsing, and reservation arithmetic
remain the repository implementations. Simulated dollars are never API spend.
"""
from copy import deepcopy
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
from lean_agent import diagnostics, harness, models, status
from lean_agent.artifacts import canonical, inventory, read, sha, write
import policy
import prompts


def load_runner():
    spec = importlib.util.spec_from_file_location(
        'repair_budget_runner', REPO / 'experiments/openrouter-budget-trial/run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score(feedback, baseline):
    if not feedback['valid']:
        return None
    return feedback['tokens'] / baseline['tokens'] + feedback['raw_hb'] / baseline['raw_hb']


def observation(folder, label, problem, raw, unsettled=False):
    code, rejection = None, None
    try:
        code = harness.parse_proof(raw, problem, 60000)
    except ValueError as exc:
        rejection = str(exc)
    report = diagnostics.response(raw, rejection, folder / (label + '-response.json'), folder)
    if unsettled:
        report = report or diagnostics.diagnosis('model', 'unknown', 'unsettled_receipt')
        kind = report['kind'] if report['kind'] in policy.FATAL else 'unknown'
        code = None
    elif code is not None:
        result = read(folder / (label + '-result.json'))
        report = diagnostics.evaluation(result, folder / label, folder, 'candidate')
        kind = policy.classify(report)
        if (folder / (label + '.lean')).read_text() != code:
            raise ValueError('Candidate differs from saved model response')
    else:
        kind = policy.classify(report)
    return {'label': label, 'policy_state': kind, 'candidate_sha256': sha(code) if code else None,
            'code': code, 'goals': None, 'local_context': None,
            'native_goals_collected': False, 'diagnostic': report}


def decorate(packet, decision, tracker, root):
    packet = deepcopy(packet)
    latest = tracker['latest']
    if latest:
        packet['latest'] = {**(packet['latest'] or {}), 'code': latest['code'],
                            'policy_state': latest['policy_state'], 'goals': None,
                            'local_context': None,
                            'diagnostic': latest['diagnostic']['excerpt'][:2200]}
    code = (latest['code'] if decision['action'] == 'repair_current' else packet['best']['code'])
    if sha(code) != decision['base_candidate_sha256']:
        raise ValueError('Decision base is not the actual request base')
    packet['control'] = prompts.control(decision, code)
    # Local output paths are not experimental treatments or model information.
    import json
    return json.loads(canonical(packet).replace(str(root), '<RUN>'))


def validate_feedback(folder, label):
    fb = read(folder / (label + '-feedback.json'))
    result = read(folder / (label + '-result.json'))
    metrics = harness.metrics(result)
    if (fb['valid'] != result['valid'] or fb['tokens'] != result['tokens']
            or fb['raw_hb'] != (metrics['raw_heartbeats'] if metrics else None)):
        raise ValueError('Feedback differs from recorded evaluation')
    return fb


def verify_code(root):
    for archived in (root / 'code/repo').rglob('*.py'):
        source = REPO / archived.relative_to(root / 'code/repo')
        if not source.is_file() or sha(source.read_bytes()) != sha(archived.read_bytes()):
            raise ValueError('Execution code changed; use a fresh run or the archived replay command')


def replay_messages(inp, base, best, latest, history, codes, tracker, decision, step, total, cap, marker):
    packet = {'problem': inp['problem'], 'context': inp['context'], 'step': step,
              'budget': {'cap_usd': str(cap), 'spent_usd': str(total), 'remaining_usd': str(cap-total)},
              'baseline': base, 'best': best, 'latest': latest, 'history': history,
              'recent_candidates': [{'label': k, 'code': v} for k, v in list(codes.items())[-3:]], 'profiles': []}
    return [{'role': 'system', 'content': inp['instructions']},
            {'role': 'user', 'content': canonical(decorate(packet, decision, tracker, marker))}]


class Experiment:
    profiling_enabled = False  # frozen for fixture checks, not a paid comparison

    def __init__(self, runner, root, protocol):
        self.runner, self.root, self.protocol = runner, root, protocol
        self.pid = protocol['order'][0]
        self.folder = root / self.pid
        self.policy = protocol['repair_policy']
        self.max_calls = protocol['max_calls_safety_fuse']
        self.progress = status.Progress(status.Journal(self.folder))
        self.responses = read(root / 'fixture-responses.json')
        self.stop_recorded = False
        self.last_record = None

    def evaluate(self, folder, label, code, problem, env):
        stage = 'baseline' if label == 'baseline' else 'final' if label.startswith('final') else 'candidate'
        source = folder / (label + '.lean')
        if not source.exists():
            source.write_text(code)
        self.progress.enter(stage, label=label)
        fb = self.runner.evaluate(folder, label, code, problem, env)
        result = read(folder / (label + '-result.json'))
        report = diagnostics.evaluation(result, folder / label, folder, stage)
        self.runner.save(folder / (label + '-diagnostic.json'), report)
        candidate = {'sha256': sha(code), 'source': source.name, 'stage': stage} if fb['valid'] else None
        self.progress.finish('passed' if fb['valid'] else 'failed',
                             paths=[label + '-result.json', label + '-diagnostic.json'], candidate=candidate)
        return fb

    def start(self, base, problem, env):
        self.base, self.problem, self.env = base, problem, env
        self.tracker = policy.initial(sha(problem['original']))

    def baseline_failed(self, baseline):
        result = {'status': 'failed', 'stop_reason': 'baseline', 'baseline': baseline,
                  'final_valid': False, 'final_q': None, 'selected_origin': None,
                  'calls': 0, 'actual_api_calls': 0, 'actual_api_cost_usd': '0'}
        self.runner.save(self.folder / 'summary.json', result)
        self.runner.save(self.folder / 'result.json', result)
        return result

    def decide(self, step, best, total, ledger):
        global_used = sum((Decimal(v['cost_usd']) if v['status'] == 'settled'
                           else Decimal(v['reserved_usd']) for v in ledger['attempts'].values()), Decimal(0))
        stop = ('call_limit' if step > self.max_calls else 'budget_limit'
                if total >= self.runner.CAP or global_used >= self.runner.TOTAL_CAP else None)
        self.snapshot = {'step': step, 'state': deepcopy(self.tracker),
                         'best_sha256': sha(best['code']), 'spent_usd': str(total),
                         'global_used_usd': str(global_used), 'stop_reason': stop}
        decision = policy.decide(self.policy, self.tracker, sha(best['code']), stop_reason=stop)
        if decision['action'] == 'stop':
            self.record_stop(decision)
        return decision

    def record_stop(self, decision):
        self.runner.save(self.folder / 'stop-decision.json', {'snapshot': self.snapshot, 'decision': decision})
        self.stop_recorded = True

    def stop_before_dispatch(self, reason):
        self.snapshot['stop_reason'] = reason
        self.record_stop(policy.decide(self.policy, self.tracker,
                                      self.snapshot['best_sha256'], stop_reason=reason))

    def packet(self, packet, decision, codes):
        return decorate(packet, decision, self.tracker, self.protocol['path_normalization_root'])

    def endpoint(self):
        data = read(self.root / 'fixture-endpoints.json')
        return data, next(e for e in data['data']['endpoints'] if e['tag'] == 'openai')

    def before_dispatch(self, label, body, decision, reserved, bound):
        record = {'schema_version': 1, 'run_id': self.protocol['run_id'],
                  'problem_id': self.pid, 'attempt_id': label,
                  'policy_id': self.policy, 'policy_revision': policy.REVISION,
                  'classifier_revision': policy.CLASSIFIER_REVISION,
                  'snapshot': deepcopy(self.snapshot), 'decision': decision,
                  'request_sha256': sha(canonical(body)),
                  'reserved_usd': str(reserved), 'input_token_bound': bound,
                  'cost_basis': 'simulated_fixture',
                  'prompt_manifest_sha256': sha((self.root / 'prompt-manifest.json').read_bytes())}
        path = self.folder / (label + '-decision.json')
        if path.exists():
            raise ValueError('Never overwrite an existing decision')
        self.runner.save(path, record)
        self.last_record = record
        self.progress.enter('model', attempt=label, transport='fixture')
        self.progress.calls += 1

    def query(self, body, step):
        # Decision and request must be durable before even a fixture dispatch.
        label = f'attempt-{step:03}'
        record = read(self.folder / (label + '-decision.json'))
        if record['request_sha256'] != sha(canonical(body)):
            raise ValueError('Request changed after decision was saved')
        raw = deepcopy(self.responses[step - 1])
        raw['cost_basis'] = 'simulated_fixture'
        return raw

    def received(self, label, entry):
        self.progress.finish('passed' if entry['status'] == 'settled' else 'failed',
                             paths=[label + '-request.json', label + '-response.json', label + '-decision.json'])

    def observe(self, label, raw, code, feedback, best, rejection):
        entry = read(self.root / 'budget.json')['attempts'][self.pid + '/' + label]
        obs = observation(self.folder, label, self.problem, raw, entry['status'] != 'settled')
        write(self.folder / (label + '-observation.json'), obs)
        self.tracker = policy.advance(self.tracker, self.last_record['decision'], obs)

    def finish(self, best, history, stop):
        if not self.stop_recorded:
            ledger = read(self.root / 'budget.json')
            known = sum((Decimal(e['cost_usd']) for e in ledger['attempts'].values()
                         if e['cost_usd'] is not None), Decimal(0))
            self.snapshot = {'step': self.progress.calls + 1, 'state': deepcopy(self.tracker),
                             'best_sha256': sha(best['code']), 'spent_usd': str(known),
                             'global_used_usd': None, 'stop_reason': stop}
            self.record_stop(policy.decide(self.policy, self.tracker, sha(best['code']), stop_reason=stop))
        (self.folder / 'best.lean').write_text(best['code'])
        final = self.evaluate(self.folder, 'final-selected', best['code'], self.problem, self.env)
        selected, origin = best['code'], 'baseline' if sha(best['code']) == sha(self.problem['original']) else 'generated'
        final_label = 'final-selected'
        if not final['valid']:
            diagnosis = read(self.folder / 'final-selected-diagnostic.json')
            if policy.classify(diagnosis) in {'proof_error', 'incomplete', 'response_rejected'}:
                final_label = 'final-baseline'
                final = self.evaluate(self.folder, final_label, self.problem['original'], self.problem, self.env)
                selected, origin = self.problem['original'], 'baseline'
        final_q = (2 if origin == 'baseline' else score(final, self.base)) if final['valid'] else None
        entries = read(self.root / 'budget.json')['attempts']
        unknown = any(e['status'] != 'settled' for e in entries.values())
        known = sum((Decimal(e['cost_usd']) for e in entries.values() if e['cost_usd'] is not None), Decimal(0))
        summary = {'schema_version': 1, 'status': 'completed' if final['valid'] and not unknown and stop not in policy.FATAL else 'stopped',
                   'problem': self.pid, 'policy_id': self.policy, 'backend': 'fixture',
                   'actual_api_calls': 0, 'actual_api_cost_usd': '0',
                   'cost_basis': 'simulated_fixture', 'simulated_cost_usd': None if unknown else str(known),
                   'simulated_known_subtotal_usd': str(known), 'unknown_cost': unknown,
                   'calls': self.progress.calls, 'baseline': self.base, 'best': best,
                   'history': history, 'stop_reason': stop,
                   'final_valid': bool(final['valid']), 'final_label': final_label,
                   'selected_origin': origin if final['valid'] else None,
                   'selected_sha256': sha(selected) if final['valid'] else None,
                   'final_q': final_q, 'improvement': 2 - final_q if final_q is not None else None,
                   'final_measured_q': score(final, self.base)}
        if final['valid']:
            (self.folder / 'selected.lean').write_text(selected)
        self.runner.save(self.folder / 'summary.json', summary)
        self.runner.save(self.folder / 'result.json', summary)
        return summary


def replay(root, *, verify_inventory=True):
    """Verify bytes and recompute decisions, requests, billing and selection. No calls."""
    root = Path(root).resolve()
    if verify_inventory and inventory(root) != read(root / 'artifacts.json'):
        raise ValueError('Run artifacts changed or are missing')
    verify_code(root)
    protocol = read(root / 'protocol.json')
    if protocol['policy_revision'] != policy.REVISION or protocol['classifier_revision'] != policy.CLASSIFIER_REVISION:
        raise ValueError('Use the archived replay code for this revision')
    runner = load_runner()
    runner.CAP = Decimal(protocol['per_problem_usd'])
    runner.TOTAL_CAP = Decimal(protocol['total_usd'])
    runner.BACKEND = 'openrouter'
    pid = protocol['order'][0]
    folder = root / pid
    outcome = read(folder / 'result.json')
    if outcome['stop_reason'] in {'preflight', 'baseline'}:
        if read(root / 'budget.json')['attempts'] or list(folder.glob('attempt-*-request.json')):
            raise ValueError('An unverified baseline dispatched a request')
        if outcome['stop_reason'] == 'preflight':
            if read(folder / 'preflight/preflight.json')['status'] == 'passed':
                raise ValueError('Preflight failure contradicts its evidence')
        else:
            baseline = validate_feedback(folder, 'baseline')
            if baseline['valid'] and baseline['raw_hb']:
                raise ValueError('Baseline failure contradicts its evidence')
        return {'record_replay_passed': True, 'model_called': False, 'lean_called': False,
                'decisions': 0, 'final_valid': False, 'stop_reason': outcome['stop_reason']}
    inp = read(folder / 'input.json')
    problem = {**inp['problem'], 'id': pid, 'reference': inp['problem']['original']}
    base = validate_feedback(folder, 'baseline')
    best = {**base, 'code': problem['original']}
    tracker = policy.initial(sha(problem['original']))
    ledger = read(root / 'budget.json')['attempts']
    total, history, codes, latest = Decimal(0), [], {}, None
    endpoint_data = read(root / 'fixture-endpoints.json')
    endpoint = next(e for e in endpoint_data['data']['endpoints'] if e['tag'] == 'openai')
    records = sorted(folder.glob('attempt-*-decision.json'))
    for step, path in enumerate(records, 1):
        label = f'attempt-{step:03}'
        record = read(path)
        if (record['policy_id'] != protocol['repair_policy'] or record['policy_revision'] != policy.REVISION
                or record['classifier_revision'] != policy.CLASSIFIER_REVISION or record['problem_id'] != pid
                or record['run_id'] != protocol['run_id'] or record['attempt_id'] != label
                or record['prompt_manifest_sha256'] != sha((root/'prompt-manifest.json').read_bytes())):
            raise ValueError('Decision provenance differs from the frozen protocol')
        expected_snapshot = {'step': step, 'state': tracker, 'best_sha256': sha(best['code']),
                             'spent_usd': str(total), 'global_used_usd': str(total), 'stop_reason': None}
        if record['snapshot'] != expected_snapshot:
            raise ValueError('Decision snapshot does not follow previous observations')
        decision = policy.decide(protocol['repair_policy'], tracker, sha(best['code']))
        if decision != record['decision'] or decision['action'] == 'stop':
            raise ValueError('Policy decision differs on replay')
        messages = replay_messages(inp, base, best, latest, history, codes, tracker, decision,
                                   step, total, runner.CAP, protocol['path_normalization_root'])
        planned = runner.plan_request(messages, min(runner.CAP-total, runner.TOTAL_CAP-total), endpoint)
        if planned is None:
            raise ValueError('Recorded dispatch exceeded safe reservation')
        body, reserve, bound = planned
        if (body != read(folder / (label + '-request.json')) or sha(canonical(body)) != record['request_sha256']
                or record['reserved_usd'] != str(reserve) or record['input_token_bound'] != bound):
            raise ValueError('Saved request or reservation differs from replay')
        raw = read(folder / (label + '-response.json'))
        entry = ledger[pid + '/' + label]
        cost = models.receipt(raw)['cost_usd']
        settlement = 'uncertain' if cost is None else 'bound_violated' if Decimal(cost) > reserve else 'settled'
        if entry['cost_usd'] != cost or entry['status'] != settlement or entry['reserved_usd'] != str(reserve):
            raise ValueError('Receipt accounting differs from replay')
        obs = observation(folder, label, problem, raw, settlement != 'settled')
        if obs != read(folder / (label + '-observation.json')):
            raise ValueError('Observation/classifier differs from replay')
        tracker = policy.advance(tracker, decision, obs)
        if cost is not None:
            total += Decimal(cost)
        if settlement != 'settled':
            if step != len(records):
                raise ValueError('A request followed an unsettled receipt')
            break
        code = obs['code']
        fb = (validate_feedback(folder, label) if code is not None else read(folder / (label + '-feedback.json')))
        if code is not None:
            codes[label] = code
        improved = fb['valid'] and score(fb, base) < score(best, base)
        if improved:
            best = {**fb, 'code': code}
        latest = fb
        history.append({'label': label, 'valid': fb['valid'], 'tokens': fb['tokens'], 'hb_k': fb['hb_k'],
                        'objective': score(fb, base), 'cost_usd': cost, 'improved': improved,
                        'proof_sha256': sha(code) if code else None})
    summary = read(folder / 'summary.json')
    stop = read(folder / 'stop-decision.json')
    if stop['snapshot']['state'] != tracker or stop['snapshot']['best_sha256'] != sha(best['code']):
        raise ValueError('Terminal state differs from replay')
    expected_stop = policy.decide(protocol['repair_policy'], tracker, sha(best['code']),
                                 stop_reason=stop['snapshot']['stop_reason'])
    if stop['decision'] != expected_stop or expected_stop['action'] != 'stop' or summary['stop_reason'] != expected_stop['reason']:
        raise ValueError('Terminal decision differs from replay')
    if summary['best'] != best or summary['history'] != history or summary['calls'] != len(records):
        raise ValueError('Best/history/call count differs from replay')
    if set(ledger) != {pid + f'/attempt-{i:03}' for i in range(1, len(records)+1)}:
        raise ValueError('Ledger contains an unobserved or missing call')
    uncertain = any(e['status'] != 'settled' for e in ledger.values())
    if (summary['simulated_cost_usd'] != (None if uncertain else str(total))
            or summary['simulated_known_subtotal_usd'] != str(total)
            or summary['unknown_cost'] != uncertain
            or summary['actual_api_calls'] != 0 or summary['actual_api_cost_usd'] != '0'):
        raise ValueError('Final accounting differs from replay')
    if uncertain:
        terminal_reason = list(ledger.values())[-1]['status']
    elif (root / 'STOP').exists():
        terminal_reason = 'stop_requested'
    elif len(records) >= protocol['max_calls_safety_fuse']:
        terminal_reason = 'call_limit'
    elif total >= min(runner.CAP, runner.TOTAL_CAP):
        terminal_reason = 'budget_limit'
    else:
        next_decision = policy.decide(protocol['repair_policy'], tracker, sha(best['code']))
        if next_decision['action'] == 'stop':
            terminal_reason = next_decision['reason']
        else:
            messages = replay_messages(inp, base, best, latest, history, codes, tracker, next_decision,
                                       len(records)+1, total, runner.CAP, protocol['path_normalization_root'])
            try:
                remaining_plan = runner.plan_request(messages, min(runner.CAP-total, runner.TOTAL_CAP-total), endpoint)
            except ValueError as exc:
                terminal_reason = str(exc)
            else:
                if remaining_plan is not None:
                    raise ValueError('Premature termination despite an available request')
                terminal_reason = 'remaining_budget_below_safe_request_bound'
    if (expected_stop['reason'] != terminal_reason or stop['snapshot']['step'] != len(records)+1
            or stop['snapshot']['spent_usd'] != str(total)):
        raise ValueError('Termination reason or counters differ from replay')
    final = validate_feedback(folder, 'final-selected')
    final_code = best['code']
    if (folder / 'final-selected.lean').read_text() != final_code:
        raise ValueError('Final verification did not use the selected proof bytes')
    if not final['valid']:
        report = diagnostics.evaluation(read(folder / 'final-selected-result.json'), folder / 'final-selected', folder, 'final')
        if policy.classify(report) in {'proof_error', 'incomplete', 'response_rejected'}:
            final = validate_feedback(folder, 'final-baseline')
            final_code = problem['original']
            if (folder / 'final-baseline.lean').read_text() != final_code:
                raise ValueError('Fallback verification did not use original bytes')
    origin = 'baseline' if final_code == problem['original'] else 'generated'
    final_q = (2 if origin == 'baseline' else score(final, base)) if final['valid'] else None
    if (summary['final_valid'] != final['valid'] or summary['final_q'] != final_q
            or summary['final_measured_q'] != score(final, base)
            or summary['improvement'] != (2-final_q if final_q is not None else None)
            or summary['selected_origin'] != (origin if final['valid'] else None)
            or summary['selected_sha256'] != (sha(final_code) if final['valid'] else None)
            or (final['valid'] and (folder / 'selected.lean').read_text() != final_code)):
        raise ValueError('Final selection differs from replay')
    return {'record_replay_passed': True, 'model_called': False, 'lean_called': False,
            'decisions': len(records), 'final_valid': final['valid'], 'policy_id': protocol['repair_policy']}
