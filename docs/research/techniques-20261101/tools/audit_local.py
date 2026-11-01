"""Read-only Git/content audit of local research files against a pinned main.

No fetching, compiler execution, model calls, or source writes. The output is a
new snapshot, not a claim that matching file names prove semantic integration.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--ref', default='origin/main')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    def git(*parts, check=True):
        return subprocess.run(['git', '-C', str(root), *parts], capture_output=True,
                              check=check).stdout
    def tree(ref):
        result = {}
        for entry in git('ls-tree', '-rz', ref).split(b'\0'):
            if not entry:
                continue
            metadata, path = entry.split(b'\t', 1)
            mode, kind, oid = metadata.split()
            if kind == b'blob':
                result[path.decode()] = oid.decode()
        return result
    main_sha = git('rev-parse', args.ref).decode().strip()
    main_files = tree(main_sha)
    refs = git('for-each-ref', '--format=%(refname:short) %(objectname)',
               'refs/heads', 'refs/remotes/origin').decode().splitlines()
    branches = {line.rsplit(' ', 1)[0]: line.rsplit(' ', 1)[1] for line in refs}
    unique_trees = {}
    for sha in set(branches.values()):
        unique_trees[sha] = tree(sha)
    paths = set(git('ls-files', '--modified', '--others', '--exclude-standard', '-z').decode().split('\0'))
    groups = defaultdict(Counter)
    files = []
    for name in sorted(paths):
        if not name or not (name.startswith(('experiments/', 'src/', 'tests/', 'docs/'))
                            or name in ('.gitignore', 'README.md', 'runs/README.md')):
            continue
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        status = ('identical_to_main' if main_files.get(name) == oid else
                  'different_from_main' if name in main_files else 'absent_from_main')
        matching = [ref for ref, sha in branches.items()
                    if unique_trees[sha].get(name) == oid]
        group = '/'.join(Path(name).parts[:2]) if name.startswith('experiments/') else str(Path(name).parent)
        groups[group][status] += 1
        row = {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
               'git_blob': oid, 'main_blob': main_files.get(name), 'main_status': status,
               'exact_path_and_content_on_refs': matching}
        if name in main_files:
            row['main_last_path_commit'] = git('log', '-1', '--format=%H', main_sha, '--', name).decode().strip()
        files.append(row)
    historical = []
    for old in ('7d624d3', '03036e5', '2f7e0c6', '5339cd8', '89b133a', '762c912', 'cbc56b6', '76483ac'):
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', old + '^{commit}'],
                                capture_output=True, text=True)
        row = {'historical_document_commit': old, 'object_exists': result.returncode == 0}
        if result.returncode == 0:
            sha = result.stdout.strip()
            row['sha'] = sha
            row['ancestor_of_main'] = subprocess.run(
                ['git', '-C', str(root), 'merge-base', '--is-ancestor', sha, main_sha]).returncode == 0
            row['containing_refs'] = git('for-each-ref', '--contains', sha,
                                         '--format=%(refname:short)').decode().splitlines()
        historical.append(row)
    harness = git('show', main_sha + ':src/lean_agent/harness.py').decode()
    evaluator = git('show', main_sha + ':src/lean_agent/evaluator/lean.py').decode()
    value = {
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_checkout': root.name,
        'source_head': git('rev-parse', 'HEAD').decode().strip(),
        'main_ref': args.ref, 'main_sha': main_sha,
        'branch_heads': branches, 'groups': {g: dict(c) for g, c in sorted(groups.items())},
        'counts': dict(Counter(r['main_status'] for r in files)), 'files': files,
        'historical_commit_checks': historical,
        'specific_main_checks': {
            'harness_exposes_stat_cache': 'choices=["full", "stat-cache"]' in harness
                and 'verification=args.verification' in harness,
            'common_wrapper_uses_qualified_Lean_Name': 'Lean.Name.toString' in evaluator,
        },
        'limits': ['Exact path/blob equality is byte-level evidence, not a semantic-equivalence proof.',
                   'A file in an experiment is not automatically in the default harness.',
                   'Untracked raw runs and credentials are excluded; curated run evidence is audited separately.',
                   'Branch presence and merger status are separate; snapshot does not update itself.'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'main_sha': main_sha, 'files': len(files), 'counts': value['counts'],
                      'specific_main_checks': value['specific_main_checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
