"""Local-only P02 readiness checks; never imports or invokes a model transport."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

from common import HERE, REPO, Limits, canonical, inventory, read, sha, shared
from corpus import make_environment
from native import NativeLean
from lean_agent import harness, prepared
from lean_agent.evaluator.lean import LeanEvaluator, execute


def p02_limits():
    return Limits(lean_seconds=60, repair_seconds=600, run_seconds=1800, run_calls=100)


def calibrate(root, project, lean):
    root, project = Path(root).resolve(), Path(project).resolve()
    if root.exists():
        raise ValueError('Use a new calibration directory')
    corpus = read(HERE/'evaluation/corpus.json')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=project, text=True).strip()
    if revision != corpus['environment']['commit'] or subprocess.check_output(['git','diff','HEAD','--','.'], cwd=project):
        raise ValueError('Expected clean pinned Strata revision')
    item = corpus['problems']['P02']
    limits = p02_limits()
    env = make_environment(item, project, lean, limits)
    root.mkdir()
    prepared.freeze(env['lean_path'].split(__import__('os').pathsep), revision, root/'libraries.json', verification='stat-cache')
    libraries = prepared.PreparedLeanEvaluator(root/'libraries.json')
    def invoke(command, cwd, timeout):
        libraries.verify(full=False)
        return execute(command, cwd, timeout, lean_path=env['lean_path'])
    native = NativeLean(env, item['problem'], root/'native', invoke=invoke)
    fingerprint = LeanEvaluator(executor=invoke).fingerprint(env)
    evaluations = []
    for i in range(3):
        value = native.evaluate(item['problem']['reference'], f'original-{i+1}', limits.lean_seconds, limits.memory_mib)
        evaluations.append(value)
        shared.atomic(root/f'original-{i+1}.json', value)
        print('original', i+1, 'valid', value['valid'], flush=True)
        if not value['valid']:
            break
    observation = native.inspect(item['problem']['reference'], 'original-native', limits.lean_seconds, limits.memory_mib)
    shared.atomic(root/'observation.json', observation)
    times = [run['seconds'] for value in evaluations for row in value['environments'].values() for run in row['runs']]
    times.append(observation['seconds'])
    metrics = [harness.metrics(value) for value in evaluations if value['valid']]
    stable = bool(metrics) and max(m['raw_heartbeats'] for m in metrics) <= min(m['raw_heartbeats'] for m in metrics)*1.01
    ready = (len(metrics) == 3 and stable and max(times) <= limits.lean_seconds/2
             and observation['kind'] == 'proof' and not observation['errors'])
    result = {'revision': 'p02-readiness-1', 'ready': ready, 'problem_id': 'P02', 'problem': item['problem'],
              'environment': env, 'fingerprint': fingerprint, 'limits': asdict(limits),
              'rounds': len(evaluations), 'metrics': metrics, 'max_process_seconds': max(times),
              'time_headroom_factor': limits.lean_seconds/max(times), 'stable_within_one_percent': stable,
              'final_verification_reserve_seconds': 8*limits.lean_seconds,
              'baseline': evaluations[0], 'actual_api_calls': 0, 'actual_api_cost_usd': '0',
              'measurement_sources': {str(p.relative_to(REPO)): sha(p.read_bytes()) for p in
                  [HERE/'native.py', HERE/'Support.lean', REPO/'src/lean_agent/evaluator/lean.py']}}
    libraries.verify()
    shared.atomic(root/'result.json', result)
    shared.atomic(root/'artifacts.json', inventory(root))
    print(json.dumps({k: result[k] for k in ('ready','rounds','max_process_seconds','time_headroom_factor','metrics')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--lean', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    calibrate(args.output, args.project, args.lean)
