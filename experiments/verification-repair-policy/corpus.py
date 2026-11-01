"""Zero-model evaluation of frozen historical failures, with executable record replay."""
import argparse
from dataclasses import asdict
from functools import partial
import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

from common import HERE, REPO, TACTICS, Limits, Stop, canonical, inventory, read, safe_path, sha, shared
from adapter import operational, repair_candidate, score
from native import NativeLean
from runtime import Runtime
from lean_agent import models, openai_direct, preflight, prepared
from lean_agent.evaluator.lean import LeanEvaluator

REVISION = 'historical-auto-1'


def make_environment(item, project, lean, limits):
    source_path = project/item['source_file']
    source = source_path.read_bytes().decode()
    if sha(source) != item['source_sha256']:
        raise ValueError('Pinned source/context changed: '+item['source_file'])
    declaration = item['problem']['reference'].rstrip('\n')
    if source.count(declaration) != 1:
        raise ValueError('Original declaration must occur exactly once')
    lines = source.replace(declaration, '{{DECLARATION}}', 1).splitlines(keepends=True)
    last = max(i for i,line in enumerate(lines) if line.startswith('import '))
    lines.insert(last+1, '{{HARNESS_COMMANDS}}\n')
    return {'id':'strata-v4.26.0', 'project':str(project), 'toolchain':'leanprover/lean4:v4.26.0',
            'command':preflight.resolve_command([lean,'-j1','-T20000'], 'leanprover/lean4:v4.26.0', project),
            'timeout_seconds':limits.lean_seconds, 'template':'{{HARNESS_IMPORT}}\n'+''.join(lines),
            'fingerprint_files':[item['source_file']],
            'lean_path':os.pathsep.join(str(project/p) for p in ('.lake/build/lib/lean','.lake/packages/plausible/.lake/build/lib/lean'))}


def prepare(root, corpus_path, project, lean):
    root, project = Path(root).resolve(), Path(project).resolve()
    if root.exists():
        raise ValueError('Use a new output directory')
    corpus = read(Path(corpus_path))
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip()
    if head != corpus['environment']['commit'] or subprocess.check_output(['git','diff','HEAD','--','.'],cwd=project):
        raise ValueError('Expected clean pinned upstream source')
    limits = Limits()
    environments = {pid:make_environment(item,project,lean,limits) for pid,item in corpus['problems'].items()}
    root.mkdir(parents=True)
    shared.atomic(root/'corpus.json',corpus)
    shared.atomic(root/'environments.json',environments)
    prepared.freeze(next(iter(environments.values()))['lean_path'].split(os.pathsep), head,
                    root/'libraries.json', verification='stat-cache')
    protocol = {'revision':REVISION,'scope':'fixed historical failures; no generation loop',
                'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                'source_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip()),
                'corpus_sha256':sha(canonical(corpus)), 'limits':asdict(limits),'tactics':list(TACTICS),
                'actual_api_calls':0,'actual_api_budget_usd':'0','model_dispatch_enabled':False,
                'conditions':['no-repair','auto-solver-v1'], 'recursive_repair':'not_measured',
                'reference_policy':'one shared original evaluation per problem; baseline failure stops every corresponding case',
                'duplicate_policy':'retain all occurrences; report a separate first-occurrence unique summary',
                'profile_enabled':False}
    shared.atomic(root/'protocol.json',protocol)
    archive = root/'code/repo'
    shutil.copytree(REPO/'src/lean_agent',archive/'src/lean_agent',ignore=shutil.ignore_patterns('__pycache__'))
    for relative in ('experiments/verification-repair-policy','experiments/api-comparison'):
        dest=archive/relative;dest.mkdir(parents=True)
        for path in (REPO/relative).iterdir():
            if path.suffix in ('.py','.lean'):
                shutil.copy2(path,dest/path.name)
    shared.atomic(root/'frozen-inputs.json',inventory(root))
    return protocol


def check(root):
    for relative,digest in read(root/'frozen-inputs.json').items():
        if sha(safe_path(root,relative).read_bytes()) != digest:
            raise ValueError('Frozen input changed: '+relative)
    protocol=read(root/'protocol.json')
    if protocol['revision'] != REVISION or protocol['model_dispatch_enabled'] or protocol['actual_api_budget_usd'] != '0':
        raise ValueError('Unsupported evaluation protocol')
    for path in (root/'code/repo').rglob('*'):
        if path.is_file() and path.suffix in ('.py','.lean'):
            active=REPO/path.relative_to(root/'code/repo')
            if not active.is_file() or active.read_bytes()!=path.read_bytes():
                raise ValueError('Use the archived code for this evaluation')
    return protocol


def runtime_protocol(protocol,environment,problem):
    return {**protocol,'problem':problem,'environment':environment,'environment_sha256':sha(canonical(environment)),
            'condition':'auto-solver-v1','simulated_reservation_usd':'0.02','simulated_budget_usd':'0'}


class CorpusRuntime(Runtime):
    def __init__(self,*args,libraries=None,**kwargs):
        self.libraries=libraries
        super().__init__(*args,**kwargs)

    def _execute(self,*args,**kwargs):
        self.libraries.verify(full=False)
        return super()._execute(*args,**kwargs)

    def dispatch(self,*args,**kwargs):
        raise AssertionError('Model dispatch is forbidden in corpus evaluation')


def reference_workflow(rt):
    result={'baseline':None,'tactics':[],'status':'stopped','reason':None}
    try:
        # Whole-file suffixes may depend on the target. A declaration-free
        # preflight is not valid here: fingerprint and verify the real original.
        result['fingerprint']=rt.tape.call('fingerprint',{'environment':rt.environment},
            lambda:LeanEvaluator(executor=rt._execute).fingerprint(rt.environment))
        result['baseline']=rt.evaluate(rt.problem['reference'],'baseline')
        if not result['baseline']['valid'] or score(result['baseline'],result['baseline']) is None:
            result['reason']='baseline_unverified'
        else:
            # Keep the original target so downstream declarations still exist;
            # parser availability probes go at the end of the same full file.
            probe={**rt.environment,'template':rt.environment['template'].replace('{{DECLARATION}}',rt.problem['reference'])+'\n{{DECLARATION}}\n'}
            rt.lean_calls += 1
            records=rt.tape.call('availability_full_context',{'tactics':rt.protocol['tactics'],'environment_sha256':sha(canonical(probe))},
                lambda:NativeLean(probe,rt.problem,rt.root/'availability',invoke=rt._execute).availability(
                    rt.protocol['tactics'],rt.limits.lean_seconds,rt.limits.memory_mib))
            result['tactics']=[r['tactic'] for r in records if r['available']]
            result['status']='completed'
    except (OSError,ValueError,RuntimeError,Stop) as exc:
        result.update(reason='reference_operational_error',detail=str(exc))
    result.update(**rt.cost_summary(),elapsed_seconds=rt.now())
    rt.tape.event('finished_result',result=result)
    return result


def case_workflow(rt,case,reference):
    result={'id':case['id'],'problem_id':case['problem_id'],'historical_status':case['historical_status'],
            'duplicate_of':case['duplicate_of'],'reproduced_failure':None,'native_extracted':None,
            'recovered':None,'repair':None,'improves_historical_best':None,'final_q':None,'final_valid':None,
            'selected_origin':None,'status':'stopped','reason':None,'recursive_repair':None}
    saved=rt.tape.call('shared_reference',{'sha256':sha(canonical(reference))},lambda:reference)
    baseline=saved['baseline']
    selected=None
    retained_q=None
    try:
        if saved['status']!='completed':
            result['reason']=saved['reason']
        else:
            selected=rt.problem['reference']
            best=baseline
            before=case['best_before']['code']
            if before.rstrip('\n') != selected.rstrip('\n'):
                best=rt.evaluate(before,'historical-best')
                if best['valid'] and score(best,baseline)<2:
                    selected=before
            result['historical_best_valid']=best['valid']
            result['historical_best_q']=score(best,baseline)
            retained_q=min(2,score(best,baseline)) if best['valid'] else 2
            original=rt.evaluate(case['code'],'candidate')
            result['candidate_evaluation']=original
            if operational(original):
                result['reason']='candidate_operational_error'
            elif original['valid']:
                result['reproduced_failure']=False
                result['reason']='historical_failure_not_reproduced'
            else:
                result['reproduced_failure']=True
                if not original['environments']:
                    result.update(reason='policy_rejected',recovered=False,native_extracted=False)
                else:
                    rt.duplicate(case['code'])
                    repair=repair_candidate(rt,case['code'],case['history_id'],'auto-solver-v1',saved['tactics'])
                    result['repair']=repair
                    result['native_extracted']=None if repair['status']=='operational_error' and not repair['nodes'] else bool(repair['nodes'])
                    result['reason']=repair.get('reason',repair['status'])
                    result['recovered']=None if repair['status']=='operational_error' else repair['status']=='verified'
                    if repair['status']=='verified':
                        q=score(repair['evaluation'],baseline)
                        result['repaired_q']=q
                        result['improves_historical_best']=q<score(best,baseline) if best['valid'] else None
                        if q < min(2,score(best,baseline) if best['valid'] else 2):
                            selected=repair['code']
            # No model repair is allowed during final verification.
            final=rt.evaluate(selected,'final-selected')
            if not final['valid'] and not operational(final):
                selected=rt.problem['reference']
                final=rt.evaluate(selected,'final-baseline')
            result['final_evaluation']=final
            if final['valid']:
                origin='original' if selected==rt.problem['reference'] else 'repaired' if result['repair'] and selected==result['repair'].get('code') else 'historical-best'
                result.update(final_valid=True,final_q=score(final,baseline),selected_code=selected,selected_sha256=sha(selected),selected_origin=origin)
                if result['reason']!='candidate_operational_error' and not (result['repair'] and result['repair']['status']=='operational_error'):
                    result['status']='completed'
    except (OSError,ValueError,RuntimeError,Stop) as exc:
        result.update(reason='operational_error',detail=str(exc))
    result['no_repair']={'recovered':False if result['reproduced_failure'] is True else None,
                         'retained_best_q':retained_q}
    result.update(**rt.cost_summary(),elapsed_seconds=rt.now())
    rt.tape.event('finished_result',result=result)
    return result


def finish(root,result,runtime):
    shared.atomic(root/'result.json',result)
    if result.get('selected_code'):
        (root/'selected.lean').write_text(result['selected_code'])
    runtime.tape.journal.seal(result['status'])


def summarize(rows):
    def group(values):
        count=lambda k,v:sum(r.get(k) is v for r in values)
        reproduced=count('reproduced_failure',True)
        recovered=count('recovered',True)
        measured=sum(r.get('recovered') is not None for r in values)
        return {'candidates':len(values),'failure_reproduced':reproduced,'failure_not_reproduced':count('reproduced_failure',False),
                'initial_unmeasured':count('reproduced_failure',None),'native_extracted':count('native_extracted',True),
                'recovery_measured':measured,'recovered':recovered,'recovery_unmeasured':count('recovered',None),
                'recovery_rate_measured':recovered/measured if measured else None,
                'observed_recoveries_over_all':{'numerator':recovered,'denominator':len(values)},
                'improves_historical_best':count('improves_historical_best',True),
                'reason_counts':{reason:sum(r['reason']==reason for r in values) for reason in sorted({r['reason'] for r in values})}}
    return {'all_occurrences':group(rows),'unique_candidates':group([r for r in rows if r['duplicate_of'] is None]),
            'by_problem':{pid:group([r for r in rows if r['problem_id']==pid]) for pid in sorted({r['problem_id'] for r in rows})},
            'actual_api_calls':sum(r['actual_api_calls'] for r in rows),'actual_api_cost_usd':'0',
            'recursive_repair_effect':None,'generation_loop_effect':None}


def process(root,replay=False):
    root=Path(root).resolve()
    protocol=check(root)
    if replay and inventory(root)!=read(root/'artifacts.json'):
        raise ValueError('Recorded artifacts changed')
    if not replay and (root/'references').exists():
        raise ValueError('Run already started; use a new directory')
    corpus,environments=read(root/'corpus.json'),read(root/'environments.json')
    libraries=None if replay else prepared.PreparedLeanEvaluator(root/'libraries.json')
    if libraries:
        libraries.verify()
    references={}
    for pid,item in corpus['problems'].items():
        path=root/'references'/pid
        if not replay:path.mkdir(parents=True)
        rt=CorpusRuntime(path,runtime_protocol(protocol,environments[pid],item['problem']),replay=replay,libraries=libraries)
        result=reference_workflow(rt)
        if replay:
            rt.tape.assert_complete()
            if result!=read(path/'result.json'):raise ValueError('Reference replay differs')
        else:finish(path,result,rt)
        references[pid]=result
    rows=[]
    for case in corpus['cases']:
        pid=case['problem_id'];path=root/'cases'/case['id']
        if not replay:path.mkdir(parents=True)
        rt=CorpusRuntime(path,runtime_protocol(protocol,environments[pid],corpus['problems'][pid]['problem']),replay=replay,libraries=libraries)
        result=case_workflow(rt,case,references[pid])
        if replay:
            rt.tape.assert_complete()
            if result!=read(path/'result.json'):raise ValueError('Case replay differs: '+case['id'])
        else:
            finish(path,result,rt)
            print(case['id'],result['reason'],flush=True)
        rows.append(result)
    result=summarize(rows)
    result['reference_lean_calls']=sum(r['lean_calls'] for r in references.values())
    result['case_lean_calls']=sum(r['lean_calls'] for r in rows)
    result['repair_lean_calls']=sum(r['repair_lean_calls'] for r in rows)
    if libraries:
        libraries.verify()
        for pid,reference in references.items():
            environment=environments[pid]
            from lean_agent.evaluator.lean import execute
            final=LeanEvaluator(executor=partial(execute,lean_path=environment['lean_path'])).fingerprint(environment)
            if final!=reference.get('fingerprint'):raise ValueError('Environment changed during evaluation')
        shared.atomic(root/'summary.json',result)
        shared.atomic(root/'artifacts.json',inventory(root))
    elif result!=read(root/'summary.json'):
        raise ValueError('Summary replay differs')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','replay'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--corpus',type=Path,default=HERE/'evaluation/corpus.json')
    parser.add_argument('--project',type=Path)
    parser.add_argument('--lean',default='lean')
    args=parser.parse_args()
    if args.action=='prepare':
        if args.project is None:parser.error('prepare requires --project')
        result=prepare(args.output,args.corpus,args.project,args.lean)
    else:
        with patch.object(models,'query',side_effect=AssertionError('No model API')), \
             patch.object(openai_direct,'query',side_effect=AssertionError('No direct API')), \
             patch.object(shared,'http',side_effect=AssertionError('No HTTP')):
            result=process(args.output,replay=args.action=='replay')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
