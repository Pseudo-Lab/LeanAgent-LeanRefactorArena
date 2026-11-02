from pathlib import Path
import sys,time,json
E=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(E))
import search_agents3 as s
R=E.parents[1]/'runs/portfolio-94/p10-agent3-431'
while not (R/'state.json').exists() or len(s.read(R/'state.json')['attempts'])<2:
 time.sleep(2)
P=Path(__file__).parent
for name in ['witness_direct','castsucc','nat_finish_direct','nat_finish_seed','singlepass','small_context','nosimp_hd','finish_apply_cast','finish_clear']:
 with s.lock(R):
  code=(P/(name+'.lean')).read_text()
  if s.digest(code) in {r['code_sha256'] for r in s.read(R/'state.json')['attempts']}:continue
  r=s.evaluate(R,code,name,1); s.record(R,r,operation=name)
