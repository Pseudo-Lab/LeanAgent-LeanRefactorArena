"""Prepare, verify, monitor and audit structured versus semantic feedback."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HARNESS = REPO / "experiments/first-harness-jwkweon"
OLD = HARNESS / "feedback-ablation-v1"
sys.path.insert(0, str(HARNESS))
import harness as h
spec = importlib.util.spec_from_file_location('local_error_feedback', HERE / 'error_feedback.py')
feedback_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feedback_module)
SOURCES = {name: HARNESS / name for name in ['harness.py', 'models.py',
    'evaluator/__init__.py', 'evaluator/lean.py', 'evaluator/tokens.py', 'evaluator/provenance.json']}
SOURCES.update({'subagent_trials.py': HERE / 'worker.py', 'error_feedback.py': HERE / 'error_feedback.py',
                'legacy_error_feedback.py': HERE / 'legacy_error_feedback.py'})


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def files(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.name != 'artifacts.json'}


def worker(root, command):
    return [sys.executable, '-B', str(root / 'code/subagent_trials.py'), command, str(root)]


def setup(base):
    """Freeze new design and copy originals; never run a solver or modify origins."""
    base.mkdir(parents=True)
    design = read(HERE / 'design.json')
    write(base / 'design.frozen.json', design)
    for name in ['solver-dispatch.template.txt', 'summarizer-prompt.txt']:
        shutil.copyfile(HERE / name, base / name)
    shutil.copyfile(OLD / 'prompt.txt', base / 'prompt.txt')
    assert sha(base / 'prompt.txt') == design['prompt_sha256']
    for pid, problem in design['problems'].items():
        for relative, digest in problem['input_files_sha256'].items():
            source, target = OLD / relative, base / relative
            assert sha(source) == digest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        origin = REPO / problem['origin']
        root = base / 'readiness' / pid
        for name in ['input', 'project', 'home', 'tmp', 'code']:
            (root / name).mkdir(parents=True, exist_ok=True)
        for name in ['problem.json', 'source.lean', 'context.lean.in', 'environment.lock.json']:
            shutil.copyfile(base / 'inputs' / pid / name, root / 'input' / name)
        for relative, source in SOURCES.items():
            if relative in ['subagent_trials.py', 'error_feedback.py', 'legacy_error_feedback.py']:
                continue
            target = root / 'code' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for path in (origin / 'project').iterdir():
            if path.is_file():
                shutil.copyfile(path, root / 'project' / path.name)
        shutil.copytree(origin / 'baseline', root / 'baseline')
        shutil.copyfile(origin / 'lean_runner.py', root / 'lean_runner.py')
        write(root / 'runtime.json', {**read(origin / 'runtime.json'),
                                     'home': str(root / 'home'), 'tmp': str(root / 'tmp')})
    write(base / 'execution-protocol.json', {
        'status': 'planned_frozen_before_solver_dispatch',
        'independent_variable': design['independent_variable'],
        'details_character_limit': 1600, 'lean_timeout_seconds': 420,
        'summary_timeout_seconds': 1800, 'proposal_budget': 10,
        'checkpoints': [3, 6, 10], 'max_solver_parallelism': 2,
        'trial_count': 8, 'proposal_count': 80,
        'prompt_sha256': sha(base / 'prompt.txt'),
        'summarizer_prompt_sha256': sha(base / 'summarizer-prompt.txt'),
        'same_initial_request_across_conditions': True,
        'automatic_retries': False, 'model_internal_calls': None, 'cost_usd': None,
        'exact_backend_model_id': None, 'summarizer_jobs_are_observable': True,
        'summary_policy': design['summary_policy']})
    print(json.dumps({'setup': True, 'status': 'planned', 'cohort': str(base)}))


def run_checked(command, log):
    with log.open('x') as stream:
        result = subprocess.run(command, text=True, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed; inspect {log}')


def readiness(base):
    def check(pid):
        root = base / 'readiness' / pid
        run_checked([sys.executable, '-B', str(HERE / 'runtime_inventory.py'), str(root), 'before'],
                    base / f'{pid}-runtime-before.log')
        run_checked([sys.executable, '-B', str(HERE / 'calibrate.py'), str(root)],
                    base / f'{pid}-readiness.log')
        return pid
    with ThreadPoolExecutor(max_workers=2) as pool:
        checked = list(pool.map(check, read(base / 'design.frozen.json')['problems']))
    print(json.dumps({'readiness_passed': checked}))


def post_runtime(base):
    def check(pid):
        run_checked([sys.executable, '-B', str(HERE / 'runtime_inventory.py'),
                     str(base / 'readiness' / pid), 'after'], base / f'{pid}-runtime-after.log')
        return pid
    with ThreadPoolExecutor(max_workers=2) as pool:
        checked = list(pool.map(check, read(base / 'design.frozen.json')['problems']))
    print(json.dumps({'post_runtime_passed': checked}))


def prepare(base):
    design = read(base / 'design.frozen.json')
    protocol = read(base / 'execution-protocol.json')
    assert sha(base / 'prompt.txt') == design['prompt_sha256']
    assert sha(base / 'summarizer-prompt.txt') == protocol['summarizer_prompt_sha256']
    assert protocol['details_character_limit'] == 1600 and protocol['lean_timeout_seconds'] == 420
    for pid, problem in design['problems'].items():
        readiness = base / 'readiness' / pid
        result = read(readiness / 'summary.json')
        assert result['valid'] and result['environment_unchanged'] and result['timeout_seconds'] == 420
        assert read(readiness / 'runtime-inventory.before.json')['matches_historical_lock']
        for relative, digest in problem['input_files_sha256'].items():
            assert sha(base / relative) == digest
    for trial in design['trials']:
        root = base / trial['trial_id']
        pid = trial['problem_id']
        origin = REPO / design['problems'][pid]['origin']
        root.mkdir()
        for directory in ['input', 'project', 'home', 'tmp', 'responses']:
            (root / directory).mkdir()
        for relative, source in SOURCES.items():
            target = root / 'code' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for name in ['problem.json', 'source.lean', 'context.lean.in', 'environment.lock.json']:
            shutil.copyfile(base / 'inputs' / pid / name, root / 'input' / name)
        shutil.copyfile(base / 'prompt.txt', root / 'input/prompt.txt')
        shutil.copyfile(base / 'solver-dispatch.template.txt', root / 'input/operations.txt')
        shutil.copyfile(base / 'summarizer-prompt.txt', root / 'input/summarizer-prompt.txt')
        for p in (origin / 'project').iterdir():
            if p.is_file():
                shutil.copyfile(p, root / 'project' / p.name)
        shutil.copytree(origin / 'baseline', root / 'baseline')
        assert sha(root / 'baseline/result.json') == sha(base / 'inputs' / pid / 'baseline-observation.json')
        shutil.copyfile(origin / 'lean_runner.py', root / 'lean_runner.py')
        runtime = {**read(origin / 'runtime.json'), 'home': str(root / 'home'), 'tmp': str(root / 'tmp')}
        write(root / 'runtime.json', runtime)
        config = {**trial, 'baseline_mode': 'frozen',
                  'frozen_baseline_sha256': sha(root / 'baseline/result.json'),
                  'error_feedback_mode': design['conditions'][trial['condition']]['error_feedback_mode'],
                  'lean_timeout_seconds': 420, 'summary_timeout_seconds': 1800, 'concurrency_limit': 2, 'fork_turns': 'none',
                  'runner': 'subagent_trials.py', 'model': 'inherited Codex backend; exact ID unobservable'}
        write(root / 'trial.json', config)
        write(root / 'prepared.json', {'created_at': now(), 'files_sha256': files(root),
              'baseline_provenance': str(origin / 'baseline'), 'baseline_reused': True,
              'os_isolation': False, 'shared_libraries_read_only_by_policy': True})
        result = subprocess.run(worker(root, 'init'), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (base / f'{root.name}-initialization.log').write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(f'Initialization failed: {root.name}')
    for pid in design['problems']:
        requests = [sha(base / t['trial_id'] / 'requests/001.json') for t in design['trials'] if t['problem_id'] == pid]
        assert len(set(requests)) == 1, (pid, 'First request differs across conditions')
    write(base / 'cohort.frozen.json', {'prepared_at': now(),
          'design_sha256': sha(base / 'design.frozen.json'), 'protocol_sha256': sha(base / 'execution-protocol.json'),
          'operations_sha256': sha(base / 'solver-dispatch.template.txt'), 'prompt_sha256': sha(base / 'prompt.txt'),
          'summarizer_prompt_sha256': sha(base / 'summarizer-prompt.txt'),
          'code_sha256': {name: sha(path) for name, path in SOURCES.items()},
          'readiness_sha256': {pid: {'summary': sha(base / 'readiness' / pid / 'summary.json'),
              'runtime_before': sha(base / 'readiness' / pid / 'runtime-inventory.before.json')}
              for pid in design['problems']}, 'max_solver_parallelism': 2})
    write(base / 'coordinator-state.json', {'phase': 'running', 'active': {}, 'pending': [t['trial_id'] for t in design['trials']], 'completed': []})
    print(json.dumps({'prepared': True, 'trial_count': len(design['trials']), 'first_requests_identical_across_conditions': True}))


def evaluation(folder, code):
    result = read(folder / 'result.json')
    for env_id, env in result['environments'].items():
        for run in env['runs']:
            source, log = [folder / env_id / run[k] for k in ['source', 'log']]
            assert sha(source) == run['source_sha256'] and sha(log) == run['log_sha256']
            assert code in source.read_text()
            if 'measurement' in run:
                lines = [line for line in log.read_text().splitlines() if 'REFACTOR_EVAL ' in line and '{' in line]
                assert len(lines) == 1 and json.loads(lines[0][lines[0].index('{'):]) == run['measurement']
        if env['valid']:
            assert len(env['runs']) == 4 and sum('measurement' in run for run in env['runs']) == 3
            assert all(run['returncode'] == 0 and not run['timed_out'] for run in env['runs'])
    return result


def summary_dispatch(base, solver_agents):
    path = base / 'summary-dispatch.jsonl'
    events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    assigned, active, finished, peak = {}, {}, set(), 0
    agents = set(solver_agents)
    for event in events:
        key = (event['trial_id'], int(event['step']))
        if event['event'] == 'dispatched':
            assert key not in assigned and event['agent'] not in agents
            assigned[key] = event
            active[key] = event['agent']
            peak = max(peak, len(active))
            assert peak <= 1
            agents.add(event['agent'])
        else:
            assert event['event'] == 'completed' and key in active
            assert event['agent'] == active.pop(key)
            finished.add(key)
    assert not active
    return assigned, finished, peak


def audit(base):
    design, frozen = read(base / 'design.frozen.json'), read(base / 'cohort.frozen.json')
    for name, digest in [('design.frozen.json', frozen['design_sha256']),
                         ('execution-protocol.json', frozen['protocol_sha256']),
                         ('solver-dispatch.template.txt', frozen['operations_sha256'])]:
        assert sha(base / name) == digest
    events = [json.loads(line) for line in (base / 'dispatch.jsonl').read_text().splitlines()]
    assert [e['trial_id'] for e in events if e['event'] == 'dispatched'] == [t['trial_id'] for t in design['trials']]
    active, peak, agent_names = set(), 0, set()
    for event in events:
        t = event['trial_id']
        if event['event'] == 'dispatched':
            assert t not in active and event['agent'] not in agent_names
            active.add(t); agent_names.add(event['agent']); peak = max(peak, len(active)); assert peak <= 2
        else:
            assert event['event'] == 'completed' and t in active
            active.remove(t)
    assert not active and len(agent_names) == 8
    dispatch = {e['trial_id']: e for e in events if e['event'] == 'dispatched'}
    completion = {e['trial_id']: e for e in events if e['event'] == 'completed'}
    summary_jobs, summary_finished, summary_peak = summary_dispatch(base, agent_names)
    summary_requests = set()
    runtime_checks = {}
    for pid in design['problems']:
        r = base / 'readiness' / pid
        assert sha(r / 'summary.json') == frozen['readiness_sha256'][pid]['summary']
        assert sha(r / 'runtime-inventory.before.json') == frozen['readiness_sha256'][pid]['runtime_before']
        before, after = [read(r / f'runtime-inventory.{phase}.json') for phase in ['before', 'after']]
        assert before['files_sha256'] == after['files_sha256'] and after['matches_historical_lock']
        assert read(r / 'summary.json')['environment_unchanged']
        assert evaluation(r / 'original', read(r / 'input/problem.json')['reference'])['valid']
        runtime_checks[pid] = {k: v for k, v in after.items() if k != 'files_sha256'}
    incident_path = base/'operator-incidents.jsonl'
    incident_rows = [json.loads(line) for line in incident_path.read_text().splitlines()] if incident_path.exists() else []
    interrupted = {t for e in incident_rows if 'account_usage_limit' in e.get('kind', '') for t in e.get('affected_trials', [])}
    rows = []
    for trial in design['trials']:
        root = base / trial['trial_id']; pid = trial['problem_id']; config = read(root / 'trial.json')
        mode = design['conditions'][trial['condition']]['error_feedback_mode']
        summary = read(root / 'summary.json')
        assert read(root / 'artifacts.json') == files(root)
        for relative, digest in read(root / 'prepared.json')['files_sha256'].items():
            assert sha(root / relative) == digest
        for relative, digest in frozen['code_sha256'].items():
            assert sha(root / 'code' / relative) == digest
        assert sha(root / 'input/prompt.txt') == frozen['prompt_sha256']
        assert sha(root / 'input/operations.txt') == frozen['operations_sha256']
        assert sha(root / 'input/summarizer-prompt.txt') == frozen['summarizer_prompt_sha256']
        assert config['error_feedback_mode'] == mode
        assert summary['proposal_count'] == summary['max_proposals'] == 10 and summary['environment_unchanged']
        assert summary['baseline']['tokens'] == design['problems'][pid]['baseline']['tokens']
        assert summary['baseline']['raw_heartbeats'] == design['problems'][pid]['baseline']['raw_heartbeats']
        assert summary['status'] == ('completed' if summary['final_valid'] else 'failed')
        for name in ['requests', 'responses']:
            assert {p.name for p in (root / name).glob('*.json')} == {f'{i:03}.json' for i in range(1,11)}
        problem = read(root / 'input/problem.json'); baseline = design['problems'][pid]['baseline']
        evaluation(root / 'baseline', problem['reference'])
        timeline, proposals, errors, summaries = [], [], Counter(), []
        for step in range(1,11):
            before, after = [read(root / f'states/{i:03}.json') for i in [step-1, step]]
            packet = read(root / f'requests/{step:03}.json')
            assert packet['instructions'] == (root / 'input/prompt.txt').read_text() and packet['problem'] == problem
            assert packet['baseline'] == before['baseline'] and packet['latest'] == before['latest']
            assert packet['best'] == {k:v for k,v in before['best'].items() if k != 'raw_samples'}
            assert packet['step'] == step and packet['total_steps'] == 10
            assert read(root / f'responses/{step:03}.json') == read(root / f'steps/{step:03}/response.json')
            latest, best = after['latest'], after['best']; result = None
            if latest['code'] is not None:
                folder = root / f'steps/{step:03}/evaluation'
                result = evaluation(folder, latest['code'])
                for env in result['environments'].values():
                    if env.get('error'): errors[env['error']['kind']] += 1
                if not result['environments']: errors[result['error']['kind']] += 1
                expected = feedback_module.format_feedback(result, None, 1600, str(root), folder, mode, replay=True)
                if expected.get('metrics'): expected['metrics'].pop('raw_samples', None)
                assert expected == latest['feedback']
                legacy = h.feedback(result, None, 1600, str(root))
                if legacy.get('metrics'): legacy['metrics'].pop('raw_samples', None)
                assert {k:v for k,v in expected.items() if k != 'details'} == {k:v for k,v in legacy.items() if k != 'details'}
                compile_error = any((env.get('error') or {}).get('kind') == 'compile' for env in result['environments'].values())
                if not compile_error: assert expected == legacy
                if mode == 'structured_v1' and compile_error: assert isinstance(json.loads(expected['details']), dict)
                summary_folder = folder.parent / 'summary'
                if mode == 'semantic_v1' and compile_error:
                    key = (root.name, step)
                    summary_requests.add(key)
                    request = read(summary_folder / 'request.json')
                    receipt = read(summary_folder / 'receipt.json')
                    assert set(request) == {'schema_version', 'details_character_limit', 'diagnostic',
                                            'source_log_sha256', 'summarizer_prompt_sha256'}
                    assert request['summarizer_prompt_sha256'] == frozen['summarizer_prompt_sha256']
                    assert receipt['model_internal_calls'] is None and receipt['cost_usd'] is None
                    response_path = summary_folder / 'response.json'
                    if receipt['status'] != 'timeout':
                        assert key in summary_jobs and key in summary_finished
                        assert sha(response_path) == receipt['response_sha256']
                    else:
                        assert receipt['fallback'] == 'structured_v1'
                    delivered = json.loads(expected['details'])
                    diagnostic = request['diagnostic']
                    counterfactual = feedback_module.legacy.format_feedback(
                        result, None, 1600, str(root), folder, 'structured_v1')
                    structured = json.loads(counterfactual['details'])
                    summaries.append({'step': step, **receipt,
                        'job_dispatched': key in summary_jobs,
                        'request': request,
                        'raw_response': response_path.read_text() if response_path.exists() else None,
                        'request_sha256': sha(summary_folder / 'request.json'),
                        'input_bytes': (summary_folder / 'request.json').stat().st_size,
                        'output_bytes': response_path.stat().st_size if response_path.exists() else 0,
                        'input_characters': len(h.canonical(diagnostic)),
                        'delivered_characters': len(expected['details']),
                        'input_goal_characters': len(diagnostic['goal'] or ''),
                        'delivered_goal_characters': len(delivered['goal'] or ''),
                        'input_context_characters': len(diagnostic['local_context']),
                        'delivered_context_characters': len(delivered['local_context']),
                        'same_error_structured_characters': len(counterfactual['details']),
                        'same_error_structured_details': counterfactual['details'],
                        'changed_from_structured': expected['details'] != counterfactual['details'],
                        'changed_payload_from_structured':
                            {k:v for k,v in delivered.items() if k != 'truncated'} !=
                            {k:v for k,v in structured.items() if k != 'truncated'},
                        'changed_from_extracted': delivered != diagnostic,
                        'message_rewritten_from_source': receipt['status'] == 'accepted' and delivered['message'] != diagnostic['message'],
                        'goal_differs_from_structured': delivered['goal'] != structured['goal'],
                        'context_differs_from_structured': delivered['local_context'] != structured['local_context'],
                        'same_error_structured_goal_characters': len(structured['goal'] or ''),
                        'same_error_structured_context_characters': len(structured['local_context']),
                        'whole_goal_preserved': delivered['goal'] == diagnostic['goal']})
                else:
                    assert not summary_folder.exists()
            else:
                errors['response_parse'] += 1; compile_error = False
            assert len(latest['feedback']['details']) <= 1600
            cost = best['rank_numerator'] / (2 * baseline['tokens'] * baseline['raw_heartbeats'])
            timeline.append({'step': step, 'local_cost': cost, 'tokens': best['tokens'],
                             'raw_heartbeats': best['raw_heartbeats'], 'code_sha256': best['sha256']})
            proposals.append({'step': step, 'valid': latest['feedback']['valid'], 'metrics': latest['feedback'].get('metrics'),
                'compiler_invocations': sum(len(env['runs']) for env in result['environments'].values()) if result else 0,
                'compile_error': compile_error, 'details': latest['feedback']['details'], 'details_characters': len(latest['feedback']['details']),
                'feedback_visible_before_step3': compile_error and step < 3,
                'feedback_visible_later': compile_error and step < 10,
                'code_sha256': hashlib.sha256(latest['code'].encode()).hexdigest() if latest['code'] else None})
        final = evaluation(root / 'final', summary['selected']['code']); assert final['valid'] == summary['final_valid']
        replay = json.loads(subprocess.check_output(worker(root, 'replay'), text=True)); assert replay['record_replay_passed']
        rows.append({**trial, 'error_feedback_mode': mode, 'usage_interrupted_and_resumed': root.name in interrupted, 'checkpoints': {str(k):timeline[k-1] for k in [3,6,10]},
            'timeline': timeline, 'proposals': proposals, 'verified_proposals': sum(p['valid'] for p in proposals),
            'valid_first3': sum(p['valid'] for p in proposals[:3]), 'improved_at3': timeline[2]['local_cost'] < 1,
            'first_valid_proposal': next((p['step'] for p in proposals if p['valid']), None),
            'first_improvement_proposal': next((p['step'] for p in timeline if p['local_cost'] < 1), None),
            'early_error_feedback_exposures': sum(p['feedback_visible_before_step3'] for p in proposals),
            'error_feedback_exposures': sum(p['feedback_visible_later'] for p in proposals),
            'post_error_transitions': [{'from_step':p['step'], 'next_valid':proposals[i+1]['valid']}
                for i,p in enumerate(proposals[:-1]) if p['compile_error']],
            'proposal_error_counts': dict(errors), 'selected': {k:v for k,v in summary['selected'].items() if k != 'code'},
            'selected_local_cost': summary['selected_local_score'], 'final': summary['final'], 'final_valid': summary['final_valid'],
            'final_validation': final, 'record_replay_passed': True, 'artifact_index_sha256':sha(root/'artifacts.json'),
            'final_compiler_invocations': sum(len(env['runs']) for env in final['environments'].values()),
            'first_request_sha256':sha(root/'requests/001.json'), 'solver_dispatched_at':dispatch[root.name]['dispatched_at'],
            'solver_completion_observed_at':completion[root.name]['observed_at'], 'codex_model_calls':None, 'codex_cost_usd':None})
        rows[-1].update(summaries=summaries, summarizer_job_count=sum(s['job_dispatched'] for s in summaries),
                        summary_fallback_count=sum(s['fallback'] is not None for s in summaries),
                        changed_feedback_exposures=sum(s['changed_payload_from_structured'] and s['step'] < 10 for s in summaries),
                        early_changed_feedback_exposures=sum(s['changed_payload_from_structured'] and s['step'] < 3 for s in summaries))
    assert set(summary_jobs) <= summary_requests
    aggregate = {}
    for pid in design['problems']:
        assert len({r['first_request_sha256'] for r in rows if r['problem_id'] == pid}) == 1
        aggregate[pid] = {}
        for condition in design['conditions']:
            runs = [r for r in rows if r['problem_id']==pid and r['condition']==condition]; assert len(runs)==2
            aggregate[pid][condition] = {'run_count':2, 'usage_interrupted_runs':sum(r['usage_interrupted_and_resumed'] for r in runs), 'improved_at3_count':sum(r['improved_at3'] for r in runs),
                'valid_first3_mean':statistics.mean(r['valid_first3'] for r in runs),
                'valid_first3_per_run':[r['valid_first3'] for r in runs],
                'first_valid_per_run':[r['first_valid_proposal'] for r in runs],
                'first_improvement_per_run':[r['first_improvement_proposal'] for r in runs],
                'early_feedback_exposures_per_run':[r['early_error_feedback_exposures'] for r in runs],
                'final_valid_count':sum(r['final_valid'] for r in runs),
                'checkpoints':{str(k):{'mean_cost':statistics.mean(r['checkpoints'][str(k)]['local_cost'] for r in runs),
                    'min_cost':min(r['checkpoints'][str(k)]['local_cost'] for r in runs),
                    'max_cost':max(r['checkpoints'][str(k)]['local_cost'] for r in runs)} for k in [3,6,10]}}
        for checkpoint in ['3','6','10']:
            control = aggregate[pid]['S']['checkpoints'][checkpoint]['mean_cost']
            aggregate[pid]['M']['checkpoints'][checkpoint]['difference_from_S'] = aggregate[pid]['M']['checkpoints'][checkpoint]['mean_cost'] - control
    clock = [json.loads(line) for line in (base/'host-clock-observations.jsonl').read_text().splitlines()]
    assert clock[-1]['event'] == 'stopped'
    incidents = base/'operator-incidents.jsonl'
    review = read(base / 'semantic-review.json')
    assert review['complete'] is True
    assert {(e['trial_id'], e['step']) for e in review['entries']} == summary_requests
    assert len(review['entries']) == len(summary_requests)
    for entry in review['entries']:
        assert type(entry.get('semantic_fidelity_concern')) is bool
        assert type(entry.get('added_repair_strategy_observed')) is bool
        assert type(entry.get('compiler_advice_retained')) is bool
        assert type(entry.get('advice_free_output_concern')) is bool
        output = base / entry['trial_id'] / f'steps/{entry["step"]:03}/summary/response.json'
        assert entry['response_sha256'] == (sha(output) if output.exists() else None)
    result = {'checked_at':now(), 'trial_count':8, 'proposal_count':80, 'all_record_checks_passed':True,
              'all_final_valid':all(r['final_valid'] for r in rows), 'trials':rows, 'aggregate':aggregate,
              'recorded_peak_solver_parallelism':peak, 'first_requests_identical_across_conditions':True,
              'recorded_peak_summarizer_parallelism': summary_peak,
              'summarizer_job_count':len(summary_jobs),
              'summary_request_count':len(summary_requests),
              'summary_fallback_count':sum(r['summary_fallback_count'] for r in rows),
              'summary_accepted_count':sum(s['status'] == 'accepted' for r in rows for s in r['summaries']),
              'summary_invalid_count':sum(s['status'] == 'invalid' for r in rows for s in r['summaries']),
              'summary_timeout_count':sum(s['status'] == 'timeout' for r in rows for s in r['summaries']),
              'summary_compliance_checked':True,
              'semantic_review': review,
              'semantic_review_sha256': sha(base / 'semantic-review.json'),
              'semantic_fidelity_concern_count': sum(e['semantic_fidelity_concern'] for e in review['entries']),
              'added_repair_strategy_observed_count': sum(e['added_repair_strategy_observed'] for e in review['entries']),
              'compiler_advice_retained_count': sum(e['compiler_advice_retained'] for e in review['entries']),
              'advice_free_output_concern_count': sum(e['advice_free_output_concern'] for e in review['entries']),
              'compiler_invocations': {
                  'candidates': sum(p['compiler_invocations'] for r in rows for p in r['proposals']),
                  'final_validation': sum(r['final_compiler_invocations'] for r in rows),
                  'readiness_including_imports': sum(1 + sum(len(e['runs']) for e in read(base/'readiness'/pid/'original/result.json')['environments'].values()) for pid in design['problems']),
                  'excludes': 'fingerprint --version/--print-prefix calls; historical baseline compiles are reused, not new invocations'},
              'runtime_checks':runtime_checks, 'observer_stopped':clock[-1]['event']=='stopped',
              'operational_incidents':[json.loads(line) for line in incidents.read_text().splitlines()] if incidents.exists() else [],
              'design_sha256':frozen['design_sha256'], 'limitations':design['limitations']}
    write(base/'cohort-summary.json',result)
    print(json.dumps({'record_audit_passed':True, 'all_final_valid':result['all_final_valid'], 'summary':str(base/'cohort-summary.json')}))


def progress(base):
    design, queue = read(base/'design.frozen.json'), read(base/'coordinator-state.json')
    milestones = base/'milestones.jsonl'
    seen = {(r['trial_id'],r['checkpoint']) for r in [json.loads(l) for l in milestones.read_text().splitlines()]} if milestones.exists() else set()
    incident_path = base/'operator-incidents.jsonl'
    incident_rows = [json.loads(line) for line in incident_path.read_text().splitlines()] if incident_path.exists() else []
    interrupted = {t for e in incident_rows if 'account_usage_limit' in e.get('kind', '') for t in e.get('affected_trials', [])}
    rows = []
    for trial in design['trials']:
        root=base/trial['trial_id']; paths=sorted((root/'states').glob('*.json'))
        try: state=read(paths[-1])
        except json.JSONDecodeError: state=read(paths[-2])
        best, baseline = state['best'], state['baseline']
        row={**trial,'step':state['step'],'tokens':best['tokens'],'raw_heartbeats':best['raw_heartbeats'],
             'local_cost':best['rank_numerator']/(2*baseline['tokens']*baseline['raw_heartbeats']),
             'status':'running' if trial['trial_id'] in queue['active'] else 'pending'}
        if (root/'summary.json').exists():
            summary=read(root/'summary.json');row.update(status=summary['status'],final_valid=summary['final_valid'])
        rows.append(row)
        for checkpoint in [3,6,10]:
            path=root/f'states/{checkpoint:03}.json';key=(root.name,checkpoint)
            if path.exists() and key not in seen:
                try: value=read(path)
                except json.JSONDecodeError: continue
                best, baseline=value['best'],value['baseline']
                event={'observed_at':now(),'trial_id':root.name,'checkpoint':checkpoint,
                    'local_cost':best['rank_numerator']/(2*baseline['tokens']*baseline['raw_heartbeats']),
                    'tokens':best['tokens'],'raw_heartbeats':best['raw_heartbeats']}
                with milestones.open('a') as stream: stream.write(json.dumps(event)+'\n')
                seen.add(key)
    print(json.dumps({'at':now(),'completed_proposals':sum(r['step'] for r in rows),'trials':rows}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['setup','readiness','prepare','post-runtime','audit','progress']);parser.add_argument('cohort',type=Path)
    args=parser.parse_args();globals()[args.command.replace('-', '_')](args.cohort.resolve())
