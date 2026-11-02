#!/usr/bin/env python3
"""Publish complete, audited Final measurements in the dashboard's canonical format."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

REPO = Path(__file__).resolve().parents[2]
DATASET_SHA = 'd53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682'
TOKEN_SPEC = importlib.util.spec_from_file_location('final_dashboard_tokens', REPO / 'experiments/proof-analyze/proof_tokens.py')
TOKEN_MODULE = importlib.util.module_from_spec(TOKEN_SPEC)
TOKEN_SPEC.loader.exec_module(TOKEN_MODULE)


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, default=REPO / 'runs/manual/final60-baselines-final-20261102')
    parser.add_argument('--audit', type=Path, default=REPO / 'runs/manual/final60-completion-audit-20261102/receipt.json')
    args = parser.parse_args()
    dataset = REPO / 'benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl'
    if digest(dataset) != DATASET_SHA:
        raise ValueError('Final dataset bytes changed')
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    report = read(REPO / 'docs/measurements/final60-baselines.json')
    audit = read(args.audit)
    if (report['dataset_sha256'] != DATASET_SHA or len(rows) != 60 or report['measured_problems'] != 60
            or report['environment_verification']['status'] != 'passed' or audit['status'] != 'passed'
            or audit['counts']['environment_pairs'] != 127 or len(audit['prepared_environments']) != 17
            or len(audit['compilers']) != 8):
        raise ValueError('Publication requires 60 problems, 127 verified pairs and a passed complete audit')
    protocol = read(args.run_root / 'protocol.json')
    records = {}
    for item in protocol.get('history_records', []):
        path = Path(item['path'])
        if digest(path) != item['sha256']:
            raise ValueError('Historical measurement record changed')
        records[path.parent.name] = path
    records.update({p.parent.name: p for p in args.run_root.glob('F*/record.json')})
    indexed = {p['id']: p for p in report['problems']}
    if len(indexed) != 60 or len(records) != 60:
        raise ValueError('Missing or duplicate Final slots')
    problems = []
    for index, row in enumerate(rows, 1):
        identifier = f'F{index:03d}'
        measured = indexed[identifier]
        record_path = records[identifier]
        record = read(record_path)
        reference_sha = hashlib.sha256(row['src'].encode()).hexdigest()
        if (TOKEN_MODULE.proof_length(row['src'], row['statement']) != row['proof_length']
                or measured['reference_sha256'] != reference_sha or measured['name'] != row['name']
                or measured['source'] != row['source'] or measured['provided_length'] != row['proof_length']
                or measured['status'] != 'measured'):
            raise ValueError('Final reference identity differs: ' + identifier)
        evidence_root = Path(record.get('evidence_root', str(record_path.parent)))
        result_path = evidence_root / 'evaluation/result.json'
        if digest(result_path) != measured['result_sha256'] or digest(result_path) != record['result_sha256']:
            raise ValueError('Raw measurement result changed: ' + identifier)
        result = read(result_path)
        pins = [(version, revision) for item in row['version_info'] for version, revision in item.items()]
        expected = {row['source'] + '-' + version for version, _ in pins}
        if set(measured['environments']) != expected or not result['valid']:
            raise ValueError('Required version coverage differs: ' + identifier)
        references = []
        for version, revision in pins:
            environment = row['source'] + '-' + version
            value = measured['environments'][environment]
            samples = value['raw_samples']
            if (not value['valid'] or not samples or any(type(n) is not int or n < 0 for n in samples)
                    or statistics.median(samples) != value['median_raw_heartbeats']
                    or statistics.median(n // 1000 for n in samples) != value['median_heartbeats']):
                raise ValueError('Invalid measured samples: ' + identifier + '/' + environment)
            references.append({'environment': environment, 'version': version, 'revision': revision,
                               'rawHeartbeats': value['median_raw_heartbeats'],
                               'scaledHeartbeats': value['median_heartbeats'], 'rawSamples': samples,
                               'sampleCount': len(samples), 'status': 'pass'})
        primary = references[0]
        primary_result = result['environments'][primary['environment']]
        folder = Path(primary_result.get('cache', {}).get('origin', str(result_path.parent / primary['environment'])))
        evidence = []
        for path in [record_path, result_path]:
            evidence.append({'path': str(path.resolve().relative_to(REPO)), 'sha256': digest(path)})
        samples, dates = [], []
        for native in primary_result['runs']:
            if native['returncode'] or native['timed_out']:
                raise ValueError('Failed native invocation: ' + identifier)
            for key in ['source', 'log']:
                path = folder / native[key]
                if digest(path) != native[key + '_sha256']:
                    raise ValueError('Changed native evidence: ' + identifier)
                evidence.append({'path': str(path.resolve().relative_to(REPO)), 'sha256': digest(path)})
            if native.get('measurement'):
                samples.append(native['measurement']['raw'])
                dates.append(native['memory_after']['at'])
        if samples != primary['rawSamples']:
            raise ValueError('Raw samples differ: ' + identifier)
        single_pass = not any(not r.get('measurement') and r.get('phase') != 'axiom-frontier-audit'
                              for r in primary_result['runs'])
        problems.append({'id': identifier, 'row': index, 'name': row['name'], 'source': row['source'],
                         'providedLength': row['proof_length'], 'referenceSha256': reference_sha,
                         'primaryVersion': primary['version'], 'primaryRevision': primary['revision'],
                         'requiredVersions': [v for v, _ in pins], 'references': references,
                         'local': {'runId': record_path.parent.parent.name, 'sampleCount': len(samples),
                                   'tokens': measured['provided_length'], 'auditTokens': measured['local_length'],
                                   'rawHeartbeats': primary['rawHeartbeats'], 'scaledHeartbeats': primary['scaledHeartbeats'],
                                   'rawSamples': samples, 'measuredAt': max(dates), 'evidence': evidence,
                                   'referenceSinglePass': single_pass}})
    snapshot = {'schemaVersion': 1, 'dataset': 'final-baselines', 'datasetSha256': DATASET_SHA,
                'generatedAt': max(p['measured_at'] for p in report['problems']), 'runId': args.run_root.name,
                'measurementPolicy': 'all-pins-local-samples',
                'verification': {'status': 'passed', 'problemVersions': 127, 'environments': 17, 'compilerVersions': 8,
                                 'auditSha256': digest(args.audit)}, 'problems': problems}
    (REPO / 'dashboard/public/data/final-baselines.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    print('EXPORTED canonical Final data: 60 complete problems, 127 versions, candidate results 0')


if __name__ == '__main__':
    main()
