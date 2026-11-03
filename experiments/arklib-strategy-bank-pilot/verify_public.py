#!/usr/bin/env python3
"""Check the published package without API, Lean, credentials, or the private archives."""
import csv,hashlib,importlib.util,json,statistics,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'runtime/src'))
from lean_agent import openai_direct

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(root=ROOT):
    root=Path(root);r=read(root/'results.json');spec=importlib.util.spec_from_file_location('public_tokens',root/'runtime/evaluator-adapter/temp3_tokens.py');tokens=importlib.util.module_from_spec(spec);spec.loader.exec_module(tokens)
    manifest=read(root/'artifact-manifest.json')
    for name,expected in manifest['files'].items():
        if sha(root/name)!=expected['sha256']:raise ValueError('Artifact hash mismatch: '+name)
    runtime=read(root/'runtime-manifest.json')
    for name,expected in runtime['files'].items():
        if sha(root/name)!=expected['sha256']:raise ValueError('Runtime hash mismatch')
    payload=[json.loads(x) for x in (root/'submission.jsonl').read_text().splitlines()];rows=r['problems'];names=[x['name'] for x in rows]
    if len(rows)!=10 or len(set(names))!=10 or set(names)!={x['name'] for x in payload} or len(payload)!=10:raise ValueError('Expected 10 unique final problems')
    totals={'initial':Decimal(0),'problem07_rerun':Decimal(0)};calls=0;combinations=0
    for row in rows:
        proof=(root/row['proof_file']).read_text();original=(root/row['original_file']).read_text();tokens.validate_declaration(proof,row['statement'])
        if sha(root/row['proof_file'])!=row['proof_sha256'] or sha(root/row['original_file'])!=row['original_sha256']:raise ValueError('Proof hash mismatch')
        if tokens.proof_tokens(proof,row['statement'])!=row['selected_tokens'] or tokens.proof_tokens(original,row['statement'])!=row['original_tokens']:raise ValueError('Token mismatch')
        if next(x['proof'] for x in payload if x['name']==row['name'])!=proof:raise ValueError('JSONL differs from Lean file')
        evidence=root/'evidence'/row['name'];measurements=read(evidence/'measurements.json');ratios=[]
        expected={k:v for x in row['version_info'] for k,v in x.items()}
        if set(expected)!={x['version'] for x in measurements}:raise ValueError('Required-version mismatch')
        for e in measurements:
            if e['source_revision']!=expected[e['version']]:raise ValueError('Source pin mismatch')
            for label in ('baseline','selected'):
                m=e[label]
                if not m['valid'] or len(m['raw_hb_samples'])!=3 or m['raw_hb_median']!=statistics.median(m['raw_hb_samples']):raise ValueError('Invalid/missing measurements')
                reports=[x['measurement'] for x in m['runs'] if 'measurement' in x]
                if [x['raw'] for x in reports]!=m['raw_hb_samples'] or any(not set(x['axioms'])<={'propext','Classical.choice','Quot.sound'} for x in reports):raise ValueError('Axiom/sample mismatch')
                if any(x['timed_out'] or x['returncode']!=0 for x in m['runs']):raise ValueError('Failed selected compiler record')
            ratios.append(e['selected']['raw_hb_median']/e['baseline']['raw_hb_median']);combinations+=1
        length=100*(1-row['selected_tokens']/row['original_tokens']);hb=100*(1-statistics.mean(ratios));score=(length+hb+100)/3
        for actual,want in [(row['length_reduction_pct'],length),(row['hb_reduction_pct_mean_within_version'],hb),(row['local_combined_score'],score)]:
            if abs(actual-want)>1e-9:raise ValueError('Metric arithmetic mismatch')
        records=read(evidence/'costs.json')['calls'];spent={};seen=set()
        for c in records:
            key=(c['run'],c['step'])
            if key in seen:raise ValueError('Duplicate request')
            seen.add(key);cost=Decimal(openai_direct.compute_cost({'model':c['model'],'service_tier':c['service_tier'],'usage':c['usage']})['cost_usd']);reserve=Decimal(c['reserved_usd']);prior=spent.get(c['run'],Decimal(0))
            cap=Decimal('2.241848') if row['index']==1 and c['run']=='initial' else Decimal('2.50')
            if cost!=Decimal(c['cost_usd']) or cost>reserve or prior+reserve>cap:raise ValueError('Cost/reservation mismatch')
            spent[c['run']]=prior+cost;totals[c['run']]+=cost;calls+=1
        if sum(spent.values(),Decimal(0))!=Decimal(row['total_cost_usd']):raise ValueError('Problem total mismatch')
    if totals['initial']!=Decimal(r['initial_cost_usd']) or totals['problem07_rerun']!=Decimal(r['problem07_rerun_cost_usd']) or sum(totals.values())!=Decimal(r['total_cost_usd']):raise ValueError('Batch total mismatch')
    if totals['initial']+Decimal(r['initial_unknown_reservation_usd'])>Decimal('25') or totals['problem07_rerun']>Decimal('2.50'):raise ValueError('Batch envelope exceeded')
    ranked=read(root/'evidence/problem07-ranked-checks.json');candidates=ranked['ranked_candidates']
    if [x['rank'] for x in candidates]!=list(range(1,20)) or [x['core_ratio_sum'] for x in candidates]!=sorted(x['core_ratio_sum'] for x in candidates):raise ValueError('Rank order mismatch')
    if any(x['compatibility_status']!='rejected' for x in candidates[:-1]) or candidates[-1]['candidate_id']!='c000' or not candidates[-1]['selected']:raise ValueError('Ranked selection mismatch')
    if calls!=r['api_calls'] or combinations!=25:raise ValueError('Count mismatch')
    if abs(statistics.mean(x['local_combined_score'] for x in rows)-r['mean_score'])>1e-9:raise ValueError('Mean score mismatch')
    return {'public_consistency_passed':True,'problems':10,'problem_version_combinations':25,'api_calls':calls,'total_cost_usd':str(sum(totals.values())),'problem07_generated_rejections':18,'lean_called':False,'model_called':False}
if __name__=='__main__':print(json.dumps(verify(),ensure_ascii=False))
