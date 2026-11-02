from pathlib import Path
import sys
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parent.parent/'runs/portfolio-94/p11-exclusive4-431'
name=sys.argv[1]
code=(Path(__file__).parent/(name+'.lean')).read_text()
state=s.read(R/'state.json')
# Independent receipt only: never writes shared search state while a batch runs.
res=s.evaluate(R,code,'checkpoint-'+name,3)
report={'valid':res['valid'],'baseline':state['baseline'],'confirmation':res,
        'scope':'Lean4.31 primary only; independent 3 measurements'}
if res['valid']:
 b=state['baseline'];report['local_score']=100-100/3*(res['tokens']/b['tokens']+res['raw']/b['raw'])
 (R/('checkpoint-'+name+'.lean')).write_text(code)
s.write(R/('checkpoint-'+name+'.json'),report)
print(report.get('local_score'),res['valid'],res['tokens'],res['raw_samples'],flush=True)
