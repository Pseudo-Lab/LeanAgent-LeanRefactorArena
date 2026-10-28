"""Materialize and import the hash-locked main harness without changing this branch."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def artifact_hashes(root):
    """Inventory an experiment, including nested harness manifests but not itself."""
    return {str(p.relative_to(root)): sha(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts
            and p != root / "artifacts.json"}


def prepare(cache=None):
    lock = json.loads((HERE / "baseline.lock.json").read_bytes())
    if sha((HERE / lock["design"]["path"]).read_bytes()) != lock["design"]["sha256"]:
        raise ValueError("Experiment design differs from baseline.lock.json")
    source = lock["sources"]["main"]
    root = cache or os.environ.get("PROJECT_CACHE_DIR")
    if not root:
        raise ValueError("Set PROJECT_CACHE_DIR using the project's env/use.sh")
    target = Path(root).resolve() / "environment-preflight-baseline" / source["revision"]
    for relative, expected in source["files"].items():
        path = target / relative
        if not path.resolve().is_relative_to(target) or path.is_symlink():
            raise ValueError("Invalid baseline cache path")
        if not path.exists():
            data = subprocess.check_output(["git", "show", source["revision"] + ":" + relative], cwd=REPO)
            if sha(data) != expected["sha256"]:
                raise ValueError("Pinned Git source mismatch: " + relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("xb") as stream:
                    stream.write(data)
            except FileExistsError:
                pass  # Another reader may have materialized the same pinned file.
        if sha(path.read_bytes()) != expected["sha256"]:
            raise ValueError("Baseline cache changed: " + relative)
    return target


def load(cache=None):
    root = prepare(cache)
    existing = sys.modules.get("lean_agent")
    if existing and Path(existing.__file__).resolve() != root / "src/lean_agent/__init__.py":
        raise ValueError("A different lean_agent package is already imported; use a fresh process")
    sys.path.insert(0, str(root / "src"))
    try:
        harness = importlib.import_module("lean_agent.harness")
        evaluator = importlib.import_module("lean_agent.evaluator.lean")
    finally:
        sys.path.pop(0)
    return harness, evaluator, root
