"""Record actual fresh-agent dispatch/completion; never launch solvers itself."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def main(base, command, trial_id, agent):
    path = base / 'coordinator-state.json'
    now = datetime.now(timezone.utc).isoformat()
    if command == 'init':
        assert not path.exists()
        trials = json.loads((base / 'design.frozen.json').read_text())['trials']
        state = {'phase': 'running', 'pending': [t['trial_id'] for t in trials],
                 'active': {}, 'completed': []}
        event = None
    else:
        state = json.loads(path.read_text())
        if command == 'dispatch':
            assert agent and len(state['active']) < 2
            assert state['pending'].pop(0) == trial_id
            record = {'agent': agent, 'dispatched_at': now}
            state['active'][trial_id] = record
            event = {'event': 'dispatched', 'trial_id': trial_id, **record}
        else:
            summary = json.loads((base / trial_id / 'summary.json').read_text())
            assert summary['proposal_count'] == 10 and (base / trial_id / 'artifacts.json').exists()
            record = state['active'].pop(trial_id)
            state['completed'].append(trial_id)
            event = {'event': 'completed', 'trial_id': trial_id, 'agent': record['agent'],
                     'observed_at': now, 'final_valid': summary['final_valid']}
            if not state['active'] and not state['pending']:
                state['phase'] = 'auditing'
    if event:
        with (base / 'dispatch.jsonl').open('a') as stream:
            stream.write(json.dumps(event) + '\n')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(path)
    print(json.dumps(state))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('command', choices=['init', 'dispatch', 'complete'])
    parser.add_argument('trial_id', nargs='?')
    parser.add_argument('agent', nargs='?')
    args = parser.parse_args()
    main(args.cohort.resolve(), args.command, args.trial_id, args.agent)
