from pathlib import Path
import sys
W=Path(__file__).resolve().parents[4]; E=W/'experiments/portfolio-94'; R=W/'runs/portfolio-94/p08-agent3-433'
sys.path.insert(0,str(E));import search_agents3 as s
with s.lock(R):
 for name in ['common_elim_backtrack','common_elim_depth3_backtrack','common_aesop_unfold','aesop_inversions_unfold','structural_induction_infer']:
  s.record(R,s.evaluate(R,Path(__file__).with_name(name+'.lean').read_text(),name),operation=name)
