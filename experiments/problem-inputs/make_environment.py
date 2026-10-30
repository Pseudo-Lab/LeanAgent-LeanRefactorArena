"""Build a machine-local environment.json for a committed problem packet.

Packets (agent-input.json, original.lean) are portable; Lean paths are not.
The template is the pinned upstream source with the official declaration
replaced, built the same way as experiments/api-comparison/compare.py.
Run once per required Lean version; --append adds versions to the same output.
"""
import argparse
import json
from pathlib import Path
import shutil

SANDBOX = ['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*) (deny file-write*)']


def template(source, declaration):
    if source.count(declaration) != 1:
        raise ValueError('Official declaration must occur exactly once; check the source revision')
    lines = source.replace(declaration, '{{DECLARATION}}', 1).splitlines(keepends=True)
    last_import = max(i for i, line in enumerate(lines) if line.startswith('import '))
    lines.insert(last_import + 1, '{{HARNESS_COMMANDS}}\n')
    return '{{HARNESS_IMPORT}}\n' + ''.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--packet', type=Path, required=True, help='experiments/problem-inputs/PXX')
    ap.add_argument('--source', type=Path, required=True, help='Upstream file at the pinned revision')
    ap.add_argument('--project', type=Path, required=True, help='Built project directory with lean-toolchain')
    ap.add_argument('--lean', required=True, help='Lean binary of this version')
    ap.add_argument('--lean-path', required=True, help='LEAN_PATH: project build lib dirs and toolchain lib/lean')
    ap.add_argument('--version', required=True, help='Environment id, e.g. v4.26.0')
    ap.add_argument('--revision', default='', help='Pinned upstream commit, recorded only')
    ap.add_argument('--sandbox', choices=['none', 'macos'], default='none')
    ap.add_argument('--timeout', type=int, default=90)
    ap.add_argument('--output', type=Path, required=True, help='Local packet copy for run.py --input-root / golf.py')
    ap.add_argument('--append', action='store_true', help='Add this version to an existing output')
    a = ap.parse_args()
    packet = json.loads((a.packet / 'agent-input.json').read_text())
    declaration = packet['problem']['original'].rstrip('\n')
    if not (a.project / 'lean-toolchain').is_file():
        raise FileNotFoundError('Project must contain lean-toolchain: ' + str(a.project))
    env = {'id': a.version, 'project': str(a.project.resolve()),
           'toolchain': (a.project / 'lean-toolchain').read_text().strip(),
           'command': (SANDBOX if a.sandbox == 'macos' else []) +
                      ['/usr/bin/env', 'LEAN_PATH=' + a.lean_path, a.lean, '-j1', '-M2048', '-T200000'],
           'timeout_seconds': a.timeout, 'sourceRevision': a.revision,
           'template': template(a.source.read_text(), declaration)}
    path = a.output / 'environment.json'
    if a.append:
        data = json.loads(path.read_text())
        data['environments'] = [e for e in data['environments'] if e['id'] != a.version] + [env]
    else:
        if path.exists():
            raise FileExistsError('Output already has environment.json; use --append for another version')
        a.output.mkdir(parents=True, exist_ok=True)
        for name in ('agent-input.json', 'original.lean'):
            shutil.copy2(a.packet / name, a.output / name)
        data = {'environments': [env], 'lead': ''}
    data['required_versions'] = [e['id'] for e in data['environments']]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(path, [e['id'] for e in data['environments']])


if __name__ == '__main__':
    main()
