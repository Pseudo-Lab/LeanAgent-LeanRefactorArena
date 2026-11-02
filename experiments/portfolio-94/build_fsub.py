"""Build exact pinned CSLib imports into a new, isolated library. No target import."""
from pathlib import Path
import os, subprocess, json, hashlib, time, re, argparse
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]
a=argparse.ArgumentParser();a.add_argument('pin');x=a.parse_args()
old=ROOT/'insights-20261024-round5/validation'/('environment'+x.pin+'.json')
cfg=json.loads(old.read_text());src=Path(cfg['source']);out=HERE.parent.parent/'runs/portfolio-94'/('p07-runtime-'+x.pin);out.mkdir(parents=True,exist_ok=True)
lib=out/'lib';lib.mkdir(exist_ok=True)
extra=ROOT/'insights-20261024-round7/restore431/cache_union'
paths=[str(lib)]+([str(extra)] if x.pin=='431' else [])+[cfg['LEAN_PATH']]
env=dict(os.environ,LEAN_PATH=':'.join(paths))
# Lean resolves a namespace root once, so missing Mathlib modules need a complete local union.
if x.pin=='431':
 for source in (extra/'Mathlib').rglob('*'):
  if source.is_file():
   dest=lib/source.relative_to(extra);dest.parent.mkdir(parents=True,exist_ok=True)
   if not dest.exists():dest.symlink_to(source.resolve())
 package=ROOT/'LEArN/.cache/arklib-c1712f6c496d0aef04f09bae42aec13811b3273f/.lake/packages/mathlib'
 math_records=[]
 for module in ['Mathlib.Data.List.Lookmap','Mathlib.Data.List.Sigma']:
  source=package/(module.replace('.','/')+'.lean');target=lib/(module.replace('.','/')+'.olean');target.parent.mkdir(parents=True,exist_ok=True)
  command=[cfg['compiler'],'-j1','-M4096','--root='+str(package),'-o',str(target),str(source)]
  r=subprocess.run(command,env=env,text=True,capture_output=True,timeout=300);log=r.stdout+r.stderr
  (out/(module+'.log')).write_text(log)
  rec={'module':module,'command':command,'returncode':r.returncode,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
  if r.returncode==0:rec['olean_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
  math_records.append(rec);(out/'mathlib_receipts.json').write_text(json.dumps(math_records,indent=2)+'\n');print(module,r.returncode,log[-800:],flush=True)
  if r.returncode:raise SystemExit(r.returncode)
seen=set();order=[]
def visit(m):
 if m in seen:return
 seen.add(m);p=src/(m.replace('.','/')+'.lean')
 for d in re.findall(r'(?m)^\s*(?:public\s+)?(?:meta\s+)?import\s+(Cslib\.[\w.]+)',p.read_text()):visit(d)
 order.append(m)
visit('Cslib.Languages.LambdaCalculus.LocallyNameless.Fsub.Typing')
records=[]
for module in order:
 source=src/(module.replace('.','/')+'.lean');target=lib/(module.replace('.','/')+'.olean');target.parent.mkdir(parents=True,exist_ok=True)
 command=[cfg['compiler'],'-j1','-M4096','--root='+str(src),'-o',str(target),str(source)]
 start=time.monotonic()
 try:
  r=subprocess.run(command,env=env,text=True,capture_output=True,timeout=300);rc=r.returncode;log=r.stdout+r.stderr
 except subprocess.TimeoutExpired as e:rc=124;log=str(e)
 (out/(module+'.log')).write_text(log)
 rec=dict(module=module,command=command,returncode=rc,seconds=time.monotonic()-start,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),log_sha256=hashlib.sha256(log.encode()).hexdigest())
 if rc==0:rec['olean_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
 records.append(rec);(out/'build_receipts.json').write_text(json.dumps(records,indent=2)+'\n');print(module,rc,log[-800:],flush=True)
 if rc:break
cfg.update(LEAN_PATH=env['LEAN_PATH'],library=str(lib),modules=order,ready=len(records)==len(order) and all(r['returncode']==0 for r in records),build_receipts=str(out/'build_receipts.json'))
(out/'environment.json').write_text(json.dumps(cfg,indent=2)+'\n')
