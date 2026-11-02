from pathlib import Path
import sys,time,json
E=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(E))
import search_exclusive4 as s
R=E.parents[1]/'runs/portfolio-94/p10-exclusive4-431'
while not (R/'state.json').exists() or len(s.read(R/'state.json')['attempts'])<2:
 time.sleep(2)
P=Path(__file__).parent
while True:
 with s.lock(R):
  seen={r['code_sha256'] for r in s.read(R/'state.json')['attempts']}
  pending=[n for n in json.loads((P/'queue.json').read_text()) if s.digest((P/(n+'.lean')).read_text()) not in seen]
  if not pending:break
  name=pending[0]; code=(P/(name+'.lean')).read_text()
  r=s.evaluate(R,code,name,1); s.record(R,r,operation=name)
