from pathlib import Path
import sys
from types import SimpleNamespace
W=Path(__file__).resolve().parents[4]
E=W/'experiments/portfolio-94'; R=W/'runs/portfolio-94/p08-agent3-433'
sys.path.insert(0,str(E))
import search_agents3 as s
s.init(SimpleNamespace(root=R,adapter=E/'p08_agent_adapter.py',environment=W.parents[1]/'insights-20261024-round5/validation/environment433.json',seed=Path(__file__).with_name('seed.lean'),timeout=180))
with s.lock(R):
 for name in ['common_elim','common_aesop','aesop_inversions','structural_induction']:
  p=Path(__file__).with_name(name+'.lean')
  s.record(R,s.evaluate(R,p.read_text(),name),operation=name)
