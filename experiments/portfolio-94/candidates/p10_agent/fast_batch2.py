from pathlib import Path
import sys,json,time
E=Path(__file__).resolve().parents[2];sys.path.insert(0,str(E))
from fast_probe import probe
R=E.parents[1]/'runs/portfolio-94/p10-exclusive4-431'
while True:
 rows=[json.loads(p.read_text()) for p in (R/'fast-probes').glob('range_delay_direct_coe-*/result.json')]
 if any('returncode' in x for x in rows):break
 time.sleep(2)
for label in ['range_explicit_direct_coe','range_finset_cover_notation','range_explicit_card_term_infer','range_generic_hamming_bound','range_explicit_arithmetic_direct','range_explicit_fiber_bound_lemma']:
 probe(R,E/'candidates/p10_agent'/f'{label}.lean',label)
