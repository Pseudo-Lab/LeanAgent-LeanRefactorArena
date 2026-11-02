"""Read-only progress snapshot; never starts or resumes a solver or Lean job."""
import argparse
import json
from pathlib import Path


def main(base):
    design=json.loads((base/'design.frozen.json').read_text())
    ledger=base/'amendments/canonical-parent-order/invocations.jsonl'
    calls=[json.loads(line) for line in ledger.read_text().splitlines() if line] if ledger.exists() else []
    for spec in design['planned_trials']:
        root=base/spec['id'];states=sorted((root/'states').glob('*.json'))
        if not states:
            print(spec['id'],'initializing');continue
        state=json.loads(states[-1].read_text());best=state['best'];b=state['baseline']
        summary=root/'summary.json'
        status=json.loads(summary.read_text())['status'] if summary.exists() else 'ready'
        if not summary.exists() and (root/f"steps/{state['step']+1:03}/response.json").exists():
            status='evaluation pending (running or lock wait)'
            trial_calls=[c for c in calls if c['trial_id']==spec['id']]
            if trial_calls:
                last=trial_calls[-1]
                if (last['status']=='failed' and last.get('step_before')==state['step']
                    and last.get('error')=='Less than 1 GiB free; coordinator must inspect'
                    and not (root/f"steps/{state['step']+1:03}/evaluation").exists()):
                    status='paused: storage preflight; no Lean evaluation for pending proposal'
        elif not summary.exists() and state['step']==design['proposal_budget']:
            status='awaiting final verification'
        cost=best['rank_numerator']/(2*b['tokens']*b['raw_heartbeats'])
        print(f"{spec['id']} {state['step']}/{design['proposal_budget']} "
              f"valid={sum(a['valid'] for a in state['attempts'])} "
              f"tokens={best['tokens']} raw={best['raw_heartbeats']} cost={cost:.6f} {status}")


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('cohort',type=Path)
    main(ap.parse_args().cohort)
