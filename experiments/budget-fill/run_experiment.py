#!/usr/bin/env python3
"""Frozen, paired API pilot for conservative output-budget tail fitting."""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
ROWS = [6, 45, 48]
ARMS = ['control', 'adaptive']
CAP = Decimal('3.00')
BASE = 'a517db26b8eee1b58f30810dca5d66000c810748'

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp-' + str(os.getpid()))
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n'); os.replace(tmp, p)

def load_driver(root):
    rt = root / 'runtime'
    sys.path[:0] = [str(rt/'src'), str(rt/'experiments/final-batch-next'), str(rt/'experiments/budget-fill')]
    d = importlib.import_module('driver'); d.TARGET = CAP
    return d

def verify(root):
    p = read(root/'protocol.json')
    if p['rows'] != ROWS or p['arms'] != ARMS or p['total_cap_usd'] != '18.00':
        raise ValueError('Protocol differs from authorized scope')
    for rel, digest in read(root/'experiment-frozen.json').items():
        if sha(root/rel) != digest: raise ValueError('Frozen source changed: '+rel)
    return p

def prepare(root, envrepo, slots):
    from baseline_snapshot import verify_baseline_snapshot
    if root.exists(): raise ValueError('Fresh experiment root required')
    verify_baseline_snapshot(REPO, BASE)  # Fail before making any run directory.
    rt = root/'runtime'; rt.mkdir(parents=True)
    for directory in ['src', 'examples/actions', 'experiments/final-batch-next', 'experiments/proof-analyze', 'experiments/budget-fill']:
        shutil.copytree(REPO/directory, rt/directory, ignore=shutil.ignore_patterns('__pycache__'))
    baseline_verification = verify_baseline_snapshot(REPO, BASE, source_root=rt)
    (rt/'sources').mkdir(); (rt/'sources/final').symlink_to(envrepo/'sources/final', target_is_directory=True)
    (rt/'configs').mkdir(); shutil.copyfile(envrepo/'configs/final-environments.local.json',rt/'configs/final-environments.local.json')
    save(root/'protocol.json', {'base_commit':BASE,'baseline_verification':baseline_verification,'rows':ROWS,'arms':ARMS,'total_cap_usd':'18.00',
        'per_problem_per_arm_cap_usd':'3.00','minimum_output_tokens':2048,'model':'gpt-6.1-sol',
        'api_slots':str(slots.resolve()),'environment_repo':str(envrepo.resolve()),
        'cohort_reason':'F006 medium prior score 62.75, F045 low 48.88, F048 low 48.36; Strata/LeanPool, original token lengths 972/1756/2879. Selected using prior main20; exploratory Final adaptation.',
        'comparison':'#67 merger-until-budget, scouts 6 each. Both arms use strict reservation guard in every phase. Adaptive only lowers output allowance when the normal full-output reservation will not fit; input bound unchanged. Both start from original.',
        'cost_basis':'OpenAI provider usage times frozen public list prices; not invoice verified or official eligible submission.',
        'limitations':'One trajectory per arm/problem, selected cohort; no significance or generalization claim.'})
    files=[p for p in rt.rglob('*') if p.is_file() and 'sources' not in p.relative_to(rt).parts and '__pycache__' not in p.parts]
    files.append(root/'protocol.json');save(root/'experiment-frozen.json',{str(p.relative_to(root)):sha(p) for p in files})
    d=load_driver(root)
    settings={**d.DEFAULT_PORTFOLIO,'merger_until_budget':True}
    for arm in ARMS:
        d.prepare(root/arm,ROWS,workers=1,portfolio_settings=settings)
        authpath=root/arm/'authorization.json'
        authorization=read(authpath);authorization['last_call_may_overshoot']=False
        authorization['strict_guard_scope']='all phases, coordinator-enforced'
        save(authpath,authorization)
        frozen=read(root/arm/'frozen.json');frozen[str(authpath)]=sha(authpath);save(root/arm/'frozen.json',frozen)
    verify(root)
    print(json.dumps({'prepared':str(root),'trials':6,'api_calls':0}),flush=True)

def install_hooks(root, arm, d):
    from budget_policy import fit_output
    protocol=verify(root)
    original_make, original_dispatch, original_check, original_verify = d.make_request,d.dispatch,d.check_dispatchable,d.verify_frozen
    def checked(path): verify(root); original_verify(path)
    d.verify_frozen=checked
    def check(path, ledger):
        if (root/'operator/stop.json').exists(): raise ValueError('Experiment stopped; no automatic paid retry')
        original_check(path,ledger)
        for other in ARMS:
            otherpath=root/other
            if otherpath.resolve()!=Path(path).resolve(): original_check(otherpath,read(otherpath/'ledger.json'))
    d.check_dispatchable=check
    @contextmanager
    def shared_slots(_):
        while True:
            acquired=False
            for number in range(2):
                try:
                    with d.locked(Path(protocol['api_slots'])/f'api-slot-{number}.lock',blocking=False):
                        acquired=True; yield; return
                except BlockingIOError:
                    if acquired: raise
            time.sleep(.25)
    d.api_slot=shared_slots
    def make(state, problem, config, prompt):
        body=original_make(state,problem,config,prompt)
        if arm=='adaptive' and d.h.portfolio.budget_phase(state['portfolio'],config):
            body=fit_output(body,CAP-Decimal(state['cost_usd']),d.transport.request_cost,protocol['minimum_output_tokens'])
        return body
    d.make_request=make
    def dispatch(path,row,step,body,model,stepdir):
        # run_problem holds an exclusive per-row lock for its entire lifetime.
        # No other dispatcher can add a charge to this row between guard and send.
        with d.locked(path/'ledger.lock'):
            ledger=read(path/'ledger.json');check(path,ledger)
            bound=Decimal(d.transport.request_cost(body)['reserved_usd'])
            if d.problem_spend(ledger,row)+bound>CAP: raise ValueError('Strict all-stage cap: request reservation will not fit')
        return original_dispatch(path,row,step,body,model,stepdir)
    d.dispatch=dispatch


def worker(root,arm,row,key):
    d=load_driver(root); install_hooks(root,arm,d)
    os.environ['OPENAI_API_KEY']=d.transport.load_key(key)
    d.run_with_preflight(root/arm,row,ensure=True)


def audit(root):
    d=load_driver(root);verify(root);report=importlib.import_module('report');outputs={}
    for arm in ARMS:
        d.verify_frozen(root/arm)
        data=report.build_report(root/arm)
        ledger=read(root/arm/'ledger.json')
        for row in ROWS:
            spent=Decimal(0)
            config=read(d.folder(root/arm,row)/'input/config.json')
            items=sorted((i for i in ledger['attempts'].values() if i['row']==row),key=lambda i:i['step'])
            for item in items:
                step=d.folder(root/arm,row)/'steps'/f"{item['step']:04}"
                body=read(step/'request.json');bound=d.transport.request_cost(body)
                packet=json.loads(body['messages'][1]['content'])
                full_body={**body,'max_completion_tokens':config['model']['max_tokens']}
                expected_body=full_body
                if arm=='adaptive' and packet.get('portfolio',{}).get('stops_at') is not None:
                    from budget_policy import fit_output
                    expected_body=fit_output(full_body,CAP-spent,d.transport.request_cost)
                if body!=expected_body:data['audit_errors'].append('Output allowance differs from sealed arm policy')
                if read(step/'cost-bound.json')!=bound: data['audit_errors'].append('Cost bound receipt differs')
                if spent+Decimal(bound['reserved_usd'])>CAP: data['audit_errors'].append('Hard reservation cap violated')
                spent+=Decimal(item['cost_usd'])
            if spent>CAP:data['audit_errors'].append('Settled cap violated')
        data['audit_passed']=not data['audit_errors'];save(root/arm/'report.json',data);outputs[arm]=data
    paired=[]
    for row in ROWS:
        pair={'row':row}
        for arm in ARMS:
            data=next(x for x in outputs[arm]['rows'] if x['row']==row)
            folder=d.folder(root/arm,row);cfg=read(folder/'input/config.json');state=read(folder/'state.json');problem=read(folder/'input/problem.json');prompt=(folder/'input/prompt.txt').read_text()
            body=None
            if not d.h.portfolio.finished(state):
                body=d.make_request(state,problem,cfg,prompt)
                from budget_policy import fit_output
                if arm=='adaptive' and d.h.portfolio.budget_phase(state['portfolio'],cfg):
                    body=fit_output(body,CAP-Decimal(state['cost_usd']),d.transport.request_cost)
            responses=[read(p) for p in folder.glob('steps/*/provider-response.json')]
            truncations=sum(any(c.get('finish_reason')=='length' for c in r.get('choices',[])) for r in responses)
            json_failures=0
            for r in responses:
                try:json.loads(r['choices'][0]['message']['content'])
                except (ValueError,KeyError,IndexError,TypeError):json_failures+=1
            pair[arm]={**data,'truncated_responses':truncations,'invalid_json_responses':json_failures,'next_request_bound_usd':d.transport.request_cost(body)['reserved_usd'] if body else None,'next_output_tokens':body['max_completion_tokens'] if body else None,
                'reduced_output_calls':sum(read(p)['max_completion_tokens']<cfg['model']['max_tokens'] for p in folder.glob('steps/*/request.json'))}
        pair['cost_delta_usd']=str(Decimal(pair['adaptive']['known_cost_usd'])-Decimal(pair['control']['known_cost_usd']))
        if 'local_score_estimate' in pair['adaptive'] and 'local_score_estimate' in pair['control']:
            pair['score_delta']=pair['adaptive']['local_score_estimate']-pair['control']['local_score_estimate']
        paired.append(pair)
    value={'all_trials_completed':all(x['all_completed'] for x in outputs.values()),'audit_passed':all(x['audit_passed'] for x in outputs.values()),'known_total_usd':str(sum(Decimal(x['known_total_usd']) for x in outputs.values())), 'pairs':paired,'official_evaluation':False}
    save(root/'comparison.json',value);return value


def manage(root,key):
    d=load_driver(root);verify(root);op=root/'operator';op.mkdir(exist_ok=True)
    with d.locked(op/'manager.lock',blocking=False):
        if (op/'started.json').exists():raise ValueError('Already started; inspect evidence rather than retry')
        jobs=[(arm,row) for index,row in enumerate(ROWS) for arm in (ARMS if index%2==0 else ARMS[::-1])]
        save(op/'started.json',{'pid':os.getpid(),'jobs':jobs,'started_at':d.now()})
        awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
        try:
            # One worker avoids sharing process-global imports/config hooks and
            # leaves the second shared API slot available to existing pilots.
            for arm,row in jobs:
                save(op/'status.json',{'status':'running','active':{'arm':arm,'row':row},'pid':os.getpid(),'at':d.now()})
                with (op/f'{arm}-F{row:03}.log').open('a') as out:
                    child=subprocess.Popen([sys.executable,'-u','-B',str(Path(__file__)),'worker','--root',str(root),'--arm',arm,'--row',str(row),'--key-file',str(key)],stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
                    save(op/'child.json',{'pid':child.pid,'arm':arm,'row':row})
                    code=child.wait()
                if code!=0:
                    save(op/'stop.json',{'reason':'Worker failed; no automatic paid retry','arm':arm,'row':row,'exit_code':code,'at':d.now()})
                    save(op/'status.json',{'status':'needs_review','arm':arm,'row':row,'exit_code':code});return
            result=audit(root)
            save(op/'finished.json',{'status':'completed' if result['audit_passed'] and result['all_trials_completed'] else 'needs_review','at':d.now(),**result})
            save(op/'status.json',read(op/'finished.json'))
        except Exception as exc:
            save(op/'manager-failure.json',{'at':d.now(),'error_type':type(exc).__name__,'message':str(exc)[:2000]})
            save(op/'status.json',{'status':'needs_review','reason':'Manager/audit exception; inspect evidence','error_type':type(exc).__name__})
            raise
        finally:awake.terminate()


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','manage','worker','audit']);p.add_argument('--root',type=Path,required=True);p.add_argument('--environment-repo',type=Path);p.add_argument('--api-slots',type=Path);p.add_argument('--key-file',type=Path);p.add_argument('--arm',choices=ARMS);p.add_argument('--row',type=int,choices=ROWS);a=p.parse_args();a.root=a.root.resolve()
    if a.command=='prepare':prepare(a.root,a.environment_repo.resolve(),a.api_slots.resolve())
    elif a.command=='worker':worker(a.root,a.arm,a.row,a.key_file)
    elif a.command=='manage':manage(a.root,a.key_file)
    else:print(json.dumps(audit(a.root),ensure_ascii=False))
if __name__=='__main__':main()
