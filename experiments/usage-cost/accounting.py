"""Compatibility entry point; shared implementation lives in lean_agent.accounting."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lean_agent.accounting import *  # noqa: F401,F403
from lean_agent.accounting import main

if __name__ == "__main__":
    sys.exit(main())
