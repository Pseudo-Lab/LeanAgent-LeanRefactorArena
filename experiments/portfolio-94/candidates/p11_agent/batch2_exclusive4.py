from pathlib import Path
import sys
E=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parent.parent/'runs/portfolio-94/p11-exclusive4-431'
with s.lock(R):
 for name in ['fiber_add_positional_repaired', 'compact_skeleton', 'compact_fold_simp', 'final_dot_product', 'final_dot_product_lambda', 'final_simp_ac_general', 'final_simp_ac_staged', 'fiber_fixed_y', 'fiber_simp_default', 'fiber_single_pass', 'fiber_dsimp_stage', 'fiber_onelevel_stage', 'fiber_eqrw_stage', 'fiber_aux', 'qmap_infer_type', 'qmap_simp_using_inline', 'split_bare', 'polynomial_generalize']:
  code=(Path(__file__).parent/(name+'.lean')).read_text()
  s.record(R,s.evaluate(R,code,name,1),operation=name)
