"""Audit a finished cohort and write descriptive results, never official scores."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'first-harness-jwkweon'))
import harness as h
from evaluator.lean import render, ALLOWED_AXIOMS
import re


def completed_bridge_calls(calls,recovery):
    assert all(c['status'] in ('completed','failed') for c in calls)
    failed=[c for c in calls if c['status']=='failed']
    expected=recovery['manifest']['failed_preflight_invocations'] if recovery else []
    assert failed==expected, 'Unaccounted failed bridge invocation'
    assert all(c['error']=='Less than 1 GiB free; coordinator must inspect' for c in failed)
    return [c for c in calls if c['status']=='completed']


def audit_storage_recovery(base):
    patch=base/'amendments/storage-preflight-recovery'
    if not patch.exists():return None
    manifest=h.read(patch/'manifest.json')
    assert h.digest((patch/'resume_preflight.py').read_bytes())==manifest['resume_code_sha256']
    assert h.digest((base/'amendments/canonical-parent-order/canonical_order_bridge.py').read_bytes())==manifest['canonical_bridge_sha256']
    assert manifest['minimum_free_bytes_unchanged']==1024**3
    assert manifest['new_lean_calls_before_failure']==0 and not manifest['proposal_budget_changed']
    calls=[json.loads(line) for line in (patch/'resumptions.jsonl').read_text().splitlines() if line]
    assert len(calls)==len(manifest['pending'])
    assert all(c['status']=='completed' for c in calls)
    assert sorted(c['trial_id'] for c in calls)==sorted(manifest['pending'])
    for name,evidence in manifest['pending'].items():
        assert evidence['evaluation_absent_at_inspection']
        for relative,digest in evidence['files'].items():
            assert h.digest((base/name/relative).read_bytes())==digest
        resumed=next(c for c in calls if c['trial_id']==name)
        failed=next(c for c in manifest['failed_preflight_invocations'] if c['trial_id']==name)
        assert resumed['step']==evidence['step']==failed['step_before']+1
        assert resumed['started_at']>=failed['finished_at']
    return {'manifest':manifest,'resumptions':calls}


def audit_amendment(base,design,recovery=None):
    patch=base/'amendments/canonical-parent-order'
    if not patch.exists():return None
    manifest=h.read(patch/'manifest.json')
    assert manifest['base_policy_sha256']==design['code_sha256']['policy.py']
    for name,digest in manifest['files'].items():
        assert h.digest((patch/name).read_bytes())==digest
    evidence=h.read(patch/'existing-request-equivalence.json')
    assert evidence['all_existing_requests_identical']
    assert evidence['request_count']==len(evidence['sha256'])
    for name,digest in evidence['sha256'].items():assert h.digest((base/name).read_bytes())==digest
    all_calls=[json.loads(line) for line in (patch/'invocations.jsonl').read_text().splitlines() if line]
    calls=completed_bridge_calls(all_calls,recovery)
    assert all(c['command'] in ('submit','finish') for c in calls)
    for trial in design['planned_trials']:
        name=trial['id'];before=manifest['completed_steps_before'][name]
        submitted=[c['step_before'] for c in calls if c['trial_id']==name and c['command']=='submit']
        assert sorted(submitted)==list(range(before,design['proposal_budget']))
        finished=[c['step_before'] for c in calls if c['trial_id']==name and c['command']=='finish']
        assert finished==([design['proposal_budget']] if before<design['proposal_budget'] else [])
    clarification=h.read(patch/'scope-clarification.json')
    assert clarification['future_parent_membership_can_change'] is True
    return {'manifest':manifest,'scope_clarification':clarification,'unchanged_existing_requests':evidence['request_count'],
            'bridge_calls':len(all_calls),'completed_bridge_calls':len(calls),
            'preflight_blocked_calls':len(all_calls)-len(calls),'new_lean_calls_for_replay_fix':0}


def audit_final_summary(summary,state,final):
    assert final['valid'] and summary['final_valid'], 'Final verification failed; do not publish scored comparisons'
    assert summary['environment_unchanged'], 'Environment changed; do not publish scored comparisons'
    assert summary['baseline']==state['baseline'], 'Summary baseline differs from replayed state'
    assert summary['selected']==state['best'], 'Summary selection differs from replayed state'
    assert summary['valid_proposals']==sum(a['valid'] for a in state['attempts']), 'Summary validity count differs'
    assert summary['proposal_count']==state['step'], 'Summary proposal count differs'


def audit_dispatch(base, design):
    events=[json.loads(line) for line in (base/'dispatch.jsonl').read_text().splitlines() if line]
    planned=[spec['id'] for spec in design['planned_trials']]
    dispatched=[];active=set();completed=set();agents=set();peak=0
    for event in events:
        trial=event['trial_id']
        assert trial in planned
        if event['event']=='dispatched':
            assert trial not in dispatched and event['fork_turns']=='none'
            assert event['agent'] not in agents
            agents.add(event['agent']);dispatched.append(trial);active.add(trial)
            peak=max(peak,len(active))
            assert peak<=design['max_solver_parallelism']
        elif event['event']=='completed':
            assert trial in active and trial not in completed
            active.remove(trial);completed.add(trial)
        else:
            raise ValueError('Incomplete or unexpected dispatch event: '+event['event'])
    assert dispatched==planned and not active and completed==set(planned)
    return {'fresh_agents':len(agents),'peak_active_solvers':peak,
            'dispatch_order_as_planned':True,'source':'coordinator event log; instruction-based isolation'}


def audit_evaluation(folder,problem,template,code,nonces):
    result=h.read(folder/'result.json')
    for key,env in result['environments'].items():
        for run in env['runs']:
            source,log=folder/key/run['source'],folder/key/run['log']
            assert h.digest(source.read_bytes())==run['source_sha256']
            assert h.digest(log.read_bytes())==run['log_sha256']
            raw=source.read_text();match=re.search(r'#refactor_eval "([a-f0-9]{32})"',raw)
            nonce=match[1] if match else None
            assert raw==render(template,code,problem['name'],nonce)
            if 'measurement' in run:
                assert nonce and nonce not in nonces;nonces.add(nonce)
                reports=re.findall(r'REFACTOR_EVAL '+nonce+r' (\{[^\n]*\})',log.read_text())
                assert len(reports)==1 and json.loads(reports[0])==run['measurement']
                assert set(run['measurement']['axioms'])<=ALLOWED_AXIOMS
                assert run['measurement']['target']==problem['name']
        if env['valid']:
            assert len(env['runs'])==4
            assert sum('measurement' in r for r in env['runs'])==3
            assert all(r['returncode']==0 and not r['timed_out'] for r in env['runs'])
    return result


def main(base,output):
    design=h.read(base/'design.frozen.json');rows=[];nonces=set()
    dispatch=audit_dispatch(base,design)
    recovery=audit_storage_recovery(base)
    amendment=audit_amendment(base,design,recovery)
    runtime={}
    for pid in ['P01','P13']:
        r=base/f'readiness-{pid}'
        before,after=[h.read(r/f'runtime-inventory.{phase}.json') for phase in ['before','after']]
        assert before['files_sha256']==after['files_sha256']
        assert before['matches_historical_lock'] and after['matches_historical_lock']
        p=h.read(r/'input/problem.json')
        assert audit_evaluation(r/'baseline',p,(r/'input/context.lean.in').read_text(),p['reference'],nonces)['valid']
        runtime[pid]={'files':before['file_count'],'unchanged':True,'sha256':before['artifacts_sha256']}
    for spec in design['planned_trials']:
        root=base/spec['id'];summary=h.read(root/'summary.json')
        readiness=base/f"readiness-{spec['problem']}"
        for name in ('problem.json','source.lean','context.lean.in','environment.lock.json'):
            assert (root/'input'/name).read_bytes()==(readiness/'input'/name).read_bytes()
        assert (root/'baseline/result.json').read_bytes()==(readiness/'baseline/result.json').read_bytes()
        entrypoint=base/'amendments/canonical-parent-order/canonical_order_bridge.py' if amendment else root/'code/worker.py'
        replay=json.loads(subprocess.check_output([sys.executable,'-B',str(entrypoint),'replay',str(root)],text=True))
        assert replay['record_replay_passed']
        for name,digest in design['code_sha256'].items():assert h.digest((root/'code'/name).read_bytes())==digest
        assert h.digest((root/'input/prompt.txt').read_bytes())==design['prompt_sha256'][spec['condition']]
        config=h.read(root/'trial.json')
        for key,value in [('trial_id',spec['id']),('problem_id',spec['problem']),('condition',spec['condition']),('repetition',spec['repetition'])]:
            assert config[key]==value and summary[key]==value
        assert summary['proposal_count']==design['proposal_budget']==6
        assert summary['environment_unchanged']
        problem=h.read(root/'input/problem.json');template=(root/'input/context.lean.in').read_text()
        timeline=[];errors=Counter();families=Counter();parents=0;valid_parents=0;failed_parents=0;lean_seconds=0;lean_jobs=0
        for step in range(1,7):
            state=h.read(root/f'states/{step:03}.json');latest=state['latest'];event=state['attempts'][-1]
            result=None
            if latest['code']:
                result=audit_evaluation(root/f'steps/{step:03}/evaluation',problem,template,latest['code'],nonces)
                if result.get('error') and not result['environments']:errors[result['error']['kind']]+=1
                for env in result['environments'].values():
                    if env.get('error'):errors[env['error']['kind']]+=1
                    lean_jobs+=len(env['runs'])
                    lean_seconds+=sum(run['seconds'] for run in env['runs'])
            else:errors['response_parse']+=1
            if event['hypothesis']:
                families[event['hypothesis']['family']]+=1
                prior=h.read(root/f'states/{step-1:03}.json')
                parent=event['hypothesis']['parent']
                if parent not in ('original',prior['best']['sha256']):
                    parents+=1
                    if parent in prior['registry']:valid_parents+=1
                    else:failed_parents+=1
            b=state['baseline'];best=state['best']
            proposed=h.metrics(result) if result and result['valid'] else None
            timeline.append({'step':step,'local_cost':best['rank_numerator']/(2*b['tokens']*b['raw_heartbeats']),
                'tokens':best['tokens'],'raw_heartbeats':best['raw_heartbeats'],
                'proposal_metrics':proposed,
                'proposal_valid':event['valid'],'hypothesis':event['hypothesis'],'duplicate':event['duplicate']})
        final=audit_evaluation(root/'final',problem,template,summary['selected']['code'],nonces)
        audit_final_summary(summary,state,final)
        assert summary['final_valid']==final['valid']
        assert summary['status']==('completed' if final['valid'] and summary['environment_unchanged'] else 'failed')
        b=summary['baseline'];selected=summary['selected']
        final_cost=None
        if final['valid']:
            m=h.metrics(final);final_cost=.5*(m['tokens']/b['tokens']+m['raw_heartbeats']/b['raw_heartbeats'])
        rows.append({**spec,'baseline':b,'selected_tokens':selected['tokens'],'selected_raw':selected['raw_heartbeats'],
            'selected_local_cost':summary['local_cost'],'final_local_cost':final_cost,
            'length_reduction_pct':100*(1-selected['tokens']/b['tokens']),
            'hb_reduction_pct':100*(1-selected['raw_heartbeats']/b['raw_heartbeats']),
            'valid_proposals':summary['valid_proposals'],'final_valid':summary['final_valid'],
            'final_raw_drift_pct':100*(h.metrics(final)['raw_heartbeats']/selected['raw_heartbeats']-1) if final['valid'] else None,
            'proposal_lean_jobs':lean_jobs,'proposal_lean_seconds':lean_seconds,
            'request_utf8_bytes':sum((root/f'requests/{k:03}.json').stat().st_size for k in range(1,7)),
            'errors':dict(errors),'families':dict(families) if spec['condition']=='B' else None,
            'nonbest_parent_uses':parents if spec['condition']=='B' else None,
            'valid_nonbest_parent_uses':valid_parents if spec['condition']=='B' else None,
            'failed_parent_uses':failed_parents if spec['condition']=='B' else None,
            'timeline':timeline,'replay_passed':True,'receipt':str(root/'summary.json')})
    aggregates={}
    for pid in ['P01','P13']:
        aggregates[pid]={}
        for mode in ['A','B']:
            values=[r for r in rows if r['problem']==pid and r['condition']==mode]
            assert len(values)==2
            aggregates[pid][mode]={'runs':2,'mean_cost':statistics.mean(r['selected_local_cost'] for r in values),
                'cost_range':[min(r['selected_local_cost'] for r in values),max(r['selected_local_cost'] for r in values)],
                'valid_proposals':sum(r['valid_proposals'] for r in values),
                'mean_hb_reduction_pct':statistics.mean(r['hb_reduction_pct'] for r in values),
                'mean_length_reduction_pct':statistics.mean(r['length_reduction_pct'] for r in values),
                'checkpoints':{str(k):statistics.mean(r['timeline'][k-1]['local_cost'] for r in values) for k in design['checkpoints']}}
        a,b=aggregates[pid]['A']['mean_cost'],aggregates[pid]['B']['mean_cost']
        aggregates[pid]['B_cost_reduction_vs_A_pct']=100*(1-b/a)
    result={'audit_status':'PASS','trials':rows,'aggregates':aggregates,'runtime':runtime,'dispatch':dispatch,
        'protocol_amendment':amendment,
        'storage_recovery':recovery,
        'reported_at':datetime.now(timezone.utc).isoformat(),
        'report_code_sha256':h.digest(Path(__file__).read_bytes()),
        'fresh_measured_jobs':len(nonces),'all_final_valid':all(r['final_valid'] for r in rows),
        'proposal_count':48,'valid_proposals':sum(r['valid_proposals'] for r in rows),
        'official_submission':False,'limits':design['scope'],'statistical_superiority_claimed':False,
        'external_api_calls':0,'codex_model_call_count':None,'codex_cost_usd':None,
        'measurement_drift_alerts':[r['id'] for r in rows if r['final_raw_drift_pct'] is not None and abs(r['final_raw_drift_pct'])>1]}
    output.mkdir(parents=True,exist_ok=True)
    h.write(output/'results.json',result)
    h.write(output/'design.frozen.json',design)
    (output/'dispatch.jsonl').write_bytes((base/'dispatch.jsonl').read_bytes())
    if amendment:
        h.write(output/'ordering-amendment.json',amendment)
    if recovery:
        h.write(output/'storage-recovery.json',recovery)
    for r in rows:
        path=output/'selected'/f"{r['id']}.lean";path.parent.mkdir(exist_ok=True)
        path.write_bytes((base/r['id']/'selected.lean').read_bytes())
    lines=['# 비용 가설 파이프라인 pilot 결과','',
        'A는 naive prompt와 best/latest, B는 비용 가설 프롬프트와 단계·분기 부모·Pareto 기억을 함께 사용한다. 각 문제·조건 두 반복, 실행당 후보 6개다. local cost는 낮을수록 좋고 원본은 1이다.','',
        '| 문제 | A 평균 cost | B 평균 cost | B의 A 대비 cost 감소 | A/B 유효 후보 |',
        '|---|---:|---:|---:|---:|']
    for pid,v in aggregates.items():
        lines.append(f"| {pid} | {v['A']['mean_cost']:.6f} | {v['B']['mean_cost']:.6f} | {v['B_cost_reduction_vs_A_pct']:.2f}% | {v['A']['valid_proposals']}/12 · {v['B']['valid_proposals']}/12 |")
    lines+=['','| 문제·조건 | 평균 길이 감소 | 평균 HB 감소 | cost 범위 |','|---|---:|---:|---:|']
    for pid,v in aggregates.items():
        for mode in ('A','B'):
            x=v[mode];lo,hi=x['cost_range']
            lines.append(f"| {pid} {mode} | {x['mean_length_reduction_pct']:.2f}% | {x['mean_hb_reduction_pct']:.2f}% | {lo:.6f}–{hi:.6f} |")
    lines+=['','음수는 B가 더 비쌌다는 뜻이다. 다음은 개별 반복이다.','',
        '| 실행 | 토큰 | raw HB | HB 감소 | cost | 최종 검증 |','|---|---:|---:|---:|---:|---|']
    for r in rows:
        lines.append(f"| {r['id']} | {r['selected_tokens']} | {r['selected_raw']:,} | {r['hb_reduction_pct']:.2f}% | {r['selected_local_cost']:.6f} | {r['final_valid']} |")
    lines+=['','## 탐색 진행과 비용','',
        '| 문제·조건 | 2회 cost | 4회 cost | 6회 cost |','|---|---:|---:|---:|']
    for pid,v in aggregates.items():
        for mode in ('A','B'):
            c=v[mode]['checkpoints']
            lines.append(f"| {pid} {mode} | {c['2']:.6f} | {c['4']:.6f} | {c['6']:.6f} |")
    lines+=['','| 실행 | 유효 후보 | 중복 | 유효 비최선 / 실패 부모 사용 | Lean 작업 수·초 | 요청 UTF-8 bytes | 최종 HB 변동 |',
            '|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        drift=r['final_raw_drift_pct']
        drift_text=f'{drift:+.3f}%' if drift is not None else 'unavailable'
        parent_text=f"{r['valid_nonbest_parent_uses']} / {r['failed_parent_uses']}" if r['condition']=='B' else '미관측'
        lines.append(f"| {r['id']} | {r['valid_proposals']}/6 | {sum(t['duplicate'] for t in r['timeline'])} | {parent_text} | {r['proposal_lean_jobs']} · {r['proposal_lean_seconds']:.1f}s | {r['request_utf8_bytes']:,} | {drift_text} |")
    lines+=['','Lean 작업 시간은 후보 실행만 합산하며 잠금 대기와 모델 추론 시간은 제외한다. 요청 bytes는 모델 토큰이나 청구 비용이 아니다. B는 추가 문맥을 받으므로 동일한 모델 계산량 비교로 해석하지 않는다. 공유 머신의 부하를 통제하지 않았으므로 Lean 실행 초의 차이를 조건별 속도의 인과 효과로 해석하지 않는다.']
    if amendment:
        lines+=['','## 실행 중 정렬 버그 수정','',
            f"첫 B 실행의 replay에서 부모 dictionary 순서가 JSON 저장 전후 달라지는 문제가 발견됐다. 기존 요청 {amendment['unchanged_existing_requests']}개가 수정된 정책과 모두 같음을 확인하고, 원래 trial 파일을 변경하지 않는 frozen bridge로 후속 실행과 replay를 진행했다. 부모 선택 전 정렬 한 줄이 바뀌었다. 이후 상태에서는 노출되는 부모의 순서뿐 아니라 구성도 바뀔 수 있으므로 단순 표시 수정으로 해석하지 않는다. 점수·예산·프롬프트·Lean 측정은 그대로다. 수정 이력은 ordering-amendment.json에 있다. 사전 고정된 코드가 수정 없이 끝난 실험으로 표현하지 않는다."]
    if recovery:
        lines+=['','## 디스크 사전 검사 중단과 복구','',
            '공유 머신의 여유 공간이 1GiB 아래로 내려가 두 제출이 Lean 실행 전에 중단됐다. 저장된 응답·후보·입력 상태의 hash와 평가 폴더 부재를 기록한 뒤, 같은 후보를 이어서 평가했다. 1GiB 기준과 후보 예산·검증 절차는 유지했다. 원래 실패 호출도 남겼으며 알려진 두 사전 검사 실패만 집계 감사에서 별도로 인정한다. 세부 증거는 storage-recovery.json에 있다.']
    lines+=['','모든 상태 전이·요청·선택 replay, 원문 source/log hash, target 계측 nonce·공리 검사와 공유 runtime 전후 hash를 확인했다. 원시 기록은 각 results.json의 receipt 경로에 있다.','',
        '이 결과는 두 개발 문제에서의 작은 pilot이다. 프롬프트와 메모리 구조의 효과를 분리하지 않았고 정확한 모델 ID·sampling seed·Codex 비용은 관측하지 못했다. A도 자기 대화와 요청·응답 이력을 유지하므로 기억을 제거한 대조군은 아니다. 공식 평가나 전 버전 점수, 통계적 우위로 해석하지 않는다.']
    (output/'RESULTS.ko.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'audit_status':'PASS','all_final_valid':result['all_final_valid'],'aggregates':aggregates},ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('cohort',type=Path);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();main(a.cohort.resolve(),a.output.resolve())
