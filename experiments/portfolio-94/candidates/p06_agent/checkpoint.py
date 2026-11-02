from pathlib import Path
import sys,json
W=Path(__file__).resolve().parents[4];E=W/'experiments/portfolio-94';R=W/'runs/portfolio-94/p06-432'
sys.path.insert(0,str(E));import search_exclusive4 as s
candidate=Path(sys.argv[1]).resolve()
with s.lock(R):
 r=s.evaluate(R,candidate.read_text(),'agent-final-checkpoint',runs=3)
 s.record(R,r,operation='independent Check/Audit + 3 fresh measurements')
 if not r['valid']:raise RuntimeError(r.get('error','Checkpoint invalid'))
 state=s.read(R/'state.json');b=state['baseline']
 r['local_score']=100-100/3*(r['tokens']/b['tokens']+r['raw']/b['raw'])
 r['baseline']={k:b[k] for k in ['tokens','raw','raw_samples']}
 r['selected_candidate']=str(candidate)
 s.write(R/'p06-agent-checkpoint.json',r)
 Path(__file__).with_name('confirmed-primary.lean').write_text(candidate.read_text())
 print(json.dumps({k:r[k] for k in ['tokens','raw','raw_samples','local_score','folder']},ensure_ascii=False),flush=True)
