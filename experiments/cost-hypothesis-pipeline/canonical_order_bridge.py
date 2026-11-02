"""Audited canonical parent-selection/order amendment for immutable snapshots.

New cohorts use fixed policy.py directly. This bridge preserves the first
cohort's original code, manifests, requests, responses and Lean receipts.
Sorting before the family slice can change future visible parent membership;
existing-request equivalence does not claim future treatment equivalence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

OLD="    for key in list(state['parents'].values())[-3:]:"
NEW="    for key in [state['parents'][family] for family in sorted(state['parents'])][-3:]:"


def main(command,root,response):
    patch=Path(__file__).resolve().parent
    manifest=json.loads((patch/'manifest.json').read_text())
    assert root.parent==patch.parents[1]
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((patch/name).read_bytes()).hexdigest()==digest
    original=(root/'code/policy.py').read_text()
    assert hashlib.sha256(original.encode()).hexdigest()==manifest['base_policy_sha256']
    assert original.count(OLD)==1
    assert original.replace(OLD,NEW)==(patch/'policy.py').read_text()
    sys.path.insert(0,str(root/'code'))
    import worker
    worker.load(root)
    spec=importlib.util.spec_from_file_location('canonical_order_policy',patch/'policy.py')
    fixed=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixed)
    worker.policy=fixed
    event={'command':command,'trial_id':root.name,'started_at':datetime.now(timezone.utc).isoformat(),
           'step_before':worker.current(root)['step']}
    try:
        if command=='submit':worker.submit(root,response.resolve())
        else:getattr(worker,command)(root)
        event['status']='completed'
    except Exception as error:
        event['status']='failed';event['error']=str(error)
        raise
    finally:
        if command!='replay':
            event['finished_at']=datetime.now(timezone.utc).isoformat()
            with (patch/'invocations.jsonl').open('a') as stream:
                stream.write(json.dumps(event,ensure_ascii=False)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['submit','finish','replay'])
    ap.add_argument('trial',type=Path);ap.add_argument('--response',type=Path)
    args=ap.parse_args();main(args.command,args.trial.resolve(),args.response)
