"""Screen hand- or model-written block rewrites of a base candidate.

Each trial is {"label", "edits": [[old, new], ...]} applied to the base text;
every old string must occur exactly once. Results use the golf screening path
(one measured compile) and report J = T + H/r in token units.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golf import Golf


def apply(base, edits):
    for old, new in edits:
        if base.count(old) != 1:
            raise ValueError('Edit target must occur once: ' + old)
        base = base.replace(old, new)
    return base


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--problem-dir', type=Path, required=True)
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--trials', type=Path, required=True, help='JSON list of trials')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--h0', type=int, required=True)
    ap.add_argument('--t0', type=int, required=True)
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    golf = Golf(a.problem_dir.resolve(), out, a.workers)
    golf.load()
    rate = a.h0 / a.t0
    base = a.base.read_text()
    rows = []
    for trial in [{'label': 'base', 'edits': []}] + json.loads(a.trials.read_text()):
        try:
            code = apply(base, trial['edits'])
            rows.append((trial['label'], code, golf.tokens(code), None))
        except ValueError as exc:
            rows.append((trial['label'], None, None, str(exc)))
    with ThreadPoolExecutor(a.workers) as pool:
        results = list(pool.map(lambda r: golf.screen(r[1]) if r[1] else None, rows))
    with (out / 'trial-log.jsonl').open('a') as log:
        for (label, code, t, err), res in zip(rows, results):
            j = t + res['hb'] / rate if res and res['valid'] else None
            row = {'label': label, 'T': t, 'hb_k': res['hb'] // 1000 if res and res['valid'] else None,
                   'J': round(j, 2) if j else None, 'error': err or (res and res['error']),
                   'dir': res and res['dir']}
            log.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
