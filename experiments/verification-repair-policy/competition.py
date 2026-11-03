"""Compatibility contract for the exact, frozen warm-up problem; no model calls."""
import json

from common import REPO, sha

SNAPSHOT = 'benchmarks/arena/56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c'


def contract(data, snapshot, ready):
    source = snapshot['files']['benchmark_data_warmup.jsonl']
    if sha(data) != source['sha256']:
        raise ValueError('Official warm-up snapshot checksum differs')
    matches = [row for row in map(json.loads, data.decode().splitlines())
               if row['name'] == ready['problem']['name']]
    if len(matches) != 1:
        raise ValueError('Expected one official problem definition')
    row = matches[0]
    if (row['src'].rstrip() != ready['problem']['reference'].rstrip()
            or row['statement'].rstrip() != ready['problem']['statement'].rstrip()):
        raise ValueError('Calibrated problem differs from official original')
    pins = {version: revision for entry in row['version_info'] for version, revision in entry.items()}
    version = ready['environment']['toolchain'].split(':')[-1]
    revision = ready['fingerprint']['git']['head']
    # This P02 has exactly one official environment. Never label a partial matrix as all compatible.
    if pins != {version: revision}:
        raise ValueError('Prepare every official environment before using this compatibility adapter')
    return {'benchmark_profile': 'warmup', 'benchmark_revision': snapshot['arena_revision'],
            'benchmark_sha256': sha(data), 'source_url': source['url'], 'problem_name': row['name'],
            'source_file': row['file_path'], 'library_url': row['url'],
            'required_environments': [{'lean_version': version, 'library_revision': revision,
                                       'environment_id': ready['environment']['id']}],
            'candidate_policy': 'same selected declaration; no per-version edits',
            'official_evaluation': False}


def report(protocol, reference, rows):
    spec = protocol['compatibility']
    if spec is None:
        return {'status': 'fixture_only', 'official_evaluation': False}
    selected = rows[0] if len(rows) == 1 else {}
    code, digest = selected.get('selected_code'), selected.get('selected_sha256')
    evaluation = selected.get('final_evaluation', {})
    outcomes = []
    for pin in spec['required_environments']:
        observed = reference.get('fingerprint', {})
        matched = (observed.get('git', {}).get('head') == pin['library_revision']
                   and protocol['environment']['toolchain'] == 'leanprover/lean4:'+pin['lean_version']
                   and reference['status'] == 'completed')
        valid = (matched and bool(code) and sha(code) == digest and selected.get('final_valid') is True
                 and evaluation.get('valid') is True
                 and evaluation.get('environments', {}).get(pin['environment_id'], {}).get('valid') is True)
        outcomes.append({**pin, 'status': 'passed' if valid else 'not_confirmed',
                         'candidate_sha256': digest, 'environment_matches_pin': matched,
                         'evidence': 'runs/'+protocol['condition_order'][0][0]+'/summary.json',
                         'evidence_field': 'final_evaluation'})
    passed = sum(row['status'] == 'passed' for row in outcomes)
    return {**spec, 'status': 'passed' if passed == len(outcomes) else 'not_confirmed',
            'passed_versions': passed, 'required_versions': len(outcomes), 'environments': outcomes}
