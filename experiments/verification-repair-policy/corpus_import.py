"""Fetch pinned historical observations and freeze all nonpassing P01-P03 candidates."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

from common import HERE, REPO, canonical, read, sha, shared

SOURCE_REPO = 'Pseudo-Lab/LeanAgent'
SOURCE_COMMIT = 'e302e89eadf2c7eb2b65f0035f7dbba0b8e09130'
RUN = '20261024T000653+0900'
SOURCE_PATH = 'docs/research/verification-repair/손지연/experiment(week4)/evidence/experiment/runs/' + RUN + '/runs/P_A'
TREES = {1: '171e30036a9d51419e3eb03804469e5587fc26d6',
         2: '167c17baabcf947369e657e7edb288228f066f57',
         3: 'e85c46a8fac0e2db677622f43cad87e02d916c1a'}
STRATA = '451e5f047bafa010d178856db76c00029bfa4d7f'
FILES = {1: 'Strata/Transform/CallElimCorrect.lean', 2: 'Strata/Transform/CallElimCorrect.lean',
         3: 'Strata/Languages/Core/StatementSemanticsProps.lean'}


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def fetch(root):
    """GitHub source download only. No model, credentials file or paid endpoint."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for number, tree in TREES.items():
        data = json.loads(subprocess.check_output(['gh', 'api', f'repos/{SOURCE_REPO}/git/trees/{tree}?recursive=1']))
        if data.get('truncated'):
            raise ValueError('Incomplete source tree')
        for row in data['tree']:
            if row['type'] == 'blob' and any(row['path'].endswith('/'+name) for name in ('config.json','candidate.json','result.json')):
                rows.append({'problem': number, **row})
    def download(row):
        relative = Path(f'P{row["problem"]}')/row['path']
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe source path')
        path = root/relative
        if not path.exists():
            encoded = subprocess.check_output(['gh','api',f'repos/{SOURCE_REPO}/git/blobs/{row["sha"]}','--jq','.content'])
            data = base64.b64decode(encoded)
            if git_blob(data) != row['sha']:
                raise ValueError('Downloaded blob hash mismatch')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if git_blob(path.read_bytes()) != row['sha']:
            raise ValueError('Source blob changed: '+str(relative))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, rows))
    shared.atomic(root/'inventory.json', rows)


def freeze(root):
    root = Path(root)
    inventory = read(root/'inventory.json')
    indexed = {}
    for row in inventory:
        relative = f'P{row["problem"]}/'+row['path']
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Unsafe source path')
        data = (root/relative).read_bytes()
        if git_blob(data) != row['sha']:
            raise ValueError('Source blob changed: '+relative)
        indexed[relative] = {'git_blob': row['sha'], 'sha256': sha(data)}
    problems, histories, cases, seen = {}, [], [], {}
    for number in TREES:
        pid = f'P{number:02}'
        packet = read(REPO/f'experiments/problem-inputs/{pid}/agent-input.json')['problem']
        for condition in ('A0','A1','A2','A3'):
            for repeat in (1,2,3):
                relative = f'P{number}/normal/{condition}/repeat_{repeat}'
                cfg = read(root/relative/'config.json')
                terminal = read(root/relative/'result.json')
                assert cfg['family'] == 'P_A' and cfg['problem'] == number
                assert cfg['condition'] == condition and cfg['repeat'] == repeat
                original = cfg['prefix'] + cfg['original_body'] + cfg['suffix']
                marker = packet['statement']+' := '
                assert cfg['prefix'].endswith(marker)
                assert packet['original'].rstrip('\n') == marker+cfg['original_body']
                problem = {'problem': {'name': packet['name'], 'statement': packet['statement'], 'reference': packet['original']},
                           'source_file': FILES[number], 'source_sha256': sha(original)}
                if pid in problems and problems[pid] != problem:
                    raise ValueError('Original problem/context differs between histories')
                problems[pid] = problem
                history_id = f'{pid}-{condition}-r{repeat}'
                history = {'id': history_id, 'source_path': relative,
                           'config': indexed[relative+'/config.json'], 'terminal': indexed[relative+'/result.json'], 'candidates': []}
                prior = [cfg['original_candidate']]
                paths = sorted((root/relative/'candidates').glob('*/candidate.json'))
                if len(paths) != terminal['generated_count']:
                    raise ValueError('Missing historical candidates')
                for path in paths:
                    record = read(path)
                    if sha(record['body']) != record['proof_sha256'] or sha(cfg['prefix']+record['body']+cfg['suffix']) != record['full_source_sha256']:
                        raise ValueError('Historical proof/source hash mismatch')
                    source = {'path': str(path.relative_to(root)), **indexed[str(path.relative_to(root))]}
                    history['candidates'].append({'call': record['call'], 'historical_status': record['verification']['status'],
                                                  'eligible': record['eligible'], 'proof_sha256': record['proof_sha256'], 'source': source})
                    if not record['eligible']:
                        best = min((c for c in prior if c['eligible']), key=lambda c: (
                            -c['measurement']['search_score'], c['measurement']['proof_tokens'],
                            c['measurement']['raw_heartbeats'], c['proof_sha256']))
                        cid = history_id+f'-c{record["call"]:02}'
                        code = marker+record['body']
                        key = sha(canonical([pid, problem['source_sha256'], code.replace('\r\n','\n')]))
                        cases.append({'id': cid, 'problem_id': pid, 'history_id': history_id,
                                      'call': record['call'], 'source': source, 'code': code, 'code_sha256': sha(code),
                                      'historical_status': record['verification']['status'], 'duplicate_of': seen.get(key),
                                      'best_before': {'code': marker+best['body'], 'source_call': best['call'],
                                                      'proof_sha256': best['proof_sha256']}})
                        seen.setdefault(key, cid)
                    prior.append(record)
                histories.append(history)
    return {'schema_version': 1, 'dataset_kind': 'historical_generated_failures',
            'source': {'repository': SOURCE_REPO, 'commit': SOURCE_COMMIT, 'path': SOURCE_PATH,
                       'subtrees': {f'P{n}':v for n,v in TREES.items()}, 'run': RUN},
            'selection': 'All noneligible generated candidates in all A0-A3 x repeats 1-3 histories for P01-P03; no V_A/V_B damage fixtures.',
            'environment': {'repository': 'strata-org/Strata', 'commit': STRATA, 'toolchain': 'leanprover/lean4:v4.26.0'},
            'problems': problems, 'histories': histories, 'cases': cases,
            'counts': {'histories': len(histories), 'generated': sum(len(h['candidates']) for h in histories),
                       'nonpassing': len(cases), 'unique_nonpassing': sum(c['duplicate_of'] is None for c in cases)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['fetch','freeze'])
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'fetch':
        fetch(args.source_root)
    else:
        if args.output is None or args.output.exists():
            parser.error('freeze requires a new --output')
        data = freeze(args.source_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shared.atomic(args.output, data)
        print(json.dumps(data['counts']))


if __name__ == '__main__':
    main()
