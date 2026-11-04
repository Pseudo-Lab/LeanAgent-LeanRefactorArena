#!/usr/bin/env python3
"""Offline reconcile paid pilot raw provider usage, reservations, run receipts and selected hashes."""
from decimal import Decimal
import argparse,hashlib,json
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO/'src'))
from lean_agent import openai_direct,budgeting,artifacts

def read(p):return json.loads(p.read_text())
def audit(root):
    ledger=read(root/'budget.json');plan=read(root/'plan.json');items={r['name']:r for r in plan['problems']}
    spent=Decimal(0);by_problem={};requests=set()
    for row in ledger['calls']:
        if row['status']!='settled':raise ValueError('Unsettled request: '+row['key'])
        name=row['problem'];step=row['step'];item=items[name]
        request_path=root/'runs'/f"{item['index']:02}"/'steps'/f'{step:03}'/'request.json'
        body=read(request_path);bound=budgeting.request_cost(body)
        if Decimal(bound['reserved_usd'])!=Decimal(row['reserved_usd']):raise ValueError('Reservation mismatch')
        raw=read(root/'provider-responses'/name/(str(step)+'.json'));receipt=openai_direct.compute_cost(raw)
        if Decimal(receipt['cost_usd'])!=Decimal(row['charged_usd']):raise ValueError('Raw provider cost mismatch')
        normalized=read(request_path.parent/'response.json')
        if normalized!=openai_direct.normalize(raw):raise ValueError('Normalized receipt mismatch')
        if Decimal(row['charged_usd'])>Decimal(row['reserved_usd']):raise ValueError('Charge exceeded reservation')
        if spent+Decimal(row['reserved_usd'])>Decimal(ledger['total_cap_usd']):raise ValueError('Pre-dispatch total reservation exceeded cap')
        cap=Decimal(ledger.get('problem_caps',{}).get(name,ledger['problem_cap_usd']))
        if by_problem.get(name,Decimal(0))+Decimal(row['reserved_usd'])>cap:raise ValueError('Pre-dispatch problem reservation exceeded cap')
        if row['key'] in requests:raise ValueError('Duplicate request')
        requests.add(row['key']);spent+=Decimal(row['charged_usd'])
        by_problem[name]=by_problem.get(name,Decimal(0))+Decimal(row['charged_usd'])
    for name,value in by_problem.items():
        if value>Decimal(ledger.get('problem_caps',{}).get(name,ledger['problem_cap_usd'])):raise ValueError('Problem cap exceeded')
    prior=Decimal(ledger.get('prior_unsettled_reservation_usd','0'))
    if spent+prior>Decimal('25'):raise ValueError('Total envelope exceeded')
    results=read(root/'results.json') if (root/'results.json').exists() else []
    for row in results:
        src=(root/'selected'/f"{row['index']:02}.lean").read_bytes()
        if hashlib.sha256(src).hexdigest()!=row['selected_sha256']:raise ValueError('Selected source hash mismatch')
        if Decimal(row['cost_usd'])!=by_problem.get(row['name'],Decimal(0)):raise ValueError('Run cost mismatch')
        run_result=read(root/'runs'/f"{row['index']:02}"/'result.json')
        if not run_result['replay']['record_replay_passed']:raise ValueError('Common receipt replay did not pass')
        measured=read(root/'verification'/f"{row['index']:02}"/row['selection']/'result.json')
        if set(measured['environments'])!=set(items[row['name']]['required_versions']):raise ValueError('Missing required versions')
        if not row['all_versions_valid'] or not measured['valid']:raise ValueError('Selected proof is not fully valid')
        for env in measured['environments'].values():
            if not env['valid']:raise ValueError('Selected environment failed')
            if len([r for r in env['runs'] if 'measurement' in r])!=3:raise ValueError('Missing final HB samples')
    return {'offline_audit_passed':True,'model_called':False,'lean_called':False,'settled_calls':len(requests),
            'calculated_cost_usd':str(spent),'prior_unknown_reserved_usd':str(prior),'encumbered_total_usd':str(spent+prior),
            'completed_problems':len(results),'planned_problems':len(items),'all_problems_complete':len(results)==len(items),'invoice_verified':False,'problem_cost_usd':{k:str(v) for k,v in by_problem.items()}}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();v=audit(a.root);a.output.write_text(json.dumps(v,ensure_ascii=False,indent=2));print(json.dumps(v,ensure_ascii=False))
