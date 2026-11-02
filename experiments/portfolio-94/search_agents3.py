"""Resumable offline proof search using an audited full-source adapter.

The first adapter is P12's existing full_probe.py. No model/API calls are made.
Probe ranking is provisional; certify remeasures original, seed and selected proof.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
from mutations import variants

HERE = Path(__file__).resolve().parent
LEGACY = HERE.parent / 'first-harness-jwkweon'
sys.path.insert(0, str(LEGACY))
from evaluator.lean import execute as _execute
from resources import lease
def execute(*args, **kwargs):
    with lease():
        return _execute(*args, **kwargs)


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(p)


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


@contextmanager
def lock(root):
    with (root / 'search.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        if shutil.disk_usage(root).free < 1024**3:
            raise RuntimeError('Less than 1 GiB free')
        yield


def adapter(path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('full_source_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(root):
    cfg = read(root / 'config.json')
    for path, expected in cfg['code_hashes'].items():
        if digest(Path(path).read_bytes()) != expected:
            raise ValueError('Code changed; start a separate run: ' + path)
    m = adapter(Path(cfg['adapter']))
    env = m.load_environment(Path(cfg['environment']))
    if env[-1]['identity_sha256'] != cfg['environment_identity']:
        raise ValueError('Environment identity changed')
    if digest(m.META['src']) != cfg['original_sha256']:
        raise ValueError('Original changed')
    return cfg, m, env


def evaluate(root, code, label, runs=1):
    cfg, m, loaded = load(root)
    ecfg, lean, args, env, source, fingerprint = loaded
    folder = root / 'evaluations' / (label + '-' + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    (folder / 'candidate.lean').write_text(code)
    result = {'valid': False, 'code_sha256': digest(code), 'label': label,
              'tokens': None, 'raw': None, 'raw_samples': [], 'jobs': [],
              'environment_identity': fingerprint['identity_sha256'],
              'scope': 'primary-only full-source local evaluation', 'folder': str(folder)}
    write(folder / 'result.json', result)
    try:
        m.validate_declaration(code, m.STATEMENT)
        result['tokens'] = m.proof_tokens(code, m.STATEMENT)
        # A private launcher preserves the adapter's pinned package environment.
        write(folder / 'runtime.json', {'lean': str(lean), 'env': {
            'PATH': env.get('PATH', '/usr/bin:/bin'), 'HOME': str(root / 'home'),
            'TMPDIR': str(root / 'tmp'), 'LEAN_PATH': env['LEAN_PATH']}})
        launcher = folder / 'runner.py'
        launcher.write_text('import json,os,sys\nfrom pathlib import Path\n'
            'r=json.loads(Path(__file__).with_name("runtime.json").read_text())\n'
            'os.execve(r["lean"],[r["lean"],*sys.argv[1:]],r["env"])\n')
        def job(name, text, extra=()):
            p = folder / (name + '.lean'); p.write_text(text)
            cmd = [sys.executable, str(launcher), '-j1', '-M3072', '--root=' + str(folder), *args, *extra, str(p)]
            r = execute(cmd, folder, cfg['timeout_seconds'])
            log = r.pop('output'); (folder / (name + '.log')).write_text(log)
            result['jobs'].append({**r, 'name': name, 'source_sha256': digest(text), 'log_sha256': digest(log)})
            write(folder / 'result.json', result)
            if r['returncode'] or r['timed_out']:
                raise ValueError(name + ' failed: ' + log[-2500:])
            return log
        job('Check', m.plain_source(source, code), ['-o', str(folder / 'Check.olean')])
        rt = read(folder / 'runtime.json'); rt['env']['LEAN_PATH'] = str(folder) + os.pathsep + env['LEAN_PATH']
        write(folder / 'runtime.json', rt)
        audit = ('import Check\nimport Lean\nopen Lean Elab Command in\nrun_cmd do\n'
                 '  let ax ← Lean.collectAxioms `' + m.TARGET + '\n'
                 '  logInfo m!"OFFLINE_AXIOMS {toJson (ax.toList.map Name.toString)}"\n')
        logs = re.findall(r'OFFLINE_AXIOMS (\[[^\n]*\])', job('Audit', audit))
        if len(logs) != 1 or not set(json.loads(logs[0])) <= m.ALLOWED_AXIOMS:
            raise ValueError('Axiom audit failed')
        result['axioms'] = json.loads(logs[0])
        rt['env']['LEAN_PATH'] = env['LEAN_PATH']; write(folder / 'runtime.json', rt)
        for i in range(runs):
            nonce = uuid.uuid4().hex
            log = job(f'Measure{i + 1}', m.measured_source(source, code, nonce))
            matches = re.findall(getattr(m, 'RAW_MARKER', m.TARGET.split('.')[-1]) + r' ' + nonce + r' (\d+)', log)
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous fresh measurement')
            result['raw_samples'].append(int(matches[0]))
            result['jobs'][-1]['nonce'] = nonce
        if load(root)[2][-1]['identity_sha256'] != fingerprint['identity_sha256']:
            raise ValueError('Environment changed during evaluation')
        result['valid'] = True
        result['raw'] = statistics.median(result['raw_samples'])
    except ValueError as exc:
        result['error'] = str(exc)
    except BaseException as exc:
        result['interrupted'] = repr(exc)
        write(folder / 'result.json', result)
        raise
    write(folder / 'result.json', result)
    return result


def rank(row, baseline):
    return row['tokens'] * baseline['raw'] + row['raw'] * baseline['tokens']


def pareto(rows):
    return [r for r in rows if not any(
        q['tokens'] <= r['tokens'] and q['raw'] <= r['raw'] and
        (q['tokens'] < r['tokens'] or q['raw'] < r['raw']) for q in rows)]


def record(root, result, parent=None, operation=None):
    state = read(root / 'state.json')
    row = {**result, 'parent': parent, 'operation': operation}
    state['attempts'].append(row)
    valid = [r for r in state['attempts'] if r['valid']]
    state['best'] = min(valid, key=lambda r: (rank(r, state['baseline']), r['code_sha256']))
    state['pareto'] = [r['code_sha256'] for r in pareto(valid)]
    write(root / 'state.json', state)
    print(json.dumps({'label': result['label'], 'valid': result['valid'], 'tokens': result['tokens'],
          'raw': result['raw'], 'best_tokens': state['best']['tokens'], 'best_raw': state['best']['raw'],
          'operation': operation}, ensure_ascii=False), flush=True)


def init(args):
    root = args.root.resolve(); root.mkdir(parents=True, exist_ok=False)
    for name in ['home', 'tmp', 'snapshots']:
        (root / name).mkdir()
    ap = args.adapter.resolve(); m = adapter(ap)
    env = m.load_environment(args.environment.resolve())
    paths = [Path(__file__), HERE / 'mutations.py', LEGACY / 'evaluator/lean.py', ap, m.META_PATH, HERE / 'resources.py', *m.DEPENDENCIES]
    cfg = {'adapter': str(ap), 'environment': str(args.environment.resolve()),
           'environment_identity': env[-1]['identity_sha256'], 'timeout_seconds': args.timeout,
           'original_sha256': digest(m.META['src']), 'code_hashes': {str(p): digest(p.read_bytes()) for p in paths},
           'objective': 'min L/L0 + H/H0; no search-time penalty', 'candidate_limit': None, 'memory_limit_mib': 3072, 'max_concurrent_lean': 2}
    write(root / 'config.json', cfg)
    write(root / 'environment.json', env[-1])
    for i, p in enumerate(paths):
        shutil.copyfile(p, root / 'snapshots' / f'{i}-{p.name}')
    (root / 'original.lean').write_text(m.META['src'])
    (root / 'seed.lean').write_bytes(args.seed.read_bytes())
    # Legal local context only: original target and suffix excluded.
    (root / 'prefix.lean').write_text(env[-2][:env[-2].index(m.META['src'])])
    with lock(root):
        baseline = evaluate(root, m.META['src'], 'original', 3)
        if not baseline['valid']:
            raise ValueError('Original failed: ' + str(baseline.get('error')))
        write(root / 'state.json', {'baseline': baseline, 'attempts': [], 'expanded': []})
        record(root, baseline)
        record(root, evaluate(root, args.seed.read_text(), 'seed', 3))


def search(args):
    root = args.root.resolve()
    with lock(root):
        cfg, m, _ = load(root)
        for _ in range(args.steps):
            state = read(root / 'state.json')
            seen = {r['code_sha256'] for r in state['attempts']}
            parents = sorted([r for r in state['attempts'] if r['valid'] and r['label'] != 'original'
                              and r['code_sha256'] not in state['expanded']],
                             key=lambda r: (rank(r, state['baseline']), r['code_sha256']))
            choice = None
            for parent in parents:
                code = (Path(parent['folder']) / 'candidate.lean').read_text()
                options = [(op, c) for op, c in variants(code, m.STATEMENT) if digest(c) not in seen]
                if options:
                    choice = parent, options[0]; break
                state['expanded'].append(parent['code_sha256'])
            write(root / 'state.json', state)
            if choice is None:
                print('Current mutation neighborhood exhausted; add structural seeds or new operators.', flush=True)
                break
            parent, (op, code) = choice
            record(root, evaluate(root, code, f'probe-{len(state["attempts"]):04}'), parent['code_sha256'], op)


def submit(args):
    root = args.root.resolve()
    with lock(root):
        code = args.candidate.read_text()
        if digest(code) in {r['code_sha256'] for r in read(root / 'state.json')['attempts']}:
            raise ValueError('Source already measured; use certify for independent confirmation')
        record(root, evaluate(root, code, 'manual', args.runs), operation=args.note)


def certify(args):
    root = args.root.resolve()
    with lock(root):
        state = read(root / 'state.json')
        codes = {'original': (root / 'original.lean').read_text(), 'seed': (root / 'seed.lean').read_text(),
                 'selected': (Path(state['best']['folder']) / 'candidate.lean').read_text()}
        results = {name: evaluate(root, code, 'confirm-' + name, 3) for name, code in codes.items()}
        valid = all(r['valid'] for r in results.values())
        report = {'all_valid': valid, 'scope': 'primary-only; not official LB or all-pin certification',
                  'results': results, 'attempts': len(state['attempts']), 'valid_attempts': sum(r['valid'] for r in state['attempts'])}
        if valid:
            b = results['original']
            report['local_scores'] = {k: 100 - 100/3*(r['tokens']/b['tokens'] + r['raw']/b['raw']) for k,r in results.items()}
            winner = min(('seed', 'selected'), key=lambda k: rank(results[k], b))
            report['confirmed_choice'] = winner
            (root / 'confirmed.lean').write_text(codes[winner])
        write(root / ('confirmation-' + uuid.uuid4().hex[:10] + '.json'), report)
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    i = sub.add_parser('init'); i.add_argument('root', type=Path); i.add_argument('--adapter', type=Path, required=True)
    i.add_argument('--environment', type=Path, required=True); i.add_argument('--seed', type=Path, required=True)
    i.add_argument('--timeout', type=int, default=180)
    s = sub.add_parser('search'); s.add_argument('root', type=Path); s.add_argument('--steps', type=int, default=20)
    s = sub.add_parser('submit'); s.add_argument('root', type=Path); s.add_argument('candidate', type=Path)
    s.add_argument('--runs', type=int, default=1); s.add_argument('--note', default='structural candidate')
    s = sub.add_parser('certify'); s.add_argument('root', type=Path)
    s = sub.add_parser('lookup'); s.add_argument('root', type=Path); s.add_argument('pattern')
    args = p.parse_args()
    if args.action == 'lookup':
        # Show line numbers and context in the verified original prefix only.
        subprocess.run(['rg', '-n', '-C', '3', '--', args.pattern, str(args.root / 'prefix.lean')], check=False)
    else:
        globals()[args.action](args)
