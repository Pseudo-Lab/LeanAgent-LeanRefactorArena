#!/usr/bin/env python3
"""Read-only audit/export of original ArkLib archives; no model or Lean calls."""
import argparse,csv,difflib,hashlib,importlib.util,json,statistics,sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'runtime/src'))
from lean_agent import artifacts as a,harness,openai_direct

def read(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def export(initial,rerun,ranked,dataset,out):
    out.mkdir(parents=True,exist_ok=True)
    helper=module('archive_helpers',ROOT/'runtime/experiments/strategy-bank-pilot/run.py')
    lean=module('lean_agent.evaluator.export_frozen',initial/'code/temp3_lean.py')
    tokenizer=module('export_tokens',initial/'code/temp3_tokens.py')
    lean.WRAPPER=lean.WRAPPER.replace('axioms.toList.map Name.toString','axioms.toList.map _root_.Lean.Name.toString')
    lean.proof_tokens=tokenizer.proof_tokens;lean.validate_declaration=tokenizer.validate_declaration
    plan=read(initial/'plan.json')
    if digest(dataset)!=plan['dataset_sha256']:raise ValueError('Dataset SHA mismatch')
    records={r['name']:r for r in map(json.loads,dataset.read_text().splitlines())}
    replacements=[(str(initial),'<INITIAL_RUN>'),(str(rerun),'<PROBLEM07_RERUN>'),(str(ranked),'<RANKED_CHECKS>'),(str(Path.home()),'<LOCAL_HOME>')]
    def public(value):
        if isinstance(value,str):
            for old,new in replacements:value=value.replace(old,new)
            return value
        if isinstance(value,list):return [public(x) for x in value]
        if isinstance(value,dict):return {k:public(v) for k,v in value.items()}
        return value
    costs={}
    for label,root in [('initial',initial),('problem07_rerun',rerun)]:
        ledger=read(root/'budget.json');running=Decimal(0);by_problem={};keys=set()
        for c in ledger['calls']:
            if c['status']!='settled' or c['key'] in keys:raise ValueError('Unsettled/duplicate API call')
            keys.add(c['key']);rawpath=root/'provider-responses'/c['problem']/(str(c['step'])+'.json');raw=read(rawpath)
            receipt=openai_direct.compute_cost(raw);paid=Decimal(receipt['cost_usd']);reserve=Decimal(c['reserved_usd'])
            prior=by_problem.get(c['problem'],Decimal(0));cap=Decimal(ledger.get('problem_caps',{}).get(c['problem'],ledger['problem_cap_usd']))
            if paid!=Decimal(c['charged_usd']) or paid>reserve or prior+reserve>cap or running+reserve>Decimal(ledger['total_cap_usd']):raise ValueError('Cost/reservation audit failed')
            running+=paid;by_problem[c['problem']]=prior+paid
            costs.setdefault(c['problem'],[]).append({'run':label,'step':c['step'],'reserved_usd':str(reserve),'cost_usd':str(paid),'model':raw['model'],'service_tier':raw['service_tier'],'usage':raw['usage'],'raw_response_sha256':digest(rawpath),'receipt_cost_basis':receipt['basis']})
    initial_rows=read(initial/'results.json');final7=read(ranked/'result.json');rank_rows=read(ranked/'ranked-candidates.json');summary7=read(rerun/'runs/07/summary.json')
    archive7=summary7['state']['exploration']['candidates'];env7={e['id']:e for e in read(rerun/'inputs/07/environments.json')}
    rank_provenance=[]
    for row in rank_rows:
        cid=row['candidate_id'];candidate=archive7[cid]
        if candidate['sha256']!=row['sha256']:raise ValueError('Ranked candidate SHA mismatch')
        for version,check in row['checked_versions'].items():
            value=helper.cached_verification(lean,env7[version],candidate['code'],read(rerun/'inputs/07/problem.json'),Path(check['receipt']).parent,3)
            if value is None or value['valid']!=check['valid']:raise ValueError('Ranked receipt audit failed')
            rank_provenance.append({'rank':row['rank'],'candidate_id':cid,'version':version,'valid':value['valid'],'result_sha256':digest(Path(check['receipt'])),'error':public(value['environments'][version].get('error'))})
    write(out/'evidence/problem07-ranked-checks.json',{'source_result_sha256':digest(ranked/'result.json'),'ranked_candidates':public(rank_rows),'checks':rank_provenance,'selected_id':final7['selected_id'],'selected_rank':final7['selected_rank'],'additional_api_cost_usd':'0'})
    rows=[];versions=[];submission=[];all_replay=[]
    for item in plan['problems']:
        i=item['index'];name=item['name'];raw=records[name];run=initial/'runs'/f'{i:02}';problem=read(run/'input/problem.json');original=raw['src']
        replay=harness.replay(run)
        if not replay['record_replay_passed']:raise ValueError('Common replay failed')
        all_replay.append({'index':i,**replay})
        selected_row=next(x for x in initial_rows if x['index']==i);proof=(initial/'selected'/f'{i:02}.lean').read_text();chosen=selected_row['selection']
        if i==7:proof=(ranked/'selected.lean').read_text();chosen='rerun-ranked/'+final7['selected_id']
        tokenizer.validate_declaration(proof,raw['statement']);t0=tokenizer.proof_tokens(original,raw['statement']);t=tokenizer.proof_tokens(proof,raw['statement'])
        if sha:=hashlib.sha256(proof.encode()).hexdigest():
            expected=final7['selected_sha256'] if i==7 else selected_row['selected_sha256']
            if sha!=expected:raise ValueError('Selected proof hash mismatch')
        envs=read(initial/'inputs'/f'{i:02}'/'environments.json');measurement=[];hb_ratios=[]
        for e in envs:
            if i==7:
                folder=rerun/'version-checks'/e['id']/'baseline';bdir=cdir=folder
            else:
                bdir=initial/'verification'/f'{i:02}'/'baseline'/e['id'];cdir=initial/'verification'/f'{i:02}'/selected_row['selection']/e['id']
            b=helper.cached_verification(lean,e,original,problem,bdir,3);c=helper.cached_verification(lean,e,proof,problem,cdir,3)
            if b is None or c is None or not b['valid'] or not c['valid']:raise ValueError('Final version receipt missing/failed')
            def metrics(value):
                erow=value['environments'][e['id']];samples=[x['measurement']['raw'] for x in erow['runs'] if 'measurement' in x]
                return {'tokens':value['tokens'],'raw_hb_samples':samples,'raw_hb_median':statistics.median(samples),'valid':erow['valid'],'runs':public(erow['runs'])}
            bm,cm=metrics(b),metrics(c);ratio=cm['raw_hb_median']/bm['raw_hb_median'];hb_ratios.append(ratio)
            erow={'version':e['id'],'source_revision':e['sourceRevision'],'toolchain':e['toolchain'],'source_sha256':e['source_sha256'],'template_sha256':hashlib.sha256(e['template'].encode()).hexdigest(),'baseline':bm,'selected':cm,'baseline_result_sha256':digest(bdir/'result.json'),'selected_result_sha256':digest(cdir/'result.json')};measurement.append(erow)
            versions.append({'index':i,'name':name,'version':e['id'],'original_tokens':t0,'selected_tokens':t,'original_raw_hb':bm['raw_hb_median'],'selected_raw_hb':cm['raw_hb_median'],'hb_reduction_pct':100*(1-ratio),'valid':True})
        initial_cost=sum((Decimal(c['cost_usd']) for c in costs[name] if c['run']=='initial'),Decimal(0));rerun_cost=sum((Decimal(c['cost_usd']) for c in costs[name] if c['run']=='problem07_rerun'),Decimal(0));length=100*(1-t/t0);hb=100*(1-statistics.mean(hb_ratios));primary=next(x for x in measurement if x['version']=='v4.31.0');fname=name+'.lean'
        row={'index':i,'name':name,'source':'arklib','file_path':raw['file_path'],'statement':raw['statement'],'selection':chosen,'status':'original_retained_after_ranked_rejections' if i==7 else 'improved_all_versions','proof_file':'proofs/'+fname,'original_file':'originals/'+fname,'proof_sha256':sha,'original_sha256':hashlib.sha256(original.encode()).hexdigest(),'original_tokens':t0,'selected_tokens':t,'representative_version':'v4.31.0','representative_original_raw_hb':primary['baseline']['raw_hb_median'],'representative_selected_raw_hb':primary['selected']['raw_hb_median'],'length_reduction_pct':length,'hb_reduction_pct_mean_within_version':hb,'compatibility_pct':100,'passed_versions':len(measurement),'required_versions':len(measurement),'local_combined_score':(length+hb+100)/3,'initial_cost_usd':str(initial_cost),'problem07_rerun_cost_usd':str(rerun_cost),'total_cost_usd':str(initial_cost+rerun_cost),'budget_usd_by_run':['2.50','2.50'] if i==7 else ['2.50'],'api_calls':len(costs[name]),'input_policy':'single_reference_with_version_info' if 'version_info' in problem else 'legacy_duplicate_reference','version_info':raw['version_info']}
        for label,text in [('proofs',proof),('originals',original)]:
            p=out/label/fname;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        diff=out/'diffs'/(name+'.patch');diff.parent.mkdir(exist_ok=True);diff.write_text(''.join(difflib.unified_diff(original.splitlines(True),proof.splitlines(True),fromfile='original.lean',tofile='selected.lean')))
        folder=out/'evidence'/name;write(folder/'measurements.json',measurement);write(folder/'costs.json',{'invoice_verified':False,'cost_basis':'provider token usage times frozen public list prices','calls':costs[name]});write(folder/'config.json',public(read(run/'input/config.json')));write(folder/'source-replay.json',replay)
        (folder/'prompt.txt').write_text(public((run/'input/prompt.txt').read_text()))
        review=initial/'reviews'/f'{i:02}.json'
        if review.exists():write(folder/'source-review.json',public(read(review)))
        rows.append(row);submission.append({'name':name,'proof':proof})
    replay=harness.replay(rerun/'runs/07')
    if not replay['record_replay_passed']:raise ValueError('Rerun replay failed')
    write(out/'evidence/problem07-rerun-core-result.json',public(read(rerun/'result.json')))
    write(out/'evidence/problem07-rerun-selection-policy.json',public(read(rerun/'selection-policy.json')))
    initial_total=sum((Decimal(r['initial_cost_usd']) for r in rows),Decimal(0));extra=sum((Decimal(r['problem07_rerun_cost_usd']) for r in rows),Decimal(0));held=Decimal(read(initial/'budget.json')['prior_unsettled_reservation_usd'])
    result={'scope':'ArkLib 10; 20-card contextual top-1 single-arm pilot; standalone problem07 rerun and ranked compatibility selection','dataset_sha256':digest(dataset),'initial_runtime_base_commit':'7d537bf0dbf67e58fe6edcc3209f8feff3f66cbb','selection_reference_commit':'a517db26b8eee1b58f30810dca5d66000c810748','model':'gpt-6.1-sol','reasoning_effort':'high','provider':'OpenAI direct','official_evaluation':False,'invoice_verified':False,'score_definition':'(length reduction % + mean of per-version HB reduction % + compatibility %) / 3','representative_hb_display':'v4.31.0, median of 3 fresh-process samples; combined score uses all designated versions','initial_cost_usd':str(initial_total),'problem07_rerun_cost_usd':str(extra),'total_cost_usd':str(initial_total+extra),'initial_unknown_reservation_usd':str(held),'total_with_unknown_reservation_usd':str(initial_total+extra+held),'mean_score':statistics.mean(r['local_combined_score'] for r in rows),'mean_length_reduction_pct':statistics.mean(r['length_reduction_pct'] for r in rows),'mean_hb_reduction_pct':statistics.mean(r['hb_reduction_pct_mean_within_version'] for r in rows),'required_problem_version_combinations':len(versions),'api_calls':sum(r['api_calls'] for r in rows),'problems':rows}
    write(out/'results.json',result);write(out/'pricing.json',openai_direct.PRICING)
    fields=[k for k in rows[0] if k not in ('statement','version_info')]
    for name,items,columns in [('results.csv',rows,fields),('metrics-by-version.csv',versions,list(versions[0]))]:
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(items)
    (out/'submission.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in submission))
    for name in ('verification-policy-update.json','verification-order-update.json','input-policy-update.json'):
        if (initial/name).exists():write(out/'evidence'/name,public(read(initial/name)))
    write(out/'audit.json',{'passed':True,'model_called':False,'lean_called':False,'original_archive_audit':True,'source_log_context_hashes_checked':True,'raw_api_costs_recomputed':True,'pre_dispatch_reservations_checked':True,'common_record_replay_runs':len(all_replay)+1,'selected_proofs':len(rows),'required_problem_version_combinations':len(versions),'samples_per_valid_proof_per_version':3,'problem07_ranked_generated_rejections':final7['rejected_candidates'],'raw_archives_included':False,'public_summary_limit':'Public files permit arithmetic/hash/usage audits; full compiler logs and provider response bodies remain in the original local archives.'})
    print(json.dumps({k:result[k] for k in ('total_cost_usd','mean_score','api_calls','required_problem_version_combinations')}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--initial',type=Path,required=True);p.add_argument('--rerun',type=Path,required=True);p.add_argument('--ranked',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT);x=p.parse_args();export(x.initial.resolve(),x.rerun.resolve(),x.ranked.resolve(),x.dataset.resolve(),x.output.resolve())
