"""Provisional one-process full-source screening; never final certification.

Uses the frozen run's source adapter and environment. The existing synchronous
measurement is followed by target-axiom inspection in the SAME Lean process.
No frozen config, evaluation receipt, or search state is changed. Promote a
winner only after the original runner's plain Check, independent Audit and fresh
measurements. A failed process is always rejected even if a raw marker exists.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

from search_exclusive4 import load, digest, write
from resources_exclusive import lease


def probe(root, candidate, label, timeout=None):
    cfg, module, loaded = load(root)
    _, lean, args, env, source, fingerprint = loaded
    code = candidate.read_text()
    module.validate_declaration(code, module.STATEMENT)
    folder = root / 'fast-probes' / (label + '-' + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    (folder / 'candidate.lean').write_text(code)
    nonce = uuid.uuid4().hex
    audit = ('\nopen Lean Elab Command in\nrun_cmd do\n'
             '  let ax ← Lean.collectAxioms `' + module.TARGET + '\n'
             '  logInfo m!"FAST_AXIOMS ' + nonce + ' {toJson (ax.toList.map Name.toString)}"\n')
    text = module.measured_source(source, code, nonce) + audit
    path = folder / 'Screen.lean'
    path.write_text(text)
    tracked = [Path(__file__).resolve(), Path(__file__).with_name('search_exclusive4.py'),
               Path(__file__).with_name('resources_exclusive.py'),
               Path(__file__).with_name('resources.py'), root / 'config.json']
    hashes = {str(p): digest(p.read_bytes()) for p in tracked}
    for i, p in enumerate(tracked):
        (folder / ('snapshot-' + str(i) + '-' + p.name)).write_bytes(p.read_bytes())
    command = [str(lean), '-j1', '-M4096', '--root=' + str(folder), *args, str(path)]
    row = dict(scope='PROVISIONAL combined full-source measurement and same-process axiom audit; requires independent final certification',
               final_certified=False, valid_fast=False, label=label,
               candidate_sha256=digest(code), tokens=module.proof_tokens(code, module.STATEMENT),
               environment_identity=fingerprint['identity_sha256'], nonce=nonce,
               source_sha256=digest(text), command=command, code_hashes=hashes,
               frozen_code_hashes=cfg['code_hashes'], raw=None, axioms=None)
    write(folder / 'result.json', row)
    try:
        with lease():
            started = time.monotonic()
            try:
                result = subprocess.run(command, cwd=folder, env=env, capture_output=True,
                                        text=True, timeout=timeout or cfg['timeout_seconds'])
                log, rc = result.stdout + result.stderr, result.returncode
            except subprocess.TimeoutExpired as exc:
                def decode(value):
                    return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                log = decode(exc.stdout) + decode(exc.stderr) + '\nFAST_TIMEOUT\n'
                rc = 124
            row['execution_seconds'] = time.monotonic() - started
        (folder / 'Screen.log').write_text(log)
        row.update(returncode=rc, log_sha256=digest(log))
        if rc:
            raise ValueError('Whole process failed: ' + log[-1800:])
        values = re.findall(module.RAW_MARKER + ' ' + nonce + r' (\d+)', log)
        axioms = re.findall('FAST_AXIOMS ' + nonce + r' (\[[^\n]*\])', log)
        if len(values) != 1 or len(axioms) != 1:
            raise ValueError('Missing or ambiguous measurement/audit marker')
        row['axioms'] = json.loads(axioms[0])
        if not set(row['axioms']) <= module.ALLOWED_AXIOMS:
            raise ValueError('Unapproved target axiom')
        if hashes != {str(p): digest(p.read_bytes()) for p in tracked}:
            raise ValueError('Screening code changed during run')
        if load(root)[2][-1]['identity_sha256'] != fingerprint['identity_sha256']:
            raise ValueError('Frozen environment changed during run')
        row.update(valid_fast=True, raw=int(values[0]))
    except ValueError as exc:
        row['error'] = str(exc)
    except BaseException as exc:
        row['interrupted'] = repr(exc)
        write(folder / 'result.json', row)
        raise
    write(folder / 'result.json', row)
    print(json.dumps({k: row[k] for k in ['scope', 'label', 'valid_fast', 'tokens', 'raw']}, ensure_ascii=False), flush=True)
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    probe(args.root.resolve(), args.candidate.resolve(), args.label)
