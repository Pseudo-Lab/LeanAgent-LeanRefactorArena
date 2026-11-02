from pathlib import Path
import importlib.util, sys
LEGACY = Path('/Users/zzu0203/projects/01_가짜연구소/insights-20261024-round7/p11')
sys.path.insert(0,str(LEGACY))
spec = importlib.util.spec_from_file_location('legacy_p11', LEGACY/'full_probe.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.META_PATH=LEGACY.parents[1]/'LEArN/week3-experiments/experiments/evidence/2026-10-16-warmup15-xhigh/P10/metadata.json'
import json
m.PINS['v4.28.0']=json.loads((Path(__file__).parent/'p10-pin428.json').read_text())
m.META=json.loads(m.META_PATH.read_text());m.META['src']=m.PINS['v4.28.0']['original_declaration'];m.TARGET=m.META['name'];m.STATEMENT=m.META['statement']
m.WRAP=m.WRAP.replace('fold_advances_evaluation_poly','fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius').replace('p11_measure','p10_measure').replace('P11_RAW','P10_RAW')
for name in ['load_environment','plain_source','measured_source','validate_declaration','proof_tokens','META','META_PATH','STATEMENT','TARGET','ALLOWED_AXIOMS','WRAP']:
    globals()[name]=getattr(m,name)
RAW_MARKER='P10_RAW'
DEPENDENCIES=[LEGACY/n for n in ['full_probe.py','tokens_snapshot.py','prepared.json','pins.json']] + [Path(__file__).parent/'p10-pin428.json']

_legacy_measured=measured_source
def measured_source(source,code,nonce):
    return _legacy_measured(source,code,nonce).replace('#p11_measure ', '#p10_measure ')
