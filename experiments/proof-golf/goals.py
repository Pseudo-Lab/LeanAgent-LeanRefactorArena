"""Print the goal state before each tactic of a candidate (one check compile).

Block-wise rewriting needs the exact goals at block boundaries. `trace_state`
is inserted before every logical tactic and the messages are matched back.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golf import Golf, assemble, parse
from lean_agent.evaluator.lean import execute, render


def trace(golf, code):
    tactics = parse(code, golf.statement)
    traced = []
    for k, (ind, text) in enumerate(tactics):
        m = re.match(r'([·.]\s+)', text)
        # A bullet focuses a goal: trace inside it, after the bullet marker.
        if m:
            traced += [(ind, m[1] + f'trace "@@{k}"'), (ind + 2, 'trace_state'), (ind + 2, text[len(m[1]):])]
        else:
            traced += [(ind, f'trace "@@{k}"'), (ind, 'trace_state'), (ind, text)]
    env = golf.envs[0]
    folder = golf.out / 'goals' / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    path = folder / 'check.lean'
    path.write_text(render(env['template'], assemble(golf.statement, traced), golf.name, None))
    r = execute([*env['command'], '--root=' + str(folder.resolve()), str(path.resolve())],
                Path(env['project']), env['timeout_seconds'])
    (folder / 'check.log').write_text(r['output'])
    return tactics, r['output']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--problem-dir', type=Path, required=True)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    golf = Golf(a.problem_dir.resolve(), a.output.resolve(), 1)
    tactics, log = trace(golf, a.candidate.read_text())
    # Messages may carry a `file:line:col: info:` prefix depending on the Lean driver.
    chunks = re.split(r'^(?:.*?info: )?@@(\d+)\s*$', log, flags=re.M)
    states = {int(chunks[i]): chunks[i + 1] for i in range(1, len(chunks) - 1, 2)}
    for k, (ind, text) in enumerate(tactics):
        goal = states.get(k, '(not reached)')
        goal = goal.strip()
        print(f'===== [{k}] before: {text}\n{goal}\n')
    errors = re.findall(r'error: [^\n]*', log)
    if errors:
        print('ERRORS:', json.dumps(errors[:3], ensure_ascii=False))


if __name__ == '__main__':
    main()
