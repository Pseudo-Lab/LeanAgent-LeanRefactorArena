"""Audit one completed receipt independently of unfinished sibling searches.

Read-only for Lean sources, evaluator state, and receipts; no Lean execution.
"""
import argparse
import json
from pathlib import Path
import re
import statistics

from search import digest, load, read, write


def audit_selected(root, receipt):
    _, module, loaded = load(root)
    source, fingerprint = loaded[-2:]
    row = read(receipt)
    folder = receipt.parent
    code = (folder / 'candidate.lean').read_text()
    assert row['valid'], 'Selected receipt is not valid'
    assert digest(code) == row['code_sha256']
    assert row['environment_identity'] == fingerprint['identity_sha256']
    module.validate_declaration(code, module.STATEMENT)
    assert row['tokens'] == module.proof_tokens(code, module.STATEMENT)
    names, samples, nonces = [], [], set()
    for job in row['jobs']:
        name = job['name']
        assert name not in names, 'Duplicate job name'
        names.append(name)
        assert not job['returncode'] and not job['timed_out']
        text = (folder / (name + '.lean')).read_text()
        log = (folder / (name + '.log')).read_text()
        assert digest(text) == job['source_sha256']
        assert digest(log) == job['log_sha256']
        if name == 'Check':
            assert text == module.plain_source(source, code)
        elif name == 'Audit':
            expected = ('import Check\nimport Lean\nopen Lean Elab Command in\nrun_cmd do\n'
                        '  let ax ← Lean.collectAxioms `' + module.TARGET + '\n'
                        '  logInfo m!"OFFLINE_AXIOMS {toJson (ax.toList.map Name.toString)}"\n')
            assert text == expected
            matches = re.findall(r'OFFLINE_AXIOMS (\[[^\n]*\])', log)
            assert len(matches) == 1
            assert json.loads(matches[0]) == row['axioms']
            assert set(row['axioms']) <= module.ALLOWED_AXIOMS
        else:
            assert name == 'Measure' + str(len(samples) + 1)
            nonce = job['nonce']
            assert nonce not in nonces
            nonces.add(nonce)
            assert text == module.measured_source(source, code, nonce)
            matches = re.findall(module.RAW_MARKER + r' ' + nonce + r' (\d+)', log)
            assert len(matches) == 1
            samples.append(int(matches[0]))
    assert names[:2] == ['Check', 'Audit']
    assert samples and samples == row['raw_samples']
    assert statistics.median(samples) == row['raw']
    return dict(passed=True, scope='Selected completed receipt only; unfinished sibling candidates excluded',
                receipt=str(receipt), receipt_sha256=digest(receipt.read_bytes()),
                candidate_sha256=digest(code), tokens=row['tokens'], raw_samples=samples,
                raw_median=row['raw'], axioms=row['axioms'],
                environment_identity=fingerprint['identity_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Use a fresh output path'
    result = audit_selected(args.root.resolve(), args.receipt.resolve())
    write(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
