from pathlib import Path
import sys,time
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parent.parent/'runs/portfolio-94/p11-exclusive4-431'
for _ in range(7200):
 state=s.read(R/'state.json')
 if len(state['attempts']) >= 13:break
 time.sleep(5)
else:raise RuntimeError('Five further attempts did not complete')
best=state['best']; code=(Path(best['folder'])/'candidate.lean').read_text()
# evaluate writes only its unique receipt directory, never state.json. The global
# exclusive resource lease serializes every Lean process with the search batch.
res=s.evaluate(R,code,'checkpoint-after-5-more',3)
report={'valid':res['valid'],'best_snapshot':best,'baseline':state['baseline'],
        'confirmation':res,'attempt_count_at_snapshot':len(state['attempts']),
        'scope':'Lean4.31 primary only; not all pins; independent 3 measurements'}
if res['valid']:
 b=state['baseline'];report['local_score']=100-100/3*(res['tokens']/b['tokens']+res['raw']/b['raw'])
 (R/'checkpoint.lean').write_text(code)
s.write(R/'checkpoint.json',report)
print(report.get('local_score'),res['valid'],res['tokens'],res['raw_samples'],flush=True)
