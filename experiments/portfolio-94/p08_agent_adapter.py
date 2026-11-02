"""Full-source P08 adapter; target absent on measurement entry, pinned CSLib imports."""
from pathlib import Path
import sys, json, os, hashlib, re
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]
TOKENS=ROOT/'insights-20261024-round7/p11/tokens_snapshot.py'
sys.path.insert(0,str(TOKENS.parent))
from tokens_snapshot import proof_tokens,validate_declaration
META_PATH=ROOT/'LEArN/week3-experiments/experiments/evidence/2026-10-16-warmup15-xhigh/P08/metadata.json'
META=json.loads(META_PATH.read_text());TARGET=META['name'];STATEMENT=META['statement']
ALLOWED_AXIOMS={'propext','Classical.choice','Quot.sound'};RAW_MARKER='P08_RAW'
DEPENDENCIES=[TOKENS]
WRAP='''
open Lean Elab Command in
elab "#p08_measure " tag:str cmd:command : command => do
  let name := `Cslib.SKI.parallelReduction_diamond
  if (← getEnv).contains name then throwError "target already exists"
  let before ← IO.getNumHeartbeats
  elabCommand cmd
  let after ← IO.getNumHeartbeats
  unless (← getEnv).contains name do throwError "target not defined"
  logInfo m!"P08_RAW {tag.getString} {after - before}"
'''
def digest(s):return hashlib.sha256(s.encode() if isinstance(s,str) else s).hexdigest()
def plain_source(source,code):
 validate_declaration(code,STATEMENT)
 if source.count(META['src'])!=1:raise ValueError('Target source mismatch')
 return source.replace(META['src'],code,1)
def measured_source(source,code,nonce):
 if not re.fullmatch(r'[a-f0-9]{32}',nonce):raise ValueError('Bad nonce')
 plain=plain_source(source,code);start=source.index(META['src']);lead=source.rfind('/--',0,start)
 if lead<=0 or not source[lead:start].rstrip().endswith('-/'):raise ValueError('Expected target doc comment')
 command=source[lead:start]+code;marker='set_option Elab.async false in\n#p08_measure "'+nonce+'"\n'
 measured=plain.replace(command,marker+command,1)
 imports=list(re.finditer(r'(?m)^(?:(?:public|private) )?(?:meta )?import [^\n]+',measured));last=imports[-1].end()
 instrumentation='\npublic import Lean\n'+WRAP
 measured=measured[:last]+instrumentation+measured[last:]
 if measured.replace(instrumentation,'',1).replace(marker,'',1)!=plain:raise ValueError('Context changed')
 return measured

def load_environment(path):
 cfg=json.loads(path.read_text())
 if not cfg.get('ready'):raise ValueError('Dependencies not READY')
 srcroot=Path(cfg['source']);lean=Path(cfg['compiler']);sourcepath=srcroot/META['file_path'];source=sourcepath.read_text()
 if source.count(META['src'])!=1:raise ValueError('Original absent')
 pin=(srcroot/'lean-toolchain').read_text().strip().split(':')[-1]
 pins={k:v for entry in META['version_info'] for k,v in entry.items()}
 if pin not in pins:raise ValueError('Unexpected pin')
 # Extracted checkout: verify every CSLib input byte against the pinned source archive.
 import tarfile
 revision=pins[pin]
 archive=ROOT/'insights-20261024-round5/validation'/('cslib-'+revision[:7]+'.tar.gz')
 receipt=path.with_name('build_receipts'+pin.removeprefix('v').split('.')[0]+pin.removeprefix('v').split('.')[1]+'.json')
 files=[lean,sourcepath,srcroot/'lake-manifest.json',srcroot/'lean-toolchain',receipt,archive]
 receipts=json.loads(receipt.read_text())
 with tarfile.open(archive) as tar:
  prefix='cslib-'+revision+'/'
  for rel in [META['file_path'],'lake-manifest.json','lean-toolchain',*[r['module'].replace('.','/')+'.lean' for r in receipts]]:
   if tar.extractfile(prefix+rel).read()!=(srcroot/rel).read_bytes():raise ValueError('Pinned archive differs: '+rel)
 for r in receipts:
  p=srcroot/(r['module'].replace('.','/')+'.lean');o=Path(cfg['library'])/(r['module'].replace('.','/')+'.olean')
  if r['returncode']!=0 or digest(p.read_bytes())!=r['source_sha256'] or not o.exists():raise ValueError('Build changed')
  files.extend([p,o])
 # Historical receipts lack output hashes; freeze current outputs and cache identity in this run.
 for name in ['cache_identity','hash_receipt','cache_selection','cache_extract']:
  evidence=path.with_name(name+pin.removeprefix('v').split('.')[0]+pin.removeprefix('v').split('.')[1]+'.json')
  if evidence.exists():files.append(evidence)
 files.extend(sorted((lean.parent.parent/'lib/lean').glob('*shared*.dylib')))
 fp={'lean_pin':pin,'source_revision':revision,'LEAN_PATH':cfg['LEAN_PATH'],'files':{str(p):digest(p.read_bytes()) for p in files}}
 fp['identity_sha256']=digest(json.dumps(fp,sort_keys=True))
 env=dict(os.environ,LEAN_PATH=cfg['LEAN_PATH'])
 return cfg,lean,[],env,source,fp
