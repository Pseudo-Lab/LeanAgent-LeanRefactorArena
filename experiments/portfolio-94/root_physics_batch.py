from pathlib import Path
import time,json,sys
import search_exclusive4 as s
E=Path(__file__).resolve().parent
R=E.parent.parent/'runs/portfolio-94'
for problem in ['p05','p06']:
 root=R/(problem+'-432')
 while True:
  if (root/'state.json').exists():
   st=s.read(root/'state.json')
   if any(r['label']=='seed' and r['valid'] for r in st['attempts']):break
  time.sleep(3)
 for candidate in sorted((E/'candidates'/problem).glob('*.lean')):
  if candidate.stem in ('archived','submitted'):continue
  with s.lock(root):
   code=candidate.read_text()
   if s.digest(code) in {r['code_sha256'] for r in s.read(root/'state.json')['attempts']}:continue
   result=s.evaluate(root,code,candidate.stem)
   s.record(root,result,operation='physics structural exploration')
