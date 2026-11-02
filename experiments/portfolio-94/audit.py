"""Recompute saved full-source measurement evidence without starting Lean."""
import argparse
import json
from pathlib import Path
import re
import statistics
from search import load, read, digest, write


def audit(root):
    _, m, loaded = load(root)
    source, fp = loaded[-2:]
    nonces, counts, incomplete = set(), {'receipts': 0, 'valid': 0, 'failed': 0}, []
    for p in sorted((root / 'evaluations').glob('*/result.json')):
        row = read(p); code = (p.parent / 'candidate.lean').read_text()
        assert digest(code) == row['code_sha256'], str(p)
        assert row['environment_identity'] == fp['identity_sha256'], str(p)
        samples = []
        for job in row['jobs']:
            name = job['name']; text = (p.parent / (name + '.lean')).read_text()
            log = (p.parent / (name + '.log')).read_text()
            assert digest(text) == job['source_sha256'], str(p)
            assert digest(log) == job['log_sha256'], str(p)
            if name == 'Check':
                assert text == m.plain_source(source, code), str(p)
            if name.startswith('Measure') and 'nonce' in job:
                nonce = job['nonce']; assert nonce not in nonces, nonce; nonces.add(nonce)
                assert text == m.measured_source(source, code, nonce), str(p)
                values = re.findall(m.RAW_MARKER + r' ' + nonce + r' (\d+)', log)
                assert len(values) == 1, str(p)
                samples.append(int(values[0]))
            if row['valid']:
                assert not job['returncode'] and not job['timed_out'], str(p)
        if row['valid']:
            assert samples and samples == row['raw_samples'], str(p)
            assert statistics.median(samples) == row['raw'], str(p)
            log = (p.parent / 'Audit.log').read_text()
            values = re.findall(r'OFFLINE_AXIOMS (\[[^\n]*\])', log)
            assert len(values) == 1 and json.loads(values[0]) == row['axioms'], str(p)
            assert set(row['axioms']) <= m.ALLOWED_AXIOMS, str(p)
            assert row['tokens'] == m.proof_tokens(code, m.STATEMENT), str(p)
            counts['valid'] += 1
        elif row.get('error') or row.get('interrupted'):
            assert row['raw'] is None, str(p)
            counts['failed'] += 1
        else:
            incomplete.append(str(p))
        counts['receipts'] += 1
    state = read(root / 'state.json')
    for row in state['attempts']:
        receipt = read(Path(row['folder']) / 'result.json')
        assert all(row[k] == v for k,v in receipt.items())
    return {**counts, 'unique_measurement_nonces': len(nonces), 'incomplete': incomplete,
            'passed': not incomplete, 'scope': 'saved source/log/hash/nonce/context/axiom/metric audit; no new Lean execution',
            'environment_identity': fp['identity_sha256']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('root', type=Path)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    result = audit(a.root.resolve())
    if a.output.exists():
        raise ValueError('Use a fresh audit path')
    write(a.output, result); print(json.dumps(result, ensure_ascii=False, indent=2))
