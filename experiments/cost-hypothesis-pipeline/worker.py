"""Immutable manual-solver bridge with a replayable hypothesis policy."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
if not (HERE/'harness.py').exists():
    sys.path.insert(0, str(HERE.parent/'first-harness-jwkweon'))
import harness as h
from evaluator.lean import LeanEvaluator
from error_feedback import format_feedback
import policy


def now():
    return datetime.now(timezone.utc).isoformat()


def load(root):
    config = h.read(root/'trial.json')
    assert config['condition'] in ('A','B') and h.positive(config['max_proposals'])
    for rel, expected in h.read(root/'manifest.json')['files'].items():
        path = root/rel
        if not path.resolve().is_relative_to(root) or h.digest(path.read_bytes()) != expected:
            raise ValueError('Frozen input/code mismatch: '+rel)
    problem = h.read(root/'input/problem.json')
    environment = {'id':'fixed', 'project':str(root/'project'),
        'template':(root/'input/context.lean.in').read_text(),
        'toolchain':config['toolchain'],
        'command':[sys.executable,str(root/'lean_runner.py'),'-j1','-M4096','-T200000'],
        'timeout_seconds':420}
    return config, problem, environment


def evaluate(root, code, folder):
    _, problem, environment = load(root)
    # One Lean evaluation at a time across this cohort. Solvers may think in parallel.
    with (root.parent/'lean.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if shutil.disk_usage(root).free < 1024**3:
            raise RuntimeError('Less than 1 GiB free; coordinator must inspect')
        result = LeanEvaluator().evaluate(code, problem, [environment], folder, 3)
    h.write(folder/'result.json', result)
    return result


def baseline(root):
    result = h.read(root/'baseline/result.json')
    if h.digest((root/'baseline/result.json').read_bytes()) != h.read(root/'trial.json')['baseline_sha256']:
        raise ValueError('Baseline receipt changed')
    assert result['valid'] and h.metrics(result)['raw_heartbeats'] > 0
    return result


def current(root):
    return h.read(sorted((root/'states').glob('*.json'))[-1])


def request(root, state):
    config, problem, _ = load(root)
    return policy.packet(state, problem, (root/'input/prompt.txt').read_text(),
                         config['condition'], config['max_proposals'])


def init(root):
    config, problem, environment = load(root)
    state = policy.initial(problem, baseline(root))
    h.write(root/'start.json', {'started_at':now(), 'environment':LeanEvaluator().fingerprint(environment),
        'backend':'fresh-codex-subagent', 'model_id_unobservable':True, 'api_calls':0,
        'codex_cost_usd':None, 'hidden_context_controlled':False, 'os_isolation':False})
    h.write(root/'states/000.json', state)
    h.write(root/'requests/001.json',request(root,state))
    print(json.dumps({'ready':True,'request':str(root/'requests/001.json')}))


def decode(root, state, response):
    config, problem, _ = load(root)
    try:
        code, card = policy.parse(response, problem, config['condition'], state)
        return code, card, None
    except (ValueError, TypeError, KeyError) as error:
        return None, None, str(error)


def feedback(root, result, rejection, folder):
    value = format_feedback(result,rejection,1600,str(root),folder,'structured_v1')
    if value.get('metrics'):
        value['metrics'].pop('raw_samples',None)
    return value


def submit(root, response_path):
    config, _, _ = load(root)
    state = current(root); step = state['step']+1
    if step > config['max_proposals'] or (root/'summary.json').exists():
        raise ValueError('Proposal budget exhausted')
    assert h.read(root/f'requests/{step:03}.json') == request(root,state)
    response = h.read(response_path)
    folder = root/f'steps/{step:03}'
    h.write(folder/'response.json',response)
    code, card, rejection = decode(root,state,response)
    result = None
    if code:
        (folder/'candidate.lean').write_text(code)
        result = evaluate(root,code,folder/'evaluation')
    value = feedback(root,result,rejection,folder/'evaluation')
    state = policy.transition(state,code,card,result,value)
    h.write(folder/'event.json',{'recorded_at':now(),'state_after':state})
    h.write(root/f'states/{step:03}.json',state)
    if result and h.environment_failed(result):
        raise RuntimeError('Environment failed; stop and contact coordinator')
    if step < config['max_proposals']:
        h.write(root/f'requests/{step+1:03}.json',request(root,state))
    print(json.dumps({'step':step,'feedback':value,'best_tokens':state['best']['tokens'],
        'best_raw_heartbeats':state['best']['raw_heartbeats']},ensure_ascii=False))


def finish(root):
    config, _, environment = load(root); state = current(root)
    if state['step'] != config['max_proposals']:
        raise ValueError('Complete the fixed proposal budget first')
    (root/'selected.lean').write_text(state['best']['code'])
    final = evaluate(root,state['best']['code'],root/'final')
    unchanged = LeanEvaluator().fingerprint(environment) == h.read(root/'start.json')['environment']
    b = state['baseline']; cost = state['best']['rank_numerator']/(2*b['tokens']*b['raw_heartbeats'])
    summary = {'trial_id':config['trial_id'],'problem_id':config['problem_id'],
        'condition':config['condition'],'repetition':config['repetition'],
        'started_at':h.read(root/'start.json')['started_at'],'finished_at':now(),
        'status':'completed' if final['valid'] and unchanged else 'failed',
        'proposal_count':state['step'],'valid_proposals':sum(x['valid'] for x in state['attempts']),
        'baseline':b,'selected':state['best'],'local_cost':cost,
        'final_valid':final['valid'],'final_metrics':h.metrics(final),
        'environment_unchanged':unchanged,'official_score':False,
        'api_calls':0,'codex_cost_usd':None,'model_id':None,
        'all_required_pins_verified':False,'input_scope':'development problems; not held out'}
    h.write(root/'summary.json',summary); h.seal(root)
    print(json.dumps({k:v for k,v in summary.items() if k!='selected'}))


def replay(root):
    h.check_artifacts(root)
    config, problem, _ = load(root)
    state = policy.initial(problem,baseline(root))
    assert state == h.read(root/'states/000.json')
    for step in range(1,config['max_proposals']+1):
        assert h.read(root/f'requests/{step:03}.json') == request(root,state)
        folder = root/f'steps/{step:03}'
        response = h.read(folder/'response.json')
        assert response == h.read(root/f'responses/{step:03}.json')
        code, card, rejection = decode(root,state,response)
        result = h.read(folder/'evaluation/result.json') if code else None
        if code:
            assert code == (folder/'candidate.lean').read_text()
        state = policy.transition(state,code,card,result,feedback(root,result,rejection,folder/'evaluation'))
        assert state == h.read(root/f'states/{step:03}.json')
        assert state == h.read(folder/'event.json')['state_after']
    summary = h.read(root/'summary.json')
    assert summary['selected'] == state['best']
    assert (root/'selected.lean').read_text() == state['best']['code']
    assert summary['final_valid'] == h.read(root/'final/result.json')['valid']
    assert summary['final_metrics'] == h.metrics(h.read(root/'final/result.json'))
    assert summary['proposal_count'] == state['step']
    b = state['baseline']
    assert summary['local_cost'] == state['best']['rank_numerator']/(2*b['tokens']*b['raw_heartbeats'])
    print(json.dumps({'record_replay_passed':True,'trial_id':root.name,'new_lean_or_model_calls':False}))


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['init','submit','finish','replay'])
    ap.add_argument('trial',type=Path); ap.add_argument('--response',type=Path)
    args=ap.parse_args(); root=args.trial.resolve()
    if args.command=='submit':submit(root,args.response.resolve())
    else:globals()[args.command](root)
