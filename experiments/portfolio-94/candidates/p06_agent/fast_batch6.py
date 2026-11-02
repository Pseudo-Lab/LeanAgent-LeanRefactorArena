from pathlib import Path
import sys
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-432'
sys.path.insert(0,str(E));from fast_probe import probe
cal=probe(R,Path(__file__).with_name('bilinear_inline_maps_shape_unfold.lean'),'agent-calibration422')
if not cal['valid_fast'] or abs(cal['raw']-11134816)>1000:
 raise RuntimeError('Calibration mismatch; stop and inspect independently')
for name in ['closure_composed_map','closure_specialized_maps','closure_map_mul_first','closure_congr_map_mul_first','bilinear_existential_placeholders','bilinear_direct_congr','bilinear_target_mul','bilinear_simp_apply']:
 probe(R,Path(__file__).with_name(name+'.lean'),'agent-'+name)
