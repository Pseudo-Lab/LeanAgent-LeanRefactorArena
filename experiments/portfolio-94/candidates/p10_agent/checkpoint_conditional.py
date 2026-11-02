from pathlib import Path
import sys,time,json
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parents[1]/'runs/portfolio-94/p10-exclusive4-431'
threshold=len(s.read(R/'state.json')['attempts'])+2
while len(s.read(R/'state.json')['attempts'])<threshold:time.sleep(2)
with s.lock(R):
 st=s.read(R/'state.json');best=st['best'];code=(Path(best['folder'])/'candidate.lean').read_text()
 r=s.evaluate(R,code,'checkpoint-conditional',3)
 report={'result':r,'baseline':st['baseline'],'seed':st['attempts'][1],'attempts':len(st['attempts']),'scope':'Lean 4.31 only; not all-pin or official LB'}
 if r['valid']:
  b=st['baseline'];report['score']=100-100/3*(r['tokens']/b['tokens']+r['raw']/b['raw']);(R/'checkpoint-conditional.lean').write_text(code)
 s.write(R/'checkpoint-conditional.json',report);print(json.dumps({'valid':r['valid'],'tokens':r['tokens'],'raw':r['raw'],'score':report.get('score')}),flush=True)
