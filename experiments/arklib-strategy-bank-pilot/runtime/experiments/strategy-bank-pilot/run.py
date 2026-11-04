#!/usr/bin/env python3
"""Serial paid ArkLib pilot using common actions harness and existing temp3 packets.
No writes to prepared repositories. Per-problem and batch reservations persist before dispatch.
"""
import argparse
from decimal import Decimal
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'src'))
from lean_agent import harness as h, models, budgeting, artifacts as a, prepared
from lean_agent.evaluator.lean import execute

ENVFILE=Path('<LOCAL_HOME>/Documents/Codex/2026-11-03/x20/work/openai.env')
DATA=Path('<LOCAL_HOME>/_feynlang/temp3')
EXPECTED='d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682'

def sha(b):return hashlib.sha256(b.encode() if isinstance(b,str) else b).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def log(event,**kw):print(json.dumps({'time':datetime.now(timezone.utc).isoformat(),'event':event,**kw},ensure_ascii=False),flush=True)

def pinned_module(root):
    src=DATA/'arena/src/lean_agent/evaluator/lean.py'
    frozen=root/'code/temp3_lean.py'
    if frozen.exists():
        if frozen.read_bytes()!=src.read_bytes():raise ValueError('External evaluator changed')
    else:
        frozen.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,frozen)
    spec=importlib.util.spec_from_file_location('lean_agent.evaluator.pilot_pinned',frozen)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.WRAPPER=mod.WRAPPER.replace('axioms.toList.map Name.toString','axioms.toList.map _root_.Lean.Name.toString')
    tokens_source=DATA/'arena/src/lean_agent/evaluator/tokens.py'
    tokens_frozen=root/'code/temp3_tokens.py'
    if tokens_frozen.exists() and tokens_frozen.read_bytes()!=tokens_source.read_bytes():raise ValueError('External tokenizer changed')
    if not tokens_frozen.exists():shutil.copyfile(tokens_source,tokens_frozen)
    tspec=importlib.util.spec_from_file_location('pilot_tokens',tokens_frozen)
    tokens=importlib.util.module_from_spec(tspec);tspec.loader.exec_module(tokens)
    mod.proof_tokens=tokens.proof_tokens
    mod.validate_declaration=tokens.validate_declaration
    return mod

def normalize(e):
    e=dict(e);command=e['command']
    if command[0]!='/usr/bin/env' or not command[1].startswith('LEAN_PATH='):raise ValueError('Unexpected packet command')
    e['lean_path']=command[1].split('=',1)[1];e['command']=command[2:]
    e['timeout_seconds']=300
    return e

def check_pin(e):
    project=Path(e['project'])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip()
    if head!=e['sourceRevision']:raise ValueError('Source pin mismatch')
    if subprocess.check_output(['git','diff','HEAD','--','.'],cwd=project):raise ValueError('Dirty pinned source')
    manifest=read(project/'lake-manifest.json')
    for dep in manifest.get('packages',[]):
        p=project/'.lake/packages'/dep['name'].strip('«»')
        if dep.get('type')=='git':
            actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip()
            if actual!=dep['rev']:raise ValueError('Dependency pin mismatch: '+dep['name'])
            if subprocess.check_output(['git','diff','HEAD','--','.'],cwd=p):raise ValueError('Dirty dependency: '+dep['name'])
    return head

class Ledger:
    def __init__(self,root):self.root=root
    def transact(self,name,step,reserve=None,raw=None):
        with (self.root/'budget.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            path=self.root/'budget.json';d=read(path) if path.exists() else {'total_cap_usd':'25.00','problem_cap_usd':'2.50','calls':[]}
            key=name+':'+str(step)
            if reserve is not None:
                if any(c['key']==key for c in d['calls']):raise ValueError('No automatic redispatch of a reserved call')
                if any(c['status']!='settled' for c in d['calls']):raise ValueError('Unsettled call blocks paid execution')
                total=sum(Decimal(c['charged_usd']) for c in d['calls'])
                spent=sum(Decimal(c['charged_usd']) for c in d['calls'] if c['problem']==name)
                if total+reserve>Decimal(d['total_cap_usd']) or spent+reserve>Decimal(d.get('problem_caps',{}).get(name,d['problem_cap_usd'])):raise ValueError('Batch reservation would exceed cap')
                d['calls'].append({'key':key,'problem':name,'step':step,'reserved_usd':str(reserve),'status':'pending'})
            else:
                row=next(c for c in d['calls'] if c['key']==key)
                bill=models.receipt(raw)['cost_usd']
                row.update(status='unknown' if bill is None else 'settled',charged_usd=bill)
                if bill is not None and Decimal(bill)>Decimal(row['reserved_usd']):
                    row['status']='over_reservation'
            write(path,d)
            return d
    def query(self,name,run):
        def query(body,model,step,fixtures=None):
            bound=Decimal(budgeting.request_cost(body)['reserved_usd'])
            self.transact(name,step,reserve=bound)
            log('dispatch',problem=name,step=step,reserved_usd=str(bound))
            if model['backend']=='openai':
                from lean_agent import openai_direct
                provider_raw=openai_direct.query(body,model,step)
                write(self.root/'provider-responses'/name/(str(step)+'.json'),provider_raw)
                raw=openai_direct.normalize(provider_raw)
            else:
                raw=models.query(body,model,step,fixtures)
            write(self.root/'receipts'/name/(str(step)+'.json'),raw)
            d=self.transact(name,step,raw=raw)
            bill=models.receipt(raw)['cost_usd']
            log('settled' if bill is not None else 'unknown_cost',problem=name,step=step,cost_usd=bill)
            if d['calls'][-1]['status']=='over_reservation':raise ValueError('Actual cost exceeded declared reservation; batch stopped')
            return raw
        return query

def adapter_class(mod, library_guard=None):
    class PacketEvaluator(mod.LeanEvaluator):
        def __init__(self,primary):
            self.primary=primary
            super().__init__(executor=self.invoke)
        def invoke(self,command,cwd,timeout,**kwargs):
            # Prevent generated Lean from writing or reaching network; credentials are stripped by execute.
            return execute(['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*) (deny file-write*) (allow file-write* (literal "/dev/null"))',*command],cwd,timeout,lean_path=self.primary['lean_path'],**kwargs)
        def fingerprint(self,environment,**kwargs):
            if library_guard is not None:library_guard.verify(full=False)
            check_pin(self.primary)
            return super().fingerprint(self.primary,**kwargs)
        def preflight(self,environment,output,progress):
            fp=self.fingerprint(environment)
            write(output/'environment.json',fp)
            result={'schema_version':1,'status':'passed','stage':'environment','error':None,
                    'api_calls':0,'model_requests':0,'environment':fp,'effective_command':self.primary['command'],
                    'context_check':'Deferred to mandatory original full-module compile before first model call.'}
            write(output/'preflight.json',result)
            return result
        def evaluate(self,code,problem,environments,folder,runs):
            if library_guard is not None:library_guard.verify(full=False)
            return super().evaluate(code,problem,[self.primary],folder,runs)
    return PacketEvaluator

def prepare(root):
    if sha((DATA/'benchmark_data_final.jsonl').read_bytes())!=EXPECTED:raise ValueError('Dataset hash mismatch')
    rows=[json.loads(l) for l in (DATA/'benchmark_data_final.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source']=='arklib'];assert len(rows)==10
    bank=read(REPO/'strategy-bank/team-v1/bank.json')
    result=[]
    for i,row in enumerate(rows,1):
        packet=DATA/'work/packets/arklib'/row['name']
        problem=read(packet/'input.json')['problem']
        assert problem['reference']==row['src'] and problem['statement']==row['statement']
        if problem.get('original')==problem['reference']:problem.pop('original')
        problem['version_info']=row['version_info']
        problem['screening_version']='v4.31.0'
        envs=[normalize(e) for e in read(packet/'environment.json')['environments']]
        expected={(v,c) for obj in row['version_info'] for v,c in obj.items()}
        assert {(e['id'],e['sourceRevision']) for e in envs}==expected
        primary=next(e for e in envs if e['id']=='v4.31.0')
        # Check packet template against the pinned full source, not a historical candidate.
        for e in envs:
            check_pin(e)
            src=(Path(e['project'])/row['file_path']).read_text()
            assert sha(src)==e['source_sha256']
        dest=root/'inputs'/f'{i:02}';dest.mkdir(parents=True,exist_ok=True)
        write(dest/'problem.json',problem);write(dest/'environments.json',envs)
        (dest/'context.lean.in').write_text(primary['template'])
        prefix=primary['template'].split('{{DECLARATION}}')[0]
        # Only pre-target context. No improved proofs or future declarations.
        corpus=[]
        lines=prefix.splitlines(keepends=True)
        starts=[n for n,l in enumerate(lines) if re.match(r'\s*(?:(?:private|protected|noncomputable)\s+)*(?:theorem|lemma|def|abbrev)\s+',l)]
        for n,start in enumerate(starts):
            end=starts[n+1] if n+1<len(starts) else len(lines)
            text=''.join(lines[start:end])[:9000]
            match=re.search(r'(?:theorem|lemma|def|abbrev)\s+([^\s:(]+)',text)
            if match and match[1] not in {c['name'] for c in corpus}:corpus.append({'name':match[1],'source':row['file_path'],'text':text})
        # Bound corpus; source search is optional and frozen.
        while len(json.dumps(corpus))>150000:corpus.pop(0)
        write(dest/'corpus.json',{'schema_version':1,'entries':corpus})
        prompt=(REPO/'examples/actions/prompt.txt').read_text()+'''\nThis is an ArkLib refactoring experiment. Minimize combined source-token and raw-heartbeat ratios. Only edit the proof body; preserve the exact statement. No new imports, global helpers, options, axioms, sorry or unsafe evaluation. Use original input and generic strategy hints; historical improved proofs are unavailable. On propose/repair include strategy_ids for Bank strategies you selected (empty if none); the IDs are declarations, not verified attribution. Try concrete changes and repair from the diagnostics. All search/analysis calls also cost money. Stop after the configured reservation budget; do not finish early solely because one candidate passes. Screening uses Lean v4.31.0; final compatibility is checked separately on every required version.\nPre-target source context (tail only, truncated; full proof in problem.reference):\n'''+prefix[-12000:]
        (dest/'prompt.txt').write_text(prompt)
        config={'schema_version':1,'problem':str(dest/'problem.json'),'template':str(dest/'context.lean.in'),
          'project':primary['project'],'prompt':str(dest/'prompt.txt'),
          'lean':{'toolchain':primary['toolchain'],'command':primary['command'],'timeout_seconds':300,'repetitions':1},
          'limits':{'max_calls':40,'cost_stop_usd':'2.50','cost_cap_usd':'2.50','max_proof_characters':max(30000,len(row['src'])*3),'max_feedback_characters':6000,'max_request_characters':180000},
          'model':{'backend':'openrouter','id':'openai/gpt-6.1-sol','provider':'openai','reasoning_effort':'high','seed':42,'max_tokens':32768 if len(row['src'])>12000 else 16384,'max_price':{'prompt':2,'completion':10},'timeout_seconds':600},
          'agent':{'mode':'actions-v1','corpus':str(dest/'corpus.json'),'history_limit':4,'candidate_limit':4,'allow_finish':False,'strategy_bank':{'bank':bank,'top_k':1,'contextual':True}}}
        write(dest/'config.json',config)
        result.append({'index':i,'name':row['name'],'input':str(dest),'required_versions':[e['id'] for e in envs]})
    write(root/'plan.json',{'dataset_sha256':EXPECTED,'source':'arklib','problems':result,'total_cap_usd':'25.00','problem_cap_usd':'2.50','condition':'20-card Bank, contextual retriever, top-1; not an A/B experiment','historical_cost_scope':'new pilot calls only; not a competition cumulative-cost certificate'})
    return result

def cached_verification(mod,e,code,problem,directory,runs):
    path=directory/'result.json'
    if not path.exists():return None
    result=read(path)
    if result['tokens']!=mod.proof_tokens(code,problem['statement']) or set(result['environments'])!={e['id']}:
        raise ValueError('Cached verification identity mismatch')
    row=result['environments'][e['id']]
    if not result['valid'] and (not row.get('error') or row['error']['kind']!='compile'):
        return None
    records=row['runs']
    expected=['check']+[f'measure-{i+1}' for i in range(runs)]
    if result['valid'] and (not row['valid'] or len(records)!=len(expected)):
        raise ValueError('Cached successful verification is incomplete')
    for n,record in enumerate(records):
        label=expected[n];source=directory/e['id']/(label+'.lean');logfile=source.with_suffix('.log')
        if record['source']!=source.name or record['log']!=logfile.name:
            raise ValueError('Unexpected cached source path')
        text=source.read_text()
        nonce=None
        if n:
            match=re.search(r'(?m)^#refactor_eval "([0-9a-f]{32})"',text)
            if not match:raise ValueError('Cached measurement nonce missing')
            nonce=match[1]
        if text!=mod.render(e['template'],code,problem['name'],nonce):
            raise ValueError('Cached full source differs from pinned context/candidate')
        if sha(source.read_bytes())!=record['source_sha256'] or sha(logfile.read_bytes())!=record['log_sha256']:
            raise ValueError('Cached source/log hash mismatch')
        tail=[*e['command'],'--root='+str(source.parent.resolve()),str(source.resolve())]
        if record['command'][-len(tail):]!=tail:raise ValueError('Cached compiler command differs')
        if record['timed_out']:return None
        if result['valid'] and record['returncode']!=0:raise ValueError('Successful cache has failed compiler')
        if n and record['returncode']==0:
            reports=re.findall(r'REFACTOR_EVAL '+nonce+r' (\{[^\n]*\})',logfile.read_text())
            if len(reports)!=1 or json.loads(reports[0])!=record['measurement']:
                raise ValueError('Cached heartbeat/axiom report differs from log')
            if not set(record['measurement']['axioms'])<=mod.ALLOWED_AXIOMS:raise ValueError('Cached forbidden axioms')
    if not result['valid'] and (not records or records[-1]['returncode']==0):
        raise ValueError('Cached compile rejection lacks compiler failure')
    return result


def verification_order(envs,out):
    failures={}
    for path in out.parent.glob('c*/result.json'):
        for version,row in read(path).get('environments',{}).items():
            if not row['valid'] and (row.get('error') or {}).get('kind')=='compile':
                failures[version]=failures.get(version,0)+1
    return [e for _,e in sorted(enumerate(envs),key=lambda pair:(-failures.get(pair[1]['id'],0),pair[0]))]


def full_verify(mod,envs,code,problem,out,runs=3):
    envs=verification_order(envs,out)
    results={'valid':True,'tokens':None,'environments':{},'error':None,'verification_order':[e['id'] for e in envs]}
    for e in envs:
        check_pin(e)
        directory=out/e['id']
        r=cached_verification(mod,e,code,problem,directory,runs)
        if r is None:
            if directory.exists():
                preserved=directory.with_name(directory.name+'.interrupted-'+datetime.now(timezone.utc).strftime('%H%M%S%f'))
                directory.rename(preserved)
            ev=adapter_class(mod)(e)
            r=ev.evaluate(code,problem,[],directory,runs)
            write(directory/'result.json',r)
        else:
            log('reuse_verified_receipt',problem=problem['name'],candidate_sha256=sha(code),version=e['id'],valid=r['valid'])
        results['tokens']=r['tokens'];results['environments'].update(r['environments'])
        if not r['valid']:
            results['valid']=False
            results['error']={'kind':'required-version-failed','version':e['id'],'remaining_versions':'not needed to reject candidate'}
            break
    write(out/'result.json',results)
    return results

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--resume-verified',action='store_true');args=ap.parse_args()
    root=args.root.resolve();root.mkdir(parents=True,exist_ok=True)
    with (root/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        mod=pinned_module(root)
        if (root/'plan.json').exists():items=read(root/'plan.json')['problems']
        else:items=prepare(root)
        if args.prepare_only:log('prepared',problems=len(items));return
        # Refuse automatic continuation after any dispatched call (including unknown outcomes).
        if (root/'budget.json').exists() and read(root/'budget.json')['calls']:
            if not args.resume_verified:raise ValueError('Existing paid ledger; inspect receipts before explicit continuation')
            audit_spec=importlib.util.spec_from_file_location('pilot_audit',Path(__file__).with_name('audit.py'))
            audit_module=importlib.util.module_from_spec(audit_spec);audit_spec.loader.exec_module(audit_module)
            audit_result=audit_module.audit(root)
            write(root/'resume-audit.json',audit_result)
            log('explicit_verified_continuation',settled_calls=audit_result['settled_calls'],new_calls_repeated=0)
        guard=prepared.PreparedLeanEvaluator(root/'prepared-v4.31.0.json')
        guard.verify(full=True)
        ledger=Ledger(root);summaries=read(root/'results.json') if args.resume_verified and (root/'results.json').exists() else []
        for item in items:
            if any(row['name']==item['name'] for row in summaries):
                log('skip_completed_problem',problem=item['name'])
                continue
            dest=Path(item['input']);envs=read(dest/'environments.json');primary=next(e for e in envs if e['id']=='v4.31.0');problem=read(dest/'problem.json')
            name=item['name'];run=root/'runs'/f"{item['index']:02}"
            log('problem_start',index=item['index'],problem=name)
            try:
                if run.exists():
                    if not args.resume_verified or not (run/'summary.json').exists() or not (run/'result.json').exists():
                        raise ValueError('Unfinished screening run requires receipt recovery, never automatic redispatch')
                    replay=h.replay(run)
                    if not replay['record_replay_passed']:raise ValueError('Stored screening replay failed')
                    summary=read(run/'summary.json')
                    log('reuse_completed_screening',problem=name,new_api_calls=0)
                else:
                    summary=h.run(dest/'config.json',run,evaluator=adapter_class(mod,guard)(primary),query=ledger.query(name,run),dotenv=ENVFILE)
                spec=importlib.util.spec_from_file_location('pilot_trace',REPO/'scripts/export_strategy_trace.py');tr=importlib.util.module_from_spec(spec);spec.loader.exec_module(tr)
                trace=tr.export(run);write(root/'traces'/f"{item['index']:02}.json",trace)
                # Verify every unique valid candidate in screening rank order until a full-version improvement is found.
                state=read(sorted((run/'steps').glob('*/event.json'))[-1])['state_after'] if list((run/'steps').glob('*/event.json')) else read(run/'initial-state.json')
                baseline=full_verify(mod,envs,problem['reference'],problem,root/'verification'/f"{item['index']:02}"/'baseline')
                selected=problem['reference'];selected_result=baseline;selection='baseline';candidate_reports=[]
                archive=state['exploration']['candidates']
                ranked=sorted(((cid,c) for cid,c in archive.items() if c.get('valid') and cid!='c000'),key=lambda pair:h.ranking(pair[1]))
                seen={sha(problem['reference'])}
                for cid,c in ranked:
                    if sha(c['code']) in seen:continue
                    seen.add(sha(c['code']))
                    v=full_verify(mod,envs,c['code'],problem,root/'verification'/f"{item['index']:02}"/cid)
                    score=None
                    if baseline['valid'] and v['valid']:
                        ratios=[]
                        for key,e in v['environments'].items():
                            import statistics
                            bh=statistics.median(x['measurement']['raw'] for x in baseline['environments'][key]['runs'] if 'measurement' in x)
                            ch=statistics.median(x['measurement']['raw'] for x in e['runs'] if 'measurement' in x)
                            ratios.append(ch/bh)
                        score=v['tokens']/baseline['tokens']+sum(ratios)/len(ratios)
                    candidate_reports.append({'candidate_id':cid,'valid':v['valid'],'ratio_sum':score})
                    if score is not None and score<2:
                        selected=c['code'];selected_result=v;selection=cid;break
                out=root/'selected'/f"{item['index']:02}.lean";out.parent.mkdir(exist_ok=True);out.write_text(selected)
                row={'index':item['index'],'name':name,'run_status':summary['status'],'stop_reason':summary['stop_reason'],'cost_usd':summary['state']['cost_usd'],
                     'selection':selection,'selected_sha256':sha(selected),'all_versions_valid':selected_result['valid'],'candidate_checks':candidate_reports,
                     'baseline_tokens':baseline['tokens'],'selected_tokens':selected_result['tokens'],'strategy_application_review':'pending; IDs self-reported','screening_run':str(run)}
                summaries.append(row);write(root/'results.json',summaries);log('problem_complete',**row)
            except Exception as exc:
                write(root/'problem-error.json',{'index':item['index'],'name':name,'exception_type':type(exc).__name__,'message':str(exc)})
                log('stopped',index=item['index'],problem=name,error_type=type(exc).__name__)
                raise
        guard.verify(full=True)
        log('batch_complete',problems=len(summaries))
if __name__=='__main__':main()
