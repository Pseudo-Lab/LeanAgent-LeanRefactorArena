"""Proposed #37 adapter plus a one-candidate fixture Controller for integration tests.

The fixture Controller does not implement a Planner, route search or performance
comparison. A real #37 integration remains pending its published interface.
"""
from common import Stop, sha
from lean_agent import harness
from lean_agent.evaluator.tokens import validate_declaration
from repair import RepairEngine


def score(evaluation, baseline):
    if not evaluation['valid']:
        return None
    e, b = harness.metrics(evaluation), harness.metrics(baseline)
    if not b or not b['raw_heartbeats'] or not baseline['tokens']:
        return None
    return evaluation['tokens']/baseline['tokens'] + e['raw_heartbeats']/b['raw_heartbeats']


def operational(evaluation):
    return any(row.get('error', {}).get('kind') in ('timeout', 'environment')
               for row in evaluation.get('environments', {}).values() if row.get('error'))


def repair_candidate(runtime, code, route_id, arm, tactics):
    """The outer Controller calls this only for a nonduplicate invalid candidate."""
    validate_declaration(code, runtime.problem['statement'])
    return RepairEngine(runtime, arm, tactics).repair(code, route_id)


def workflow(rt):
    protocol = rt.protocol
    original = rt.problem['reference']
    best_code, best, repaired, stop = original, None, None, 'completed'
    result = {'schema_version': 2, 'condition': protocol['condition'],
              'integration': 'fixture_controller; #37 integration pending',
              'baseline': None, 'repair': None, 'selected_sha256': None, 'selected_origin': None,
              'final_valid': None, 'final_q': None}
    try:
        preflight = rt.preflight()
        if preflight['status'] != 'passed':
            raise Stop('preflight_failed')
        tactics = rt.availability()
        baseline = rt.evaluate(original, 'baseline')
        result['baseline'] = baseline
        if not baseline['valid'] or score(baseline, baseline) is None:
            stop = 'baseline_unverified'
        else:
            best = baseline
            # This fixed root request represents a Worker dispatched by #37;
            # it contains no condition-specific intervention.
            raw = rt.dispatch('root', {'problem': rt.problem, 'context': protocol.get('context', {}),
                                       'route_id': 'fixture-route', 'instruction': 'Generate one proof candidate.'})
            try:
                code = harness.parse_proof(raw, rt.problem, 60000)
                validate_declaration(code, rt.problem['statement'])
            except ValueError as exc:
                rt.tape.event('root_rejected', reason=str(exc))
                stop = 'response_rejected'
            else:
                if rt.duplicate(code):
                    stop = 'duplicate'
                else:
                    evaluation = rt.evaluate(code, 'candidate')
                    if operational(evaluation):
                        stop = 'candidate_operational_error'
                    elif not evaluation['valid'] and protocol['condition'] != 'planner-worker-v1':
                        repaired = repair_candidate(rt, code, 'fixture-route', protocol['condition'], tactics)
                        result['repair'] = repaired
                        if repaired['status'] == 'verified':
                            code, evaluation = repaired['code'], repaired['evaluation']
                        else:
                            stop = repaired.get('reason', repaired['status'])
                    if evaluation['valid'] and score(evaluation, baseline) < score(best, baseline):
                        best, best_code = evaluation, code
                    rt.tape.event('selected', candidate_sha256=sha(best_code), objective=score(best, baseline))
    except Stop as exc:
        stop = exc.reason
    except (OSError, RuntimeError, ValueError) as exc:
        stop = 'operational_error'
        result['error'] = str(exc)
        rt.tape.event('operation_failed', detail=str(exc))

    if best is not None:
        try:
            final = rt.evaluate(best_code, 'final-selected')
            if not final['valid'] and not operational(final):
                best_code = original
                final = rt.evaluate(original, 'final-baseline')
            origin = 'baseline' if best_code == original else 'generated'
            result.update(final_evaluation=final, final_valid=True if final['valid'] else None,
                          selected_sha256=sha(best_code) if final['valid'] else None,
                          selected_origin=origin if final['valid'] else None,
                          final_q=(2 if origin == 'baseline' else score(final, result['baseline'])) if final['valid'] else None,
                          final_measured_q=score(final, result['baseline']),
                          selected_code=best_code if final['valid'] else None)
        except (Stop, OSError, RuntimeError, ValueError) as exc:
            result['final_error'] = str(exc)
    result.update(stop_reason=stop, **rt.cost_summary())
    result['status'] = ('completed' if result['final_valid'] and not result['unknown_cost']
                        and stop not in ('operational_error','candidate_operational_error','lean_timeout','preflight_failed')
                        else 'stopped')
    result['elapsed_seconds'] = rt.now()
    rt.tape.event('finished_result', result=result)
    return result
