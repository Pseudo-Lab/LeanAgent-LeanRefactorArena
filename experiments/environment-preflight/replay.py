"""Offline replay using only a run's saved code and artifacts, including feedback."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def replay(root):
    root = Path(root).resolve()
    # Invoke the archived implementation in a fresh process: no Git cache,
    # environment setup, Lean compiler or model client is needed for replay.
    child = subprocess.run([sys.executable, "-B", str(root / "code/replay.py"),
                            "--archived", str(root)], capture_output=True, text=True)
    if child.returncode:
        raise ValueError(child.stderr.strip() or child.stdout.strip())
    return json.loads(child.stdout)


def archived(root):
    import baseline
    import diagnostics
    from lean_agent import harness

    expected = json.loads((root / "artifacts.json").read_bytes())
    actual = {str(p.relative_to(root)): baseline.sha(p.read_bytes()) for p in root.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and p != root / "artifacts.json"}
    if actual != expected:
        raise ValueError("Experiment artifact inventory/hash differs")
    for name in ("replay.py", "diagnostics.py", "baseline.py", "preflight.py"):
        if Path(__file__).with_name(name).read_bytes() != (root / "code" / name).read_bytes():
            raise ValueError("Replay must use archived experiment code")
    return diagnostics.replay(harness, root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archived", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(archived(args.run_directory.resolve()) if args.archived else replay(args.run_directory)))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
