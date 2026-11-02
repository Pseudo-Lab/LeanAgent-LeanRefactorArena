from pathlib import Path
import sys,json,shutil,argparse
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94'
sys.path.insert(0,str(E));import search_exclusive4 as s
candidate=W/'submissions/warmup/best/P09.lean';ap=E/'p09_agent_adapter.py'
report={'candidate':str(candidate),'candidate_sha256':s.digest(candidate.read_bytes()),'primary_pin':'433','pins':[]}
for pin in ['433','432','431']:
 root=R/('p09-agent-'+pin);environment=R/('p09-runtime-'+pin)/'environment.json'
 if pin=='433':
  s.init(argparse.Namespace(root=root,adapter=ap,environment=environment,timeout=300,seed=candidate))
  st=s.read(root/'state.json');result=next(r for r in st['attempts'] if r['label']=='seed');base=st['baseline']
  score=100-100/3*(result['tokens']/base['tokens']+result['raw']/base['raw']) if result['valid'] else None
 else:
  root.mkdir(parents=True,exist_ok=False)
  for name in ['home','tmp','snapshots']:(root/name).mkdir()
  m=s.adapter(ap);env=m.load_environment(environment)
  paths=[Path(s.__file__),E/'mutations.py',s.LEGACY/'evaluator/lean.py',ap,m.META_PATH,E/'resources.py',E/'resources_exclusive.py',*m.DEPENDENCIES]
  cfg={'adapter':str(ap),'environment':str(environment),'environment_identity':env[-1]['identity_sha256'],'timeout_seconds':300,'original_sha256':s.digest(m.META['src']),'code_hashes':{str(p):s.digest(p.read_bytes()) for p in paths},'objective':'compatibility verification only; no same-pin score without baseline','memory_limit_mib':4096,'max_concurrent_lean':1}
  s.write(root/'config.json',cfg);s.write(root/'environment.json',env[-1])
  for i,p in enumerate(paths):shutil.copyfile(p,root/'snapshots'/f'{i}-{p.name}')
  (root/'original.lean').write_text(m.META['src']);(root/'seed.lean').write_bytes(candidate.read_bytes())
  with s.lock(root):result=s.evaluate(root,candidate.read_text(),'selected79',runs=1)
  s.write(root/'checkpoint.json',result);score=None
 row={'pin':pin,'valid':result['valid'],'tokens':result['tokens'],'raw':result['raw'],'raw_samples':result['raw_samples'],'receipt':str(Path(result['folder'])/'result.json'),'primary_score':score,'environment_identity':result['environment_identity']}
 report['pins'].append(row);s.write(Path(__file__).with_name('certification.json'),report);print(json.dumps(row),flush=True)
 if not result['valid']:raise RuntimeError(result.get('error','Candidate invalid'))
