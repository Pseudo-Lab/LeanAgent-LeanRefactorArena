"""Prepare/run/replay a zero-API-cost repair-policy fixture experiment."""
import argparse
from decimal import Decimal
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'src'))
from lean_agent import models, preflight, status
from lean_agent.artifacts import canonical, inventory, read, sha, write
from lean_agent.evaluator.lean import LeanEvaluator
import adapter
import policy
import prompts


def money(value):
    amount = Decimal(value)
    if not amount.is_finite() or amount <= 0:
        raise ValueError('Simulated budget must be positive and finite')
    return amount


def prepare(root, selected_policy, responses, max_calls=None, simulated_budget='1', input_root=None, pid='SMOKE'):
    root = Path(root).resolve()
    if root.exists():
        raise ValueError('Choose a new output directory')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', pid):
        raise ValueError('Problem ID must be a single directory name')
    if selected_policy not in policy.POLICIES:
        raise ValueError('Unknown policy')
    fixtures = read(Path(responses))
    if not isinstance(fixtures, list) or not fixtures or not all(isinstance(r, dict) for r in fixtures):
        raise ValueError('Fixtures must be a nonempty list of raw response envelopes')
    max_calls = len(fixtures) if max_calls is None else max_calls
    if type(max_calls) is not int or not 1 <= max_calls <= len(fixtures):
        raise ValueError('max_calls must fit the supplied fixture responses')
    cap = money(simulated_budget)
    source_prompt = REPO / 'experiments/prompt-design/p01-p05-reasoning-prompts.v4.en.json'
    common, _ = prompts.build(source_prompt)
    # Temporary inputs let the existing preparation path freeze exactly the
    # sanitized packet. Top-level strategy/instructions never reach the model.
    with tempfile.TemporaryDirectory(prefix='repair-inputs-') as temporary:
        staging = Path(temporary)
        source = staging / pid
        source.mkdir()
        if input_root is None:
            example = REPO / 'examples/first-harness'
            p = read(example / 'problem.json')
            packet = {'problem': {'name': p['name'], 'statement': p['statement'], 'original': p['reference']},
                      'context': {}}
            env = {'environments': [{'id': 'fixed', 'name': 'fixed',
                    'toolchain': 'leanprover/lean4:v4.26.0',
                    'command': ['lean', '-j1', '-M1024', '-T20000'],
                    'timeout_seconds': 30, 'project': str(example / 'project'),
                    'template': (example / 'context.lean.in').read_text()}]}
            dropped = []
        else:
            source_dir = Path(input_root).resolve() / pid
            supplied = read(source_dir / 'agent-input.json')
            if set(supplied['problem']) != {'name', 'statement', 'original'} or not isinstance(supplied['context'], dict):
                raise ValueError('Expected name/statement/original and an audited context object')
            if (source_dir / 'original.lean').read_text().strip() != supplied['problem']['original'].strip():
                raise ValueError('Original differs from packet')
            packet = {key: supplied[key] for key in ('problem', 'context')}
            dropped = sorted(set(supplied) - set(packet))
            env = read(source_dir / 'environment.json')
        if len(env.get('environments', [])) != 1:
            raise ValueError('v1 checks one pinned Lean environment')
        e = env['environments'][0]
        if not Path(e['project']).is_absolute():
            raise ValueError('Prepared Lean project must be an absolute path')
        e['toolchain'] = e.get('toolchain') or (Path(e['project']) / 'lean-toolchain').read_text().strip()
        e['command'] = preflight.resolve_command(e['command'], e['toolchain'], e['project'])
        packet['strategy_prompt'] = ''  # required by the original packet loader
        write(source / 'agent-input.json', packet)
        write(source / 'environment.json', env)
        (source / 'original.lean').write_text(packet['problem']['original'])
        draft = {'version': prompts.VERSION, 'language': 'en', 'common_prompt': common,
                 'case_prompts': {pid: ''}}
        draft_path = staging / 'prompt.json'
        write(draft_path, draft)
        runner = adapter.load_runner()
        runner.ROOT, runner.SOURCE, runner.PROMPT_PATH = root, staging, draft_path
        runner.PROBLEMS, runner.CAP, runner.TOTAL_CAP = [pid], cap, cap
        runner.prepare(instructions_builder=prompts.instructions)
    prompts.write_assets(root, source_prompt)
    write(root / 'fixture-responses.json', fixtures)
    shutil.copy2(REPO / 'experiments/openrouter-budget-trial/fixtures/openrouter-endpoints.json', root / 'fixture-endpoints.json')
    protocol = read(root / 'protocol.json')
    protocol.update(backend='fixture', model='fixture-v1', cost_basis='simulated_fixture',
                    actual_api_budget_usd='0', repair_policy=selected_policy,
                    policy_revision=policy.REVISION, classifier_revision=policy.CLASSIFIER_REVISION,
                    max_calls_safety_fuse=max_calls, profile_policy='disabled_for_fixture_checks',
                    packet_layout='sorted', run_id=root.name, path_normalization_root=str(root),
                    dropped_packet_fields=dropped, common_prompt_version=prompts.VERSION,
                    prompt_manifest_sha256=sha((root / 'prompt-manifest.json').read_bytes()),
                    price_scope='historical fixture for testing reservation arithmetic, not current API prices',
                    paid_execution_enabled=False)
    try:
        protocol['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        protocol['source_commit'] = None
    runner.save(root / 'protocol.json', protocol)
    # Preserve executable replay code, including its normal repository layout.
    archive = root / 'code/repo'
    shutil.copytree(REPO / 'src/lean_agent', archive / 'src/lean_agent', ignore=shutil.ignore_patterns('__pycache__'))
    for relative in ('experiments/verification-repair-policy', 'experiments/openrouter-budget-trial',
                     'experiments/api-comparison'):
        dest = archive / relative
        dest.mkdir(parents=True)
        for file in (REPO / relative).glob('*.py'):
            shutil.copy2(file, dest / file.name)
    frozen = {str(path.relative_to(root)): sha(path.read_bytes()) for path in root.rglob('*')
              if path.is_file() and path.name != 'budget.json'}
    write(root / 'frozen-inputs.json', frozen)
    return protocol


def check(root):
    root = Path(root).resolve()
    for relative, digest in read(root / 'frozen-inputs.json').items():
        p = root / relative
        if p.is_symlink() or not p.resolve().is_relative_to(root) or sha(p.read_bytes()) != digest:
            raise ValueError('Frozen input or code changed: ' + relative)
    protocol = read(root / 'protocol.json')
    if protocol['backend'] != 'fixture' or protocol['paid_execution_enabled'] or protocol['actual_api_budget_usd'] != '0':
        raise ValueError('This command supports fixture transport only')
    adapter.verify_code(root)
    return protocol


def run(root):
    root = Path(root).resolve()
    protocol = check(root)
    pid = protocol['order'][0]
    folder = root / pid
    if (folder / 'events.jsonl').exists():
        raise ValueError('Run already started; use a new directory, never resume')
    runner = adapter.load_runner()
    runner.ROOT = root
    runner.PROBLEMS = [pid]
    runner.CAP = Decimal(protocol['per_problem_usd'])
    runner.TOTAL_CAP = Decimal(protocol['total_usd'])
    runner.PACKET_LAYOUT = 'sorted'
    experiment = adapter.Experiment(runner, root, protocol)
    env = read(folder / 'environment.json')['environments'][0]
    experiment.progress.enter('preflight')
    report = preflight.check(env, folder / 'preflight', LeanEvaluator())
    experiment.progress.finish('passed' if report['status'] == 'passed' else 'failed',
                               paths=['preflight/preflight.json'])
    if report['status'] != 'passed':
        result = {'status': 'failed', 'stop_reason': 'preflight', 'actual_api_calls': 0,
                  'actual_api_cost_usd': '0', 'preflight': report}
        runner.save(folder / 'result.json', result)
        experiment.progress.journal.seal('failed')
        write(folder / 'artifacts.json', inventory(folder))
        write(root / 'artifacts.json', inventory(root))
        return result
    # An accidental network call is a test failure, including metadata requests.
    from unittest.mock import patch
    with patch.object(models, 'query', side_effect=AssertionError('No model API in fixture experiment')), \
         patch.object(runner.openai_direct, 'query', side_effect=AssertionError('No direct API in fixture experiment')), \
         patch.object(runner.transport, 'http', side_effect=AssertionError('No network metadata in fixture experiment')):
        with runner.run_lock():
            result = runner.run_problem(pid, experiment=experiment)
    result['replay'] = adapter.replay(root, verify_inventory=False)
    runner.save(folder / 'summary.json', result)
    runner.save(folder / 'result.json', result)
    experiment.progress.journal.seal(result['status'])
    write(folder / 'artifacts.json', inventory(folder))
    write(root / 'artifacts.json', inventory(root))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'check', 'run', 'replay', 'status'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--policy', choices=policy.POLICIES, default=policy.POLICIES[0])
    parser.add_argument('--responses', type=Path, default=HERE / 'fixtures/responses.json')
    parser.add_argument('--max-calls', type=int)
    parser.add_argument('--simulated-budget-usd', default='1')
    parser.add_argument('--input-root', type=Path)
    parser.add_argument('--problem', default='SMOKE')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.output, args.policy, args.responses, args.max_calls,
                         args.simulated_budget_usd, args.input_root, args.problem)
    elif args.action == 'check':
        check(args.output)
        result = {'frozen_inputs_valid': True, 'model_called': False, 'lean_called': False}
    elif args.action == 'run':
        result = run(args.output)
    elif args.action == 'replay':
        result = adapter.replay(args.output)
    else:
        protocol = read(args.output / 'protocol.json')
        result = status.inspect(args.output / protocol['order'][0])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
