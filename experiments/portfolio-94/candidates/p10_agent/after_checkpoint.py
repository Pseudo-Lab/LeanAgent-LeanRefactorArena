from pathlib import Path
import sys,subprocess
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parents[1]/'runs/portfolio-94/p10-exclusive4-431'
P=Path(__file__).parent
with s.lock(R):
 subprocess.run([sys.executable,str(P/'diagnose_exclusive_detail.py'),str(R),str(P/'range_inline_conditional_term.lean'),'inline253-detail'],check=True)
subprocess.run([sys.executable,str(P/'batch4.py')],check=True)
