from pathlib import Path
import sys,uuid,json,re
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-432'
sys.path.insert(0,str(E));import search_exclusive4 as s
candidate=Path(sys.argv[1]);cfg,m,loaded=s.load(R);ecfg,lean,args,env,source,fp=loaded
code=candidate.read_text();body=code[len(m.STATEMENT):]
anchors=[('lets','  let m'),('map_equality','  suffices h'),('basis_ext','  apply '),('change','  change '),('basis_simp','  simp only [c,' if '  simp only [c,' in body else '  simp only [ofListBasis_eq_ofList'),('uniform_factors','  obtain ⟨l, r, f⟩'),('pair_expansion','  trans crAnTimeOrderSign'),('centrality','  rw [Subalgebra.mem_center_iff'),('statistics','  by_cases q')]
for name,anchor in anchors:
 if anchor in body: body=body.replace(anchor,'  hbPhase "'+name+'"\n'+anchor,1)
body+='\n  hbPhase "done"\n'
instrument='''
open Lean Elab Tactic in
elab "hbPhase " tag:str : tactic => do
  let n ← IO.getNumHeartbeats
  logInfo m!"PHASE {tag.getString} {n}"
'''
folder=R/'diagnostics'/('p06-agent-'+uuid.uuid4().hex[:10]);folder.mkdir(parents=True)
text=m.measured_source(source,m.STATEMENT+body,uuid.uuid4().hex).replace(m.WRAP,instrument+m.WRAP)
p=folder/'Diagnostic.lean';p.write_text(text)
s.write(folder/'runtime.json',{'lean':str(lean),'env':{'PATH':env.get('PATH','/usr/bin:/bin'),'HOME':str(R/'home'),'TMPDIR':str(R/'tmp'),'LEAN_PATH':env['LEAN_PATH']}})
launcher=folder/'runner.py';launcher.write_text('import json,os,sys\nfrom pathlib import Path\nr=json.loads(Path(__file__).with_name("runtime.json").read_text())\nos.execve(r["lean"],[r["lean"],*sys.argv[1:]],r["env"])\n')
cmd=[sys.executable,str(launcher),'-j1','-M4096','--root='+str(folder),*args,str(p)]
r=s.execute(cmd,folder,240);log=r.pop('output');(folder/'Diagnostic.log').write_text(log)
rows=[(k,int(v)) for k,v in re.findall(r'PHASE (\w+) (\d+)',log)]
rec={'scope':'instrumented diagnostic only; never a candidate metric','candidate_sha256':s.digest(candidate.read_bytes()),'environment_identity':fp['identity_sha256'],'job':r,'phase_starts':rows,'phase_costs':[(rows[i][0],rows[i+1][1]-rows[i][1]) for i in range(len(rows)-1)]}
s.write(folder/'result.json',rec);print(json.dumps(rec,ensure_ascii=False))
