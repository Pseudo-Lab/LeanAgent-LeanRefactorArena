"""Assemble a local Arena upload from explicit, hash-locked selections.

No Lean execution, network calls, state promotion, or contest submission.
The JSONL is the upload. The JSON array is a human-readable companion.
"""
from pathlib import Path
import ast
import datetime
import hashlib
import json
import re
import sys

HERE = Path(__file__).resolve().parent
E = HERE.parent
W = E.parents[1]
ROOT = W.parents[1]
sys.path.insert(0, str(ROOT / 'insights-20261024-round7/p11'))
from tokens_snapshot import validate_declaration, proof_tokens
from evidence_gate import verified_pins as evidence_verified_pins


def sha(data):
    return hashlib.sha256(data).hexdigest()


def public_filter(path):
    """Execute only the five pure intake declarations, never the Space app."""
    names = {'_FORBIDDEN_PATTERNS', '_HEARTBEAT_IDENT', '_MAX_PROOF_BYTES',
             '_strip_lean_comments', '_check_forbidden'}
    nodes = []
    found = set()
    for node in ast.parse(path.read_text()).body:
        name = None
        if isinstance(node, ast.FunctionDef):
            name = node.name
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in names:
            nodes.append(node)
            found.add(name)
    assert found == names
    scope = {'re': re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return scope['_check_forbidden']


def build(selection_path, output, *, require_complete=False):
    selection = json.loads(selection_path.read_text())
    benchmark_path = Path(selection['benchmark'])
    benchmark = [json.loads(line) for line in benchmark_path.read_text().splitlines() if line.strip()]
    assert len(benchmark) == 15 and len({r['name'] for r in benchmark}) == 15
    assert all(proof_tokens(r['src'], r['statement']) == r['proof_length'] for r in benchmark)
    assert {int(i) for i in selection['problems']} == set(range(1, 16))
    rules = E / 'rules/app.py'
    check_forbidden = public_filter(rules)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'proofs').mkdir(exist_ok=True)
    (output / 'evidence').mkdir(exist_ok=True)
    rows, manifest_rows, pending = [], [], []
    for n, meta in enumerate(benchmark, 1):
        selected = selection['problems'][str(n)]
        source = Path(selected['source'])
        data = source.read_bytes()
        assert sha(data) == selected['sha256'], (n, 'selection source changed')
        code = data.decode('utf-8')
        validate_declaration(code, meta['statement'])
        assert check_forbidden(code) is None, (n, check_forbidden(code))
        assert len(data) < 256 * 1024
        required = [pin for entry in meta['version_info'] for pin in entry]
        verified = evidence_verified_pins(n, selected, sha(data))
        assert set(verified) == set(selected['verified_pins']), (n, 'declared and evidence-derived pins differ')
        assert len(verified) == len(set(verified)) and set(verified) <= set(required)
        missing = [pin for pin in required if pin not in verified]
        if missing:
            pending.append({'id': n, 'pins': missing})
        path = output / 'proofs' / f'P{n:02}.lean'
        path.write_bytes(data)
        snapshots = []
        for i, evidence in enumerate(selected.get('evidence', []), 1):
            evidence_path = Path(evidence)
            ev_data = evidence_path.read_bytes()
            copy = output / 'evidence' / f'P{n:02}-{i:02}-{evidence_path.name}'
            copy.write_bytes(ev_data)
            snapshots.append({'source': str(evidence_path), 'path': str(copy.relative_to(output)),
                              'sha256': sha(ev_data)})
        rows.append({'name': meta['name'], 'proof': code})
        manifest_rows.append(dict(id=n, name=meta['name'], path=str(path.relative_to(output)),
            sha256=sha(data), source=str(source), tokens=proof_tokens(code, meta['statement']),
            upstream_source_url=meta['url'],
            required_revisions={pin: rev for entry in meta['version_info'] for pin, rev in entry.items()},
            original_tokens=meta['proof_length'], required_pins=required, verified_pins=verified,
            pending_pins=missing, evidence=snapshots, note=selected.get('note', ''),
            strategy=selected.get('strategy', ''), metrics=selected.get('metrics')))
    if require_complete:
        assert not pending, ('required pin verification remains', pending)
    payload = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode()
    assert len(payload) < 8 * 1024 * 1024
    array = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode()
    (output / 'submission.jsonl').write_bytes(payload)
    (output / 'proofs-readable.json').write_bytes(array)
    # Independent round trip checks on the actual files being handed over.
    parsed = [json.loads(line) for line in (output / 'submission.jsonl').read_text().splitlines()]
    assert parsed == rows == json.loads((output / 'proofs-readable.json').read_text())
    assert [r['name'] for r in parsed] == [r['name'] for r in benchmark]
    for row, entry in zip(parsed, manifest_rows):
        assert sha(row['proof'].encode()) == entry['sha256']
        assert row['proof'].encode() == (output / entry['path']).read_bytes()
    manifest = dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='ALL_REQUIRED_PINS_EVIDENCED' if not pending else 'PENDING_PIN_VERIFICATION',
        official_submission=False, official_score=None,
        upload='submission.jsonl', readable_companion='proofs-readable.json',
        benchmark=str(benchmark_path), benchmark_sha256=sha(benchmark_path.read_bytes()),
        selection=str(selection_path), selection_sha256=sha(selection_path.read_bytes()),
        exporter_sha256=sha(Path(__file__).read_bytes()),
        evidence_gate_sha256=sha((HERE / 'evidence_gate.py').read_bytes()),
        tokenizer_source=sys.modules[proof_tokens.__module__].__file__,
        tokenizer_sha256=sha(Path(sys.modules[proof_tokens.__module__].__file__).read_bytes()),
        rules_snapshot=str(rules), rules_sha256=sha(rules.read_bytes()),
        rules_source='https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/main/app.py',
        checks=dict(rows=15, unique_official_names=True, exact_statements=True,
                    no_additional_declarations=True, public_intake_filter=True,
                    roundtrip_and_proof_hashes=True, proof_to_successful_pin_evidence=True,
                    tokenizer_matches_all_benchmark_original_lengths=True),
        submission_sha256=sha(payload), submission_bytes=len(payload),
        pending=pending, problems=manifest_rows,
        scope='Local and archived evidence, not an official worker acceptance or score. '
              'Different evidence tiers and heartbeat environments remain identified per problem.')
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ['status', 'submission_bytes', 'submission_sha256', 'pending']}, ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    assert len(sys.argv) in (3, 4)
    if len(sys.argv) == 4:
        assert sys.argv[3] == '--require-complete'
    build(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(),
          require_complete=len(sys.argv) == 4)
