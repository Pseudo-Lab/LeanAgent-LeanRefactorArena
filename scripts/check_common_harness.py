#!/usr/bin/env python3
"""Run the common harness and its experiment contracts without model/Lean calls.

Separate processes isolate historical experiment modules named worker/report/etc.
Frozen-dataset checks run when the separately distributed dataset is installed;
full environment inspection requires ARENA_FINAL_INTEGRATION=1 explicitly.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = (
    "test_harness.py", "test_actions.py", "test_portfolio.py", "test_budgeting.py", "test_repair_feedback.py",
    "test_autosolver.py", "test_autosolver_native.py",
    "test_runtime_integration.py", "test_api_integration.py", "test_prepared_cache.py",
    "test_accounting.py", "test_usage_*.py", "test_evaluation.py", "test_corpus_storage.py",
    "test_final_*.py",
)
EXPERIMENTS = (
    "api-comparison", "usage-cost", "final-batch-next",
)


def main():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    # macOS /var and /private/var aliases must not break path identity assertions.
    cache_root = os.environ.get("PROJECT_CACHE_DIR")
    if cache_root:
        Path(cache_root).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache_root) as directory:
        env["PROJECT_CACHE_DIR"] = env["TMPDIR"] = str(Path(directory).resolve())
        suites = [("tests", pattern) for pattern in CORE]
        suites += [("experiments/" + name, "test_*.py") for name in EXPERIMENTS]
        failed = []
        for folder, pattern in suites:
            print(f"\n== {folder}/{pattern} ==", flush=True)
            result = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "discover", "-s", folder,
                 "-p", pattern, "-v"], cwd=ROOT, env=env,
            )
            if result.returncode:
                failed.append(f"{folder}/{pattern}")
        if failed:
            print("Failed suites: " + ", ".join(failed), file=sys.stderr)
            return 1
    print("All common-harness suites passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
