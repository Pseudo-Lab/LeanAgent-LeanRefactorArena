"""Issue #37-based generation experiment. Prepare/check/replay never call APIs."""
import argparse
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import shutil
import competition

from common import HERE, REPO, TACTICS, canonical, inventory, read, safe_path, sha, shared
from calibrate import p02_limits
from controller import generation_loop
from corpus import reference_workflow
from generation_runtime import GenerationRuntime
from generation_transport import ScriptedTransport
from openrouter_transport import OpenRouterTransport, fetch_endpoint, validate_endpoint, terminal_key
from generation_records import (record, usage_inputs, save_execution, verify_execution,
                                seal_execution, verify_seal)
from lean_agent import accounting, harness, prepared, status

REVISION = 'single-repair-4-official-compatibility'
RUN_BUDGET, SUITE_BUDGET = '2.50', '2.50'
ORDER = [('repair-r1', 'recursive-repair-v1')]
FOUR_RUN_FIXTURE = [('baseline-r1', 'planner-worker-v1'), ('repair-r1', 'recursive-repair-v1'),
                    ('repair-r2', 'recursive-repair-v1'), ('baseline-r2', 'planner-worker-v1')]
CONTROL = {'max_steps': 100, 'planner_max_calls': 3, 'planner_budget_usd': '0.50',
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
        benchmark = (REPO/competition.SNAPSHOT/'benchmark_data_warmup.jsonl').read_bytes()
        snapshot_meta = read(REPO/competition.SNAPSHOT/'snapshot.json')
        compatibility = competition.contract(benchmark, snapshot_meta, ready)
        order = ORDER
    else:
        problem, environment, limits = fixture['problem'], fixture['environment'], fixture['limits']
        context, backend = fixture.get('context', {}), 'fixture'
        control = {**CONTROL, **fixture.get('controller', {})}
        compatibility = None
        order = fixture.get('condition_order', ORDER)
    if not order or len({row[0] for row in order}) != len(order):
        raise ValueError('Expected distinct execution IDs')
    run_budget = str(Decimal(SUITE_BUDGET)/len(order))
    root.mkdir(parents=True)
    protocol = {'revision': REVISION, 'backend': backend, 'problem': problem, 'context': context,
                'integration': 'issue-37-based-local-implementation', 'condition_order': order,
                'environment': environment, 'environment_sha256': sha(canonical(environment)),
                'limits': limits, 'controller': control, 'tactics': list(TACTICS),
                'run_budget_usd': run_budget, 'suite_budget_usd': SUITE_BUDGET,
                'endpoint': endpoint if backend == 'openrouter' else None,
                'simulated_reservation_usd': '0.02', 'simulated_budget_usd': run_budget,
                'paid_enabled_by_default': False, 'profile_enabled': False,
                'credential_input': 'hidden-terminal-only', 'selection': harness.SELECTION,
                'compatibility': compatibility,
                'interpretation': 'one repair-enabled optimization run; compare final proof with its original; no ablation or repeatability claim'}
    if fixture is None:
        shutil.copytree(calibration, root/'calibration')
        (root/'competition').mkdir()
        (root/'competition/benchmark.jsonl').write_bytes(benchmark)
        shared.atomic(root/'competition/snapshot.json', snapshot_meta)
    else:
        shared.atomic(root/'fixture.json', fixture)
    shared.atomic(root/'protocol.json', protocol)
    for relative, value in usage_inputs(root, protocol, suite=True).items():
        record(root, relative, value)
    snapshot(root)
    shared.atomic(root/'frozen-inputs.json', inventory(root))
    return protocol


def check(root):
    root = Path(root).resolve()
    for relative, digest in read(root/'frozen-inputs.json').items():
        if sha(safe_path(root, relative).read_bytes()) != digest:
            raise ValueError('Frozen input changed: '+relative)
    protocol = read(root/'protocol.json')
    expected_order = read(root/'fixture.json').get('condition_order', ORDER) if protocol['backend'] == 'fixture' else ORDER
    expected_order = [list(row) for row in expected_order]
    if (protocol['revision'] != REVISION or protocol['backend'] not in ('fixture', 'openrouter')
        or protocol['paid_enabled_by_default']
        or protocol['credential_input'] != 'hidden-terminal-only' or protocol['selection'] != harness.SELECTION
        or protocol['condition_order'] != expected_order
        or protocol['run_budget_usd'] != str(Decimal(SUITE_BUDGET)/len(expected_order)) or protocol['suite_budget_usd'] != SUITE_BUDGET
        or protocol['environment_sha256'] != sha(canonical(protocol['environment']))):
        raise ValueError('Unsupported or changed protocol')
    if protocol['backend'] == 'openrouter':
        validate_endpoint(protocol['endpoint'])
        expected = competition.contract((root/'competition/benchmark.jsonl').read_bytes(),
                   read(root/'competition/snapshot.json'), read(root/'calibration/result.json'))
        if protocol['compatibility'] != expected:
            raise ValueError('Official compatibility contract changed')
    for path in (root/'code/repo').rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.lean'):
            active = REPO/path.relative_to(root/'code/repo')
            if not active.is_file() or active.read_bytes() != path.read_bytes():
                raise ValueError('Use the archived code for this suite')
    return protocol


def summarize(rows, backend, reference, protocol):
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
    unknown = any(row['unknown_cost'] for row in rows)
    actual = None if unknown and backend != 'fixture' else str(sum(
        (Decimal(row['actual_api_cost_usd'] or '0') for row in rows), Decimal(0)))
    original = harness.metrics(reference['baseline']) if reference['status'] == 'completed' else None
    final = rows[0].get('final_metrics') if len(rows) == 1 and rows[0]['final_valid'] else None
    change = None if not original or not final else {
        key: {'before': original[key], 'after': final[key], 'delta': final[key]-original[key],
              'reduction_percent': 100*(original[key]-final[key])/original[key]}
        for key in ('tokens', 'raw_heartbeats')}
    return {'backend': backend, 'experiment': 'single_repair_optimization' if backend != 'fixture' else 'fixture_contract',
            **({'arms': arms} if backend == 'fixture' else {}), 'original': original, 'final': final, 'change': change,
            'status': 'completed' if reference['status'] == 'completed' and len(rows) == len(protocol['condition_order'])
                      and all(row['status'] == 'completed' for row in rows) else 'stopped',
            'final_q': rows[0]['final_q'] if len(rows) == 1 else None,
            'selected_origin': rows[0]['selected_origin'] if len(rows) == 1 else None,
            'repair_activity': {'entered_candidates': sum(bool(a['repair']) for row in rows for a in row['attempts']),
                'verified_candidates': sum(bool(a['repair'] and a['repair']['status'] == 'verified') for row in rows for a in row['attempts']),
                'selected_from_repair': rows[0]['selected_origin'] == 'repaired' if len(rows) == 1 else None},
            'stop_reason': rows[0]['stop_reason'] if len(rows) == 1 else reference['reason'],
            'compatibility': competition.report(protocol, reference, rows),
            'actual_api_calls': sum(row['actual_api_calls'] for row in rows),
            'actual_api_cost_usd': actual, 'unknown_cost': unknown,
            'budget_debit_usd': None if unknown else str(sum((Decimal(row['budget_debit_usd']) for row in rows), Decimal(0))),
            'evidence_kind': 'fixture_contract_only' if backend == 'fixture' else 'generation_sample',
            'run_ids': [row['run_id'] for row in rows]}


def process(root, *, allow_paid=False, replay=False):
    root = Path(root).resolve()
    protocol = check(root)
    if replay and inventory(root) != read(root/'artifacts.json'):
        raise ValueError('Recorded artifacts changed')
    # Gate before key access, native work or budget reservation.
    if protocol['backend'] != 'fixture' and not replay and not allow_paid:
        raise ValueError('Paid execution disabled: --allow-paid is required')
    if not replay and (root/'reference').exists():
        raise ValueError('Suite already started; replay or prepare a new directory')
    libraries, key = None, None
    if protocol['backend'] == 'openrouter' and not replay:
        fresh = fetch_endpoint()
        if fresh['pricing'] != protocol['endpoint']['pricing']:
            raise ValueError('Endpoint pricing changed; prepare a new suite before spending')
        libraries = prepared.PreparedLeanEvaluator(root/'calibration/libraries.json')
        libraries.verify()
        key = terminal_key()
    summary, runs = replay_records(root, protocol, replay=replay, key=key, libraries=libraries)
    if replay:
        for rt, result in runs:
            verify_seal(rt, result)
    else:
        if libraries:
            libraries.verify()
        # Replay the complete shared ledger chain before claiming any run is final.
        verified, _ = replay_records(root, protocol, replay=True)
        if verified != summary:
            raise ValueError('Suite replay differs')
        for rt, result in runs:
            seal_execution(rt, result)
        shared.atomic(root/'artifacts.json', inventory(root))
    return summary


def replay_records(root, protocol, *, replay=False, key=None, libraries=None):
    """Execute or reconstruct decisions; lifecycle records are sealed separately."""
    ledger = {'per_trial_usd': protocol['run_budget_usd'], 'total_usd': protocol['suite_budget_usd'],
              'max_trials': len(protocol['condition_order'])*protocol['limits']['run_calls'], 'attempts': {}}
    completed = []
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
                reference['calibration_baseline'] = ready['baseline']
    reference_rt.tape.event('common_reference', reference=reference)
    if replay:
        verify_execution(reference_rt, reference)
    else:
        save_execution(reference_rt, reference)
    completed.append((reference_rt, reference))
    rows = []
    if reference['status'] == 'completed':
        for run_id, condition in protocol['condition_order']:
            # One unknown charge blocks every later arm, not just this run.
            if any(row['status'] != 'settled' for row in ledger['attempts'].values()):
                break
            transport = None if replay else (ScriptedTransport(fixture['responses'][run_id]) if fixture else
                                             OpenRouterTransport(protocol, enabled=True, key=key))
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
                verify_execution(rt, result)
            else:
                save_execution(rt, result)
                print(run_id, result['stop_reason'], result['final_q'], flush=True)
            completed.append((rt, result))
            rows.append(result)
    summary = {**summarize(rows, protocol['backend'], reference, protocol), 'reference_status': reference['status'],
               'reference_reason': reference['reason']}
    if replay:
        if summary != read(root/'summary.json') or ledger != read(root/'budget.json'):
            raise ValueError('Summary or ledger replay differs')
        if accounting.native_report(root) != read(root/'usage-cost.json'):
            raise ValueError('Suite usage/cost report differs from original receipts')
        if summary['compatibility'] != read(root/'compatibility.json'):
            raise ValueError('Compatibility report differs from final verification')
    else:
        shared.atomic(root/'budget.json', ledger)
        shared.atomic(root/'summary.json', summary)
        shared.atomic(root/'usage-cost.json', accounting.native_report(root))
        shared.atomic(root/'compatibility.json', summary['compatibility'])
    return summary, completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'check', 'run', 'replay', 'status'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--calibration', type=Path)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--endpoint', type=Path, help='Frozen public OpenRouter endpoint metadata; never credentials')
    parser.add_argument('--allow-paid', action='store_true')
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
            result = process(args.output, allow_paid=args.allow_paid)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
