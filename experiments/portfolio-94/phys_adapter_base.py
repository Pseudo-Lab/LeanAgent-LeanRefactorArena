"""Common full-source Physlib validation, pinned to the supplied warmup metadata."""
from pathlib import Path
import sys,json,re,os,hashlib,tarfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];RUN=HERE.parent.parent/'runs/portfolio-94'
TOKENS=ROOT/'insights-20261024-round7/p11/tokens_snapshot.py';sys.path.insert(0,str(TOKENS.parent))
from tokens_snapshot import proof_tokens,validate_declaration
ALLOWED_AXIOMS={'propext','Classical.choice','Quot.sound'}
def digest(s):return hashlib.sha256(s.encode() if isinstance(s,str) else s).hexdigest()
class Adapter:
 def __init__(self,problem):
  self.META_PATH=ROOT/'LEArN/week3-experiments/experiments/evidence/2026-10-16-warmup15-xhigh'/problem/'metadata.json'
  self.META=json.loads(self.META_PATH.read_text());self.STATEMENT=self.META['statement'];self.TARGET=self.META['name'];self.RAW_MARKER=problem+'_RAW';self.proof_tokens=proof_tokens;self.validate_declaration=validate_declaration;self.ALLOWED_AXIOMS=ALLOWED_AXIOMS
  self.DEPENDENCIES=[Path(__file__),TOKENS,HERE/'build_projects.py']
  self.WRAP='''
open Lean Elab Command in
elab "#phys_measure " tag:str cmd:command : command => do
  let name := `'''+self.TARGET+'''
  if (← getEnv).contains name then throwError "target already exists"
  let before ← IO.getNumHeartbeats
  elabCommand cmd
  let after ← IO.getNumHeartbeats
  unless (← getEnv).contains name do throwError "target not defined"
  logInfo m!"'''+self.RAW_MARKER+''' {tag.getString} {after - before}"
'''
 def plain_source(self,source,code):
  validate_declaration(code,self.STATEMENT)
  if source.count(self.META['src'])!=1:raise ValueError('Target not unique')
  return source.replace(self.META['src'],code,1)
 def measured_source(self,source,code,nonce):
  if not re.fullmatch(r'[a-f0-9]{32}',nonce):raise ValueError('Bad nonce')
  plain=self.plain_source(source,code);start=source.index(self.META['src']);lead=source.rfind('/--',0,start)
  if lead<0 or source[source.index('-/',lead)+2:start].strip():lead=start
  command=source[lead:start]+code;marker='set_option Elab.async false in\n#phys_measure "'+nonce+'"\n'
  measured=plain.replace(command,marker+command,1)
  imports=list(re.finditer(r'(?m)^(?:(?:public|private) )?(?:meta )?import [^\n]+',measured));last=imports[-1].end();instrument='\npublic import Lean\n'+self.WRAP
  measured=measured[:last]+instrument+measured[last:]
  if measured.replace(instrument,'',1).replace(marker,'',1)!=plain:raise ValueError('Context changed')
  return measured
 def load_environment(self,path):
  cfg=json.loads(path.read_text())
  if not cfg.get('ready'):raise ValueError('Not ready')
  srcroot=Path(cfg['source']);sourcepath=srcroot/self.META['file_path'];source=sourcepath.read_text();lean=Path(cfg['compiler']);revision=list(self.META['version_info'][0].values())[0]
  if (srcroot/'lean-toolchain').read_text().strip()!='leanprover/lean4:v4.32.0':raise ValueError('Wrong pin')
  receipt=Path(cfg['build_receipts']);rows=json.loads(receipt.read_text());archive=RUN/'physlib-runtime-432/source.tar.gz'
  files=[sourcepath,lean,srcroot/'lake-manifest.json',archive,receipt,Path(cfg['dependency_manifest'])]
  with tarfile.open(archive) as tar:
   prefix='physlib-'+revision+'/'
   for rel in [self.META['file_path'],'lake-manifest.json','lean-toolchain',*[r['module'].replace('.','/')+'.lean' for r in rows]]:
    if tar.extractfile(prefix+rel).read()!=(srcroot/rel).read_bytes():raise ValueError('Archive mismatch: '+rel)
  for r in rows:
   p=Path(r['source']);o=Path(cfg['library'])/(r['module'].replace('.','/')+'.olean')
   if digest(p.read_bytes())!=r['source_sha256'] or digest(o.read_bytes())!=r['olean_sha256']:raise ValueError('Build changed')
   files.extend([p,o])
  files.extend(sorted((lean.parent.parent/'lib/lean').glob('*shared*.dylib')))
  fp={'lean_pin':'v4.32.0','source_revision':revision,'LEAN_PATH':cfg['LEAN_PATH'],'files':{str(p):digest(p.read_bytes()) for p in files}}
  fp['identity_sha256']=digest(json.dumps(fp,sort_keys=True));env=dict(os.environ,LEAN_PATH=cfg['LEAN_PATH'])
  return cfg,lean,[],env,source,fp
