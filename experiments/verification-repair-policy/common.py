"""Experiment constants and shared repository facilities; no network calls."""
from dataclasses import asdict, dataclass
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'src'))
from lean_agent.artifacts import canonical, inventory, read, sha, write

# Reservation, settlement and durable writes are the existing implementation.
spec = importlib.util.spec_from_file_location('repair_shared_budget', REPO / 'experiments/api-comparison/compare.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)

ARMS = ('planner-worker-v1', 'auto-solver-v1', 'recursive-repair-v1')
TACTICS = ('rfl', 'assumption', 'trivial', 'simp', 'omega', 'grind')
REVISION = 'recursive-repair-1'


class Stop(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Limits:
    depth: int = 2
    nodes: int = 8
    node_calls: int = 2
    repair_calls: int = 6
    run_calls: int = 32
    lean_calls: int = 64
    lean_seconds: float = 10
    memory_mib: int = 2048
    repair_seconds: float = 120
    run_seconds: float = 600

    def __post_init__(self):
        import math
        for k, v in asdict(self).items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                raise ValueError('Invalid positive limit: ' + k)
            if k not in ('lean_seconds', 'repair_seconds', 'run_seconds') and type(v) is not int:
                raise ValueError('Expected integer limit: ' + k)


def safe_path(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Artifact path escapes run directory')
    return path
