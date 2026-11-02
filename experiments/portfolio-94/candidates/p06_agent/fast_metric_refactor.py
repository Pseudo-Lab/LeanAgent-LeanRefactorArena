from pathlib import Path
import sys
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-432'
sys.path.insert(0,str(E));from fast_probe import probe
for name in ['bilinear_simp_apply','bilinear_direct_congr','bilinear_congr_arg','bilinear_congr_term','closure_composed_map']:
 probe(R,Path(__file__).with_name(name+'.lean'),'metric-refactor-'+name)
