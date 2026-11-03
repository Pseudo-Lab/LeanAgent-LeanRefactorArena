"""Normalize omitted empty logs for leantar 0.1.16's trace reader.

Only use on unsealed preparation caches. Compiler outputs are untouched.
"""
import hashlib
import json
from pathlib import Path

HASH_CHECKER = '''import Lake.Build.Trace
def main (args : List String) : IO UInt32 := do
  let rows ← IO.FS.lines args.head!
  let mut bad := 0
  for row in rows do
    let fields := row.splitOn "\\t"
    let path := fields[0]!
    let expected := fields[1]!
    try
      let actual ← Lake.computeFileHash path
      if actual.toString != expected then
        bad := bad + 1
        IO.println s!"BAD\\t{path}\\t{expected}\\t{actual}"
    catch _ =>
      bad := bad + 1
      IO.println s!"BAD\\t{path}\\t{expected}\\tmissing"
  IO.println s!"CHECKED\\t{rows.size}\\tBAD\\t{bad}"
  return 0
'''


def trace_outputs(build_roots):
    records = []
    for root in map(Path, build_roots):
        library = root / 'lib/lean'
        for trace in sorted(library.rglob('*.trace')):
            try:
                data = json.loads(trace.read_bytes())
            except (ValueError, UnicodeDecodeError):
                continue
            outputs = data.get('outputs') if isinstance(data, dict) else None
            if not isinstance(outputs, dict) or not isinstance(outputs.get('o'), list):
                continue
            relative = trace.relative_to(library).with_suffix('')
            for key, descriptors in outputs.items():
                if key not in {'o', 'i', 'r', 'c', 'b'}:
                    continue
                for descriptor in descriptors if isinstance(descriptors, list) else [descriptors]:
                    expected, extension = descriptor.split('.', 1)
                    if len(expected) != 16 or not all(c in '0123456789abcdef' for c in expected):
                        raise ValueError('Invalid Lake output hash')
                    parent = root / 'ir' if key in {'c', 'b'} else library
                    output = parent / (str(relative) + '.' + extension)
                    records.append({'trace': str(trace), 'path': str(output), 'expected': expected})
    return records


def invalidate_bad_traces(records, bad_paths, backup_root):
    invalidated = []
    for trace in sorted({r['trace'] for r in records if r['path'] in bad_paths}):
        path = Path(trace)
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        backup = Path(backup_root) / (digest + '.json')
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(original)
        path.unlink()  # Generated metadata only; the official cache restores the outputs.
        invalidated.append({'path': trace, 'before_sha256': digest})
    return invalidated


def normalize_cache_traces(build_roots, backup_root):
    records = []
    for root in build_roots:
        root = Path(root)
        for path in sorted(root.rglob('*.trace')):
            original = path.read_bytes()
            try:
                data = json.loads(original)
            except (ValueError, UnicodeDecodeError):
                continue
            if (not isinstance(data, dict) or data.get('schemaVersion') != '2025-09-10'
                    or 'log' in data):
                continue
            before = hashlib.sha256(original).hexdigest()
            backup = Path(backup_root) / (before + '.json')
            backup.parent.mkdir(parents=True, exist_ok=True)
            if backup.exists() and backup.read_bytes() != original:
                raise ValueError('Trace backup identity differs')
            if not backup.exists():
                backup.write_bytes(original)
            data['log'] = []
            normalized = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
            path.write_bytes(normalized)
            records.append({'path': str(path), 'before_sha256': before,
                            'after_sha256': hashlib.sha256(normalized).hexdigest()})
    return records
