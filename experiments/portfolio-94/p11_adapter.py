from pathlib import Path
import importlib.util, sys
LEGACY = Path('/Users/zzu0203/projects/01_가짜연구소/insights-20261024-round7/p11')
sys.path.insert(0,str(LEGACY))
spec = importlib.util.spec_from_file_location('legacy_p11', LEGACY/'full_probe.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for name in ['load_environment','plain_source','measured_source','validate_declaration','proof_tokens','META','META_PATH','STATEMENT','TARGET','ALLOWED_AXIOMS','WRAP']:
    globals()[name]=getattr(m,name)
RAW_MARKER='P11_RAW'
DEPENDENCIES=[LEGACY/n for n in ['full_probe.py','tokens_snapshot.py','prepared.json','pins.json']]
