"""The frozen warm-up experiment input must match the published snapshot (no Lean, no network).

Kept apart from test_warmup_validator.py, which warmup-verification.yml runs before every
build: a stale experiment pin should fail here, not block ordinary verification jobs.
"""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts import verify_warmup_pins as verifier

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / 'experiments/warmup/2026-10-26/candidates.json'


class FrozenExperimentPinTests(unittest.TestCase):
    def test_workflow_experiment_input_loads_against_current_snapshot(self):
        # warmup-verification.yml passes this file when experiment=true; a startingSnapshotSha256
        # that no longer matches dashboard/public/data/warmup-team-results.json makes every
        # verify/verify-selected matrix job fail before any build.
        groups = verifier.load_experiment(EXPERIMENT)
        self.assertTrue(groups)


if __name__ == '__main__':
    unittest.main()
