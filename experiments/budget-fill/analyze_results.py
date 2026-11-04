#!/usr/bin/env python3
"""Post-run evidence audit; no API, Lean execution, runtime edits or paid retry.

Finalization requires a finished, exited manager. It preserves the original
comparison/finished bytes before adding an explicit audited terminal annotation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ARMS = ('control', 'adaptive')
ROWS = (6, 45, 48)
CAP = Decimal('3')


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def score(value, baseline):
    return 100 - 100 / 3 * (value['tokens'] / baseline['tokens']
                          + value['raw_heartbeats'] / baseline['raw_heartbeats'])


def assert_manager_exited(root, probe=os.kill):
    started = read(root / 'operator/started.json')
    finished = read(root / 'operator/finished.json')
    require(finished.get('status') in ('completed', 'needs_review'), 'Manager has no terminal finished record')
    pid = started.get('pid')
    require(type(pid) is int and pid > 1, 'Invalid manager PID')
    try:
        probe(pid, 0)
    except ProcessLookupError:
        return {'pid': pid, 'process_exited': True, 'finished_status': finished['status']}
    except PermissionError as exc:
        raise ValueError('Cannot verify manager exit; do not finalize') from exc
    raise ValueError('Manager is still alive; do not finalize or modify results')


def terminal_flags(trials):
    require(len(trials) == 6 and {(t['arm'], t['row']) for t in trials}
            == {(a, r) for a in ARMS for r in ROWS}, 'Need exactly all six authorized trials')
    terminal = all(t['receipt_audit_passed'] and t['proof_audit_passed']
                   and t['status'] in ('completed', 'stopped') for t in trials)
    return {'all_trials_terminal': terminal,
            'all_trials_completed': all(t['status'] == 'completed' for t in trials),
            'completed_trials': sum(t['status'] == 'completed' for t in trials),
            'stopped_trials': sum(t['status'] == 'stopped' for t in trials)}


def checked_metrics(summary, baseline_result, final_result, metrics):
    baseline, final = metrics(baseline_result), metrics(final_result)
    require(baseline is not None and final is not None, 'Invalid baseline/final measurement')
    require(baseline == summary['baseline'] and final == summary['final'],
            'Summary score inputs differ from actual evaluator measurements')
    require(len(baseline['raw_samples']) == len(final['raw_samples']) == 3,
            'Expected three actual baseline and final HB samples')
    return baseline, final


def tail_observation(state, summary, steps, baseline):
    reduced = [s for s in steps if s['reduced_output']]
    if not reduced:
        return {'reduced_calls': 0, 'tail_cost_usd': '0', 'first_reduced_step': None,
                'selected_source_created_in_tail': False,
                'incremental_selected_primary_screening_score_delta': 0.0}
    first = reduced[0]
    previous = next((s for s in steps if s['step'] == first['step'] - 1), None)
    require(previous is not None, 'Tail reduction unexpectedly began before an initial incumbent existed')
    before_sha = previous['best_sha256_after']
    require(first['request_best_sha256'] == before_sha, 'Tail incumbent differs between preceding event and actual request')
    candidates = list(state['exploration']['candidates'].values())
    before = next(c for c in candidates if c['sha256'] == before_sha and c['valid'])
    selected_sha = summary['selected']['sha256']
    selected = next(c for c in candidates if c['sha256'] == selected_sha and c['valid'])
    first_seen = min(c['step'] for c in candidates if c['sha256'] == selected_sha and c['valid'])
    unchanged = before_sha == selected_sha
    return {'reduced_calls': len(reduced), 'first_reduced_step': first['step'],
        'cost_before_tail_usd': first['spent_before_usd'],
        'tail_cost_usd': str(sum((Decimal(s['cost_usd']) for s in steps if s['step'] >= first['step']), Decimal(0))),
        'pre_tail_best_sha256': before_sha,
        'pre_tail_best_primary_screening': {k: before[k] for k in ('tokens', 'raw_heartbeats')},
        'selected_source_first_seen_step': first_seen,
        'selected_source_created_in_tail': first_seen >= first['step'],
        'selected_source_unchanged_from_pre_tail': unchanged,
        'incremental_selected_primary_screening_score_delta': 0.0 if unchanged else score(selected, baseline)-score(before, baseline),
        'score_delta_scope': 'Within-trajectory primary screening measurements; not independently remeasured counterfactual or causal policy effect.',
        'calls': [{k: s[k] for k in ('step', 'output_tokens', 'spent_before_usd', 'reservation_usd', 'cost_usd', 'valid_candidate', 'best_sha256_after', 'finish_reason')} for s in reduced]}


def load_frozen(root):
    runtime = root / 'runtime'
    sys.path[:0] = [str(runtime / 'src'), str(runtime / 'experiments/final-batch-next'),
                    str(runtime / 'experiments/budget-fill')]
    path = runtime / 'experiments/budget-fill/run_experiment.py'
    spec = importlib.util.spec_from_file_location('audited_budget_run', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify(root)
    d = module.load_driver(root)
    require(Path(d.__file__).resolve() == (runtime / 'experiments/final-batch-next/driver.py').resolve(),
            'Different driver already imported; use a fresh process')
    reporter = importlib.import_module('report')
    require(Path(reporter.__file__).resolve() == (runtime / 'experiments/final-batch-next/report.py').resolve(),
            'Different reporter already imported')
    return module, d, reporter


def audit_run(root):
    """Read-only audit of the complete, already-finished run."""
    module, d, reporter = load_frozen(root)
    from budget_policy import fit_output
    protocol = read(root / 'protocol.json')
    require(protocol['rows'] == list(ROWS) and protocol['arms'] == list(ARMS), 'Unexpected experiment scope')
    original_comparison = read(root / 'comparison.json')
    original_finished = read(root / 'operator/finished.json')
    require(original_comparison.get('audit_passed') is True and original_finished.get('audit_passed') is True,
            'Frozen coordinator audit failed; investigate instead of bypassing it')
    manifests = {}
    def record(path):
        path = Path(path)
        relative = str(path.relative_to(root))
        manifests[relative] = digest(path)
    for relative in ('protocol.json', 'experiment-frozen.json', 'operator/started.json',
                     'operator/finished.json', 'comparison.json'):
        record(root / relative)
    generations, trials, arm_reports = set(), [], {}
    for row in ROWS:
        for name in ('problem.json', 'config.json', 'action-corpus.json', 'context-metadata.json', 'prompt.txt'):
            require(digest(d.folder(root/'control', row)/'input'/name)
                    == digest(d.folder(root/'adaptive', row)/'input'/name), f'Paired input differs F{row:03}/{name}')
    for arm in ARMS:
        armroot = root / arm
        d.verify_frozen(armroot)
        auth = read(armroot / 'authorization.json')
        require(auth['rows'] == list(ROWS) and Decimal(auth['per_problem_target_usd']) == CAP
                and auth['last_call_may_overshoot'] is False, 'Authorization/cap changed')
        for name in ('authorization.json', 'frozen.json', 'pricing.json', 'ledger.json'):
            record(armroot / name)
        ledger = read(armroot / 'ledger.json')
        require(not (armroot / 'stop-unknown-cost.json').exists(), 'Unresolved billing marker')
        require(all(v['row'] in ROWS and v['status'] == 'settled' and v.get('cost_usd') is not None
                    for v in ledger['attempts'].values()), 'Unknown, unresolved or out-of-scope billing')
        arm_report = reporter.build_report(armroot)
        require(arm_report['audit_passed'], f'{arm}: frozen proof/receipt audit failed: {arm_report["audit_errors"]}')
        arm_reports[arm] = arm_report
        for row in ROWS:
            folder = d.folder(armroot, row)
            summary, state = read(folder/'summary.json'), read(folder/'state.json')
            config, problem = read(folder/'input/config.json'), read(folder/'input/problem.json')
            require(summary['status'] in ('completed', 'stopped') and state['unknown_cost'] is False,
                    f'{arm}/F{row:03}: no known terminal state')
            baseline, final = checked_metrics(summary, read(folder/'baseline/result.json'),
                                              read(folder/'final/result.json'), d.h.metrics)
            expected_envs = set(problem['environments'])
            chosen = summary['selected']['sha256']
            compatibility = read(folder/'compatibility'/chosen/'result.json')
            require(set(compatibility['environments']) == expected_envs
                    and compatibility['valid'] and summary['all_versions_valid']
                    and all(v['valid'] for v in compatibility['environments'].values()), 'Required-version verification missing')
            require(all(not v.get('cache') for v in read(folder/'final/result.json')['environments'].values()),
                    'Final measurement must be fresh')
            before, after = read(folder/'initial-environment-fingerprints.json'), read(folder/'final/environment-fingerprints.json')
            require(before.get('full_content_verification') and after.get('full_content_verification')
                    and before['environments'] == after['environments'], 'Full environment boundary fingerprints differ')
            items = sorted(((k, i) for k, i in ledger['attempts'].items() if i['row'] == row), key=lambda p:p[1]['step'])
            require([i['step'] for _, i in items] == list(range(1, summary['calls']+1)), 'Non-contiguous/repeated paid step inventory')
            reporter.audit_portfolio(folder, summary, items)
            spent = Decimal(0)
            maximum_reserved_total = Decimal(0)
            steps, transitions = [], []
            replay = {}
            d.h.portfolio.initialize(replay, config)
            for attempt, item in items:
                step = folder/'steps'/f"{item['step']:04}"
                body = read(step/'request.json')
                bound = d.transport.request_cost(body)
                reservation = Decimal(bound['reserved_usd'])
                require(read(step/'cost-bound.json') == bound and item['maximum_request_cost_usd'] == bound['reserved_usd'], 'Stored reservation differs from request')
                require(spent+reservation <= CAP and Decimal(item['cost_usd']) <= reservation, 'Hard reservation cap violated')
                maximum_reserved_total = max(maximum_reserved_total, spent+reservation)
                packet = json.loads(body['messages'][1]['content'])
                full = {**body, 'max_completion_tokens': config['model']['max_tokens']}
                expected = full
                if arm == 'adaptive' and packet.get('portfolio', {}).get('stops_at') is not None:
                    expected = fit_output(full, CAP-spent, d.transport.request_cost, protocol['minimum_output_tokens'])
                require(body == expected, 'Request output allowance differs from sealed arm policy')
                generation = item['response_id']
                require(generation and generation not in generations, 'Repeated/missing provider generation across trials')
                generations.add(generation)
                raw = read(step/'provider-response.json')
                event = read(step/'event.json')
                evaluated = (step/'selection-result.json').exists()
                valid = read(step/'selection-result.json')['valid'] if evaluated else None
                old_branch = replay['portfolio']['active']
                d.h.portfolio.record_progress(replay, config, evaluated)
                if old_branch != replay['portfolio']['active']:
                    transitions.append({'after_step': item['step'], 'from': old_branch, 'to': replay['portfolio']['active'],
                        'reason': replay['portfolio']['exits'][old_branch], 'calls': replay['portfolio']['calls'][old_branch],
                        'evaluations': replay['portfolio']['evaluations'][old_branch]})
                try:
                    json.loads(raw['choices'][0]['message']['content'])
                    invalid_json = False
                except (ValueError, KeyError, IndexError, TypeError):
                    invalid_json = True
                steps.append({'step': item['step'], 'branch': old_branch, 'spent_before_usd': str(spent),
                    'cost_usd': item['cost_usd'], 'reservation_usd': bound['reserved_usd'],
                    'output_tokens': body['max_completion_tokens'], 'reduced_output': body != full,
                    'finish_reason': raw['choices'][0].get('finish_reason'), 'invalid_json': invalid_json,
                    'valid_candidate': valid, 'request_best_sha256': packet['best']['sha256'], 'best_sha256_after': event['best_sha256']})
                spent += Decimal(item['cost_usd'])
            require(spent == Decimal(summary['cost_usd']) == Decimal(state['cost_usd']), 'Summary/state cost mismatch')
            terminal_reason = None
            next_stop = None
            if d.h.portfolio.finished(state):
                require(summary['stop_reason'] == d.h.portfolio.stop_reason(state, config), 'Terminal portfolio reason differs')
                terminal_reason = 'portfolio_progress_guard' if summary['status'] == 'stopped' else 'portfolio_quota_complete'
            else:
                require(d.h.portfolio.budget_phase(state['portfolio'], config), 'Nonterminal/non-budget stop needs manual investigation')
                body = d.make_request(state, problem, config, (folder/'input/prompt.txt').read_text())
                full_bound = d.transport.request_cost(body)
                minimum_bound = d.transport.request_cost({**body, 'max_completion_tokens': protocol['minimum_output_tokens']})
                policy_body = fit_output(body, CAP-spent, d.transport.request_cost, protocol['minimum_output_tokens']) if arm == 'adaptive' else body
                policy_bound = d.transport.request_cost(policy_body)
                require(spent+Decimal(policy_bound['reserved_usd']) > CAP, 'Budget stop left a dispatchable policy request')
                terminal_reason = 'next_request_reservation_exceeds_cap'
                next_stop = {'remaining_usd': str(CAP-spent), 'full_output_tokens': config['model']['max_tokens'],
                    'full_reservation_usd': full_bound['reserved_usd'], 'minimum_output_tokens': protocol['minimum_output_tokens'],
                    'minimum_reservation_usd': minimum_bound['reserved_usd'], 'policy_reservation_usd': policy_bound['reserved_usd']}
            trial = {'arm': arm, 'row': row, 'name': problem['name'], 'status': summary['status'],
                'stop_reason': summary['stop_reason'], 'audited_terminal_reason': terminal_reason,
                'portfolio_complete': summary['portfolio']['complete'], 'portfolio': summary['portfolio'],
                'model_settings': config['model'],
                'input_sha256': {name: digest(folder/'input'/name) for name in ('problem.json','config.json','prompt.txt','action-corpus.json')},
                'transitions': transitions, 'cost_usd': str(spent), 'calls': len(items),
                'target_2_8_to_2_9_reached': Decimal('2.8') <= spent <= Decimal('2.9'),
                'max_spent_plus_reservation_usd': str(maximum_reserved_total), 'baseline': baseline, 'final': final,
                'local_score_estimate': score(final, baseline), 'selected_sha256': chosen,
                'selected_step': summary['selected']['step'], 'required_versions': sorted(expected_envs),
                'truncations': [x['step'] for x in steps if x['finish_reason'] == 'length'],
                'invalid_json_steps': [x['step'] for x in steps if x['invalid_json']],
                'next_request_stop': next_stop, 'tail': tail_observation(state, summary, steps, baseline),
                'receipt_audit_passed': True, 'proof_audit_passed': True, 'official_evaluation': False}
            trials.append(trial)
            # Hash source evidence without copying private requests or responses.
            for path in folder.rglob('*'):
                if path.is_file() and path.suffix in ('.json', '.lean', '.log', '.txt'):
                    record(path)
    flags = terminal_flags(trials)
    require(flags['all_trials_terminal'], 'Not every trial has an audited terminal outcome')
    require(original_comparison['all_trials_completed'] == flags['all_trials_completed'], 'Original completion flag differs from evidence')
    total = sum((Decimal(t['cost_usd']) for t in trials), Decimal(0))
    require(total <= 18, 'Study stage-1 total cap exceeded')
    require(total == Decimal(original_comparison['known_total_usd']), 'Original total cost differs')
    pairs = []
    for row in ROWS:
        byarm = {t['arm']:t for t in trials if t['row']==row}
        pairs.append({'row':row, 'score_delta_adaptive_minus_control':byarm['adaptive']['local_score_estimate']-byarm['control']['local_score_estimate'],
            'cost_delta_adaptive_minus_control_usd':str(Decimal(byarm['adaptive']['cost_usd'])-Decimal(byarm['control']['cost_usd']))})
    result = {'schema':1, 'audit_passed':True, **flags, 'known_total_usd':str(total), 'trials':trials, 'pairs':pairs,
        'protocol':{key:protocol[key] for key in ('base_commit','rows','arms','total_cap_usd','per_problem_per_arm_cap_usd','minimum_output_tokens','model','cohort_reason','comparison')},
        'frozen_runtime_manifest_sha256':digest(root/'experiment-frozen.json'),
        'paired_mean_score_delta':sum(p['score_delta_adaptive_minus_control'] for p in pairs)/3,
        'official_evaluation':False, 'cost_basis':'provider usage times frozen public prices; invoice not verified',
        'limitations':['One stochastic trajectory per arm/problem; paired score differences are not causal estimates.',
            'Selected Final adaptation cohort; no unseen-holdout claim.',
            'Within-trajectory tail effects use primary screening metrics; no counterfactual rerun or fresh pre-tail remeasurement.',
            'Direct OpenAI evidence does not claim official OpenRouter provenance eligibility.']}
    return result, manifests


def report_text(result):
    lines = ['# Budget-fill pilot results', '',
        'Six authorized trials are terminal and audited. Portfolio quota completion remains a separate outcome; no trial was retried or relabeled to hide an incomplete scout.', '',
        f'Total settled model cost: **${result["known_total_usd"]}** (cap $18). Completed portfolios: {result["completed_trials"]}; verified stopped portfolios: {result["stopped_trials"]}. Costs use provider usage and frozen public prices, not a verified invoice.', '',
        '| Problem | Arm | Cost | Score | Status | Reduced calls | Tail cost | Selected source first created in tail |',
        '| --- | --- | ---: | ---: | --- | ---: | ---: | --- |']
    for t in sorted(result['trials'], key=lambda t:(t['row'], t['arm'])):
        tail=t['tail']
        lines.append(f'| F{t["row"]:03} | {t["arm"]} | ${t["cost_usd"]} | {t["local_score_estimate"]:.6f} | {t["status"]} | {tail["reduced_calls"]} | ${tail["tail_cost_usd"]} | {tail["selected_source_created_in_tail"]} |')
    lines += ['', '## Interpretation', '',
        f'The observed paired mean score difference is {result["paired_mean_score_delta"]:+.6f} points. This is one stochastic trajectory per arm/problem, so the difference does not isolate the output policy. More spending is not itself a score improvement.', '',
        'Tail attribution below compares the selected source with the incumbent immediately before output reduction. A same-source result has zero additional selected-proof gain; changed-source deltas use primary screening measurements and are not a remeasured counterfactual.', '']
    for t in result['trials']:
        if t['arm']!='adaptive':continue
        tail=t['tail']
        lines += [f'- F{t["row"]:03}: {tail["reduced_calls"]} reduced-output calls; additional tail cost ${tail["tail_cost_usd"]}; incremental selected primary-screening score delta {tail["incremental_selected_primary_screening_score_delta"]:+.6f}. Selected proof first created in the tail: {tail["selected_source_created_in_tail"]}.']
    lines += ['', '## Stops and verification', '']
    for t in sorted(result['trials'], key=lambda t:(t['row'],t['arm'])):
        stop=t['next_request_stop']
        desc=f'next policy reservation ${stop["policy_reservation_usd"]} exceeds remaining ${stop["remaining_usd"]}' if stop else t['audited_terminal_reason']
        lines.append(f'- {t["arm"]}/F{t["row"]:03}: saved `{t["status"]}/{t["stop_reason"]}`; {desc}; scout exits `{t["portfolio"].get("exits",{})}`. Required versions: {", ".join(t["required_versions"])}. Truncations {len(t["truncations"])}, invalid JSON {len(t["invalid_json_steps"])}.')
    lines += ['', 'Every selected proof passed every required version. Baseline/final score inputs match actual evaluator results, with three fresh final primary-version measurements. Receipt normalization, request/response hashes, hard reservations, routing, cache evidence, source/log hashes and full environment boundary fingerprints passed audit.', '',
        'Original runtime comparison and manager finished records are preserved with hashes. Post-analysis adds `all_trials_terminal` while preserving `all_trials_completed` and every original trial status. No frozen runtime, authorization, input, ledger or proof evidence was changed.', '',
        'Compact JSON, selected proofs and source-evidence hash manifest are under `results/20261103-exp1-r1/`. Raw private API requests/responses and credentials are not included. This is local research evidence, not an official evaluation or an OpenRouter-eligible submission claim.', '',
        'Reproduce the read-only audit with:', '',
        '```sh', 'python3 -B experiments/budget-fill/analyze_results.py audit --root /ABS/RUN', '```', '']
    return '\n'.join(lines)


def finalize(root, output, report_path):
    exit_evidence = assert_manager_exited(root)
    module, d, _ = load_frozen(root)
    with d.locked(root/'operator/manager.lock', blocking=False):
        assert_manager_exited(root)
        require(not output.exists(), 'Result package already exists; inspect before repeating finalization')
        require(not report_path.exists(), 'REPORT.md exists; do not overwrite a prior report')
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        post = root/'post-analysis'/timestamp
        post.mkdir(parents=True)
        original_hashes = {}
        for relative in ('comparison.json', 'operator/finished.json'):
            original = root/relative
            copy = post/'original'/relative
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, copy)
            original_hashes[relative] = digest(original)
            require(digest(copy) == original_hashes[relative], 'Original backup bytes differ')
        provenance = {'schema':1,'created_at':datetime.now(timezone.utc).isoformat(),
            'purpose':'Add audited terminal flag without changing quota-completion semantics',
            'analyzer_sha256':digest(Path(__file__)), 'manager_exit':exit_evidence,
            'original_sha256':original_hashes, 'api_calls':0,'lean_executions':0,'paid_retries':0}
        write_json(post/'provenance.json', provenance)
        try:
            result, manifest = audit_run(root)
        except Exception as exc:
            write_json(post/'audit-failure.json', {'error_type':type(exc).__name__,'message':str(exc),
                                                 'comparison_updated':False})
            raise
        # No source input may change between audit and annotation/export.
        for relative, expected in manifest.items():
            require(digest(root/relative)==expected, 'Evidence changed during post-analysis: '+relative)
        output.mkdir(parents=True)
        write_json(output/'summary.json', result)
        write_json(output/'source-evidence-manifest.json', {'run_id':root.name,'files_sha256':manifest,
            'content_policy':'Hashes only; raw provider/request content is not exported'})
        for trial in result['trials']:
            path=output/'selected-proofs'/trial['arm']/f'F{trial["row"]:03}.lean'
            path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(root/trial['arm']/'problems'/f'F{trial["row"]:03}'/'selected.lean',path)
            require(digest(path)==trial['selected_sha256'],'Exported proof differs from audited selection')
        text=report_text(result)
        (output/'REPORT.md').write_text(text)
        report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(text)
        comparison=read(root/'comparison.json')
        comparison.update(all_trials_terminal=result['all_trials_terminal'],
            post_analysis={'provenance':str(post.relative_to(root)/'provenance.json'),
                'compact_result_sha256':digest(output/'summary.json'),
                'quota_completion_preserved':True,'completed_trials':result['completed_trials'],
                'stopped_trials':result['stopped_trials']})
        require(comparison['all_trials_completed']==result['all_trials_completed'],'Completion flag changed')
        write_json(root/'comparison.json',comparison)
        # Keep original manager finished/status bytes unchanged, including needs_review.
        provenance.update(audit_passed=True,all_trials_terminal=result['all_trials_terminal'],
            all_trials_completed=result['all_trials_completed'],comparison_sha256_after=digest(root/'comparison.json'),
            compact_result_sha256=digest(output/'summary.json'),manager_finished_unchanged=digest(root/'operator/finished.json')==original_hashes['operator/finished.json'])
        write_json(post/'provenance.json',provenance)
        write_json(output/'post-analysis-provenance.json',provenance)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('audit','finalize'))
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--report',type=Path,default=HERE/'REPORT.md')
    args=parser.parse_args();root=args.root.resolve()
    if args.command=='audit':
        assert_manager_exited(root)
        result,_=audit_run(root)
    else:
        output=(args.output or HERE/'results'/root.name).resolve()
        result=finalize(root,output,args.report.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
