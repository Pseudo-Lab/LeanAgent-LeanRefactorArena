from pathlib import Path
import sys
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-432'
sys.path.insert(0,str(E));import search_exclusive4 as s
with s.lock(R):
 for name in ['closure_congr','bilinear_ext_basis_shape_unfold','bilinear_ext_basis_scalar','bilinear_ext_basis_i_typed']:
  r=s.evaluate(R,Path(__file__).with_name(name+'.lean').read_text(),'agent-'+name)
  s.record(R,r,operation=name)

