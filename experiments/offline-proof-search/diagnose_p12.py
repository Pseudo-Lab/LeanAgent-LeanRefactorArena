"""Separate, instrumented P12 phase observations; never use as scoring input."""
import argparse
import json
from pathlib import Path
import re
import sys
import uuid
from search import load, lock, execute, digest, write


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root', type=Path); ap.add_argument('candidate', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(); root = a.root.resolve(); folder = a.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    cfg, m, data = load(root); ecfg, lean, args, env, source, fp = data
    code = a.candidate.read_text(); nonce = uuid.uuid4().hex
    rendered = m.measured_source(source, code, nonce)
    phase_tactic = ('\nopen Lean Elab Tactic in\n'
        'elab "offline_phase " label:str : tactic => do\n'
        '  let n ← IO.getNumHeartbeats\n'
        f'  logInfo m!"OFFLINE_PHASE {nonce} {{label.getString}} {{n}}"\n')
    # Compile the measurement tactic once outside the target instead of elaborating
    # a run_tac program at every boundary. This is diagnostics, never a candidate.
    assert rendered.count(m.WRAP) == 1
    rendered = rendered.replace(m.WRAP, m.WRAP + phase_tactic, 1)
    boundaries = [
        ('base-start', '    simp_rw [multilinearCombine₁_eq_affineLineEvaluation] at hp'),
        ('base-probability', '    have hc := hC_proximityGapAffineLines'),
        ('base-transport', '    simp only [jointProximityNat₂'),
        ('base-end', '    exact hc'),
        ('succ-start', '    let U :='),
        ('succ-recursion', '    simp_rw [multilinearCombine_recursive_form] at hp'),
        ('succ-split', '    erw [prob_split_last_uniform_sampling_of_finFun'),
        ('succ-chain', '    apply CA_split_rowwise_implies_CA'),
        ('succ-prob-bound', '    apply lt_of_lt_of_le'),
        ('succ-witness', '    exact Pr_le_Pr_of_implies')]
    added = []
    # Replace only within candidate so prefix declarations cannot match a marker.
    diagnostic = code
    for label, needle in boundaries:
        if diagnostic.count(needle) != 1:
            continue
        marker = f'    offline_phase "{label}"\n'
        diagnostic = diagnostic.replace(needle, marker + needle, 1); added.append(label)
    if rendered.count(code) != 1:
        raise ValueError('Ambiguous target source')
    rendered = rendered.replace(code, diagnostic, 1)
    file = folder / 'Diagnostic.lean'; file.write_text(rendered)
    write(folder / 'runtime.json', {'lean': str(lean), 'env': {
        'PATH': env.get('PATH', '/usr/bin:/bin'), 'HOME': str(root / 'home'),
        'TMPDIR': str(root / 'tmp'), 'LEAN_PATH': env['LEAN_PATH']}})
    launcher = folder / 'runner.py'
    launcher.write_text('import json,os,sys\nfrom pathlib import Path\n'
        'r=json.loads(Path(__file__).with_name("runtime.json").read_text())\n'
        'os.execve(r["lean"],[r["lean"],*sys.argv[1:]],r["env"])\n')
    with lock(root):
        result = execute([sys.executable, str(launcher), '-j1', '-M4096', '--root=' + str(folder),
                          *args, str(file)], folder, cfg['timeout_seconds'])
    log = result.pop('output'); (folder / 'Diagnostic.log').write_text(log)
    phases = [(label, int(n)) for label,n in re.findall('OFFLINE_PHASE ' + nonce + r' ([\w-]+) (\d+)', log)]
    result.update(scope='instrumented phase observations; includes marker overhead; NOT score input',
                  source_sha256=digest(rendered), candidate_sha256=digest(code), log_sha256=digest(log),
                  environment_identity=fp['identity_sha256'], phases=phases, expected_labels=added)
    result['adjacent_deltas'] = [{'from': a[0], 'to': b[0], 'raw': b[1]-a[1]} for a,b in zip(phases,phases[1:])]
    write(folder / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
