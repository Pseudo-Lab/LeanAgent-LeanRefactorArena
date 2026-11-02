from pathlib import Path
import sys,re,uuid,json
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parent.parent/'runs/portfolio-94/p11-exclusive4-431'
cfg,m,loaded=s.load(R);ecfg,lean,args,env,source,fp=loaded
candidate=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).parent/'qmap_infer_type.lean'
original=candidate.read_text(); code=original
anchor='  intro P_i'
assert code.count(anchor)==1
code=code.replace(anchor,'  hbPhase "body"\n'+anchor,1)
code+='\n  hbPhase "done"\n'
nonce=uuid.uuid4().hex;folder=R/'diagnostics'/('p11-boundaries-'+nonce[:8]);folder.mkdir(parents=True)
instrument='''
open Lean Elab Tactic in
elab "hbPhase " tag:str : tactic => do
  let n ← IO.getNumHeartbeats
  logInfo m!"PHASE {tag.getString} {n}"
'''
observed_wrap=m.WRAP.replace('  logInfo m!"P11_RAW {tag.getString} {after - before}"', '  logInfo m!"P11_RAW {tag.getString} {after - before}"\n  logInfo m!"P11_BOUNDARY {before} {after}"')
text=m.measured_source(source,code,nonce).replace(m.WRAP,instrument+observed_wrap)
f=folder/'Diagnostic.lean';f.write_text(text)
# Reuse the exact approved runner entry point: both shared Lean slots are leased.
rt={'lean':str(lean),'env':{'PATH':env.get('PATH','/usr/bin:/bin'),'HOME':str(R/'home'),'TMPDIR':str(R/'tmp'),'LEAN_PATH':env['LEAN_PATH']}}
s.write(folder/'runtime.json',rt)
launcher=folder/'runner.py';launcher.write_text('import json,os,sys\nfrom pathlib import Path\nr=json.loads(Path(__file__).with_name("runtime.json").read_text())\nos.execve(r["lean"],[r["lean"],*sys.argv[1:]],r["env"])\n')
cmd=[sys.executable,str(launcher),'-j1','-M4096','--root='+str(folder),*args,str(f)]
r=s.execute(cmd,folder,180);log=r.pop('output');(folder/'Diagnostic.log').write_text(log)
rows=[(k,int(v)) for k,v in re.findall(r'PHASE (\w+) (\d+)',log)]
boundaries=re.findall(r'P11_BOUNDARY (\d+) (\d+)',log)
if boundaries:
 before,after=map(int,boundaries[-1]);rows=[('declaration',before),*rows,('after',after)]
rec={'scope':'instrumented diagnostic only; excluded from candidate scores','candidate_sha256':s.digest(original),'environment_identity':fp['identity_sha256'],'source_sha256':s.digest(text),'log_sha256':s.digest(log),'job':r,'phase_starts':rows,'phase_costs':[(rows[i][0],rows[i+1][1]-rows[i][1]) for i in range(len(rows)-1)]}
s.write(folder/'result.json',rec);print(json.dumps(rec,ensure_ascii=False),flush=True)
