"""Zero-API fixture Controller: prepare, run, replay and inspect recursive repair."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from common import ARMS, HERE, REPO, REVISION, TACTICS, Limits, canonical, inventory, read, safe_path, sha, shared
from runtime import FixtureWorker, Runtime
from adapter import workflow
from lean_agent import models, openai_direct, preflight, status


def prepare(root, case, arm='recursive-repair-v1', environment=None, limits=None, simulated_budget='1'):
    root = Path(root).resolve()
    if root.exists():
        raise ValueError('Use a new run directory; never overwrite or resume')
    if arm not in ARMS:
        raise ValueError('Unknown condition')
    limits = limits or Limits()
    shared.money(simulated_budget)
    problem = case['problem']
    if set(problem) != {'name', 'statement', 'reference'}:
        raise ValueError('Expected fixed name/statement/reference')
    if environment is None:
        project = REPO/'examples/first-harness/project'
        template = '{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n' + case.get('context_source', '') + '\n{{DECLARATION}}\n'
        environment = {'id': 'fixed', 'project': str(project), 'toolchain': 'leanprover/lean4:v4.26.0',
                       'command': ['lean', '-j1', '-T20000'], 'timeout_seconds': limits.lean_seconds, 'template': template}
    environment = json.loads(canonical(environment))
    environment['command'] = preflight.resolve_command(environment['command'], environment['toolchain'], environment['project'])
    root.mkdir(parents=True)
    protocol = {'schema_version': 2, 'revision': REVISION, 'run_id': root.name, 'condition': arm,
                'integration': 'fixture_controller', 'backend': 'fixture', 'paid_execution_enabled': False,
                'actual_api_budget_usd': '0', 'problem': problem, 'context': case.get('context', {}),
                'environment': environment, 'environment_sha256': sha(canonical(environment)),
                'limits': asdict(limits), 'tactics': list(TACTICS), 'profile_enabled': False,
                'simulated_budget_usd': str(simulated_budget), 'simulated_reservation_usd': '0.02',
                'fixture_id': case.get('id', 'custom'), 'fixture_sha256': sha(canonical(case))}
    try:
        protocol['source_commit'] = subprocess.check_output(['git','rev-parse','HEAD'], cwd=REPO, text=True).strip()
        protocol['source_tree_dirty'] = bool(subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        protocol['source_commit'] = None
        protocol['source_tree_dirty'] = None
    shared.atomic(root/'protocol.json', protocol)
    shared.atomic(root/'fixture.json', case)
    # Preserve the existing repository layout for standalone archived replay.
    archive = root/'code/repo'
    shutil.copytree(REPO/'src/lean_agent', archive/'src/lean_agent', ignore=shutil.ignore_patterns('__pycache__'))
    for relative in ('experiments/verification-repair-policy', 'experiments/api-comparison'):
        dest = archive/relative
        dest.mkdir(parents=True)
        for path in (REPO/relative).iterdir():
            if path.suffix in ('.py', '.lean'):
                shutil.copy2(path, dest/path.name)
    shared.atomic(root/'frozen-inputs.json', inventory(root))
    return protocol


def check(root):
    root = Path(root).resolve()
    for relative, digest in read(root/'frozen-inputs.json').items():
        if sha(safe_path(root, relative).read_bytes()) != digest:
            raise ValueError('Frozen input/code changed: ' + relative)
    protocol = read(root/'protocol.json')
    if protocol['revision'] != REVISION or protocol['actual_api_budget_usd'] != '0' or protocol['paid_execution_enabled']:
        raise ValueError('Only this offline revision is executable')
    if protocol['environment_sha256'] != sha(canonical(protocol['environment'])):
        raise ValueError('Environment fingerprint changed')
    for path in (root/'code/repo').rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.lean'):
            active = REPO/path.relative_to(root/'code/repo')
            if not active.is_file() or sha(active.read_bytes()) != sha(path.read_bytes()):
                raise ValueError('Use the archived code to replay this run revision')
    return protocol


def replay(root, verify_inventory=True):
    root = Path(root).resolve()
    protocol = check(root)
    if verify_inventory and inventory(root) != read(root/'artifacts.json'):
        raise ValueError('Run artifacts changed or are missing')
    runtime = Runtime(root, protocol, replay=True)
    # This re-executes the policy/transformations against saved observations.
    # Tape does not invoke callbacks, so no compiler or worker can run.
    result = workflow(runtime)
    runtime.tape.assert_complete()
    saved = read(root/'result.json')
    saved_replay = saved.pop('replay', None)
    if result != saved:
        raise ValueError('Recomputed result differs from saved selection/costs')
    summary = {'record_replay_passed': True, 'model_called': False, 'lean_called': False,
               'operations': runtime.tape.index, 'final_valid': result['final_valid']}
    if saved_replay is not None and saved_replay != summary:
        raise ValueError('Saved replay claim differs from recomputation')
    return summary


def run(root):
    root = Path(root).resolve()
    protocol = check(root)
    if (root/'events.jsonl').exists():
        raise ValueError('Run already started; choose a new directory')
    runtime = Runtime(root, protocol, FixtureWorker(read(root/'fixture.json')))
    # Even an accidental use of the shared live adapters must fail locally.
    with patch.object(models, 'query', side_effect=AssertionError('No model API')), \
         patch.object(openai_direct, 'query', side_effect=AssertionError('No direct API')), \
         patch.object(shared, 'http', side_effect=AssertionError('No network metadata')):
        result = workflow(runtime)
    shared.atomic(root/'result.json', result)
    if result.get('selected_code'):
        (root/'selected.lean').write_text(result['selected_code'])
    result['replay'] = replay(root, verify_inventory=False)
    shared.atomic(root/'result.json', result)
    runtime.tape.journal.seal(result['status'])
    shared.atomic(root/'artifacts.json', inventory(root))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','check','run','replay','status'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--condition', choices=ARMS, default='recursive-repair-v1')
    parser.add_argument('--cases', type=Path, default=HERE/'fixtures/cases.json')
    parser.add_argument('--case', default='F04')
    parser.add_argument('--environment', type=Path)
    parser.add_argument('--simulated-budget-usd', default='1')
    args = parser.parse_args()
    if args.action == 'prepare':
        rows = read(args.cases)
        selected = next(row for row in rows if row['id'] == args.case)
        result = prepare(args.output, selected, args.condition,
                         read(args.environment) if args.environment else None,
                         simulated_budget=args.simulated_budget_usd)
    elif args.action == 'check':
        check(args.output)
        result = {'frozen_inputs_valid': True, 'lean_called': False, 'model_called': False}
    elif args.action == 'run':
        result = run(args.output)
    elif args.action == 'replay':
        result = replay(args.output)
    else:
        result = status.inspect(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
