#!/usr/bin/env python3
"""Export audited final20 proof evidence; never makes model or compiler calls."""
import argparse
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import median

ROWS = [*range(1, 11), *range(41, 51)]
SHA = 'd53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682'

def read(p):
    return json.loads(p.read_text())

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def score(s):
    b, f = s['baseline'], s['final']
    return 100 - Fraction(100, 3) * (Fraction(f['tokens'], b['tokens']) + Fraction(f['raw_heartbeats'], b['raw_heartbeats']))

def audit_result(path, code, expected_envs, metrics=None):
    result = read(path)
    require(result['valid'] and set(result['environments']) == set(expected_envs), f'{path.name}: incomplete versions')
    if metrics is not None:
        require(result['tokens'] == metrics['tokens'], 'Token measurement mismatch')
    records = []
    for env, value in result['environments'].items():
        require(value['valid'], 'Invalid environment result')
        samples = []
        for run in value['runs']:
            require(run['returncode'] == 0 and not run['timed_out'], 'Compiler failure')
            folder = path.parent / env
            for key in ['source', 'log']:
                require(Path(run[key]).name == run[key], 'Unsafe evidence path')
                require(digest(folder / run[key]) == run[key + '_sha256'], 'Compiler evidence hash mismatch')
            if run['source'] == 'check.lean':
                require(code.strip() in (folder / run['source']).read_text(), 'Proof differs from compiled source')
            if 'measurement' in run:
                samples.append(run['measurement']['raw'])
            records.append({'environment': env, **{k: run[k] for k in ['source', 'source_sha256', 'log', 'log_sha256']},
                            'compilerSetupSha256': run.get('compiler_setup_sha256')})
        require(any(x['source'] == 'check.lean' for x in value['runs']), 'Missing compile check')
        if metrics is not None:
            require(not value.get('cache') and len(samples) == 3 and samples == metrics['raw_samples']
                    and median(samples) == metrics['raw_heartbeats'] == value['median_raw_heartbeats'], 'Fresh three-sample measurement mismatch')
    return records

def audit_candidate(root, row, *, allow_budget_stop=False):
    folder = root / 'problems' / f'F{row:03}'
    problem, s = read(folder / 'input/problem.json'), read(folder / 'summary.json')
    code = (folder / 'selected.lean').read_text()
    require(problem['row'] == row and problem['dataset_sha256'] == SHA, 'Problem identity mismatch')
    require((s['status'] == 'completed' or allow_budget_stop and s['status'] == 'stopped' and s.get('stop_reason') == 'next_request_would_exceed_budget') and s['all_versions_valid'], 'Incomplete candidate')
    require(digest(folder / 'selected.lean') == s['selected']['sha256'], 'Selected proof hash mismatch')
    start, end = [read(folder / name) for name in ['initial-environment-fingerprints.json', 'final/environment-fingerprints.json']]
    require(start['full_content_verification'] and end['full_content_verification']
            and start['environments'] == end['environments'] and set(start['environments']) == set(problem['environments']), 'Environment boundary mismatch')
    paths = ['input/problem.json', 'summary.json', 'initial-environment-fingerprints.json', 'final/environment-fingerprints.json',
             'baseline/result.json', 'final/result.json', 'reference-compatibility/result.json', f"compatibility/{s['selected']['sha256']}/result.json"]
    records = {}
    for name, proof, envs, metrics in [
        ('baseline/result.json', problem['reference'], problem['environments'][:1], s['baseline']),
        ('final/result.json', code, problem['environments'][:1], s['final']),
        ('reference-compatibility/result.json', problem['reference'], problem['environments'], None),
        (paths[-1], code, problem['environments'], None),
    ]:
        records[name] = audit_result(folder / name, proof, envs, metrics)
    require(read(folder / 'baseline/result.json')['tokenizer'] == read(folder / 'final/result.json')['tokenizer'], 'Tokenizer mismatch')
    return {'root': root, 'problem': problem, 'summary': s, 'proof': code, 'fingerprints': start['environments'],
            'evidence': [{'path': f'problems/F{row:03}/{name}', 'sha256': digest(folder / name)} for name in paths],
            'compilerRecords': records, 'tokenizer': read(folder / 'final/result.json')['tokenizer']}

def export(runtime, current, previous, repo):
    report = read(current / 'report.json')
    require(report['audit_passed'] and report['all_completed'] and report['completed'] == 20
            and not report['audit_errors'] and sorted(x['row'] for x in report['rows']) == ROWS, 'Run audit is not complete')
    ledger = read(current / 'ledger.json')['attempts']
    require(all(x['status'] == 'settled' and x.get('cost_usd') is not None for x in ledger.values()), 'Unsettled billing')
    costs = {row: sum((Decimal(x['cost_usd']) for x in ledger.values() if x['row'] == row), Decimal(0)) for row in ROWS}
    require(all(0 <= c <= 3 for c in costs.values()) and sum(costs.values()) <= 60
            and sum(costs.values()) == Decimal(report['known_total_usd']), 'Budget mismatch')
    frozen = read(current / 'frozen.json')
    for name, sha in frozen.items():
        require(digest(Path(name)) == sha, 'Frozen implementation/input changed')
    registry = read(runtime / 'configs/final-environments.local.json')['environments']
    out = []
    proof_dir = repo / 'solutions/final20'
    proof_dir.mkdir(parents=True, exist_ok=True)
    for row in ROWS:
        candidate = audit_candidate(current, row)
        options = [candidate]
        old_path = previous / 'problems' / f'F{row:03}' / 'summary.json'
        if old_path.exists():
            old = audit_candidate(previous, row)
            require(old['problem'] == candidate['problem'] and old['fingerprints'] == candidate['fingerprints']
                    and old['tokenizer'] == candidate['tokenizer'], 'Historical evidence is not comparable')
            options.append(old)
        selected = max(options, key=lambda c: score(c['summary']))
        p, s = selected['problem'], selected['summary']
        versions = [{'version': registry[e]['version'], 'revision': registry[e]['revision'], 'status': 'pass',
                     'environment': e, 'fingerprint': selected['fingerprints'][e]} for e in p['environments']]
        baseline_versions = read(selected['root'] / 'problems' / f'F{row:03}' / 'reference-compatibility/result.json')
        baseline_compatibility = 100 if baseline_versions['valid'] and set(baseline_versions['environments']) == set(p['environments']) else None
        record = {'row': row, 'name': p['name'], 'source': p['source'], 'runId': selected['root'].name,
                  'proofPath': f'solutions/final20/F{row:03}.lean', 'proof': selected['proof'], 'candidateHash': s['selected']['sha256'],
                  'baseline': s['baseline'], 'candidate': s['final'], 'versions': versions,
                  'baselineCompatibility': baseline_compatibility, 'measuredAt': s['finished_at'],
                  'score': float(score(s)), 'currentRunCostUsd': str(costs[row]),
                  'alternatives': [{'runId': c['root'].name, 'score': float(score(c['summary'])), 'candidateHash': c['summary']['selected']['sha256']} for c in options],
                  'evidence': selected['evidence'], 'compilerRecords': selected['compilerRecords'], 'tokenizer': selected['tokenizer'],
                  'implementationRunId': selected['root'].name}
        (proof_dir / f'F{row:03}.lean').write_text(selected['proof'])
        out.append(record)
    manifest = {'schemaVersion': 1, 'datasetSha256': SHA, 'runId': current.name,
                'generatedAt': max(read(current / 'problems' / f'F{n:03}' / 'summary.json')['finished_at'] for n in ROWS),
                'officialEvaluation': False, 'costUsd': report['known_total_usd'], 'costBasis': report['api_cost_basis'],
                'invoiceVerified': False, 'auditPassed': True, 'apiCalls': len(ledger),
                'implementation': {str(Path(k).relative_to(runtime)): v for k, v in frozen.items() if not str(Path(k).relative_to(runtime)).startswith('runs/')},
                'historicalImplementation': {str(Path(k).relative_to(runtime)): v for k, v in read(previous / 'frozen.json').items() if not str(Path(k).relative_to(runtime)).startswith('runs/')},
                'problems': out}
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    require('/Users/' not in text and 'sk-proj-' not in text, 'Private data in public manifest')
    (repo / 'dashboard/public/data/final-results.json').write_text(text)
    (proof_dir / 'submission.jsonl').write_text(''.join(json.dumps({'name': p['name'], 'proof': p['proof']}, ensure_ascii=False) + '\n' for p in out))
    print(json.dumps({'count': len(out), 'cost': manifest['costUsd'], 'mean_score': sum(p['score'] for p in out)/len(out),
                      'historical_rows': [p['row'] for p in out if p['runId'] != current.name]}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['runtime', 'current', 'previous', 'repo']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    export(args.runtime.resolve(), args.current.resolve(), args.previous.resolve(), args.repo.resolve())
