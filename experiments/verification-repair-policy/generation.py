"""Issue #37-based generation experiment. Prepare/check/replay never call APIs."""
import argparse
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import shutil
import statistics

from common import HERE, REPO, TACTICS, canonical, inventory, read, safe_path, sha, shared
from calibrate import p02_limits
from controller import generation_loop
from corpus import finish, reference_workflow
from generation_runtime import GenerationRuntime
from generation_transport import ScriptedTransport
from openrouter_transport import OpenRouterTransport, fetch_endpoint, validate_endpoint
from lean_agent import harness, prepared, status

REVISION = 'planner-worker-repair-2-openrouter'
RUN_BUDGET, SUITE_BUDGET = '0.625', '2.50'
ORDER = [('baseline-r1', 'planner-worker-v1'), ('repair-r1', 'recursive-repair-v1'),
         ('repair-r2', 'recursive-repair-v1'), ('baseline-r2', 'planner-worker-v1')]
CONTROL = {'max_steps': 100, 'planner_max_calls': 3, 'planner_budget_usd': '0.125',
           'stagnation_steps': 3, 'repeated_failure': 2, 'api_timeout_seconds': 300,
           'max_proof_characters': 60000}


def snapshot(root):
    archive = root/'code/repo'
    shutil.copytree(REPO/'src/lean_agent', archive/'src/lean_agent', ignore=shutil.ignore_patterns('__pycache__'))
    for relative in ('experiments/verification-repair-policy', 'experiments/api-comparison'):
        dest = archive/relative
        dest.mkdir(parents=True)
        for path in (REPO/relative).iterdir():
            if path.suffix in ('.py', '.lean'):
                shutil.copy2(path, dest/path.name)


def prepare(root, calibration=None, *, fixture=None, endpoint=None):
    root = Path(root).resolve()
    if root.exists():
        raise ValueError('Use a new suite directory; never overwrite or resume')
    if (calibration is None) == (fixture is None):
        raise ValueError('Supply exactly one calibration or fixture')
    if fixture is None:
        calibration = Path(calibration).resolve()
        if inventory(calibration) != read(calibration/'artifacts.json'):
            raise ValueError('Calibration evidence changed')
        ready = read(calibration/'result.json')
        if not ready['ready'] or ready['problem_id'] != 'P02' or ready['limits'] != asdict(p02_limits()):
            raise ValueError('P02 local calibration must pass before suite preparation')
        for relative, digest in ready['measurement_sources'].items():
            if sha(safe_path(REPO, relative).read_bytes()) != digest:
                raise ValueError('Measurement code changed since calibration')
        packet = read(REPO/'experiments/problem-inputs/P02/agent-input.json')
        problem, environment, limits = ready['problem'], ready['environment'], ready['limits']
        if packet['problem']['original'].rstrip() != problem['reference'].rstrip():
            raise ValueError('Agent input is not the calibrated original')
        context = packet['context']  # No strategy prompt or prior optimized proof.
        endpoint = validate_endpoint(endpoint or fetch_endpoint())
        backend, control = 'openrouter', dict(CONTROL)
    else:
        problem, environment, limits = fixture['problem'], fixture['environment'], fixture['limits']
        context, backend = fixture.get('context', {}), 'fixture'
        control = {**CONTROL, **fixture.get('controller', {})}
    root.mkdir(parents=True)
    protocol = {'revision': REVISION, 'backend': backend, 'problem': problem, 'context': context,
                'integration': 'issue-37-based-local-implementation', 'condition_order': ORDER,
                'environment': environment, 'environment_sha256': sha(canonical(environment)),
                'limits': limits, 'controller': control, 'tactics': list(TACTICS),
                'run_budget_usd': RUN_BUDGET, 'suite_budget_usd': SUITE_BUDGET,
                'endpoint': endpoint if backend == 'openrouter' else None,
                'simulated_reservation_usd': '0.02', 'simulated_budget_usd': RUN_BUDGET,
                'paid_enabled_by_default': False, 'profile_enabled': False,
                'interpretation': 'two independent runs per arm; exploratory, no statistical generalization'}
    if fixture is None:
        shutil.copytree(calibration, root/'calibration')
    else:
        shared.atomic(root/'fixture.json', fixture)
    shared.atomic(root/'protocol.json', protocol)
    snapshot(root)
    shared.atomic(root/'frozen-inputs.json', inventory(root))
    return protocol


def check(root):
    root = Path(root).resolve()
    for relative, digest in read(root/'frozen-inputs.json').items():
        if sha(safe_path(root, relative).read_bytes()) != digest:
            raise ValueError('Frozen input changed: '+relative)
    protocol = read(root/'protocol.json')
    if (protocol['revision'] != REVISION or protocol['backend'] not in ('fixture', 'openrouter')
        or protocol['paid_enabled_by_default']
        or protocol['condition_order'] != [list(row) for row in ORDER]
        or protocol['run_budget_usd'] != RUN_BUDGET or protocol['suite_budget_usd'] != SUITE_BUDGET
        or protocol['environment_sha256'] != sha(canonical(protocol['environment']))):
        raise ValueError('Unsupported or changed protocol')
    if protocol['backend'] == 'openrouter':
        validate_endpoint(protocol['endpoint'])
    for path in (root/'code/repo').rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.lean'):
            active = REPO/path.relative_to(root/'code/repo')
            if not active.is_file() or active.read_bytes() != path.read_bytes():
                raise ValueError('Use the archived code for this suite')
    return protocol


def summarize(rows, backend):
    arms = {}
    for arm in ('planner-worker-v1', 'recursive-repair-v1'):
        selected = [row for row in rows if row['condition'] == arm]
        valid = [row for row in selected if row['final_valid']]
        arms[arm] = {'runs': len(selected), 'final_verified': len(valid),
                     'completed': sum(row['status'] == 'completed' for row in selected),
                     'final_q': [row['final_q'] for row in valid],
                     'proof_tokens': [row['final_metrics']['tokens'] for row in valid],
                     'raw_heartbeats': [row['final_metrics']['raw_heartbeats'] for row in valid],
                     'distinct_selected_sources': len({row['selected_sha256'] for row in valid}),
                     'original_returns': sum(row['selected_origin'] == 'original' for row in valid),
                     'repair_entries': sum(bool(a['repair']) for row in selected for a in row['attempts']),
                     'verified_repairs': sum(bool(a['repair'] and a['repair']['status'] == 'verified')
                                             for row in selected for a in row['attempts'])}
    def mean(arm):
        values = arms[arm]['final_q']
        return statistics.mean(values) if len(values) == 2 and arms[arm]['completed'] == 2 else None
    baseline, repair = mean('planner-worker-v1'), mean('recursive-repair-v1')
    unknown = any(row['unknown_cost'] for row in rows)
    actual = None if unknown and backend != 'fixture' else str(sum(
        (Decimal(row['actual_api_cost_usd'] or '0') for row in rows), Decimal(0)))
    return {'backend': backend, 'arms': arms, 'actual_api_calls': sum(row['actual_api_calls'] for row in rows),
            'actual_api_cost_usd': actual, 'unknown_cost': unknown,
            'mean_q_repair_minus_baseline': repair-baseline if repair is not None and baseline is not None else None,
            'budget_debit_usd': None if unknown else str(sum((Decimal(row['budget_debit_usd']) for row in rows), Decimal(0))),
            'evidence_kind': 'fixture_contract_only' if backend == 'fixture' else 'generation_sample',
            'run_ids': [row['run_id'] for row in rows]}


def process(root, *, allow_paid=False, dotenv=None, replay=False):
    root = Path(root).resolve()
    protocol = check(root)
    if replay and inventory(root) != read(root/'artifacts.json'):
        raise ValueError('Recorded artifacts changed')
    # Gate before key access, native work or budget reservation.
    if protocol['backend'] != 'fixture' and not replay and not allow_paid:
        raise ValueError('Paid execution disabled: --allow-paid is required')
    if not replay and (root/'reference').exists():
        raise ValueError('Suite already started; replay or prepare a new directory')
    ledger = {'per_trial_usd': RUN_BUDGET, 'total_usd': SUITE_BUDGET, 'max_trials': 400, 'attempts': {}}
    libraries = None
    if protocol['backend'] == 'openrouter' and not replay:
        fresh = fetch_endpoint()
        if fresh['pricing'] != protocol['endpoint']['pricing']:
            raise ValueError('Endpoint pricing changed; prepare a new suite before spending')
        OpenRouterTransport(protocol, enabled=allow_paid, dotenv=dotenv).credentials()
        libraries = prepared.PreparedLeanEvaluator(root/'calibration/libraries.json')
        libraries.verify()
    fixture = read(root/'fixture.json') if protocol['backend'] == 'fixture' else None
    def make_runtime(path, run_id, condition, transport=None):
        if not replay:
            path.mkdir(parents=True)
        config = {**protocol, 'run_id': run_id, 'condition': condition}
        return GenerationRuntime(path, config, ledger, transport, replay=replay,
                                 budget_path=root/'budget.json', libraries=libraries)
    reference_root = root/'reference'
    reference_rt = make_runtime(reference_root, 'reference', 'planner-worker-v1')
    reference = reference_workflow(reference_rt)
    if protocol['backend'] == 'openrouter':
        ready = read(root/'calibration/result.json')
        if reference.get('fingerprint') != ready['fingerprint']:
            reference.update(status='stopped', reason='calibration_environment_changed')
        elif reference['status'] == 'completed':
            current = harness.metrics(reference['baseline'])
            frozen = harness.metrics(ready['baseline'])
            if current['tokens'] != frozen['tokens'] or abs(current['raw_heartbeats']/frozen['raw_heartbeats']-1) > .01:
                reference.update(status='stopped', reason='calibration_metrics_changed')
            else:
                reference['fresh_baseline'] = reference['baseline']
                reference['baseline'] = ready['baseline']
    reference_rt.tape.event('common_reference', reference=reference)
    if replay:
        reference_rt.tape.assert_complete()
        if reference != read(reference_root/'result.json'):
            raise ValueError('Reference replay differs')
    else:
        finish(reference_root, reference, reference_rt)
    rows = []
    if reference['status'] == 'completed':
        for run_id, condition in protocol['condition_order']:
            # One unknown charge blocks every later arm, not just this run.
            if any(row['status'] != 'settled' for row in ledger['attempts'].values()):
                break
            transport = None if replay else (ScriptedTransport(fixture['responses'][run_id]) if fixture else
                                             OpenRouterTransport(protocol, enabled=allow_paid, dotenv=dotenv))
            path = root/'runs'/run_id
            rt = make_runtime(path, run_id, condition, transport)
            if not replay:
                shared.atomic(path/'initial-budget.json', ledger)
            elif ledger != read(path/'initial-budget.json'):
                raise ValueError('Shared ledger chain differs')
            result = generation_loop(rt, reference)
            result['run_id'] = run_id
            ledger = rt.ledger
            if replay:
                rt.tape.assert_complete()
                if result != read(path/'result.json'):
                    raise ValueError('Run replay differs: '+run_id)
            else:
                finish(path, result, rt)
                print(run_id, result['stop_reason'], result['final_q'], flush=True)
            rows.append(result)
    summary = {**summarize(rows, protocol['backend']), 'reference_status': reference['status'],
               'reference_reason': reference['reason']}
    if replay:
        if summary != read(root/'summary.json') or ledger != read(root/'budget.json'):
            raise ValueError('Summary or ledger replay differs')
    else:
        if libraries:
            libraries.verify()
        shared.atomic(root/'budget.json', ledger)
        shared.atomic(root/'summary.json', summary)
        shared.atomic(root/'artifacts.json', inventory(root))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'check', 'run', 'replay', 'status'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--calibration', type=Path)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--endpoint', type=Path, help='Frozen public OpenRouter endpoint metadata; never credentials')
    parser.add_argument('--allow-paid', action='store_true')
    parser.add_argument('--dotenv', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.output, args.calibration, fixture=read(args.fixture) if args.fixture else None,
                         endpoint=read(args.endpoint) if args.endpoint else None)
    elif args.action == 'check':
        check(args.output)
        result = {'frozen_inputs_valid': True, 'model_called': False}
    elif args.action == 'status':
        result = {p.name: status.inspect(p) for p in sorted((args.output/'runs').glob('*')) if p.is_dir()}
    elif args.action == 'replay':
        result = process(args.output, replay=True)
    else:
        with shared.locked(args.output):
            result = process(args.output, allow_paid=args.allow_paid, dotenv=args.dotenv)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
