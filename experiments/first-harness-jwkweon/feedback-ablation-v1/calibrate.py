"""Fresh original readiness; compile true imports prefix without deleting a used theorem."""
import json
from pathlib import Path
import resource
import sys
import time

r = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(r / 'code'))
from evaluator.lean import LeanEvaluator, execute

e = {'id': 'fixed', 'project': str(r / 'project'),
     'template': (r / 'input/context.lean.in').read_text(),
     'toolchain': 'leanprover/lean4:v4.26.0',
     'command': [sys.executable, str(r / 'lean_runner.py'), '-j1', '-M4096', '-T200000'],
     'timeout_seconds': 420}
p = json.loads((r / 'input/problem.json').read_text())
v = LeanEvaluator()
before = v.fingerprint(e)
source = r / 'imports-only.lean'
source.write_text(e['template'].split('{{HARNESS_COMMANDS}}', 1)[0].replace('{{HARNESS_IMPORT}}', ''))
cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
i = execute([*e['command'], str(source)], r / 'project', 420)
after_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
i.update(child_user_cpu_seconds=after_cpu.ru_utime-cpu.ru_utime,
         child_system_cpu_seconds=after_cpu.ru_stime-cpu.ru_stime)
(r / 'imports-only.log').write_text(i.pop('output'))
(r / 'imports-only-result.json').write_text(json.dumps(i, indent=2) + '\n')
result = v.evaluate(p['reference'], p, [e], r / 'original', 3)
(r / 'original/result.json').write_text(json.dumps(result, indent=2) + '\n')
summary = {'timeout_seconds': 420, 'valid': i['returncode'] == 0 and not i['timed_out'] and result['valid'],
           'original_valid': result['valid'], 'environment_unchanged': before == v.fingerprint(e),
           'environment': before, 'imports': i}
with (r / 'summary.json').open('x') as stream:
    json.dump(summary, stream, indent=2)
    stream.write('\n')
print(json.dumps({k: summary[k] for k in ['valid', 'original_valid', 'environment_unchanged']}))
if not summary['valid'] or not summary['environment_unchanged']:
    raise SystemExit(1)
