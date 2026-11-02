from pathlib import Path
import sys
from types import SimpleNamespace
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-agent4-432'
sys.path.insert(0,str(E));import search_exclusive4 as s
s.init(SimpleNamespace(root=R,adapter=E/'p06_adapter.py',environment=W/'runs/portfolio-94/dependency-432/projects/physlib-environment.json',seed=Path(__file__).with_name('seed.lean'),timeout=180))
with s.lock(R):
 s.record(R,s.evaluate(R,Path(__file__).with_name('bilinear_basis.lean').read_text(),'bilinear_basis'),operation='Represent both sides as bilinear maps and compare on two basis arguments')
