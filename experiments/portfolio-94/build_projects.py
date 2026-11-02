"""Compile required CSLib/Physlib modules against restored exact Mathlib cache, preserving sources."""
from pathlib import Path
import os,subprocess,json,hashlib,time,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];RUN=HERE.parent.parent/'runs/portfolio-94';pin=sys.argv[1]
out=RUN/('dependency-'+pin);cfg=json.loads((out/'environment.json').read_text());assert cfg['ready'];closure=json.loads((out/'closure.json').read_text())
work=out/'projects';work.mkdir(exist_ok=True);lib=work/'lib';lib.mkdir(exist_ok=True)
env=dict(os.environ,LEAN_PATH=str(lib)+':'+cfg['LEAN_PATH'])
records={'Cslib':[],'Physlib':[]};skip={'Physlib.Electromagnetism.Dynamics.IsExtrema','Physlib.QFT.PerturbationTheory.WickAlgebra.TimeOrder'}
for row in closure['source_modules']:
 module=row['module']
 if module in skip:continue
 source=Path(row['source']);namespace=module.split('.')[0]
 srcroot=source.parents[len(module.split('.'))-1];dest=lib/(module.replace('.','/')+'.olean');dest.parent.mkdir(parents=True,exist_ok=True)
 cmd=[cfg['compiler'],'-j1','-M4096','--root='+str(srcroot),'-o',str(dest),str(source)];start=time.monotonic()
 try:r=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=300);rc=r.returncode;log=r.stdout+r.stderr
 except subprocess.TimeoutExpired as e:rc=124;log=str(e)
 (work/(module+'.log')).write_text(log)
 rec={'module':module,'source':str(source),'command':cmd,'returncode':rc,'seconds':time.monotonic()-start,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'log_sha256':hashlib.sha256(log.encode()).hexdigest()}
 if not rc:rec['olean_sha256']=hashlib.sha256(dest.read_bytes()).hexdigest()
 records[namespace].append(rec);(work/(namespace+'-build_receipts.json')).write_text(json.dumps(records[namespace],indent=2)+'\n')
 print(module,rc,log[-600:] if rc else '',flush=True)
 if rc:raise SystemExit(rc)
 # Publish completed CSLib readiness as soon as Typing is built, even if later Physlib build fails.
 if module.endswith('.Fsub.Typing'):
  c=dict(ready=True,compiler=cfg['compiler'],source=str(srcroot),library=str(lib),LEAN_PATH=env['LEAN_PATH'],build_receipts=str(work/'Cslib-build_receipts.json'))
  (work/'cslib-environment.json').write_text(json.dumps(c,indent=2)+'\n')
if records['Physlib']:
 c=dict(ready=True,compiler=cfg['compiler'],source=str(RUN/'physlib-runtime-432/source'),library=str(lib),LEAN_PATH=env['LEAN_PATH'],build_receipts=str(work/'Physlib-build_receipts.json'),dependency_manifest=str(out/'archives.json'))
 (work/'physlib-environment.json').write_text(json.dumps(c,indent=2)+'\n')
