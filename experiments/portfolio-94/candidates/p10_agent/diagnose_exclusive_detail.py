"""Exploration-only phase markers, excluded from candidate selection and submission."""
from pathlib import Path
import sys,uuid,json,subprocess,os,re,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from search_exclusive4 import load,write,digest
from resources_exclusive import lease
root=Path(sys.argv[1]).resolve();candidate=Path(sys.argv[2]);label=sys.argv[3]
cfg,m,loaded=load(root);ecfg,lean,args,env,source,fp=loaded
code=candidate.read_text();stat=m.STATEMENT;body=code[len(stat):]
markers=[]
if m.RAW_MARKER=='P10_RAW':
 anchors=[('body','  let d_fw'),('witness',"  obtain ⟨⟨g'"),('cardinality','  have hΔ'),('card_min','    rw [← hg]'),('card_set','    let B'),('card_normalize','    rw [hammingDist'),('card_cover','    have hs'),('card_finish','    calc'),('arithmetic','  have h3'),('arith_simp','  simp'),('finish','  exact (mul_le_mul_left')]
 if '    let decode' in body: anchors.insert(5,('card_decode','    let decode'))
else:raise ValueError('Select supported phase anchors')
for name,anchor in anchors:
 if body.count(anchor)!=1:raise ValueError('Anchor not unique: '+anchor)
 indent=anchor[:len(anchor)-len(anchor.lstrip())]
 body=body.replace(anchor,indent+'hbPhase "'+name+'"\n'+anchor,1);markers.append(name)
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
with lease():
 r=subprocess.run(cmd,cwd=folder,env=env,text=True,capture_output=True,timeout=240)
log=r.stdout+r.stderr;(folder/'Diagnostic.log').write_text(log)
rows=[(k,int(v)) for k,v in re.findall(r'PHASE (\w+) (\d+)',log)]
rec={'scope':'instrumented diagnostic only; never a candidate metric','candidate_sha256':digest(candidate.read_bytes()),'command':cmd,'environment_identity':fp['identity_sha256'],'returncode':r.returncode,'source_sha256':digest(text),'log_sha256':digest(log),'phase_starts':rows,'phase_costs':[(rows[i][0],rows[i+1][1]-rows[i][1]) for i in range(len(rows)-1)]}
write(folder/'result.json',rec);print(json.dumps(rec,ensure_ascii=False,indent=2))
