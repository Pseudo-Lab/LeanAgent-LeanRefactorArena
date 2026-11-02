from pathlib import Path
import sys,json,time
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
from fast_probe import probe
R=E.parents[1]/'runs/portfolio-94/p10-exclusive4-431'
while not (R/'checkpoint-cardinality.json').exists():time.sleep(2)
for label in ['range_infer_delta_forward_mem','range_exact_ncard_classical','range_delay_exact_normalize','range_delay_direct_coe']:
 r=probe(R,E/'candidates/p10_agent'/f'{label}.lean',label)
 print(json.dumps(r),flush=True)
