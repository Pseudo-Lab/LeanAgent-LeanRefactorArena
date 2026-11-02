"""Download exact public Mathlib cache closure into this experiment and extract locally."""
from pathlib import Path
import json,re,sys,urllib.request,concurrent.futures,hashlib,time,subprocess,os
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];RUN=HERE.parent.parent/'runs/portfolio-94';pin=sys.argv[1]
out=RUN/('dependency-'+pin);cache=out/'cache';cache.mkdir(exist_ok=True);overlay=out/'overlay';overlay.mkdir(exist_ok=True)
rows=re.findall(r'^CACHEHASH ([\w.]+) ([a-f0-9]+\.ltar)$',(out/'hashes-ready.log').read_text(),re.M)
if not rows:raise SystemExit('No successful exact cache hashes')
old=ROOT/'insights-20261024-round5/validation'/('cache'+pin)
urls={f:'https://lakecache.blob.core.windows.net/mathlib4-master/f/'+f for _,f in rows}
def fetch(row):
 module,key=row;p=cache/key
 if not p.exists() and (old/key).exists():p.symlink_to((old/key).resolve())
 if not p.exists():
  err=None
  for attempt in range(3):
   try:
    data=urllib.request.urlopen(urls[key],timeout=60).read();p.write_bytes(data);break
   except Exception as e:err=e;time.sleep(attempt+1)
  else:return {'module':module,'key':key,'error':repr(err)}
 data=p.read_bytes();return {'module':module,'key':key,'url':urls[key],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
records=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for rec in pool.map(fetch,rows):
  records.append(rec)
  if len(records)%100==0:print(pin,len(records),'/',len(rows),flush=True)
(out/'archives.json').write_text(json.dumps(records,indent=2)+'\n')
failures=[r for r in records if 'error' in r]
print('downloads',pin,len(rows),'failed',len(failures),flush=True)
if failures:raise SystemExit(1)
compiler=json.loads((out/'hash_request.json').read_text())['command'][0];tar=Path(compiler).with_name('leantar')
cmd=[str(tar),'-x','-C',str(overlay),'--jobs','4',*[str(cache/k) for _,k in rows]]
r=subprocess.run(cmd,text=True,capture_output=True);(out/'extract.log').write_text(r.stdout+r.stderr);(out/'extract.json').write_text(json.dumps({'command':cmd,'returncode':r.returncode},indent=2)+'\n')
print('extract',pin,r.returncode,flush=True)
paths=[overlay/'.lake/build/lib/lean',*sorted((overlay/'.lake/packages').glob('*/.lake/build/lib/lean'))]
union=out/'union';union.mkdir(exist_ok=True)
for root in paths:
 for source in root.rglob('*'):
  if source.is_file():
   target=union/source.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
   if not target.exists():target.symlink_to(source.resolve())
(out/'environment.json').write_text(json.dumps({'ready':r.returncode==0,'compiler':compiler,'LEAN_PATH':str(union),'archives_sha256':hashlib.sha256((out/'archives.json').read_bytes()).hexdigest(),'modules':len(rows)},indent=2)+'\n')
