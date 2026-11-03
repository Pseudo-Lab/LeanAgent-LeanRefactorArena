"""Prepare and audit the fixed P01 prompt ablation; never generate proof proposals.

python3 coordinator.py prepare COHORT
python3 coordinator.py audit COHORT
Solver work is explicitly dispatched to fresh subagents by the chat coordinator.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
REPO = HARNESS.parents[1]
ORIGIN = REPO / 'runs/first-harness-jwkweon/p01-p13-subagents-20261024/P01-r1'
CODE = ['harness.py', 'models.py', 'subagent_trials.py',
        'evaluator/__init__.py', 'evaluator/lean.py',
        'evaluator/tokens.py', 'evaluator/provenance.json']


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def files(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts
            and p.name != 'artifacts.json'}


def worker(root, command):
    return [sys.executable, '-B', str(root / 'code/subagent_trials.py'),
            command, str(root)]


def prepare(base):
    design = read(base / 'design.frozen.json')
    protocol = read(base / 'execution-protocol.json')
    assert protocol['lean_timeout_seconds'] == 420
    runtime_inventory = read(base / 'runtime-inventory.before.json')
    assert runtime_inventory['matches_historical_lock']
    for i in [1, 2]:
        calibration = read(base / f'calibration-{i}/summary.json')
        assert calibration['valid'] and calibration['environment_unchanged']
        assert calibration['timeout_seconds'] == 420
    for relative, digest in design['fixed_inputs_sha256'].items():
        assert sha(HERE / relative) == digest
    for arm in design['arms']:
        assert sha(HERE / arm['prompt']) == arm['prompt_sha256']
    assert sha(ORIGIN / 'baseline/result.json') == design['fixed_inputs_sha256']['input/baseline-observation.json']
    assert read(ORIGIN / 'baseline/result.json')['valid']
    runtime_template = read(ORIGIN / 'runtime.json')
    arms = {arm['condition']: arm for arm in design['arms']}
    for trial in design['trials']:
        root = base / trial['trial_id']
        root.mkdir()
        for directory in ['input', 'project', 'home', 'tmp', 'responses']:
            (root / directory).mkdir()
        for relative in CODE:
            target = root / 'code' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HARNESS / relative, target)
        for name in ['problem.json', 'source.lean', 'context.lean.in', 'environment.lock.json']:
            shutil.copyfile(HERE / 'input' / name, root / 'input' / name)
        shutil.copyfile(HERE / arms[trial['condition']]['prompt'], root / 'input/prompt.txt')
        shutil.copyfile(base / 'solver-dispatch.template.txt', root / 'input/operations.txt')
        for name in ['lean-toolchain', 'lakefile.toml', 'lake-manifest.json']:
            shutil.copyfile(ORIGIN / 'project' / name, root / 'project' / name)
        shutil.copytree(ORIGIN / 'baseline', root / 'baseline')
        shutil.copyfile(ORIGIN / 'lean_runner.py', root / 'lean_runner.py')
        runtime = {**runtime_template, 'home': str(root / 'home'), 'tmp': str(root / 'tmp')}
        write(root / 'runtime.json', runtime)
        config = {**trial, 'problem_id': 'P01', 'baseline_mode': 'frozen',
                  'frozen_baseline_sha256': sha(root / 'baseline/result.json'),
                  'lean_timeout_seconds': 420, 'concurrency_limit': 2,
                  'runner': 'subagent_trials.py', 'fork_turns': 'none',
                  'model': 'inherited Codex backend; exact model ID unobservable'}
        write(root / 'trial.json', config)
        write(root / 'prepared.json', {
            'created_at': now(), 'files_sha256': files(root),
            'baseline_provenance': str(ORIGIN / 'baseline'),
            'baseline_reused': True, 'baseline_freshness': 'historical original, current cohort readiness checked separately',
            'os_isolation': False, 'shared_libraries_read_only_by_policy': True})
        result = subprocess.run(worker(root, 'init'), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (base / f'{root.name}-initialization.log').write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(f'Initialization failed: {root.name}; inspect external initialization log')
    write(base / 'cohort.frozen.json', {
        'prepared_at': now(), 'design_sha256': sha(base / 'design.frozen.json'),
        'protocol_sha256': sha(base / 'execution-protocol.json'),
        'operations_sha256': sha(base / 'solver-dispatch.template.txt'),
        'runtime_inventory_before_sha256': sha(base / 'runtime-inventory.before.json'),
        'code_sha256': {name: sha(HARNESS / name) for name in CODE},
        'trials': design['trials'], 'max_solver_parallelism': 2,
        'common_baseline': design['common_model_input_baseline'],
        'timeout_seconds': 420, 'no_automatic_retries': True})
    print(json.dumps({'prepared': True, 'trial_count': len(design['trials']),
                      'first_wave': [t['trial_id'] for t in design['trials'][:2]]}))


def inventory(root):
    index = read(root / 'artifacts.json')
    assert index == files(root), (root.name, 'sealed inventory mismatch')
    for relative, digest in read(root / 'prepared.json')['files_sha256'].items():
        assert sha(root / relative) == digest, (root.name, relative)


def evaluation(folder, code):
    result = read(folder / 'result.json')
    for env_id, env in result['environments'].items():
        for run in env['runs']:
            source = folder / env_id / run['source']
            log = folder / env_id / run['log']
            assert sha(source) == run['source_sha256'] and sha(log) == run['log_sha256']
            assert code in source.read_text()
            if 'measurement' in run:
                lines = [line for line in log.read_text().splitlines()
                         if 'REFACTOR_EVAL ' in line and '{' in line]
                assert len(lines) == 1
                assert json.loads(lines[0][lines[0].index('{'):]) == run['measurement']
        if env['valid']:
            assert len(env['runs']) == 4
            assert sum('measurement' in run for run in env['runs']) == 3
            assert all(run['returncode'] == 0 and not run['timed_out'] for run in env['runs'])
    return result


def audit(base):
    design = read(base / 'design.frozen.json')
    frozen = read(base / 'cohort.frozen.json')
    events = [json.loads(line) for line in (base / 'dispatch.jsonl').read_text().splitlines()]
    assert [e['trial_id'] for e in events if e['event'] == 'dispatched'] == [
        t['trial_id'] for t in design['trials']]
    active, seen, peak = set(), set(), 0
    for event in events:
        trial_id = event['trial_id']
        if event['event'] == 'dispatched':
            assert trial_id not in seen
            active.add(trial_id)
            seen.add(trial_id)
            peak = max(peak, len(active))
            assert peak <= 2
        elif event['event'] == 'completed':
            assert trial_id in active
            active.remove(trial_id)
        else:
            raise ValueError('Unknown dispatch event')
    assert not active and seen == {t['trial_id'] for t in design['trials']}
    dispatch_by_trial = {r['trial_id']: r for r in events if r['event'] == 'dispatched'}
    completion_by_trial = {r['trial_id']: r for r in events if r['event'] == 'completed'}
    assert len({r['agent'] for r in dispatch_by_trial.values()}) == len(design['trials'])
    assert sha(base / 'design.frozen.json') == frozen['design_sha256']
    assert sha(base / 'execution-protocol.json') == frozen['protocol_sha256']
    assert sha(base / 'solver-dispatch.template.txt') == frozen['operations_sha256']
    assert sha(base / 'runtime-inventory.before.json') == frozen['runtime_inventory_before_sha256']
    protocol = read(base / 'execution-protocol.json')
    for i in [1, 2]:
        calibration = base / f'calibration-{i}'
        assert sha(calibration / 'summary.json') == protocol['calibration_summaries_sha256'][str(i)]
        summary = read(calibration / 'summary.json')
        assert summary['valid'] and summary['environment_unchanged'] and summary['original_valid']
        assert sha(calibration / 'initial-readiness-summary.json') == summary['initial_readiness_summary_sha256']
        assert evaluation(calibration / 'original', read(HERE / 'input/problem.json')['reference'])['valid']
        assert read(calibration / 'imports-only-result.json') == summary['imports']
        assert not summary['imports']['timed_out'] and summary['imports']['returncode'] == 0
    runtime_before = read(base / 'runtime-inventory.before.json')
    runtime_after = read(base / 'runtime-inventory.after.json')
    assert runtime_before['files_sha256'] == runtime_after['files_sha256']
    assert runtime_after['matches_historical_lock']
    arms = {arm['condition']: arm for arm in design['arms']}
    denominator = design['common_model_input_baseline']
    def score(best):
        return best['rank_numerator'] / (2 * denominator['tokens'] * denominator['raw_heartbeats'])
    rows = []
    for trial in design['trials']:
        root = base / trial['trial_id']
        summary = read(root / 'summary.json')
        inventory(root)
        assert summary['proposal_count'] == summary['max_proposals'] == 10
        assert summary['environment_unchanged']
        assert (summary['status'] == 'completed') == summary['final_valid']
        assert {k: summary['baseline'][k] for k in denominator} == denominator
        assert sha(root / 'input/prompt.txt') == arms[trial['condition']]['prompt_sha256']
        assert sha(root / 'input/operations.txt') == frozen['operations_sha256']
        for name, digest in frozen['code_sha256'].items():
            assert sha(root / 'code' / name) == digest
        assert {p.name for p in (root / 'requests').glob('*.json')} == {f'{i:03}.json' for i in range(1, 11)}
        assert {p.name for p in (root / 'responses').glob('*.json')} == {f'{i:03}.json' for i in range(1, 11)}
        problem = read(root / 'input/problem.json')
        evaluation(root / 'baseline', problem['reference'])
        timeline, proposals = [], []
        errors = Counter()
        for step in range(1, 11):
            before, after = [read(root / f'states/{i:03}.json') for i in [step - 1, step]]
            request = read(root / f'requests/{step:03}.json')
            assert request['instructions'] == (root / 'input/prompt.txt').read_text()
            assert request['baseline'] == before['baseline']
            assert request['problem'] == problem
            assert request['best'] == {k: v for k, v in before['best'].items() if k != 'raw_samples'}
            assert request['latest'] == before['latest']
            assert request['step'] == step and request['total_steps'] == 10
            assert read(root / f'responses/{step:03}.json') == read(root / f'steps/{step:03}/response.json')
            latest = after['latest']
            if latest['code'] is not None:
                result = evaluation(root / f'steps/{step:03}/evaluation', latest['code'])
                if not result['valid']:
                    for env in result['environments'].values():
                        if env.get('error'):
                            errors.update([env['error']['kind']])
                    if not result['environments']:
                        errors.update([result['error']['kind']])
            else:
                errors.update(['response_parse'])
            best = after['best']
            timeline.append({'step': step, 'tokens': best['tokens'],
                             'raw_heartbeats': best['raw_heartbeats'], 'local_cost': score(best),
                             'code_sha256': best['sha256']})
            proposals.append({'step': step, 'valid': latest['feedback']['valid'],
                              'status': latest['feedback']['status'],
                              'metrics': latest['feedback'].get('metrics'),
                              'code_sha256': hashlib.sha256(latest['code'].encode()).hexdigest() if latest['code'] else None})
        final_result = evaluation(root / 'final', summary['selected']['code'])
        assert final_result['valid'] == summary['final_valid']
        replay = json.loads(subprocess.check_output(worker(root, 'replay'), text=True))
        assert replay['record_replay_passed']
        rows.append({**trial, 'status': summary['status'], 'baseline': summary['baseline'],
                     'selected': {k: v for k, v in summary['selected'].items() if k != 'code'},
                     'selected_local_cost': summary['selected_local_score'],
                     'final': summary['final'], 'final_valid': summary['final_valid'],
                     'final_validation': final_result,
                     'timeline': timeline, 'checkpoints': {str(i): timeline[i-1] for i in [3,6,10]},
                     'proposals': proposals, 'proposal_error_counts': dict(errors),
                     'verified_proposals': sum(p['valid'] for p in proposals),
                     'distinct_valid_proofs': len({p['code_sha256'] for p in proposals if p['valid']}),
                     'record_replay_passed': True, 'artifact_index_sha256': sha(root / 'artifacts.json'),
                     'first_request_sha256': sha(root / 'requests/001.json'),
                     'started_at': summary['started_at'], 'finished_at': summary['finished_at'],
                     'started_at_semantics': 'worker initialization; may precede queue dispatch',
                     'solver_dispatched_at': dispatch_by_trial[root.name]['dispatched_at'],
                     'solver_completion_observed_at': completion_by_trial[root.name]['observed_at'],
                     'codex_model_calls': None, 'codex_cost_usd': None})
    aggregate = {}
    for condition in arms:
        runs = [row for row in rows if row['condition'] == condition]
        assert len(runs) == 2 and len({r['first_request_sha256'] for r in runs}) == 1
        aggregate[condition] = {
            'final_valid_count': sum(row['final_valid'] for row in runs),
            'checkpoints': {str(k): {
                'mean_cost': statistics.mean(row['checkpoints'][str(k)]['local_cost'] for row in runs),
                'min_cost': min(row['checkpoints'][str(k)]['local_cost'] for row in runs),
                'max_cost': max(row['checkpoints'][str(k)]['local_cost'] for row in runs)
            } for k in [3,6,10]}}
    for condition in aggregate:
        for checkpoint, values in aggregate[condition]['checkpoints'].items():
            values['difference_from_A'] = values['mean_cost'] - aggregate['A']['checkpoints'][checkpoint]['mean_cost']
    clock_file = base / 'host-clock-observations.jsonl'
    clock_rows = [json.loads(line) for line in clock_file.read_text().splitlines()] if clock_file.exists() else []
    samples = [r for r in clock_rows if r['event'] == 'sample']
    clock_summary = {
        'observer_started': clock_rows[0] if clock_rows else None,
        'observer_stopped': bool(clock_rows and clock_rows[-1]['event'] == 'stopped'),
        'sample_count': len(samples),
        'max_observed_civil_minus_monotonic_interval_seconds': max(
            [abs(r.get('civil_minus_monotonic_interval', 0)) for r in samples], default=None),
        'initial_gap_note': 'Observer started before P01 readiness and solver dispatch. Do not interpret civil elapsed time as proof/model compute time.'}
    result = {'checked_at': now(), 'status': 'completed' if all(r['final_valid'] for r in rows) else 'completed_with_validation_failures',
              'trial_count': len(rows), 'proposal_count': sum(len(r['proposals']) for r in rows),
              'all_record_checks_passed': True, 'all_final_valid': all(r['final_valid'] for r in rows),
              'same_first_request_within_condition': True, 'common_baseline': denominator,
              'shared_runtime_artifacts_unchanged': True,
              'shared_runtime_file_count': runtime_after['file_count'],
              'recorded_peak_solver_parallelism': peak,
              'trials': rows, 'aggregate': aggregate, 'design_sha256': frozen['design_sha256'],
              'host_clock_observation': clock_summary,
              'operational_incidents': [json.loads(line) for line in
                  (base / 'operator-incidents.jsonl').read_text().splitlines()],
              'limitations': design['limitations'] + [design['outcomes']['uncertainty']],
              'development_problem_overlap': True}
    write(base / 'cohort-summary.json', result)
    print(json.dumps({'record_audit_passed': True, 'all_final_valid': result['all_final_valid'],
                      'summary': str(base / 'cohort-summary.json')}))


def progress(base):
    design = read(base / 'design.frozen.json')
    state = read(base / 'coordinator-state.json')
    rows = []
    milestone_file = base / 'milestones.jsonl'
    seen = {(r['trial_id'], r['checkpoint']) for r in
            [json.loads(line) for line in milestone_file.read_text().splitlines()]} if milestone_file.exists() else set()
    for trial in design['trials']:
        root = base / trial['trial_id']
        paths = sorted((root / 'states').glob('*.json'))
        if not paths:
            continue
        try:
            current = read(paths[-1])
        except json.JSONDecodeError:
            current = read(paths[-2])
        best, baseline = current['best'], current['baseline']
        row = {'trial_id': trial['trial_id'], 'step': current['step'],
               'tokens': best['tokens'], 'raw_heartbeats': best['raw_heartbeats'],
               'local_cost': best['rank_numerator'] / (2 * baseline['tokens'] * baseline['raw_heartbeats'])}
        if (root / 'summary.json').exists():
            summary = read(root / 'summary.json')
            row.update(status=summary['status'], final_valid=summary['final_valid'])
        elif trial['trial_id'] in state['active']:
            row['status'] = 'running'
        else:
            row['status'] = 'pending'
        rows.append(row)
        for checkpoint in [3, 6, 10]:
            path = root / f'states/{checkpoint:03}.json'
            key = (trial['trial_id'], checkpoint)
            if path.exists() and key not in seen:
                try:
                    value = read(path)
                except json.JSONDecodeError:
                    continue
                best, baseline = value['best'], value['baseline']
                milestone = {'observed_at': now(), 'trial_id': trial['trial_id'],
                             'checkpoint': checkpoint, 'tokens': best['tokens'],
                             'raw_heartbeats': best['raw_heartbeats'],
                             'local_cost': best['rank_numerator'] / (2 * baseline['tokens'] * baseline['raw_heartbeats'])}
                with milestone_file.open('a') as stream:
                    stream.write(json.dumps(milestone) + '\n')
                seen.add(key)
    print(json.dumps({'at': now(), 'completed_proposals': sum(r['step'] for r in rows),
                      'active': list(state['active']), 'trials': rows}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'audit', 'progress'])
    parser.add_argument('cohort', type=Path)
    args = parser.parse_args()
    globals()[args.command](args.cohort.resolve())
