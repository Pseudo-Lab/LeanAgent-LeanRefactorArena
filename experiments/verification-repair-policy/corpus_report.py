"""Derive review tables and a portable evidence archive from a sealed corpus run."""
import argparse
import gzip
import json
from pathlib import Path
import tarfile

from common import inventory, read, sha

ROW_FIELDS = (
    'id', 'problem_id', 'historical_status', 'duplicate_of',
    'reproduced_failure', 'native_extracted', 'recovered', 'reason',
    'improves_historical_best', 'historical_best_valid', 'historical_best_q',
    'selected_origin', 'final_valid', 'actual_api_calls', 'actual_api_cost_usd',
    'lean_calls', 'repair_lean_calls', 'elapsed_seconds', 'no_repair',
)


def export(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.is_relative_to(root):
        raise ValueError('Derived output must be outside the sealed run')
    if inventory(root) != read(root / 'artifacts.json'):
        raise ValueError('Sealed run inventory changed')
    paths = sorted(root.rglob('*'))
    if any(path.is_symlink() for path in paths):
        raise ValueError('Evidence must not contain symlinks')
    out.mkdir(parents=True, exist_ok=True)
    summary = read(root / 'summary.json')
    protocol = read(root / 'protocol.json')
    corpus = read(root / 'corpus.json')
    rows = []
    for case in corpus['cases']:
        result_path = root / 'cases' / case['id'] / 'result.json'
        result = read(result_path)
        row = {key: result.get(key) for key in ROW_FIELDS}
        row['selected_q'] = (2 if result['selected_origin'] == 'original' and result['final_valid']
                             else result['final_q'])
        row['final_measured_q'] = result['final_q']
        row['repaired_q'] = result.get('repaired_q')
        repair = result['repair'] or {}
        row['repair_status'] = repair.get('status')
        row['node_depths'] = [node['depth'] for node in repair.get('nodes', [])]
        row['result_sha256'] = sha(result_path.read_bytes())
        rows.append(row)
    for name, value in [('summary.json', summary), ('protocol.json', protocol), ('rows.json', rows)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive_path = out / 'evidence.tar.gz'
    with archive_path.open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode='w') as archive:
                for path in paths:
                    if not path.is_file() or '__pycache__' in path.parts:
                        continue
                    info = archive.gettarinfo(str(path), arcname='run/' + str(path.relative_to(root)))
                    info.uid = info.gid = 0
                    info.uname = info.gname = ''
                    info.mtime = 0
                    with path.open('rb') as stream:
                        archive.addfile(info, stream)
    return {'rows': len(rows), 'evidence_bytes': archive_path.stat().st_size,
            'evidence_sha256': sha(archive_path.read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.run, args.output), indent=2))


if __name__ == '__main__':
    main()
