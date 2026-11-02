from pathlib import Path
import os,sys,json,re,hashlib,subprocess,time,tarfile
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';ROOT=W.parents[1]
sys.path.insert(0,str(E));from resources_exclusive import lease
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
meta=json.loads((ROOT/'LEArN/week3-experiments/experiments/evidence/2026-10-16-warmup15-xhigh/P09/metadata.json').read_text())
pins={k:v for e in meta['version_info'] for k,v in e.items()}
for pin in sys.argv[1:]:
 base=ROOT/'insights-20261024-round5/validation'/('environment'+pin+'.json');cfg=json.loads(base.read_text());src=Path(cfg['source'])
 out=W/'runs/portfolio-94'/('p09-runtime-'+pin);out.mkdir(parents=True,exist_ok=True);lib=out/'lib';lib.mkdir(exist_ok=True)
 extra = W/'runs/portfolio-94'/('dependency-'+pin)/'union' if pin in ['433','432'] else ROOT/'insights-20261024-round7/restore431/cache_union'
 roots=[W/'runs/portfolio-94'/('p07-runtime-'+pin)/'lib',*[Path(p) for p in cfg['LEAN_PATH'].split(':')],extra]
 links=json.loads((out/'union-links.json').read_text()) if (out/'union-links.json').exists() else []
 evidence = [W/'runs/portfolio-94'/('dependency-'+pin)/n for n in ['archives.json','hash_request.json','environment.json']] if pin in ['433','432'] else [ROOT/'insights-20261024-round7/restore431'/n for n in ['P11_source_manifest.json','cache_receipts.json']]
 cfg['cache_evidence']=[str(p) for p in evidence]
 cfg['union_links']=str(out/'union-links.json')
 for root in roots:
  if not root.exists():continue
  for p in root.rglob('*'):
   if not p.is_file():continue
   dest=lib/p.relative_to(root)
   if dest.exists():continue
   dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(p.resolve());links.append({'path':str(dest),'source':str(p.resolve())})
 (out/'union-links.json').write_text(json.dumps(links,indent=2)+'\n')
 env=dict(os.environ,LEAN_PATH=str(lib)+':'+cfg['LEAN_PATH']);seen=set();order=[]
 def imports(p):return re.findall(r'(?m)^\s*(?:(?:public|private)\s+)?(?:meta\s+)?import\s+(Cslib\.[\w.]+)',p.read_text())
 def visit(m):
  if m in seen:return
  seen.add(m)
  for d in imports(src/(m.replace('.','/')+'.lean')):visit(d)
  order.append(m)
 for m in imports(src/meta['file_path']):visit(m)
 version=(src/'lean-toolchain').read_text().strip().split(':')[-1];revision=pins[version]
 archive=ROOT/'insights-20261024-round5/validation'/('cslib-'+revision[:7]+'.tar.gz')
 with tarfile.open(archive) as tar:
  for rel in [meta['file_path'],'lake-manifest.json','lean-toolchain',*[m.replace('.','/')+'.lean' for m in order]]:
   if tar.extractfile('cslib-'+revision+'/'+rel).read()!=(src/rel).read_bytes():raise ValueError('Pinned source mismatch: '+rel)
 records=[]
 for module in order:
  source=src/(module.replace('.','/')+'.lean');target=lib/(module.replace('.','/')+'.olean');target.parent.mkdir(parents=True,exist_ok=True)
  rec={'module':module,'source_sha256':sha(source)}
  if target.exists():rec.update(returncode=0,reused_from=str(target.resolve()))
  else:
   cmd=[cfg['compiler'],'-j1','-M4096','--root='+str(src),'-o',str(target),str(source)];start=time.monotonic()
   with lease():
    start=time.monotonic()
    result=subprocess.run(cmd,env=env,cwd=out,text=True,capture_output=True,timeout=300)
   log=result.stdout+result.stderr;(out/(module+'.log')).write_text(log)
   rec.update(command=cmd,returncode=result.returncode,seconds=time.monotonic()-start,log_sha256=hashlib.sha256(log.encode()).hexdigest());print(pin,module,result.returncode,log[-1000:],flush=True)
  if rec['returncode']==0:rec['olean_sha256']=sha(target)
  records.append(rec);(out/'build_receipts.json').write_text(json.dumps(records,indent=2)+'\n')
  if rec['returncode']:break
 cfg.update(LEAN_PATH=env['LEAN_PATH'],library=str(lib),modules=order,ready=len(records)==len(order) and all(r['returncode']==0 for r in records),build_receipts=str(out/'build_receipts.json'))
 (out/'environment.json').write_text(json.dumps(cfg,indent=2)+'\n')
 print('READY',pin,cfg['ready'],flush=True)
 if not cfg['ready']:raise SystemExit(1)
