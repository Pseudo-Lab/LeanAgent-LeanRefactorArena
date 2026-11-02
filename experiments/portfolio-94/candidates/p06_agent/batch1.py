from pathlib import Path
import sys
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-432'
sys.path.insert(0,str(E));import search_exclusive4 as s
with s.lock(R):
 s.record(R,s.evaluate(R,Path(__file__).with_name('bilinear_basis.lean').read_text(),'agent-bilinear-basis'),operation='Replace six span closure branches by composed bilinear maps and two Basis.ext applications')
