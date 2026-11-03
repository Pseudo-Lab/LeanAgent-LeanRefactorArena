#!/usr/bin/env python3
"""Export audited final20 attempt history as a portable, offline HTML report.

Reads existing artifacts only. No model calls, Lean execution or raw API export.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROWS = list(range(1, 11)) + list(range(41, 51))


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(value, baseline):
    return 100 - 100 / 3 * (value['tokens'] / baseline['tokens']
                           + value['raw_heartbeats'] / baseline['raw_heartbeats'])


def rank(value):
    return value['rank_numerator'], value['tokens'], value['sha256']


def export_problem(root, row, attempts):
    folder = root / 'problems' / f'F{row:03}'
    state, summary = read(folder / 'state.json'), read(folder / 'summary.json')
    if summary['status'] != 'completed' or not summary['all_versions_valid']:
        raise ValueError('Problem lacks completed compatible proof')
    if len(summary['final']['raw_samples']) != 3:
        raise ValueError('Final measurement must have three samples')
    baseline = state['baseline']
    candidates = state['exploration']['candidates']
    best = candidates['c000']
    history = state['exploration']['history']
    if len(history) != len(attempts) or len(history) != state['calls']:
        raise ValueError('Attempt/history count differs')
    for candidate in candidates.values():
        if hashlib.sha256(candidate['code'].encode()).hexdigest() != candidate['sha256']:
            raise ValueError('Candidate source hash differs')
    points = [{'step': 0, 'cost': 0, 'best': score(best, baseline),
               'candidate': None, 'outcome': 'baseline', 'action': 'baseline',
               'length': best['tokens'], 'hb': best['raw_heartbeats'],
               'gain': 0, 'strategy': '원본 기준 풀이'}]
    spend = Decimal(0)
    for expected, history_row in enumerate(history, 1):
        step = history_row['step']
        if step != expected or step not in attempts:
            raise ValueError('Missing or unordered attempt')
        attempt = attempts[step]
        if attempt['status'] != 'settled' or attempt.get('cost_usd') is None:
            raise ValueError('Unsettled attempt')
        spend += Decimal(attempt['cost_usd'])
        event = read(folder / 'steps' / f'{step:04}' / 'event.json')
        if (event['step'] != step or Decimal(event['cost_usd_after']) != spend
                or Decimal(history_row['cost_usd_after']) != spend):
            raise ValueError('Step cost differs from ledger')
        candidate_id = history_row.get('candidate_id')
        candidate = candidates[candidate_id] if candidate_id else None
        previous = score(best, baseline)
        if candidate and candidate['valid'] and rank(candidate) < rank(best):
            best = candidate
        if event['best_sha256'] != best['sha256']:
            raise ValueError('Reconstructed best differs from saved event')
        action = (event.get('action') or {}).get('action', 'rejected')
        outcome = ('valid' if candidate['valid'] else 'invalid') if candidate else (
            'rejected' if history_row.get('rejection') else 'lookup')
        points.append({'step': step, 'cost': float(spend), 'best': score(best, baseline),
            'candidate': score(candidate, baseline) if candidate and candidate['valid'] else None,
            'outcome': outcome, 'action': action, 'candidateId': candidate_id,
            'length': candidate.get('tokens') if candidate else None,
            'hb': candidate.get('raw_heartbeats') if candidate else None,
            'gain': score(best, baseline) - previous,
            'strategy': candidate.get('strategy', '') if candidate else '',
            'parentId': candidate.get('parent_id') if candidate else None})
    if spend != Decimal(state['cost_usd']) or spend != Decimal(summary['cost_usd']) or spend > 3:
        raise ValueError('Per-problem spend mismatch/overspend')
    return {'row': row, 'id': f'F{row:03}', 'group': 'Strata' if row <= 10 else 'LeanPool',
        'name': summary['name'], 'calls': state['calls'], 'costUsd': str(spend),
        'baseline': baseline, 'final': summary['final'],
        'finalScore': score(summary['final'], baseline),
        'finalSourceSha256': summary['selected']['sha256'],
        'evidence': {'stateSha256': sha(folder / 'state.json'),
                     'summarySha256': sha(folder / 'summary.json')}, 'points': points}


def export(root):
    audit = read(root / 'report.json')
    if not audit['audit_passed'] or not audit['all_completed'] or audit['problem_count'] != 20:
        raise ValueError('A passing, complete final20 audit is required')
    ledger = read(root / 'ledger.json')['attempts']
    if set(v['row'] for v in ledger.values()) != set(ROWS):
        raise ValueError('Unexpected cohort')
    problems = []
    for row in ROWS:
        entries = [v for v in ledger.values() if v['row'] == row]
        attempts = {v['step']: v for v in entries}
        if len(attempts) != len(entries):
            raise ValueError('Duplicate attempt step')
        problems.append(export_problem(root, row, attempts))
    total = sum((Decimal(p['costUsd']) for p in problems), Decimal(0))
    if total != Decimal(audit['known_total_usd']) or total > 60:
        raise ValueError('Aggregate cost differs from audited total')
    result = {'schemaVersion': 1, 'runId': root.name, 'datasetSha256': audit['dataset_sha256'],
        'totalCostUsd': str(total), 'totalCalls': len(ledger), 'problemCount': 20,
        'costBasis': 'provider token usage × frozen list prices; not invoice verified',
        'scoreFormula': '100 - (100/3) × (length/original_length + raw_HB/original_raw_HB)',
        'measurement': 'Exploration: one sample; final: three fresh samples. Invalid candidates have no score.',
        'auditSha256': sha(root / 'report.json'), 'ledgerSha256': sha(root / 'ledger.json'),
        'problems': problems}
    text = json.dumps(result, ensure_ascii=False)
    if '/Users/' in text or '/private/' in text or 'sk-' in text:
        raise ValueError('Private-path/credential-like content in public export')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = export(args.root.resolve())
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    template = Path(__file__).with_name('final20_trajectories.html').read_text()
    assert template.count('/*__TRAJECTORY_DATA__*/null') == 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template.replace('/*__TRAJECTORY_DATA__*/null', payload))
    args.output.with_suffix('.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: data[k] for k in ('runId', 'problemCount', 'totalCalls', 'totalCostUsd')}))


if __name__ == '__main__':
    main()
