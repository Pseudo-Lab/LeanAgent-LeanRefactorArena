from pathlib import Path
import sys,json,hashlib,datetime
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94'
sys.path.insert(0,str(E/'submission-round'));import evidence_gate as gate
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
report=json.loads(Path(__file__).with_name('certification.json').read_text());assert len(report['pins'])==3 and all(r['valid'] for r in report['pins'])
candidate=Path(report['candidate']);code=candidate.read_text();h=sha(candidate);assert h==report['candidate_sha256']
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'id':9,'target':'Cslib.CCS.bisimilarity_congr_choice','scope':'All three required pins: full-source Check and independent Audit; primary HB x3, compatibility HB x1; no official submission','candidate_sha256':h,'tokens':79,'primary_pin':'v4.33.0-rc2','compatibility':'3/3','required_pin_evidence':[]}
for p in report['pins']:
 f=Path(p['receipt']);r=gate._receipt(f,h,code,sha(f));assert r['tokens']==79;pin=gate._receipt_pin(r);assert pin=={'433':'v4.33.0-rc2','432':'v4.32.0','431':'v4.31.0'}[p['pin']]
 manifest['required_pin_evidence'].append({'pin':pin,'receipt':str(f),'receipt_sha256':sha(f),'candidate_sha256':h,'tokens':r['tokens'],'raw_samples':r['raw_samples'],'raw_median':r['raw'],'axioms':r['axioms'],'environment_identity':r['environment_identity'],'saved_integrity_ok':True})
 if p['pin']=='433':manifest.update(primary_raw_median=r['raw'],primary_raw_samples=r['raw_samples'],estimated_score=p['primary_score'])
b=json.loads((R/'p09-agent-433/state.json').read_text())['baseline'];manifest['baseline_receipt']=str(Path(b['folder'])/'result.json');manifest['baseline_tokens']=b['tokens'];manifest['baseline_raw_median']=b['raw']
out=E/'validated'/('P09-'+h[:12]);out.mkdir(exist_ok=False);(out/'P09.lean').write_bytes(candidate.read_bytes());(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(out/'README.ko.md').write_text('# P09 필수3개버전 검증\n\n기존79-token 제출 증명을 수정 없이 전체소스로 검증했다. 4.33은원본과후보각3회, 4.32/4.31은후보각1회HB를측정했고 모든pin에서 별도Check와독립Audit를통과했다. source/log/hash 및 환경pin을 evidence_gate로다시확인했다.\n\n정확한파일/receipt/hash는manifest.json을참고한다. 공식제출과커밋은하지않았다.\n')
print(json.dumps({'manifest':str(out/'manifest.json'),'candidate':str(out/'P09.lean'),'tokens':79,'primary_raw':manifest['primary_raw_median'],'score':manifest['estimated_score'],'pins':[p['pin'] for p in manifest['required_pin_evidence']]},ensure_ascii=False),flush=True)
