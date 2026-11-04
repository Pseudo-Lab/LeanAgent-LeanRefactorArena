#!/usr/bin/env python3
"""Package local implementation and completed pilot evidence, with an exact-key leak check."""
import argparse, hashlib, json, subprocess, sys, zipfile
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'src'))
from lean_agent.models import load_key

def package(root,out,key_file):
    root=root.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    results=json.loads((root/'results.json').read_text())
    if len(results)!=10:raise ValueError('Pilot incomplete')
    ledger=json.loads((root/'budget.json').read_text())
    if any(c['status']!='settled' for c in ledger['calls']):raise ValueError('Unsettled request')
    key=load_key(key_file,names=('OPENAI_API_KEY','OPENROUTER_API_KEY','OPENROUTER')).encode()
    changed=subprocess.check_output(['git','diff','--name-only','-z'],cwd=REPO).decode().split('\0')
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=REPO).decode().split('\0')
    files={}
    for name in sorted(set(changed+untracked)):
        p=REPO/name
        if name and p.is_file():files['implementation/'+name]=p
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.suffix not in ('.lock','.pyc') and '__pycache__' not in p.parts:
            files['evidence/'+p.relative_to(root).as_posix()]=p
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.suffix not in ('.zip',) and p.name!='package-manifest.json':
            files['report/'+p.relative_to(out).as_posix()]=p
    forbidden=[n for n,p in files.items() if p.name.endswith('.env') or key in p.read_bytes()]
    if forbidden:raise ValueError('Credential content found in '+str(forbidden))
    patch=subprocess.check_output(['git','diff','--binary'],cwd=REPO)
    if key in patch:raise ValueError('Credential in patch')
    manifest={'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip(),
              'credential_scan_passed':True,'files':{n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()},
              'note':'Tracked changes plus untracked implementation files are an overlay on base_commit; evidence contains canonical selected proofs and raw receipts. No credentials included.'}
    (out/'package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(out/'arklib10-implementation-evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,p in files.items():z.write(p,n)
        z.writestr('implementation/tracked-changes.patch',patch)
        z.write(out/'package-manifest.json','package-manifest.json')
    print(json.dumps({'files':len(files),'credential_scan_passed':True,'zip_bytes':(out/'arklib10-implementation-evidence.zip').stat().st_size}))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--key-file',type=Path,required=True);a=ap.parse_args();package(a.root,a.output,a.key_file)
