"""Resume an audited submission stopped before Lean by the disk preflight.

The frozen trial and canonical bridge remain unchanged. This adapter skips only
the two already-written, hash-verified proposal files. It retains evaluate(),
including the 1 GiB guard, and uses the original transition/feedback functions.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_pending(root, evidence):
    step = evidence['step']
    for name, expected in evidence['files'].items():
        assert digest(root/name) == expected, 'Pending file changed: '+name
    assert sorted((root/'states').glob('*.json'))[-1].name == f'{step-1:03}.json'
    for name in (f'steps/{step:03}/evaluation', f'steps/{step:03}/event.json',
                 f'states/{step:03}.json', f'requests/{step+1:03}.json', 'summary.json'):
        assert not (root/name).exists(), 'Already evaluated or advanced: '+name


def main(root):
    patch = Path(__file__).resolve().parent
    manifest = json.loads((patch/'manifest.json').read_text())
    assert digest(Path(__file__)) == manifest['resume_code_sha256']
    assert root.parent == patch.parents[1]
    evidence = manifest['pending'][root.name]
    validate_pending(root,evidence)
    canonical = root.parent/'amendments/canonical-parent-order/canonical_order_bridge.py'
    assert digest(canonical) == manifest['canonical_bridge_sha256']
    sys.path.insert(0,str(root/'code'))
    import worker

    def resume_submit(trial,response_path):
        validate_pending(trial,evidence)
        config,_,_ = worker.load(trial)
        state = worker.current(trial);step = state['step']+1
        assert step == evidence['step'] <= config['max_proposals']
        assert worker.h.read(trial/f'requests/{step:03}.json') == worker.request(trial,state)
        folder = trial/f'steps/{step:03}'
        response = worker.h.read(response_path)
        assert response == worker.h.read(folder/'response.json')
        code,card,rejection = worker.decode(trial,state,response)
        assert code and rejection is None
        assert code == (folder/'candidate.lean').read_text()
        result = worker.evaluate(trial,code,folder/'evaluation')
        value = worker.feedback(trial,result,rejection,folder/'evaluation')
        state = worker.policy.transition(state,code,card,result,value)
        worker.h.write(folder/'event.json',{'recorded_at':worker.now(),'state_after':state})
        worker.h.write(trial/f'states/{step:03}.json',state)
        if worker.h.environment_failed(result):
            raise RuntimeError('Environment failed; stop and contact coordinator')
        if step < config['max_proposals']:
            worker.h.write(trial/f'requests/{step+1:03}.json',worker.request(trial,state))
        print(json.dumps({'step':step,'feedback':value,'best_tokens':state['best']['tokens'],
                         'best_raw_heartbeats':state['best']['raw_heartbeats']},ensure_ascii=False))

    worker.submit = resume_submit
    spec = importlib.util.spec_from_file_location('canonical_bridge_for_resume',canonical)
    bridge = importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    event = {'trial_id':root.name,'step':evidence['step'],
             'started_at':datetime.now(timezone.utc).isoformat()}
    try:
        bridge.main('submit',root,root/f"responses/{evidence['step']:03}.json")
        event['status'] = 'completed'
    except Exception as error:
        event['status'] = 'failed';event['error'] = str(error)
        raise
    finally:
        event['finished_at'] = datetime.now(timezone.utc).isoformat()
        with (patch/'resumptions.jsonl').open('a') as stream:
            stream.write(json.dumps(event,ensure_ascii=False)+'\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('trial',type=Path)
    main(ap.parse_args().trial.resolve())
