"""Observe civil/monotonic clock gaps and hold an experiment-scoped idle assertion.

Create COHORT/observer.stop to stop; no persistent power settings are changed.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

root = Path(sys.argv[1]).resolve()
assertion = None
start_error = None
try:
    binary = shutil.which('caffeinate')
    if binary:
        assertion = subprocess.Popen([binary, '-i', '-t', '21600'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except OSError as error:
    start_error = str(error)

try:
    with (root / 'host-clock-observations.jsonl').open('a', buffering=1) as stream:
        stream.write(json.dumps({'event': 'started', 'utc': datetime.now(timezone.utc).isoformat(),
                                 'observer_pid': __import__('os').getpid(),
                                 'idle_assertion_pid': assertion.pid if assertion else None,
                                 'start_error': start_error}) + '\n')
        before = None
        while not (root / 'observer.stop').exists():
            sample = {'event': 'sample', 'unix_seconds': time.time(),
                      'monotonic_seconds': time.monotonic()}
            if before:
                sample['civil_interval_seconds'] = sample['unix_seconds'] - before['unix_seconds']
                sample['monotonic_interval_seconds'] = sample['monotonic_seconds'] - before['monotonic_seconds']
                sample['civil_minus_monotonic_interval'] = sample['civil_interval_seconds'] - sample['monotonic_interval_seconds']
            if assertion:
                sample['idle_assertion_returncode'] = assertion.poll()
            stream.write(json.dumps(sample) + '\n')
            before = sample
            time.sleep(30)
        stream.write(json.dumps({'event': 'stopped', 'utc': datetime.now(timezone.utc).isoformat()}) + '\n')
finally:
    if assertion and assertion.poll() is None:
        assertion.terminate()
        assertion.wait(timeout=10)
