"""Isolated HB boundary toys. Never a submission or portfolio score."""
from pathlib import Path
import hashlib, json, os, re, statistics, subprocess, sys, time

E = Path(__file__).resolve().parents[1]
W = E.parents[1]
ROOT = W.parents[1]
OUT = W / 'runs/portfolio-94/diagnostics/metric-audit'
LEAN = ROOT / 'insights-20261024-round5/validation/toolchains/lean-4.32.0-darwin_aarch64/bin/lean'
sys.path.insert(0, str(E))
from resources_exclusive import lease

HEADER = '''import Lean
open Lean Elab Command in
elab "#metric " tag:str cmd:command : command => do
  let before ← IO.getNumHeartbeats
  elabCommand cmd
  let after ← IO.getNumHeartbeats
  logInfo m!"METRIC {tag.getString} {after - before}"
set_option maxRecDepth 10000
'''
VARIANTS = {
    'decide': 'decide',
    'rfl': 'rfl',
    'kernel': 'decide +kernel',
    'lemma': 'exact List.length_range _',
    'aux_decide': 'as_aux_lemma => decide',
    'aux_rfl': 'as_aux_lemma => rfl',
    'proof_async_aux_rfl': 'set_option Elab.async true in\n    as_aux_lemma => rfl',
    'unlimited_decide': 'set_option maxHeartbeats 0 in decide',
    'proof_async_decide': 'set_option Elab.async true in decide',
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def run_case(label, tactic, n, repetition, warm=False):
    folder = OUT / f'{label}-{n}-r{repetition}'
    folder.mkdir(exist_ok=False)
    statement = f'theorem target : (List.range {n}).length = {n} := by\n  '
    source = HEADER
    if warm:
        source += f'set_option Elab.async false in\ntheorem warmup : (List.range {n}).length = {n} := by decide +kernel\n'
    source += 'set_option Elab.async false in\n#metric "target"\n' + statement + tactic + '\n'
    source += '#print axioms target\n'
    file = folder/'Probe.lean'; file.write_text(source)
    cmd = [str(LEAN), '-j1', '-M4096', '-o', str(folder/'Probe.olean'), str(file)]
    with lease():
        start = time.monotonic()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        seconds = time.monotonic()-start
    log = result.stdout+result.stderr; (folder/'Probe.log').write_text(log)
    marks = re.findall(r'METRIC target (\d+)', log)
    axiom_free = "'target' does not depend on any axioms" in log
    valid = result.returncode == 0 and len(marks) == 1 and axiom_free
    rec = dict(label=label,n=n,repetition=repetition,warm=warm,valid=valid,
        raw=int(marks[0]) if valid else None,seconds=seconds,
        returncode=result.returncode,source_sha256=sha(file.read_bytes()),
        log_sha256=sha(log.encode()),command=cmd,axiom_free=axiom_free)
    (folder/'result.json').write_text(json.dumps(rec,indent=2)+'\n')
    print(json.dumps({k:rec[k] for k in ['label','n','repetition','valid','raw','seconds']}),flush=True)
    return rec

if __name__ == '__main__':
    records=[]
    for n in [100,300]:
        for label,tactic in VARIANTS.items():
            for repetition in range(1,4):
                records.append(run_case(label,tactic,n,repetition))
        for repetition in range(1,4):
            records.append(run_case('kernel_warm',VARIANTS['kernel'],n,repetition,warm=True))
    summary=[]
    for n in [100,300]:
        for label in [*VARIANTS,'kernel_warm']:
            rows=[r for r in records if r['label']==label and r['n']==n]
            samples=[r['raw'] for r in rows if r['valid']]
            summary.append(dict(label=label,n=n,valid_count=len(samples),samples=samples,
                median=statistics.median(samples) if len(samples)==3 else None))
    (OUT/'summary.json').write_text(json.dumps(dict(
        scope='Isolated diagnostic, not competition evidence; warmup declarations not allowed in submissions',
        lean_sha256=sha(LEAN.read_bytes()),runner_sha256=sha(Path(__file__).read_bytes()),
        summary=summary),indent=2)+'\n')
