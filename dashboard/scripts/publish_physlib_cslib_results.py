#!/usr/bin/env python3
"""Publish PR 54's summary without inventing raw samples or compiler receipts."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = 'solutions/physlib-cslib20/manifest.json'
PACK = 'solutions/physlib-cslib20/submission.jsonl'
OUTPUT = 'dashboard/public/data/physlib-cslib-results.json'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def build(root):
    m = json.loads((root / MANIFEST).read_text())
    originals = json.loads((root / 'dashboard/public/data/final-baselines.json').read_text())
    pack = [json.loads(line) for line in (root / PACK).read_text().splitlines()]
    if (m['dataset_sha256'] != originals['datasetSha256'] or m['api_calls'] != 0
            or len(m['results']) != 20 or len(pack) != 20
            or {r['row'] for r in m['results']} != set(range(11, 31))):
        raise ValueError('Invalid PhysLib/CSLib publication scope')
    records = []
    for r, submitted in zip(m['results'], pack):
        original = next(p for p in originals['problems'] if p['row'] == r['row'])
        proof_path = f"solutions/physlib-cslib20/F{r['row']:03}.lean"
        code, proof = (root / proof_path).read_bytes(), submitted['proof'].encode()
        pins = {v['version']: v['revision'] for v in original['references']}
        score = 100 - 100 / 3 * (r['candidate_tokens'] / r['original_tokens']
                                 + r['candidate_raw_heartbeats'] / r['original_raw_heartbeats'])
        if ((r['name'], r['source']) != (original['name'], original['source'])
                or submitted['name'] != r['name'] or digest(proof) != r['proof_sha256']
                or code not in (proof, proof + b'\n')
                or {k: v for item in r['versions'] for k, v in item.items()} != pins
                or len(r['versions']) != len(pins)
                or set(r['checks']) != {v['environment'] for v in original['references']}
                or any(v['valid'] is not True or type(v['repeats']) is not int or v['repeats'] < 1
                       for v in r['checks'].values())
                or not math.isclose(score, r['score_local'], rel_tol=0, abs_tol=1e-9)):
            raise ValueError(f"F{r['row']:03}: proof, version or measurement mismatch")
        records.append({**r, 'proof': submitted['proof'], 'proofPath': proof_path,
                        'proofFileSha256': digest(code)})
    if not math.isclose(sum(r['score_local'] for r in records) / 20, m['local_mean'], abs_tol=1e-9):
        raise ValueError('Summary mean mismatch')
    return {**m, 'publicationSchemaVersion': 1, 'originPr': 54,
            'evidenceLevel': 'published-summary', 'sourceManifest': MANIFEST,
            'sourceManifestSha256': digest((root / MANIFEST).read_bytes()),
            'submissionSha256': digest((root / PACK).read_bytes()), 'results': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    text = json.dumps(build(ROOT), ensure_ascii=False, indent=2) + '\n'
    path = ROOT / OUTPUT
    if args.check:
        if path.read_text() != text:
            raise SystemExit('Published PhysLib/CSLib summary differs from repository evidence')
    else:
        path.write_text(text)
    print('PhysLib/CSLib: 20 proofs, 42 version checks; original JSONL hashes and file newline differences preserved')
