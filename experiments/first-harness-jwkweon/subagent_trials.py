"""Manual subagent bridge for prepared local libraries; not a metered API backend.

The coordinator prepares each directory. A fresh subagent submits the configured
number of proof bodies, one at a time. Each directory owns its requests, candidates and
Lean processes. Shared compiler/library installations are read-only by policy.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import harness as h
from evaluator.lean import LeanEvaluator
from evaluator.tokens import proof_body


def now():
    return datetime.now(timezone.utc).isoformat()


def load(root):
    config = h.read(root / 'trial.json')
    if not h.positive(config.get('max_proposals', 3)):
        raise ValueError('max_proposals must be a positive integer')
    if not h.positive(config.get('lean_timeout_seconds', 180)):
        raise ValueError('lean_timeout_seconds must be a positive integer')
    if config.get('baseline_mode', 'measure') not in ('measure', 'frozen'):
        raise ValueError('baseline_mode must be measure or frozen')
    problem = h.read(root / 'input/problem.json')
    environment = {'id': 'fixed', 'project': str(root / 'project'),
        'template': (root / 'input/context.lean.in').read_text(),
        'toolchain': 'leanprover/lean4:v4.26.0',
        'command': [sys.executable, str(root / 'lean_runner.py'), '-j1', '-M4096', '-T200000'],
        'timeout_seconds': config.get('lean_timeout_seconds', 180)}
    return config, problem, environment


def baseline_result(root, config):
    """Read the original fallback, checking a frozen receipt on every use."""
    path = root / 'baseline/result.json'
    if config.get('baseline_mode', 'measure') != 'frozen':
        return h.read(path)
    expected = config.get('frozen_baseline_sha256')
    if (not isinstance(expected, str) or len(expected) != 64
            or any(c not in '0123456789abcdef' for c in expected)):
        raise ValueError('Frozen baseline requires frozen_baseline_sha256')
    try:
        if h.digest(path.read_bytes()) != expected:
            raise ValueError('result.json SHA256 mismatch')
        result = h.read(path)
        if result['valid'] is not True:
            raise ValueError('result must be valid')
        value = h.metrics(result)
        if value['raw_heartbeats'] <= 0:
            raise ValueError('baseline heartbeats must be positive')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid frozen baseline receipt: ' + str(error)) from error
    return result


def evaluate(root, code, folder):
    config, problem, environment = load(root)
    result = LeanEvaluator().evaluate(code, problem, [environment], folder, 3)
    h.write(folder / 'result.json', result)
    return result


def request_for(root, state):
    config, problem, _ = load(root)
    budget = config.get('max_proposals', 3)
    if state['step'] >= budget:
        return
    packet = {'instructions': (root / 'input/prompt.txt').read_text(),
        'problem': problem, 'baseline': state['baseline'],
        'best': {k: v for k, v in state['best'].items() if k != 'raw_samples'},
        'latest': state['latest'], 'step': state['step'] + 1, 'total_steps': budget,
        'source_access': 'Only input/source.lean in this assigned trial. Do not read other trials or past results.'}
    h.write(root / f'requests/{state["step"] + 1:03}.json', packet)


def init(root):
    config, problem, environment = load(root)
    # Validate the coordinator's receipt before creating any initialization files.
    frozen = config.get('baseline_mode', 'measure') == 'frozen'
    result = baseline_result(root, config) if frozen else None
    start = {'started_at': now(), 'environment': LeanEvaluator().fingerprint(environment),
             'mode': 'codex-subagent-manual-bridge', 'api_calls': 0, 'codex_cost_usd': None,
             'hidden_agent_context_controlled': False, 'os_isolation': False}
    h.write(root / 'start.json', start)
    if not frozen:
        result = evaluate(root, problem['reference'], root / 'baseline')
    state = h.initial_state(problem, result)
    # No fabricated zero model cost: CLI usage is not observable by this bridge.
    state.pop('cost_usd')
    state.pop('unknown_cost')
    state.update(codex_cost_usd=None, billing='unmetered_codex_subagent')
    h.write(root / 'states/000.json', state)
    request_for(root, state)
    print(json.dumps({'ready': True, 'request': str(root / 'requests/001.json')}))


def current(root):
    paths = sorted((root / 'states').glob('*.json'))
    return h.read(paths[-1])


def submit(root, response_path):
    config, problem, _ = load(root)
    baseline = h.metrics(baseline_result(root, config))
    state = current(root)
    step = state['step'] + 1
    budget = config.get('max_proposals', 3)
    if step > budget or (root / 'summary.json').exists():
        raise ValueError(f'This independent trial has already exhausted its {budget} proposals')
    response = h.read(response_path)
    raw = {'choices': [{'message': {'content': h.canonical(response)}}]}
    # The response is copied before compilation and never overwritten.
    folder = root / f'steps/{step:03}'
    h.write(folder / 'response.json', response)
    rejection, code, result = None, None, None
    try:
        code = h.parse_proof(raw, problem, 16000)
    except (ValueError, TypeError) as error:
        rejection = str(error)
    if code:
        (folder / 'candidate.lean').write_text(code)
        result = evaluate(root, code, folder / 'evaluation')
    proposal = h.candidate(code, result, baseline) if result else None
    if proposal and h.ranking(proposal) < h.ranking(state['best']):
        state['best'] = proposal
    state['step'] = step
    state['calls'] = step  # Counted proof proposals, not internal CLI model calls.
    state['latest'] = {'code': code, 'feedback': h.feedback(result, rejection, 1600, str(root))}
    if state['latest']['feedback'].get('metrics'):
        state['latest']['feedback']['metrics'].pop('raw_samples', None)
    h.write(folder / 'event.json', {'recorded_at': now(), 'state_after': state})
    h.write(root / f'states/{step:03}.json', state)
    if result and h.environment_failed(result):
        raise ValueError('Environment failed; coordinator must inspect this trial before continuing')
    request_for(root, state)
    print(json.dumps({'step': step, 'feedback': state['latest']['feedback'],
                      'best_tokens': state['best']['tokens'], 'best_raw_heartbeats': state['best']['raw_heartbeats']}, ensure_ascii=False))


def finish(root):
    config, problem, environment = load(root)
    baseline = h.metrics(baseline_result(root, config))
    state = current(root)
    budget = config.get('max_proposals', 3)
    if state['step'] != budget:
        raise ValueError(f'Exactly {budget} proposals are required before finalization')
    (root / 'selected.lean').write_text(state['best']['code'])
    final = evaluate(root, state['best']['code'], root / 'final')
    fingerprint = LeanEvaluator().fingerprint(environment)
    environment_unchanged = fingerprint == h.read(root / 'start.json')['environment']
    score = state['best']['rank_numerator'] / (2 * baseline['tokens'] * baseline['raw_heartbeats'])
    summary = {'trial_id': config['trial_id'], 'problem_id': config['problem_id'],
        'started_at': h.read(root / 'start.json')['started_at'], 'finished_at': now(),
        'status': 'completed' if final['valid'] and environment_unchanged else 'failed',
        'backend': 'codex-subagent-manual-bridge', 'proposal_count': state['step'], 'max_proposals': budget,
        'api_calls': 0, 'codex_model_calls': None, 'codex_cost_usd': None,
        'baseline': baseline, 'selected': state['best'], 'selected_local_score': score,
        'final': h.metrics(final), 'final_valid': final['valid'], 'environment_unchanged': environment_unchanged,
        'official_evaluation': False, 'os_isolation': False, 'hidden_agent_context_controlled': False}
    h.write(root / 'summary.json', summary)
    h.seal(root)
    print(json.dumps({k: v for k, v in summary.items() if k != 'selected'}, ensure_ascii=False))


def replay(root):
    files = h.read(root / 'artifacts.json')
    for name, value in files.items():
        path = root / name
        if not path.resolve().is_relative_to(root) or h.digest(path.read_bytes()) != value:
            raise ValueError('Trace hash mismatch: ' + name)
    config, problem, _ = load(root)
    result = baseline_result(root, config)
    baseline = h.metrics(result)
    state = h.initial_state(problem, result)
    state.pop('cost_usd'); state.pop('unknown_cost')
    state.update(codex_cost_usd=None, billing='unmetered_codex_subagent')
    if state != h.read(root / 'states/000.json'):
        raise ValueError('Initial state mismatch')
    for step in range(1, config.get('max_proposals', 3) + 1):
        folder = root / f'steps/{step:03}'
        response = h.read(folder / 'response.json')
        raw = {'choices': [{'message': {'content': h.canonical(response)}}]}
        rejection, code, result = None, None, None
        try:
            code = h.parse_proof(raw, problem, 16000)
        except (ValueError, TypeError) as error:
            rejection = str(error)
        if code:
            result = h.read(folder / 'evaluation/result.json')
            if (folder / 'candidate.lean').read_text() != code:
                raise ValueError('Candidate mismatch')
        proposal = h.candidate(code, result, baseline) if result else None
        if proposal and h.ranking(proposal) < h.ranking(state['best']):
            state['best'] = proposal
        state['step'] = step; state['calls'] = step
        state['latest'] = {'code': code, 'feedback': h.feedback(result, rejection, 1600, str(root))}
        if state['latest']['feedback'].get('metrics'):
            state['latest']['feedback']['metrics'].pop('raw_samples', None)
        if state != h.read(root / f'states/{step:03}.json') or state != h.read(folder / 'event.json')['state_after']:
            raise ValueError('State transition mismatch')
    summary = h.read(root / 'summary.json')
    if summary['selected'] != state['best'] or (root / 'selected.lean').read_text() != state['best']['code']:
        raise ValueError('Selection mismatch')
    print(json.dumps({'record_replay_passed': True, 'trial_id': summary['trial_id'],
                      'model_called': False, 'lean_called': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'submit', 'finish', 'replay'])
    parser.add_argument('trial', type=Path)
    parser.add_argument('--response', type=Path)
    args = parser.parse_args()
    root = args.trial.resolve()
    if args.command == 'submit':
        submit(root, args.response.resolve())
    else:
        globals()[args.command](root)


if __name__ == '__main__':
    main()
