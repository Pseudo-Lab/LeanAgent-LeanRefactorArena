from pathlib import Path
import sys
E=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parent.parent/'runs/portfolio-94/p11-exclusive4-431'
with s.lock(R):
 for name in ['qmap_infer_fiber', 'compact_eval_skeleton', 'compact_eval_inline', 'compact_fold_eta', 'compact_skeleton_f_eta', 'final_simp_ac_staged_both', 'final_dot_product_unfold', 'final_simp_ac_general_both', 'fiber_direct_algebra']:
  code=(Path(__file__).parent/(name+'.lean')).read_text()
  s.record(R,s.evaluate(R,code,name,1),operation=name)
