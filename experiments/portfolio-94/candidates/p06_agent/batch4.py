from pathlib import Path
import sys
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-432'
sys.path.insert(0,str(E));import search_exclusive4 as s
with s.lock(R):
 for name in ['bilinear_basis_shape_unfold','bilinear_inline_maps_shape_unfold','bilinear_mul_sided_shape_unfold']:
  r=s.evaluate(R,Path(__file__).with_name(name+'.lean').read_text(),'agent-'+name)
  s.record(R,r,operation=name)
  if not r['valid']:break
