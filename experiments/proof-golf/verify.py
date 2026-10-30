"""Final check of one candidate on every environment in a problem folder.

Uses the common LeanEvaluator (check + three measured runs per version) and
reports the local problem score. A single failed version costs about 11.1
problem points, so run this before adopting any candidate.
"""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
from lean_agent.evaluator import lean as lean_module
from lean_agent.evaluator.lean import LeanEvaluator

# Same wrapper qualification as golf.py (Cslib CCS defines its own `Name`).
lean_module.WRAPPER = lean_module.WRAPPER.replace('(axioms.toList.map Name.toString)',
                                                  '(axioms.toList.map Lean.Name.toString)')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--problem-dir', type=Path, required=True)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True, help='New output folder')
    ap.add_argument('--t0', type=int, required=True, help='Original proof tokens')
    ap.add_argument('--h0', type=int, required=True, help='Original raw heartbeats')
    a = ap.parse_args()
    packet = a.problem_dir / 'input.json'
    if not packet.exists():
        packet = a.problem_dir / 'agent-input.json'
    problem = json.loads(packet.read_text())['problem']
    envs = json.loads((a.problem_dir / 'environment.json').read_text())['environments']
    # The evaluator creates the output folder and refuses an existing one.
    result = LeanEvaluator().evaluate(a.candidate.read_text(), problem, envs, a.output, 3)
    rows = {v: {'valid': e['valid'], 'hb_k': e.get('median_heartbeats'), 'error': (e.get('error') or {}).get('kind')}
            for v, e in result['environments'].items()}
    passed = sum(r['valid'] for r in rows.values())
    hb = [r['hb_k'] for r in rows.values() if r['valid'] and r['hb_k'] is not None]
    summary = {'valid': result['valid'], 'tokens': result['tokens'], 'versions': rows,
               'compat_pct': 100 * passed / len(rows)}
    if hb:
        # Local estimate: HB from the first passing version; not an official score.
        length = 100 * (1 - result['tokens'] / a.t0)
        heartbeat = 100 * (1 - hb[0] * 1000 / a.h0)
        summary['local_problem_score'] = round((length + heartbeat + summary['compat_pct']) / 3, 2)
    (a.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
