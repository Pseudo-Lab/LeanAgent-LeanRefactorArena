"""Read-only Git comparison for the upstream files copied into a new pilot."""
import hashlib
import os
from pathlib import Path
import subprocess

UPSTREAM_DIRECTORIES = ('src', 'examples/actions', 'experiments/final-batch-next',
                        'experiments/proof-analyze')


def _git(repo, *args):
    try:
        return subprocess.run(['git', '--no-replace-objects', '-C', str(repo), *args],
                              check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError('Cannot verify pinned baseline from local Git; use a pinned checkout with the baseline object available') from exc


def verify_baseline_snapshot(repo, baseline, *, source_root=None):
    """Match every copied upstream file to Git, including untracked additions.

    __pycache__ entries are excluded exactly as in the snapshot copy operation.
    Symlinks and special files fail closed. Git is only read; no checkout/reset,
    index update, network request or source modification is performed.
    """
    repo = Path(repo)
    source = Path(source_root) if source_root is not None else repo
    object_format = _git(repo, 'rev-parse', '--show-object-format').decode().strip()
    expected = {}
    tree = _git(repo, 'ls-tree', '-r', '-z', baseline, '--', *UPSTREAM_DIRECTORIES)
    for entry in tree.split(b'\0'):
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        mode, kind, object_id = metadata.decode().split()
        relative = raw_path.decode()
        if '__pycache__' in Path(relative).parts:
            continue
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('Pinned upstream snapshot requires regular files: ' + relative)
        expected[relative] = object_id
    if not expected or any(not any(p.startswith(directory + '/') for p in expected)
                           for directory in UPSTREAM_DIRECTORIES):
        raise ValueError('Pinned baseline lacks the required upstream inventory')
    actual = {}
    for directory in UPSTREAM_DIRECTORIES:
        start = source / directory
        if start.is_symlink() or not start.is_dir():
            raise ValueError('Use a pinned checkout: missing or symlinked upstream directory ' + directory)
        for parent, directories, names in os.walk(start, followlinks=False):
            directories[:] = [name for name in directories if name != '__pycache__']
            for name in directories:
                if (Path(parent) / name).is_symlink():
                    raise ValueError('Use a pinned checkout: upstream symlink directory')
            for name in names:
                if name == '__pycache__':
                    continue
                path = Path(parent) / name
                relative = str(path.relative_to(source))
                if path.is_symlink() or not path.is_file():
                    raise ValueError('Use a pinned checkout: upstream file is not regular: ' + relative)
                actual[relative] = path
    if set(actual) != set(expected):
        extra, missing = sorted(set(actual)-set(expected)), sorted(set(expected)-set(actual))
        raise ValueError('Use a pinned checkout: upstream inventory differs from baseline; '
                         f'extra={extra[:5]}, missing={missing[:5]}')
    files = {}
    for relative, path in sorted(actual.items()):
        content = path.read_bytes()
        git_blob = b'blob ' + str(len(content)).encode() + b'\0' + content
        if hashlib.new(object_format, git_blob).hexdigest() != expected[relative]:
            raise ValueError('Use a pinned checkout: upstream content differs from baseline: ' + relative)
        files[relative] = hashlib.sha256(content).hexdigest()
    return {'baseline_commit': baseline, 'verified_against_local_git': True,
            'directories': list(UPSTREAM_DIRECTORIES), 'file_count': len(files),
            'files_sha256': files, 'excluded_entries': ['__pycache__']}
