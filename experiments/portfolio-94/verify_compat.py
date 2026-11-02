"""Full-source compilation and target-axiom audit on one additional required pin.

No HB or score is produced. Primary-pin measurements remain separate evidence.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from search import adapter, digest, write
from resources_exclusive import lease


def verify(adapter_path, environment, candidate, output, timeout=240):
    output.mkdir(parents=True, exist_ok=False)
    m = adapter(adapter_path)
    code = candidate.read_text()
    m.validate_declaration(code, m.STATEMENT)
    _, lean, args, env, source, fp = m.load_environment(environment)
    paths = [Path(__file__), adapter_path, m.META_PATH,
             Path(__file__).with_name('search.py'),
             Path(__file__).with_name('resources.py'),
             Path(__file__).with_name('resources_exclusive.py'), *m.DEPENDENCIES]
    hashes = {str(p): digest(p.read_bytes()) for p in paths}
    for i, p in enumerate(paths):
        (output / f'snapshot-{i}-{p.name}').write_bytes(p.read_bytes())
    (output / 'candidate.lean').write_text(code)
    write(output / 'environment.json', fp)
    row = dict(valid=False, scope='Additional-pin compatibility only; no HB or score',
               target=m.TARGET, candidate_sha256=digest(code),
               proof_tokens=m.proof_tokens(code, m.STATEMENT),
               statement_sha256=digest(m.STATEMENT), code_hashes=hashes,
               environment=str(environment), environment_identity=fp['identity_sha256'],
               lean_pin=fp['lean_pin'], jobs=[], axioms=None)

    def save():
        write(output / 'result.json', row)

    def job(name, text, extra=(), audit=False):
        p = output / (name + '.lean')
        p.write_text(text)
        current = dict(env)
        if audit:
            current['LEAN_PATH'] = str(output) + os.pathsep + env['LEAN_PATH']
        command = [str(lean), '-j1', '-M4096', '--root=' + str(output), *args, *extra, str(p)]
        with lease():
            start = time.monotonic()
            try:
                r = subprocess.run(command, cwd=output, env=current, capture_output=True,
                                   text=True, timeout=timeout)
                log, rc = r.stdout + r.stderr, r.returncode
            except subprocess.TimeoutExpired as exc:
                def text_value(value):
                    return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                log = text_value(exc.stdout) + text_value(exc.stderr) + '\nCOMPAT_TIMEOUT\n'
                rc = 124
            seconds = time.monotonic() - start
        (output / (name + '.log')).write_text(log)
        row['jobs'].append(dict(name=name, command=command, returncode=rc, seconds=seconds,
                                source_sha256=digest(text), log_sha256=digest(log)))
        save()
        if rc:
            raise ValueError(name + ' failed: ' + log[-2500:])
        return log

    save()
    try:
        job('Check', m.plain_source(source, code), ['-o', str(output / 'Check.olean')])
        log = job('Audit', 'import Check\nimport Lean\nopen Lean Elab Command in\nrun_cmd do\n'
                  '  let ax ← Lean.collectAxioms `' + m.TARGET + '\n'
                  '  logInfo m!"COMPAT_AXIOMS {toJson (ax.toList.map Name.toString)}"\n', audit=True)
        matches = re.findall(r'COMPAT_AXIOMS (\[[^\n]*\])', log)
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous target axiom audit')
        row['axioms'] = json.loads(matches[0])
        if not set(row['axioms']) <= m.ALLOWED_AXIOMS:
            raise ValueError('Unapproved target axiom')
        if hashes != {str(p): digest(p.read_bytes()) for p in paths}:
            raise ValueError('Runner or adapter changed')
        if m.load_environment(environment)[-1]['identity_sha256'] != fp['identity_sha256']:
            raise ValueError('Environment changed')
        row['valid'] = True
    except ValueError as exc:
        row['error'] = str(exc)
    except BaseException as exc:
        row['interrupted'] = repr(exc)
        save()
        raise
    save()
    print(json.dumps({k: row[k] for k in ['target', 'lean_pin', 'valid', 'proof_tokens']}, ensure_ascii=False), flush=True)
    return row


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['adapter', 'environment', 'candidate', 'output']:
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    verify(*(getattr(a, key).resolve() for key in ['adapter', 'environment', 'candidate', 'output']))
