#!/usr/bin/env python3
"""Import team-reported measurements without executing Lean or making API calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'solutions/team-shared-20261102'
OUTPUT = ROOT / 'dashboard/public/data/team-shared-results.json'
SOURCES = {
    'seongwoo': ('남성우', 'LRA_physlib_cslib'),
    'jiyeon': ('손지연', 'LeanRefactor_Report_2026-11-02_v4'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def import_archives(paths):
    PACK.mkdir(parents=True, exist_ok=True)
    records = {}
    with zipfile.ZipFile(PACK / 'reported-results.zip', 'w', zipfile.ZIP_DEFLATED) as out:
        for key, path in paths.items():
            author, prefix = SOURCES[key]
            archive = Path(path)
            records[key] = {'author': author, 'filename': archive.name,
                            'sha256': sha(archive.read_bytes())}
            with zipfile.ZipFile(archive) as source:
                names = [f'{prefix}/final.json']
                names += [n for n in source.namelist() if n.startswith(f'{prefix}/proofs/') and n.endswith('.lean')]
                if key == 'seongwoo':
                    rows = json.loads(source.read(f'{prefix}/final.json'))
                    names += [f"{prefix}/logs/{p['source'].removeprefix('runs/')}/summary.json" for p in rows]
                for name in sorted(set(names)):
                    out.writestr(name, source.read(name))
    metadata = {'importedAt': datetime.now(timezone.utc).isoformat(), 'sources': records}
    (PACK / 'source-archives.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')


def build(root=ROOT):
    pack = root / 'solutions/team-shared-20261102'
    meta = json.loads((pack / 'source-archives.json').read_text())
    baselines = json.loads((root / 'dashboard/public/data/final-baselines.json').read_text())
    originals = {p['name']: p for p in baselines['problems']}
    output = []
    with zipfile.ZipFile(pack / 'reported-results.zip') as source:
        for key, (author, prefix) in SOURCES.items():
            raw = source.read(f'{prefix}/final.json')
            report = json.loads(raw)
            rows = report if key == 'seongwoo' else report['problems']
            require(len(rows) == 20, 'Expected 20 team results per archive')
            for row in rows:
                if key == 'seongwoo':
                    summary_path = f"{prefix}/logs/{row['source'].removeprefix('runs/')}/summary.json"
                    summary = json.loads(source.read(summary_path))
                    name = summary['name']
                    original = originals[name]
                    require(original['row'] == row['id'] + 1 and row['compat'] == 100, 'Seongwoo identity or compatibility mismatch')
                    proof_path = next(n for n in source.namelist() if n.startswith(f"{prefix}/proofs/{row['id']}_"))
                    checks = summary.get('final_verification')
                    if checks is not None:
                        require(checks['all_ok'] and all(v['ok'] for v in checks['versions'].values()), 'Reported version failure')
                        require(set(checks['versions']) == {v['environment'] for v in original['references']}, 'Reported versions differ')
                    candidate_samples = None
                    environment = f"{original['source']}-{'v4.34.0' if original['source'] == 'physlib' else 'v4.33.1'}"
                    if checks:
                        candidate_samples = checks['versions'][environment]['samples']
                    baseline_samples = None
                    cost = row['cost']
                    measured_at = None
                    evidence = [{'path': 'solutions/team-shared-20261102/reported-results.zip',
                                 'sha256': sha((pack / 'reported-results.zip').read_bytes())}]
                else:
                    name = row['name']
                    original = originals[name]
                    require(set(row['versions']) == set(original['requiredVersions']), 'Jiyeon version set differs')
                    for ref in original['references']:
                        v = row['versions'][ref['version']]
                        require(v['valid'] and v['commit'] == ref['revision'], 'Reported pin or pass status differs')
                    proof_path = f"{prefix}/{row['proof']}"
                    primary = row['versions'][row['H_reference_version']]
                    baseline_samples, candidate_samples = primary['original_raw_samples'], primary['raw_samples']
                    environment = f"{original['source']}-{row['H_reference_version']}"
                    cost = None
                    measured_at = row['execution']['session']['finished_utc']
                    evidence = [{'path': 'solutions/team-shared-20261102/reported-results.zip',
                                 'sha256': sha((pack / 'reported-results.zip').read_bytes())}]
                proof_bytes = source.read(proof_path)
                if key == 'jiyeon':
                    require(sha(proof_bytes) == row['proof_sha256'], 'Reported proof hash differs')
                proof = proof_bytes.decode('utf-8')
                require(all(type(row[k]) is int and row[k] > 0 for k in ['T0', 'T', 'H0', 'H']), 'Invalid reported measurements')
                for samples, expected in [(baseline_samples, row['H0']), (candidate_samples, row['H'])]:
                    if samples is not None:
                        require(len(samples) in (1, 3) and sorted(samples)[len(samples)//2] == expected, 'Reported sample median differs')
                target = f"solutions/team-shared-20261102/{key}/F{original['row']:03}.lean"
                require((root / target).read_bytes() == proof_bytes, 'Saved proof differs from source archive')
                output.append({
                    'row': original['row'], 'name': name, 'source': original['source'],
                    'author': author, 'runId': f'team-report-{key}-20261102', 'proofPath': target,
                    'proof': proof, 'candidateHash': sha(proof_bytes), 'proofFileHash': sha(proof_bytes),
                    'baseline': {'tokens': row['T0'], 'raw_heartbeats': row['H0'], 'raw_samples': baseline_samples},
                    'candidate': {'tokens': row['T'], 'raw_heartbeats': row['H'], 'raw_samples': candidate_samples},
                    'versions': [{'version': v['version'], 'revision': v['revision'], 'environment': v['environment'],
                                  'status': 'pass', 'fingerprint': None} for v in original['references']],
                    'baselineCompatibility': 100, 'measuredAt': measured_at,
                    'score': 100 - 100/3*(row['T']/row['T0'] + row['H']/row['H0']),
                    'currentRunCostUsd': '0', 'reportedCostUsd': cost,
                    'evidenceLevel': 'shared-report', 'measurementEnvironment': environment,
                    'measurementNote': '팀원 공유 측정값 사용 · 이번 통합에서 Lean/API 재실행 없음',
                    'alternatives': [], 'evidence': evidence,
                })
    require({p['row'] for p in output} == {*range(11, 41), *range(51, 61)}, 'Shared result scope differs')
    return {'schemaVersion': 1, 'datasetSha256': baselines['datasetSha256'],
            'generatedAt': meta['importedAt'], 'officialEvaluation': False,
            'measurementPolicy': 'reported-paired', 'apiCallsDuringImport': 0, 'leanRunsDuringImport': 0,
            'sources': meta['sources'], 'problems': sorted(output, key=lambda p: p['row'])}


def save_proofs():
    with zipfile.ZipFile(PACK / 'reported-results.zip') as source:
        baselines = json.loads((ROOT / 'dashboard/public/data/final-baselines.json').read_text())
        originals = {p['name']: p for p in baselines['problems']}
        for key, (_, prefix) in SOURCES.items():
            report = json.loads(source.read(f'{prefix}/final.json'))
            rows = report if key == 'seongwoo' else report['problems']
            for row in rows:
                if key == 'seongwoo':
                    name = json.loads(source.read(f"{prefix}/logs/{row['source'].removeprefix('runs/')}/summary.json"))['name']
                    path = next(n for n in source.namelist() if n.startswith(f"{prefix}/proofs/{row['id']}_"))
                else:
                    name, path = row['name'], f"{prefix}/{row['proof']}"
                target = PACK / key / f"F{originals[name]['row']:03}.lean"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seongwoo')
    parser.add_argument('--jiyeon')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.seongwoo or args.jiyeon:
        require(args.seongwoo and args.jiyeon and not args.check, 'Provide both archives for import')
        import_archives({'seongwoo': args.seongwoo, 'jiyeon': args.jiyeon})
        save_proofs()
    text = json.dumps(build(), ensure_ascii=False, indent=2) + '\n'
    if args.check:
        require(OUTPUT.read_text() == text, 'Published team report differs from source records')
    else:
        OUTPUT.write_text(text)
    print('Team reports: 40 proofs imported; measurements preserved; Lean/API calls: 0')
