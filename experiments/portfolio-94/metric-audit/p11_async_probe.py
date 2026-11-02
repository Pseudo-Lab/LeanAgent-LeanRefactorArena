"""Proof-local async boundary diagnostic; NOT accepted by frozen submission validator.

Only adds a literal option/auxiliary tactic around the unchanged proof body.
Keeps original wrapper, statement, surrounding source and frozen config untouched.
No portfolio/state updates. Local regex acceptance does not establish rule compliance.
"""
from pathlib import Path
import json, re, subprocess, sys, time, uuid, hashlib

E=Path(__file__).resolve().parents[1]
W=E.parents[1]
sys.path.insert(0,str(E))
import search_exclusive4 as s
from resources_exclusive import lease

ROOT=W/'runs/portfolio-94/p11-exclusive4-431'
OUT=W/'runs/portfolio-94/diagnostics/metric-audit-p11-async'
cfg,m,loaded=s.load(ROOT)
ecfg,lean,args,env,source,fp=loaded
base=(E/'validated/P11-8a33b2dfc592/P11.lean').read_text()
rest=base[len(m.STATEMENT):]
match=re.match(r'\s*:=\s*by\s*\n',rest)
assert match
body=rest[match.end():]
variants={
 'baseline':base,
 'body_async':m.STATEMENT+' := by\n  set_option Elab.async true in\n'+''.join('  '+line+'\n' for line in body.splitlines()),
 'aux_sync':m.STATEMENT+' := by\n  as_aux_lemma =>\n'+''.join('  '+line+'\n' for line in body.splitlines()),
 'aux_async':m.STATEMENT+' := by\n  set_option Elab.async true in\n    as_aux_lemma =>\n'+''.join('    '+line+'\n' for line in body.splitlines()),
}

def sha(b):return hashlib.sha256(b).hexdigest()

def run(label,code,repeat=1):
 folder=OUT/f'{label}-r{repeat}';folder.mkdir(parents=True,exist_ok=False)
 (folder/'candidate.lean').write_text(code)
 nonce=uuid.uuid4().hex
 measured=m.measured_source(source,base,nonce)
 assert measured.count(base)==1
 measured=measured.replace(base,code,1)
 file=folder/'Measure.lean';file.write_text(measured)
 # Separate import audit below waits for exported environment and inspects target axioms.
 cmd=[str(lean),'-j1','-M4096','--root='+str(folder),*args,'-o',str(folder/'Measure.olean'),str(file)]
 with lease():
  start=time.monotonic();p=subprocess.run(cmd,env=env,cwd=folder,capture_output=True,text=True,timeout=180);seconds=time.monotonic()-start
 log=p.stdout+p.stderr;(folder/'Measure.log').write_text(log)
 marks=re.findall('P11_RAW '+nonce+r' (\d+)',log)
 ax=None; auditrc=None
 if p.returncode==0 and len(marks)==1:
  audit='import Measure\nimport Lean\nopen Lean Elab Command in\nrun_cmd do\n  let ax ← Lean.collectAxioms `'+m.TARGET+'\n  logInfo m!"AUDIT {toJson (ax.toList.map Name.toString)}"\n'
  af=folder/'Audit.lean';af.write_text(audit)
  ae=dict(env);ae['LEAN_PATH']=str(folder)+':'+env['LEAN_PATH']
  with lease():a=subprocess.run([str(lean),'-j1','-M4096',*args,str(af)],env=ae,cwd=folder,capture_output=True,text=True,timeout=180)
  al=a.stdout+a.stderr;(folder/'Audit.log').write_text(al);auditrc=a.returncode
  found=re.findall(r'AUDIT (\[[^\n]*\])',al)
  if len(found)==1:ax=json.loads(found[0])
 valid=p.returncode==0 and len(marks)==1 and auditrc==0 and ax is not None and set(ax)<=m.ALLOWED_AXIOMS
 try:m.validate_declaration(code,m.STATEMENT);gate=True
 except ValueError:gate=False
 rec=dict(label=label,repeat=repeat,diagnostic_only=True,submission_certified=False,
  frozen_validator_accepts=gate,full_source_compiled_and_axioms_audited=valid,
  tokens=m.proof_tokens(code,m.STATEMENT),raw=int(marks[0]) if valid else None,
  seconds=seconds,returncode=p.returncode,audit_returncode=auditrc,axioms=ax,
  command=cmd,environment_identity=fp['identity_sha256'],nonce=nonce,
  candidate_sha256=sha(code.encode()),source_sha256=sha(measured.encode()),log_sha256=sha(log.encode()))
 (folder/'result.json').write_text(json.dumps(rec,indent=2)+'\n')
 print(json.dumps({k:rec[k] for k in ['label','repeat','tokens','raw','full_source_compiled_and_axioms_audited','frozen_validator_accepts','seconds']}),flush=True)
 return rec

if __name__=='__main__':
 for label,code in variants.items():run(label,code)
