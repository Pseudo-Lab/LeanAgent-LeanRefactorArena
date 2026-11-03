#!/usr/bin/env python3
"""Export immutable run receipts into distinct recommendation/selection/edit/verification rows."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

def read(p):return json.loads(p.read_text())
def export(run):
    problem=read(run/'input/problem.json')
    rows=[]; previous_cost=Decimal('0')
    for folder in sorted((run/'steps').iterdir()):
        if not (folder/'event.json').exists():continue
        request=json.loads(read(folder/'request.json')['messages'][1]['content'])
        event=read(folder/'event.json');state=event['state_after'];action=event.get('action') or {}
        bank=request.get('strategy_bank',{})
        recommended=[c['id'] for c in bank.get('strategies',[])]
        selected=action.get('strategy_ids',[])
        feedback=(state.get('latest') or {}).get('feedback') or {}
        candidate=folder/'candidate.lean'
        evaluation=read(folder/'evaluation/result.json') if (folder/'evaluation/result.json').exists() else {}
        environments=evaluation.get('environments',{})
        cost=Decimal(state['cost_usd'])
        rows.append({'schema_version':2,'problem_id':problem['name'],'attempt_id':folder.name,
            'bank_sha256':bank.get('bank_sha256'),'recommended_ids':recommended,
            'selected_ids':selected,'selected_not_recommended':sorted(set(selected)-set(recommended)),
            'selection_status':'declared' if 'strategy_ids' in action else 'not_reported',
            'candidate_written':candidate.exists(),
            'application_status':'unreviewed' if selected and candidate.exists() else 'not_established',
            'verification_status':feedback.get('status'),'verified':feedback.get('valid'),
            'verification_scope':'attempt_receipt_only',
            'attempted_environment_ids':sorted(environments),
            'verified_environment_ids':sorted(k for k,v in environments.items() if v['valid']),
            'measured_samples_by_environment':{k:sum('measurement' in r for r in v['runs']) for k,v in environments.items()},
            'all_required_versions_status':'not_established_by_attempt_trace',
            'metrics':feedback.get('metrics'),'attribution':'joint',
            'cost_usd_incremental':None if state.get('unknown_cost') else str(cost-previous_cost),
            'cost_usd_cumulative':None if state.get('unknown_cost') else str(cost),
            'request_ref':str(folder/'request.json'),'event_ref':str(folder/'event.json'),
            'candidate_ref':str(candidate) if candidate.exists() else None})
        previous_cost=cost
    return rows
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();rows=export(args.run)
    with args.output.open('x') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print('Exported '+str(len(rows))+' receipt rows; application is not automatically verified.')
