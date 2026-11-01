"""Issue #37-based Controller; route decisions surround the PR B repair module."""
import re

from common import Stop, canonical, sha
from adapter import operational, repair_candidate, score
from corpus import reference_workflow
from generation_transport import parse_plan
from native import select_site
from lean_agent import harness


def failure_report(evaluation, observation=None):
    errors = (observation or {}).get('errors', [])
    message = errors[0]['message'] if errors else canonical(evaluation.get('error'))
    patterns = [('missing_alternative', r'Alternative .* has not been provided'),
                ('unknown_name', r'Unknown (?:constant|identifier)|unknown (?:constant|identifier)'),
                ('type_mismatch', r'[Tt]ype mismatch'), ('rewrite', r'[Rr]ewrite.*failed|Tactic `rewrite` failed'),
                ('unsolved_goals', r'unsolved goals')]
    kind = next((kind for kind, pattern in patterns if re.search(pattern, message)), 'proof_error')
    diagnostics = [{**row, 'message': row['message'][:2500]} for row in errors[:6]]
    return {'kind': kind, 'first_error': message[:2500], 'diagnostics': diagnostics,
            'observation_kind': (observation or {}).get('kind')}


def generation_loop(rt, reference=None):
    control = rt.protocol['controller']
    original = rt.problem['reference']
    result = {'status': 'stopped', 'stop_reason': None, 'condition': rt.protocol['condition'],
              'integration': 'issue-37-based-local-implementation', 'attempts': [], 'plans': [],
              'final_valid': None, 'final_q': None, 'selected_origin': None, 'selected_sha256': None}
    best, best_code, best_origin = None, original, 'original'
    routes, active, lessons, history = {}, [], [], []
    stale = 0
    failures = {}
    goals = None
    pending = 'start'
    attempt = None
    try:
        reference = (rt.tape.call('shared_reference', {'sha256': sha(canonical(reference))}, lambda: reference)
                     if reference is not None else reference_workflow(rt))
        if reference['status'] != 'completed':
            raise Stop(reference['reason'] or 'baseline_unverified')
        baseline = reference['baseline']
        best = baseline
        result['baseline'] = baseline
        for step in range(1, control['max_steps']+1):
            rt.check_time()
            if pending:
                packet = {'trigger': pending, 'routes': list(routes.values()), 'lessons': lessons,
                          'goals': goals, 'recent': history[-3:], 'best_q': score(best, baseline),
                          'parser_available_auto_tactics': reference['tactics']}
                try:
                    raw = rt.dispatch('planner', packet)
                    plan = parse_plan(raw)
                    active = []
                    for route in plan['routes']:
                        key = sha(canonical(route))[:16]
                        routes.setdefault(key, {**route, 'key': key, 'attempts': 0, 'best_q': None,
                                                'best': None, 'failures': {}, 'last': None})
                        active.append(key)
                    lessons = plan['lessons']
                    result['plans'].append({'step': step, 'trigger': pending, 'plan': plan})
                except ValueError as exc:
                    rt.tape.event('planner_rejected', reason=str(exc))
                except Stop as exc:
                    if exc.reason not in ('planner_call_limit', 'planner_budget_limit'):
                        raise
                    rt.tape.event('planner_skipped', reason=exc.reason, trigger=pending)
                if not active:
                    key = 'original-route'
                    routes.setdefault(key, {'id': key, 'strategy': 'Refactor the supplied original proof.',
                                            'key': key, 'attempts': 0, 'best_q': None, 'best': None,
                                            'failures': {}, 'last': None})
                    active = [key]
                pending, stale, failures = None, 0, {}
            # Explore each assigned route; do not let the first success monopolize calls.
            key = min(active, key=lambda key: (routes[key]['attempts'], active.index(key)))
            route = routes[key]
            request = {'route': {k: route[k] for k in ('id', 'strategy', 'key')}, 'lessons': lessons,
                       'parser_available_auto_tactics': reference['tactics'],
                       'best': {'code': best_code, 'tokens': best['tokens'], 'metrics': harness.metrics(best)},
                       'route_best': route['best'], 'route_last': route['last'], 'recent': history[-3:]}
            attempt = {'step': step, 'route_key': key, 'source_sha256': None, 'valid': False,
                       'improved': False, 'duplicate': False, 'repair': None, 'failure': None}
            result['attempts'].append(attempt)
            raw = rt.dispatch('root', request)
            route['attempts'] += 1
            code = None
            try:
                code = harness.parse_proof(raw, rt.problem, control['max_proof_characters'])
                attempt['source_sha256'] = sha(code)
                if rt.duplicate(code):
                    attempt.update(duplicate=True, failure={'kind': 'duplicate', 'first_error': 'Do not resubmit this source.'})
                    evaluation = None
                else:
                    evaluation = rt.evaluate(code, f'candidate-{step:03}')
                    if operational(evaluation):
                        raise Stop('candidate_operational_error')
                    if not evaluation['valid']:
                        observation = rt.observe(code) if evaluation['environments'] else None
                        if observation and observation['kind'] == 'timeout':
                            raise Stop('diagnostic_timeout')
                        site = select_site(observation, code) if observation and observation['kind'] == 'proof' else None
                        goals = site['pending_goals'] if site else None
                        attempt['failure'] = failure_report(evaluation, observation)
                        if rt.protocol['condition'] != 'planner-worker-v1' and observation and observation['kind'] == 'proof':
                            repaired = repair_candidate(rt, code, key, rt.protocol['condition'], reference['tactics'])
                            attempt['repair'] = repaired
                            goals = repaired['remaining_goals']
                            if repaired['status'] == 'operational_error':
                                raise Stop(repaired['reason'])
                            if repaired['status'] == 'verified':
                                code, evaluation = repaired['code'], repaired['evaluation']
                                attempt['repaired_source_sha256'] = sha(code)
                                attempt['failure'] = None
                    if evaluation['valid']:
                        goals = None
                        q = score(evaluation, baseline)
                        attempt.update(valid=True, q=q, tokens=evaluation['tokens'], metrics=harness.metrics(evaluation))
                        if route['best_q'] is None or q < route['best_q']:
                            route['best_q'] = q
                            route['best'] = {'code': code, 'q': q, 'metrics': harness.metrics(evaluation)}
                        if q < score(best, baseline):
                            best, best_code = evaluation, code
                            best_origin = 'repaired' if attempt['repair'] else 'generated'
                            attempt['improved'] = True
            except ValueError as exc:
                attempt['failure'] = {'kind': 'response', 'first_error': str(exc)[:2500]}
            stale = 0 if attempt['improved'] else stale+1
            if attempt['failure']:
                kind = attempt['failure']['kind']
                failures[kind] = failures.get(kind, 0)+1
                route['failures'][kind] = route['failures'].get(kind, 0)+1
                if failures[kind] >= control['repeated_failure']:
                    pending = 'repeated_failure'
            if stale >= control['stagnation_steps']:
                pending = pending or 'stagnation'
            brief = {k: v for k, v in attempt.items() if k != 'repair'}
            brief['code'] = code if attempt['source_sha256'] else None
            route['last'] = brief
            history.append(brief)
            attempt['cost'] = rt.cost_summary()
            rt.tape.event('controller_step', attempt=attempt, next_planner_trigger=pending,
                          selected_sha256=sha(best_code), best_q=score(best, baseline))
        result['stop_reason'] = 'step_limit'
    except Stop as exc:
        result['stop_reason'] = exc.reason
        if attempt is not None:
            attempt['stop_reason'] = exc.reason
            attempt['cost'] = rt.cost_summary()
    except (OSError, ValueError, RuntimeError) as exc:
        result.update(stop_reason='operational_error', error=str(exc))
    # This phase has no model dispatch and can use the previously reserved time.
    if best is not None:
        rt.finalizing = True
        try:
            final = rt.evaluate(best_code, 'final-selected')
            if not final['valid'] and not operational(final):
                best_code, best_origin = original, 'original'
                final = rt.evaluate(original, 'final-baseline')
            if final['valid']:
                result.update(final_valid=True, selected_code=best_code, selected_sha256=sha(best_code),
                              selected_origin=best_origin, final_metrics=harness.metrics(final),
                              final_q=2 if best_origin == 'original' else score(final, baseline),
                              final_measured_q=score(final, baseline))
            result['final_evaluation'] = final
        except (Stop, OSError, ValueError, RuntimeError) as exc:
            result['final_error'] = str(exc)
    result.update(**rt.cost_summary(), routes=list(routes.values()), elapsed_seconds=rt.now())
    normal = {'step_limit', 'budget_limit', 'run_call_limit', 'final_verification_reserve', 'generation_time_limit'}
    if result['final_valid'] and not result['unknown_cost'] and result['stop_reason'] in normal:
        result['status'] = 'completed'
    rt.tape.event('finished_result', result=result)
    return result
