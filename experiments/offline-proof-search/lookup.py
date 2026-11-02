"""Read-only text search through the original target's import closure and prefix.

Hits are discovery leads, not a claim that a declaration is exported or compatible
with every pin. Final proof compilation establishes availability. Unresolved
imports are reported explicitly. The original target's file is prefix-only.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from search import load, digest, write


def header_imports(text):
    # Only the module header is relevant. Stop before code/string literals so
    # Lean raw strings and quoted syntax later in a file cannot look like imports.
    depth, names = 0, []
    for line in text.splitlines():
        clean, i = '', 0
        while i < len(line):
            if line[i:i+2] == '/-':
                depth += 1; i += 2
            elif depth and line[i:i+2] == '-/':
                depth -= 1; i += 2
            elif not depth and line[i:i+2] == '--':
                break
            else:
                if not depth:
                    clean += line[i]
                i += 1
        clean = clean.strip()
        if not clean or clean in ('module', 'prelude'):
            continue
        match = re.fullmatch(r'(?:(?:public|private)\s+)?(?:meta\s+)?import\s+(.+)', clean)
        if not match:
            break
        names.extend(n for n in match[1].split() if n != 'all' and re.fullmatch(r'[\w.]+', n))
    return names


def index(root):
    cfg, m, loaded = load(root)
    ecfg, lean, _, _, source, fp = loaded
    srcroot = Path(ecfg['source_root']).resolve()
    roots = [srcroot]
    roots += sorted(p.resolve() for p in (srcroot / '.lake/packages').glob('*') if p.is_dir())
    roots.append((lean.parent.parent / 'src/lean').resolve())
    target_path = Path(fp['source_path']).resolve()
    prefix = source[:source.index(m.META['src'])]
    found = [{'module': '<target-prefix>', 'path': str(target_path), 'prefix_only': True,
              'sha256': digest(prefix), 'text': prefix}]
    queue = header_imports(prefix); seen = set(); missing = []
    while queue:
        mod = queue.pop()
        if mod in seen:
            continue
        seen.add(mod)
        rel = Path(*mod.split('.')).with_suffix('.lean')
        p = next((base / rel for base in roots if (base / rel).is_file()), None)
        if p is None:
            missing.append(mod); continue
        p = p.resolve()
        if p == target_path:
            raise ValueError('Import closure reaches target module')
        text = p.read_text()
        found.append({'module': mod, 'path': str(p), 'prefix_only': False, 'sha256': digest(text), 'text': text})
        queue.extend(header_imports(text))
    return {'environment_identity': fp['identity_sha256'], 'roots': list(map(str, roots)),
            'missing_modules': sorted(missing), 'scope': 'textual transitive import discovery, not a Lean export checker',
            'files': found}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path); p.add_argument('pattern'); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--limit', type=int, default=40)
    a = p.parse_args(); data = index(a.root.resolve()); pattern = re.compile(a.pattern)
    hits = []
    for entry in data['files']:
        lines = entry['text'].splitlines()
        for i, line in enumerate(lines):
            if pattern.search(line):
                hits.append({'module': entry['module'], 'path': entry['path'], 'line': i + 1,
                             'context': '\n'.join(lines[max(0, i-2):i+7])})
        del entry['text']
    data['hits'] = hits; data['query'] = a.pattern; data['lookup_code_sha256'] = digest(Path(__file__).read_bytes())
    if a.output.exists():
        raise ValueError('Use a fresh output path')
    write(a.output, data)
    print(json.dumps({'files': len(data['files']), 'missing_modules': data['missing_modules'],
                      'hit_count': len(hits), 'hits': hits[:a.limit]}, ensure_ascii=False, indent=2))
