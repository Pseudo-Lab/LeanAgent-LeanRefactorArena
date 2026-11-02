from pathlib import Path
import sys
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
import search_exclusive4 as s
from fast_probe import probe
R=E.parent.parent/'runs/portfolio-94/p11-exclusive4-431'
C=Path(__file__).parent
names=['qmap_infer_type', 'qmap_infer_fiber', 'compact_eval_skeleton', 'compact_eval_inline', 'compact_fold_eta', 'compact_skeleton_f_eta', 'final_simp_ac_staged_both', 'final_dot_product_unfold', 'final_simp_ac_general_both', 'fiber_direct_algebra']
with s.lock(R):
 rows=[]
 for name in names:
  rows.append(probe(R,C/(name+'.lean'),'batch3-'+name))
  s.write(R/'fast-batch3.json',{'scope':'provisional screening only','rows':rows})
 state=s.read(R/'state.json');base=state['baseline']
 valid=[r for r in rows if r['valid_fast']]
 if valid:
  best=min(valid,key=lambda r:s.rank(r,base))
  if s.rank(best,base)<s.rank(state['best'],base):
   name=best['label'].removeprefix('batch3-');code=(C/(name+'.lean')).read_text()
   result=s.evaluate(R,code,'confirm-fast-'+name,3)
   s.record(R,result,operation='independent confirmation after fast batch3')
   report={'screening':best,'confirmation':result,'baseline':base,'scope':'Lean4.31 independent 3-run confirmation; other pins separate'}
   if result['valid']:
    report['local_score']=100-100/3*(result['tokens']/base['tokens']+result['raw']/base['raw'])
    (R/('checkpoint-fast-'+name+'.lean')).write_text(code)
   s.write(R/('checkpoint-fast-'+name+'.json'),report)
   print('CONFIRM',name,report.get('local_score'),result['valid'],result['raw_samples'],flush=True)
