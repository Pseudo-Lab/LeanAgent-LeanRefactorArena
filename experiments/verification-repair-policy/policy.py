"""Pure verification-state policy. No compiler, model, clock, or filesystem calls."""
from copy import deepcopy
import re

POLICIES = ('uniform-repair-v1', 'state-aware-v1')
REVISION = 'repair-policy-1'
CLASSIFIER_REVISION = 'lean-diagnostic-1'
FATAL = {'environment', 'measurement', 'timeout', 'api', 'unknown'}
ERROR = re.compile(r'(?m)^(?:[^\n]*:\d+:\d+: )?error: ([^\n]*)')


def classify(diagnostic):
    """Use the full, evidence-checked diagnostic, before prompt truncation.

    A missing native goal collector is never evidence of an empty goal list.
    Mixed Lean errors take precedence over an unsolved-goals diagnostic.
    """
    kind, reason = diagnostic.get('kind'), diagnostic.get('reason')
    if kind is None and reason == 'verified':
        return 'valid'
    if kind in FATAL:
        return kind
    if kind == 'response':
        return 'response_rejected'
    if kind != 'proof':
        return 'unknown'
    if reason == 'disallowed_axioms':
        return 'proof_error'
    errors = ERROR.findall(diagnostic.get('excerpt', ''))
    if not errors:
        return 'unknown'
    return ('incomplete' if all(e.strip() == 'unsolved goals' for e in errors)
            else 'proof_error')


def initial(original_sha256):
    return {'latest': None, 'seen': [original_sha256], 'repair_chain_id': None,
            'repair_calls_used': 0}


def decide(policy, state, best_sha256, *, stop_reason=None):
    if policy not in POLICIES:
        raise ValueError('Unknown repair policy')
    latest = state['latest']
    kind = latest['policy_state'] if latest else 'valid'
    action, reason, base = 'optimize_best', 'valid', best_sha256
    closes = None
    if stop_reason:
        action, reason, closes = 'stop', stop_reason, stop_reason
    elif kind in FATAL:
        action, reason, closes = 'stop', kind, kind
    elif kind == 'valid':
        closes = 'valid' if state['repair_chain_id'] else None
    elif kind == 'response_rejected':
        reason, closes = 'response_rejected', 'response_rejected'
    elif latest['duplicate']:
        action, reason, closes = 'replan_from_best', 'duplicate', 'duplicate'
    elif state['repair_calls_used'] >= 2:
        action, reason, closes = 'replan_from_best', 'repair_limit', 'repair_limit'
    elif kind == 'incomplete' and policy == 'state-aware-v1':
        action, reason, closes = 'replan_from_best', 'incomplete', 'incomplete'
    elif kind in {'proof_error', 'incomplete'}:
        action, reason, base = 'repair_current', kind, latest['candidate_sha256']
    else:
        action, reason, closes = 'stop', 'unknown', 'unknown'
    return {'action': action, 'base_candidate_sha256': base, 'reason': reason,
            'repair_chain_id': state['repair_chain_id'],
            'repair_calls_used': state['repair_calls_used'],
            'repair_chain_stop_reason': closes}


def advance(state, decision, observation):
    """Charge a repair dispatch even when its response is rejected or invalid."""
    state = deepcopy(state)
    if decision['action'] == 'repair_current':
        state['repair_calls_used'] += 1
    else:
        state['repair_chain_id'] = None
        state['repair_calls_used'] = 0
    digest = observation['candidate_sha256']
    duplicate = digest is not None and digest in state['seen']
    if digest and not duplicate:
        state['seen'].append(digest)
    if (observation['policy_state'] in {'proof_error', 'incomplete'}
            and state['repair_chain_id'] is None):
        state['repair_chain_id'] = observation['label']
    state['latest'] = {**observation, 'duplicate': duplicate}
    return state
