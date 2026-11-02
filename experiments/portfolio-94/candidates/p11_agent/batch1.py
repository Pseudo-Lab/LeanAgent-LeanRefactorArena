from pathlib import Path
import sys,time,json
E=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(E))
import search_agents3 as s
R=E.parent.parent/'runs/portfolio-94/p11-agent3-431'
for _ in range(1200):
    if (R/'state.json').exists() and len(s.read(R/'state.json')['attempts']) >= 2: break
    time.sleep(1)
else: raise RuntimeError('Initialization did not complete')
with s.lock(R):
 for name in ['fiber_simp_qmap','no_symm_apply','qmap_simpa','fiber_rw','fiber_direct_change','no_first_calc','final_simp_ac','no_first_calc_simp_ac','final_simp_merge','final_ring_linear']:
    code=(Path(__file__).parent/(name+'.lean')).read_text()
    s.record(R,s.evaluate(R,code,name,1),operation=name)
