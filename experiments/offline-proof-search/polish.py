"""A resumable greedy argument-only pass; complements broader search, not replaces it."""
import argparse
from pathlib import Path
from search import load, read, lock, variants, digest, evaluate, record


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('root', type=Path)
    p.add_argument('--steps', type=int, default=6); a = p.parse_args(); root = a.root.resolve()
    with lock(root):
        _, m, _ = load(root)
        for _ in range(a.steps):
            state = read(root / 'state.json'); parent = state['best']
            code = (Path(parent['folder']) / 'candidate.lean').read_text()
            seen = {r['code_sha256'] for r in state['attempts']}
            options = [(op,c) for op,c in variants(code,m.STATEMENT)
                       if op.startswith('argument:') and digest(c) not in seen]
            if not options:
                print('Current best argument neighborhood exhausted.', flush=True); break
            op, candidate = options[0]
            record(root, evaluate(root,candidate,f'argument-{len(state["attempts"]):04}'),parent['code_sha256'],op)
