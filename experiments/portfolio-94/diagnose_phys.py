"""Exploration-only phase markers, excluded from candidate selection and submission."""
from pathlib import Path
import sys,uuid,json,subprocess,os,re,time
from search_exclusive4 import load,write,digest,execute
root=Path(sys.argv[1]).resolve();candidate=Path(sys.argv[2]);label=sys.argv[3]
cfg,m,loaded=load(root);ecfg,lean,args,env,source,fp=loaded
code=candidate.read_text();stat=m.STATEMENT;body=code[len(stat):]
markers=[]
if m.RAW_MARKER=='P06_RAW':
 anchors=[('body','  induction Basis'),('basis','    simp only [ofListBasis'),('witness','    have f'),('expand','    trans crAnTimeOrderSign'),('central','    rw [Subalgebra'),('empty','    have w'),('statistics','    by_cases q'),('linear','  all_goals')]
else:raise ValueError('Select supported phase anchors')
for name,anchor in anchors:
 if body.count(anchor)!=1:raise ValueError('Anchor not unique: '+anchor)
 body=body.replace(anchor,(' '* (len(anchor)-len(anchor.lstrip())))+'hbPhase "'+name+'"\n'+anchor,1);markers.append(name)
body+='\n  hbPhase "done"\n'
code=stat+body
folder=root/'diagnostics'/(label+'-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True)
nonce=uuid.uuid4().hex
instrument='''
open Lean Elab Tactic in
elab "hbPhase " tag:str : tactic => do
  let n ← IO.getNumHeartbeats
  logInfo m!"PHASE {tag.getString} {n}"
'''
text=m.measured_source(source,code,nonce).replace(m.WRAP,instrument+m.WRAP)
f=folder/'Diagnostic.lean';f.write_text(text)
cmd=[str(lean),'-j1','-M4096','--root='+str(folder),*args,str(f)]
import resources_exclusive
with resources_exclusive.lease(): r=subprocess.run(cmd,cwd=folder,env=env,text=True,capture_output=True,timeout=240)
log=r.stdout+r.stderr;(folder/'Diagnostic.log').write_text(log)
rows=[(k,int(v)) for k,v in re.findall(r'PHASE (\w+) (\d+)',log)]
rec={'scope':'instrumented diagnostic only; never a candidate metric','candidate_sha256':digest(candidate.read_bytes()),'command':cmd,'environment_identity':fp['identity_sha256'],'returncode':r.returncode,'source_sha256':digest(text),'log_sha256':digest(log),'phase_starts':rows,'phase_costs':[(rows[i][0],rows[i+1][1]-rows[i][1]) for i in range(len(rows)-1)]}
write(folder/'result.json',rec);print(json.dumps(rec,ensure_ascii=False,indent=2))
