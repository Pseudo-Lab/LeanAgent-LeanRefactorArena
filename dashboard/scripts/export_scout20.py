"""Publish completed scout run plus independently labelled best-of-run dashboard.
No model/compiler execution. Private receipts stay local; exported evidence is hashed.
"""
import argparse,copy,json,sys
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import mean
from export_final_results import ROWS,read,digest,require,score,audit_candidate

def export(current, historical, repo):
    runtime=current/'runtime'
    sys.path[:0]=[str(runtime/'src'),str(runtime/'experiments/final-batch-next')]
    import driver,report
    driver.verify_frozen(current)
    audit=report.build_report(current)
    require(audit['audit_passed'] and not audit['audit_errors'] and len(audit['rows'])==20,'Current receipt audit failed')
    initial_ledger=read(Path(driver.PRIOR_RUN['root'])/'ledger.json')['attempts']
    previous_root=historical/'final-batch-fast/20261102-strata-leanpool-usd3-r1'
    previous_mean=mean(float(score(read(previous_root/'problems'/f'F{n:03}'/'summary.json'))) for n in ROWS)
    ledger=read(current/'ledger.json')['attempts'];require(all(v['status']=='settled' for v in ledger.values()),'Pending calls')
    old=read(repo/'dashboard/public/data/final-results.json')
    # Repeated export takes the original baseline view, never its own output.
    saved=repo/'experiments/main-scout20/prior-dashboard.json'
    if saved.exists():old=read(saved)
    else:saved.parent.mkdir(parents=True,exist_ok=True);saved.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    registry=read(runtime/'configs/final-environments.local.json')['environments']
    rows=[];out=[];stages=defaultdict(lambda:dict(calls=0,evaluated=0,valid=0,gain=0.0));improved=[]
    for n in ROWS:
        f=current/'problems'/f'F{n:03}';c=audit_candidate(current,n,allow_budget_stop=True);s=c['summary'];inc=next(p for p in old['problems'] if p['row']==n)
        previous_root=historical/('final-batch-fast' if inc['runId']=='20261102-strata-leanpool-usd3-r1' else 'final-batch')/inc['runId']
        prior=audit_candidate(previous_root,n)
        require(prior['summary']['selected']['sha256']==inc['candidateHash'] and abs(float(score(prior['summary']))-inc['score'])<1e-9,'Incumbent evidence differs')
        require(prior['problem']==c['problem'] and prior['fingerprints']==c['fingerprints'] and prior['tokenizer']==c['tokenizer'],'Incomparable environment')
        total_cost=driver.problem_spend(read(current/'ledger.json'),n)+Decimal(driver.PRIOR_RUN['costs_usd'].get(str(n),'0'))
        points=[];best=100/3;known={driver.a.sha(c['problem']['reference']):best};largest={'gain':0,'step':0,'stage':'baseline'}
        for step in sorted((f/'steps').glob('*')):
            if not (step/'event.json').exists():continue
            event=read(step/'event.json');packet=json.loads(read(step/'request.json')['messages'][1]['content']);stage=packet['portfolio']['branch'];stats=stages[stage];stats['calls']+=1
            result=read(step/'selection-result.json') if (step/'selection-result.json').exists() else None
            value=None
            if result is not None:
                stats['evaluated']+=1
                if result['valid']:
                    stats['valid']+=1;m=driver.h.metrics(result);value=100-100/3*(m['tokens']/s['baseline']['tokens']+m['raw_heartbeats']/s['baseline']['raw_heartbeats']);known[digest(step/'candidate.lean')]=value
            previous=best;best=known.get(event['best_sha256'],best);gain=max(0,best-previous);stats['gain']+=gain
            if gain>largest['gain']:largest={'gain':gain,'step':event['step'],'stage':stage}
            points.append({'step':event['step'],'stage':stage,'action':(event.get('action') or {}).get('action','invalid'),'candidateScore':value,'bestScore':best,'evaluated':result is not None,'valid':result.get('valid') if result else None,'costUsd':event['cost_usd_after']})
        current_score=float(score(s));rows.append({'row':n,'name':s['name'],'status':s['status'],'stopReason':s['stop_reason'],'score':current_score,'priorDashboardScore':inc['score'],'baseline':s['baseline'],'candidate':s['final'],'proofHash':s['selected']['sha256'],'costUsd':str(total_cost),'calls':s['calls'],'evaluations':sum(s['portfolio']['evaluations'].values()),'largestGain':largest,'points':points,'evidence':c['evidence'],'compilerRecords':c['compilerRecords'],'versions':c['fingerprints']})
        selected=copy.deepcopy(inc);selected['currentRunCostUsd']=str(total_cost)
        selected['alternatives']=[*inc['alternatives'],{'runId':current.name,'score':current_score,'candidateHash':s['selected']['sha256']}]
        if current_score>inc['score']+1e-9:
            improved.append(n);p=c['problem'];selected.update(runId=current.name,proof=c['proof'],candidateHash=s['selected']['sha256'],baseline=s['baseline'],candidate=s['final'],score=current_score,measuredAt=s['finished_at'],evidence=c['evidence'],compilerRecords=c['compilerRecords'],tokenizer=c['tokenizer'],implementationRunId=current.name,versions=[{'version':registry[e]['version'],'revision':registry[e]['revision'],'status':'pass','environment':e,'fingerprint':c['fingerprints'][e]} for e in p['environments']])
        out.append(selected)
        for directory,code in [('solutions/final20',selected['proof']),('solutions/main-scout20',c['proof'])]:
            target=repo/directory;target.mkdir(parents=True,exist_ok=True);(target/f'F{n:03}.lean').write_text(code)
    payload={'schemaVersion':1,'runId':current.name,'officialEvaluation':False,'singleRunMean':mean(p['score'] for p in rows),'previousSingleRunMean':previous_mean,'priorDashboardMean':mean(p['score'] for p in old['problems']),'bestOfRunsMean':mean(p['score'] for p in out),'improvedRows':improved,'combinedCostUsd':audit['combined_known_total_usd'],'initialFailedRunCostUsd':audit['prior_known_total_usd'],'continuationCostUsd':audit['known_total_usd'],'calls':len(ledger),'initialFailedRunCalls':len(initial_ledger),'auditPassed':True,'statuses':dict(Counter(p['status'] for p in rows)),'stages':dict(stages),'problems':rows,'limitations':['Scores use each paired original baseline; minor HB differences retained.','Trajectory candidates are primary-version estimates; final score is fresh3 and all-version checked.','Comparison with previous run is not paired: this run deducted initial failed-call costs on three problems.','Best-of-runs dashboard is not a deployable harness result.','PR67 rounds/merger-until-budget disabled; PR69 pilot is separate.']}
    manifest=copy.deepcopy(old);manifest.update(runId=current.name,generatedAt=max(read(current/'problems'/f'F{n:03}'/'summary.json')['finished_at'] for n in ROWS),costUsd=audit['combined_known_total_usd'],apiCalls=len(initial_ledger)+len(ledger),problems=out,selectionPolicy='Best verified score per problem across archived runs; not one harness execution',singleRunMean=payload['singleRunMean'],bestOfRunsMean=payload['bestOfRunsMean'])
    manifest['implementation']={str(Path(k).relative_to(runtime)):v for k,v in read(current/'frozen.json').items() if Path(k).is_relative_to(runtime)}
    manifest['historicalImplementation']=old['implementation'];manifest['olderHistoricalImplementation']=old.get('historicalImplementation',{})
    for path,value in [(repo/'dashboard/public/data/final-results.json',manifest),(repo/'dashboard/public/reports/scout20.json',payload),(repo/'experiments/main-scout20/results.json',payload)]:
        path.parent.mkdir(parents=True,exist_ok=True);text=json.dumps(value,ensure_ascii=False,indent=2)+'\n';require('/Users/' not in text and 'sk-proj-' not in text,'Private path or key in export');path.write_text(text)
    (repo/'solutions/final20/submission.jsonl').write_text(''.join(json.dumps({'name':p['name'],'proof':p['proof']},ensure_ascii=False)+'\n' for p in out))
    (repo/'solutions/main-scout20/submission.jsonl').write_text(''.join(json.dumps({'name':p['name'],'proof':(repo/'solutions/main-scout20'/f"F{p['row']:03}.lean").read_text()},ensure_ascii=False)+'\n' for p in rows))
    print(json.dumps({k:v for k,v in payload.items() if k not in ['problems','limitations','stages']},ensure_ascii=False));print('stages',dict(stages))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--current',type=Path,required=True);ap.add_argument('--historical',type=Path,required=True);ap.add_argument('--repo',type=Path,required=True);a=ap.parse_args();export(a.current.resolve(),a.historical.resolve(),a.repo.resolve())
