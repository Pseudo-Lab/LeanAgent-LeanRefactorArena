"""Compact coordinator-only snapshot; never show diagnostic data to a solver."""
import argparse
import json
from pathlib import Path
import time


def snapshot(base):
    design = json.loads((base / 'design.frozen.json').read_text())
    rows, pending = [], []
    log = base / 'summary-dispatch.jsonl'
    assigned = {(e['trial_id'], e['step']) for e in
                (json.loads(line) for line in log.read_text().splitlines())
                if e['event'] == 'dispatched'} if log.exists() else set()
    for trial in design['trials']:
        root = base / trial['trial_id']
        states = sorted((root / 'states').glob('*.json'))
        row = {'trial': root.name, 'step': 0, 'final': None}
        if states:
            try:
                state = json.loads(states[-1].read_text())
            except json.JSONDecodeError:
                state = json.loads(states[-2].read_text())
            best, baseline = state['best'], state['baseline']
            row.update(step=state['step'], cost=round(best['rank_numerator'] /
                       (2 * baseline['tokens'] * baseline['raw_heartbeats']), 6))
        if (root / 'summary.json').exists():
            row['final'] = json.loads((root / 'summary.json').read_text())['final_valid']
        current = root / f'steps/{row["step"] + 1:03}/evaluation/fixed'
        if current.exists():
            row['evaluating_step'] = row['step'] + 1
            row['completed_compile_logs'] = len(list(current.glob('*.log')))
        if (root / 'final/fixed').exists() and row['final'] is None:
            row['final_compile_logs'] = len(list((root / 'final/fixed').glob('*.log')))
        for request in sorted((root / 'steps').glob('*/summary/request.json')):
            step = int(request.parent.parent.name)
            if (not (request.parent / 'response.json').exists()
                    and not (request.parent / 'receipt.json').exists()
                    and (root.name, step) not in assigned):
                pending.append({'trial_id': root.name, 'step': step, 'request': str(request)})
        rows.append(row)
    return {'completed_proposals': sum(r['step'] for r in rows),
            'finalized_trials': sum(r['final'] is not None for r in rows),
            'pending_summaries': pending, 'trials': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('--wait', type=float, default=0)
    args = parser.parse_args()
    assert 0 <= args.wait <= 50
    base = args.cohort.resolve()
    initial = snapshot(base)
    end = time.monotonic() + args.wait
    value = initial
    def event_key(item):
        return item['completed_proposals'], item['finalized_trials'], item['pending_summaries']
    while (not value['pending_summaries'] and event_key(value) == event_key(initial)
           and time.monotonic() < end):
        time.sleep(1)
        value = snapshot(base)
    state = base / 'coordinator-state.json'
    if state.exists():
        active = json.loads(state.read_text())['active']
        value['active'] = [r for r in value.pop('trials') if r['trial'] in active]
    print(json.dumps(value))
