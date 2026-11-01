"""Actual Lean four-run fixture suite and byte-exact offline replay; no paid calls."""
from dataclasses import asdict
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from common import HERE, REPO, Limits, read, shared
from generation import ORDER, prepare, process
from lean_agent import accounting, preflight, status
from test_generation import response


@unittest.skipUnless(os.environ.get('REPAIR_RUN_LEAN_TESTS') == '1', 'Opt-in actual Lean 4.26 check')
class GenerationLean(unittest.TestCase):
    def test_four_run_loop_recursive_repair_and_replay(self):
        evidence = os.environ.get('REPAIR_EVIDENCE_DIR')
        temp = None if evidence else tempfile.TemporaryDirectory()
        if temp:
            self.addCleanup(temp.cleanup)
        root = Path(evidence or temp.name)/'generation-suite'
        case = next(row for row in read(HERE/'fixtures/cases.json') if row['id'] == 'F04')
        project = REPO/'examples/first-harness/project'
        env = {'id': 'fixed', 'project': str(project), 'toolchain': 'leanprover/lean4:v4.26.0',
               'command': preflight.resolve_command(['lean', '-j1', '-T20000'], 'leanprover/lean4:v4.26.0', project),
               'timeout_seconds': 10, 'template': '{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n{{DECLARATION}}\n'}
        rows = {}
        for name, arm in ORDER:
            rows[name] = [response('planner'), response('root', case['candidate'])]
            if arm == 'recursive-repair-v1':
                rows[name].append(response('repair', case['responses'][0]['proof']))
            rows[name].append(response('root', case['candidate']))
        fixture = {'problem': case['problem'], 'environment': env, 'limits': asdict(Limits()),
                   'controller': {'max_steps': 2}, 'responses': rows}
        prepare(root, fixture=fixture)
        script = root/'code/repo/experiments/verification-repair-policy/generation.py'
        log = root.parent/'generation-suite.command.log'
        with log.open('w') as stream:
            completed = subprocess.run([sys.executable, str(script), 'run', '--output', str(root)],
                                       stdout=stream, stderr=subprocess.STDOUT)
        self.assertEqual(completed.returncode, 0, log.read_text()[-5000:])
        summary = read(root/'summary.json')
        self.assertEqual(summary['actual_api_calls'], 0)
        self.assertEqual(summary['actual_api_cost_usd'], '0')
        self.assertEqual(summary['arms']['recursive-repair-v1']['verified_repairs'], 2)
        self.assertEqual(summary['arms']['planner-worker-v1']['repair_entries'], 0)
        first = []
        for run_id, arm in ORDER:
            result = read(root/'runs'/run_id/'result.json')
            view = status.inspect(root/'runs'/run_id)
            self.assertEqual(view['status'], 'completed')
            self.assertTrue(view['sealed'])
            self.assertEqual(view['final_result']['sha256'], result['selected_sha256'])
            self.assertEqual(view['usage_cost']['actual_api_cost_usd'], '0')
            self.assertTrue(result['replay']['record_replay_passed'])
            self.assertTrue(result['attempts'][1]['duplicate'])
            self.assertTrue(result['final_valid'])
            requests = [read(p)['input']['packet'] for p in sorted((root/'runs'/run_id/'tape').glob('*-request.json'))
                        if read(p)['kind'] == 'worker' and read(p)['input']['packet']['role'] == 'root']
            first.append({k: v for k, v in requests[0].items() if k != 'call_id'})
        self.assertTrue(all(row == first[0] for row in first))
        costs = accounting.native_report(root)
        self.assertEqual(costs, read(root/'usage-cost.json'))
        self.assertEqual(costs['summary']['actual_api_calls'], 0)
        self.assertEqual(costs['summary']['entries'], 14)
        with patch('subprocess.Popen', side_effect=AssertionError('Replay tried a subprocess')), \
             patch('generation_transport.OpenAITransport.__call__', side_effect=AssertionError('Replay tried direct API')), \
             patch('openrouter_transport.OpenRouterTransport.__call__', side_effect=AssertionError('Replay tried OpenRouter')):
            self.assertEqual(process(root, replay=True), summary)
        shared.atomic(root.parent/'generation-suite.replay.json', {'record_replay_passed': True, 'actual_api_calls': 0})


if __name__ == '__main__':
    unittest.main()
