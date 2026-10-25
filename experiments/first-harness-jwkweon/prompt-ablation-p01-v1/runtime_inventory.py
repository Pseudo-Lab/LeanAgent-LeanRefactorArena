"""Hash shared compiler/library bytes once before and after the whole cohort."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


def main(base, phase):
    lock = json.loads((base / 'calibration-1/input/environment.lock.json').read_text())
    started = time.monotonic()
    files = {}
    for label, directory in lock['runtime_roots'].items():
        root = Path(directory)
        assert root.is_dir(), root
        for path in sorted(root.rglob('*')):
            if path.is_file():
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                files[f'{label}/{path.relative_to(root)}'] = digest.hexdigest()
    combined = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    if phase == 'after':
        before = json.loads((base / 'runtime-inventory.before.json').read_text())
        assert files == before['files_sha256'], 'Shared runtime artifacts changed during experiment'
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'phase': phase,
              'seconds': time.monotonic() - started, 'file_count': len(files),
              'artifacts_sha256': combined, 'matches_historical_lock': combined == lock['artifacts_sha256'],
              'files_sha256': files}
    with (base / f'runtime-inventory.{phase}.json').open('x') as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write('\n')
    assert result['matches_historical_lock'], 'Shared runtime differs from original frozen baseline environment'
    print(json.dumps({k: v for k, v in result.items() if k != 'files_sha256'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('phase', choices=['before', 'after'])
    args = parser.parse_args()
    main(args.cohort.resolve(), args.phase)
