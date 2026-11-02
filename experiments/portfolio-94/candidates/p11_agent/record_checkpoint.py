from pathlib import Path
import sys,time
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parent.parent/'runs/portfolio-94/p11-exclusive4-431'
p=R/('checkpoint-'+sys.argv[1]+'.json')
while not p.exists():time.sleep(5)
report=s.read(p);result=report['confirmation']
with s.lock(R):
 state=s.read(R/'state.json')
 if result['valid'] and not any(row.get('folder')==result['folder'] for row in state['attempts']):
  s.record(R,result,operation='independent 3-run checkpoint promotion')
