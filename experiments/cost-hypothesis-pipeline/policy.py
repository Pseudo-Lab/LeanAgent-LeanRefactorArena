"""Pure request/state policy. No Lean, network, filesystem or model calls."""
from copy import deepcopy
import re

import harness as h

FAMILIES = ('structure', 'evidence', 'representation', 'sharing', 'compression', 'repair')


def initial(problem, result):
    state = h.initial_state(problem, result)
    state.pop('cost_usd'); state.pop('unknown_cost')
    state.update(registry={state['best']['sha256']: state['best']}, attempts=[], parents={})
    return state


def parse(response, problem, mode, state):
    if not isinstance(response, dict):
        raise ValueError('Response must be an object')
    required = {'proof'} if mode == 'A' else {'proof', 'hypothesis'}
    if set(response) != required:
        raise ValueError('Expected exactly fields: ' + ', '.join(sorted(required)))
    card = None
    if mode == 'B':
        card = response['hypothesis']
        if not isinstance(card, dict) or set(card) != {'parent','family','target','change','expected_saving'}:
            raise ValueError('Invalid hypothesis fields')
        if any(not isinstance(v, str) or not v.strip() or len(v) > 800 for v in card.values()):
            raise ValueError('Hypothesis fields must be nonempty bounded strings')
        if card['family'] not in FAMILIES:
            raise ValueError('Unknown hypothesis family')
        known = {'original', *state['registry']}
        known.update(a['sha256'] for a in state['attempts'] if a['sha256'])
        if card['parent'] not in known:
            raise ValueError('Unknown parent')
    raw = {'choices':[{'message':{'content':h.canonical({'proof':response['proof']})}}]}
    return h.parse_proof(raw, problem, 16000), card


def frontier(registry):
    values = list(registry.values())
    return sorted([a for a in values if not any(
        b['tokens'] <= a['tokens'] and b['raw_heartbeats'] <= a['raw_heartbeats'] and
        (b['tokens'] < a['tokens'] or b['raw_heartbeats'] < a['raw_heartbeats'])
        for b in values)], key=h.ranking)


def transition(state, code, card, result, feedback):
    state = deepcopy(state)
    previous = state['best']
    proposal = h.candidate(code, result, state['baseline']) if result else None
    digest = h.digest(code) if code else None
    # All duplicate proposals count; never let remeasurement noise rewrite an
    # already registered declaration's selection metric.
    duplicate = digest in state['registry'] or any(a['sha256'] == digest for a in state['attempts']) if digest else False
    if proposal and digest not in state['registry']:
        state['registry'][digest] = proposal
        if h.ranking(proposal) < h.ranking(state['best']):
            state['best'] = proposal
    if proposal and card:
        family = card['family']; old = state['parents'].get(family)
        registered = state['registry'][digest]
        if old is None or h.ranking(registered) < h.ranking(state['registry'][old]):
            state['parents'][family] = digest
    state['step'] += 1; state['calls'] += 1
    state['latest'] = {'code':code, 'feedback':feedback}
    state['attempts'].append({'step':state['step'], 'sha256':digest,
        'valid':bool(proposal), 'hypothesis':card, 'duplicate':duplicate,
        'metrics':h.metrics(result) if proposal else None,
        'best_improved':h.ranking(state['best']) < h.ranking(previous)})
    return state


def compact(candidate):
    return {k:v for k,v in candidate.items() if k != 'raw_samples'}


def packet(state, problem, prompt, mode, budget):
    result = {'instructions':prompt, 'problem':problem, 'baseline':state['baseline'],
        'best':compact(state['best']), 'latest':state['latest'],
        'step':state['step']+1, 'total_steps':budget,
        'source_access':'Only this trial input/source.lean, requests and responses; no other trials or archives.'}
    if mode == 'A':
        return result
    b, original = state['best'], state['baseline']
    length, heartbeat = b['tokens']/original['tokens'], b['raw_heartbeats']/original['raw_heartbeats']
    step = state['step'] + 1
    stage = 'structural_route' if step <= 2 else 'remove_repeated_or_inferred_work' if step <= 4 else 'consolidate_and_compress'
    if state['latest'] and not state['latest']['feedback']['valid']:
        stage = 'repair_or_abandon_failed_hypothesis'
    source = problem['reference']
    selected = {x['sha256']:x for x in frontier(state['registry'])[:3]}
    for key in [state['parents'][family] for family in sorted(state['parents'])][-3:]:
        selected[key] = state['registry'][key]
    selected.pop(b['sha256'], None)
    result['pipeline'] = {'stage':stage, 'residual_ratios':{'length':length,'heartbeat':heartbeat},
        'larger_score_component':'length' if length >= heartbeat else 'heartbeat',
        'syntax_inventory_not_profile':{word:len(re.findall(r'\b'+word+r'\b',source)) for word in ['grind','simp','omega','ring','have','let','set','cases','induction']},
        'family_parents':state['parents'], 'alternatives':[compact(x) for x in list(selected.values())[:4]],
        'attempts':[{**a, 'metrics':({k:v for k,v in a['metrics'].items() if k!='raw_samples'} if a['metrics'] else None)} for a in state['attempts']]}
    if len(h.canonical(result)) > 90000:
        result['pipeline']['alternatives'] = []
    return result
