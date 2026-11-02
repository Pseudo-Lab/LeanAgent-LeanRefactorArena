"""Derive external imports and generate a hash request for pinned Mathlib's cache implementation."""
from pathlib import Path
import json,re,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];RUN=HERE.parent.parent/'runs/portfolio-94'
pin=sys.argv[1];out=RUN/('dependency-'+pin);out.mkdir(parents=True,exist_ok=True)
validation=ROOT/'insights-20261024-round5/validation';cs=validation/('overlay'+pin)/'source'
source_roots={'Cslib':cs};targets=['Cslib.Languages.LambdaCalculus.LocallyNameless.Fsub.Typing']
if pin=='432':
 source_roots['Physlib']=RUN/'physlib-runtime-432/source'
 targets.extend(['Physlib.Electromagnetism.Dynamics.IsExtrema','Physlib.QFT.PerturbationTheory.WickAlgebra.TimeOrder'])
seen=set();order=[];external=set()
def go(m):
 if m in seen:return
 seen.add(m);root=source_roots.get(m.split('.')[0])
 if root is None:
  if not m.startswith(('Lean.','Init.','Std.')):external.add(m)
  return
 src=root/(m.replace('.','/')+'.lean')
 for d in re.findall(r'(?m)^\s*(?:public\s+)?(?:meta\s+)?import\s+(?:all\s+)?([\w.]+)',src.read_text()):go(d)
 order.append({'module':m,'source':str(src)})
for m in targets:go(m)
(out/'closure.json').write_text(json.dumps({'targets':targets,'source_modules':order,'external_roots':sorted(external)},indent=2)+'\n')
hashes='''import Cache.Hashing
open Lean Cache Cache.IO Cache.Hashing in
def main : IO Unit := CacheM.run do
  let names := ['''+', '.join('`'+n for n in sorted(external))+''']
  let memo ← getHashMemo {}
  let hashes ← memo.filterByRootModules names
  for (name, hash) in hashes.toArray do
    IO.println s!"CACHEHASH {name} {hash.asLTar}"
'''
(out/'Hashes.lean').write_text(hashes)
receipt=json.loads((validation/('overlay'+pin)/'hash_receipt.json').read_text())
receipt['command'][-1]=str(out/'Hashes.lean');receipt['env']['PATH']=str(Path(receipt['command'][0]).parent)+':/usr/bin:/bin';(out/'hash_request.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(pin,len(order),'project modules,',len(external),'external roots')
