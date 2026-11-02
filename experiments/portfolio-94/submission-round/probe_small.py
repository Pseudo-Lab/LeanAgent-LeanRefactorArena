"""Fresh full-source measurements for the submission round. No submission calls."""
from pathlib import Path
import hashlib,json,os,re,statistics,subprocess,sys,uuid

E=Path(__file__).resolve().parents[1];W=E.parents[1];ROOT=W.parents[1]
OUT=W/'runs/portfolio-94/submission-round'
sys.path.insert(0,str(E));from resources_exclusive import lease
sys.path.insert(0,str(ROOT/'insights-20261024-round7/p11'))
from tokens_snapshot import validate_declaration,proof_tokens
from phys_adapter_base import Adapter
ARCHIVE=ROOT/'LEArN/week3-experiments/experiments/evidence/2026-10-16-warmup15-xhigh'
PINS={'4.25.0':'1ccd71f89cbbd82ae7d097723ce1722ca7b01c33','4.26.0':'2df2f0150c275ad53cb3c90f7c98ec15a56a1a67','4.27.0':'a3a10db0e9d66acbebf76c5e6a135066525ac900'}
ALLOWED={'propext','Classical.choice','Quot.sound'}
WRAP='''
open Lean Elab Command in
elab "#submission_measure " nonce:str target:str cmd:command : command => do
  let name := target.getString.toName
  if (← getEnv).contains name then throwError "target exists"
  let before ← IO.getNumHeartbeats
  elabCommand cmd
  let after ← IO.getNumHeartbeats
  unless (← getEnv).contains name do throwError "target missing"
  logInfo m!"SUBMIT_RAW {nonce.getString} {after-before}"
'''

def sha(s):return hashlib.sha256(s if isinstance(s,bytes) else s.encode()).hexdigest()

def setup(n,pin=None):
 meta=json.loads((ARCHIVE/f'P{n:02}/metadata.json').read_text())
 env=dict(os.environ);args=[]
 if n==4:
  a=Adapter('P04');cfg,lean,args,env,source,fp=a.load_environment(W/'runs/portfolio-94/dependency-432/projects/physlib-environment.json')
  return meta,source,lean,args,env,fp
 if n in [1,2]:
  project=ROOT/'LEArN/Strata';pin='4.26.0';source=(project/meta['file_path']).read_text()
  lean=Path.home()/'.elan/toolchains/leanprover--lean4---v4.26.0/bin/lean';args=['-Dexperimental.module=true']
 else:
  pin=pin or '4.25.0';project=ROOT/'LEArN/.cache'/('mathlib-'+PINS[pin]);source=(ARCHIVE/f'P{n:02}/source.lean').read_text()
  lean=Path.home()/f'.elan/toolchains/leanprover--lean4---v{pin}/bin/lean'
 assert (project/'lean-toolchain').read_text().strip()=='leanprover/lean4:v'+pin
 paths=[project/'.lake/build/lib/lean']+sorted((project/'.lake/packages').glob('*/.lake/build/lib/lean'))
 env['LEAN_PATH']=':'.join(map(str,paths))
 fp=dict(pin=pin,source_sha256=sha(source),compiler=str(lean),compiler_sha256=sha(lean.read_bytes()),
  manifest_sha256=sha((project/'lake-manifest.json').read_bytes()),LEAN_PATH=env['LEAN_PATH'])
 return meta,source,lean,args,env,fp

def evaluate(n,code,label,pin=None,runs=1):
 meta,source,lean,args,env,fp=setup(n,pin)
 validate_declaration(code,meta['statement']);assert source.count(meta['src'])==1
 folder=OUT/f'P{n:02}-{label}-{pin or "primary"}-{uuid.uuid4().hex[:8]}';folder.mkdir(parents=True)
 (folder/'candidate.lean').write_text(code)
 plain=source.replace(meta['src'],code,1)
 start=source.index(meta['src']);lead=source.rfind('/--',0,start)
 if lead<0 or source[source.index('-/',lead)+2:start].strip():lead=start
 whole=source[lead:start]+code
 assert plain.count(whole)==1
 jobs=[];samples=[];axioms=None
 rec=dict(id=n,label=label,pin=pin,valid=False,candidate_sha256=sha(code),tokens=proof_tokens(code,meta['statement']),
  fingerprint=fp,folder=str(folder),jobs=jobs,raw_samples=samples,runner_sha256=sha(Path(__file__).read_bytes()))
 def save(): (folder/'result.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
 def job(name,text,opts=(),audit=False):
  f=folder/(name+'.lean');f.write_text(text);ee=dict(env)
  if audit:ee['LEAN_PATH']=str(folder)+':'+env['LEAN_PATH']
  cmd=[str(lean),'-j1','-M4096','--root='+str(folder),*args,*opts,str(f)]
  with lease():
   p=subprocess.run(cmd,env=ee,cwd=folder,capture_output=True,text=True,timeout=240)
  log=p.stdout+p.stderr;(folder/(name+'.log')).write_text(log)
  jobs.append(dict(name=name,command=cmd,returncode=p.returncode,source_sha256=sha(text),log_sha256=sha(log)));save()
  return p.returncode==0,log
 save();ok,_=job('Check',plain,['-o',str(folder/'Check.olean')])
 if ok:
  audit='import Check\nimport Lean\nopen Lean Elab Command in\nrun_cmd do\n  let ax ← Lean.collectAxioms `'+meta['name']+'\n  logInfo m!"SUBMIT_AXIOMS {toJson (ax.toList.map Name.toString)}"\n'
  ok,log=job('Audit',audit,audit=True);found=re.findall(r'SUBMIT_AXIOMS (\[[^\n]*\])',log)
  if len(found)==1:axioms=json.loads(found[0])
  ok=ok and axioms is not None and set(axioms)<=ALLOWED
 if ok:
  for i in range(runs):
   nonce=uuid.uuid4().hex;marker='set_option Elab.async false in\n#submission_measure "'+nonce+'" '+json.dumps(meta['name'])+'\n'
   measured=plain.replace(whole,marker+whole,1)
   imports=list(re.finditer(r'(?m)^(?:(?:public|private) )?(?:meta )?import [^\n]+',measured));pos=imports[-1].end()
   instrument='\n'+('public ' if re.search(r'(?m)^module\s*$',source) else '')+'import Lean\n'+WRAP
   measured=measured[:pos]+instrument+measured[pos:]
   assert measured.replace(instrument,'',1).replace(marker,'',1)==plain
   ok,log=job(f'Measure{i+1}',measured);marks=re.findall('SUBMIT_RAW '+nonce+r' (\d+)',log);jobs[-1]['nonce']=nonce
   if not ok or len(marks)!=1:ok=False;break
   samples.append(int(marks[0]));save()
 rec.update(valid=ok and len(samples)==runs,axioms=axioms,raw=statistics.median(samples) if ok and len(samples)==runs else None);save()
 print(json.dumps({k:rec[k] for k in ['id','label','pin','valid','tokens','raw','folder']}),flush=True)
 return rec
