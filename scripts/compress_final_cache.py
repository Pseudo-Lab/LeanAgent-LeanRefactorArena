#!/usr/bin/env python3
"""Apply transparent filesystem compression while preserving every cache byte."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import time
import uuid

CACHE = Path(os.environ["PROJECT_CACHE_DIR"])
ALLOWED = [CACHE, Path(os.environ["PROJECT_ENV_DIR"]) / "toolchains",
           Path("/Users/jwkweon/00_work/00_project/cache/05_pseudolab/LeanAgent-LeanRefactorArena")]


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path.relative_to(root))] = ["link", os.readlink(path)]
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            result[str(path.relative_to(root))] = ["file", stat.S_IMODE(path.stat().st_mode), digest.hexdigest()]
    return result


def allocated(root):
    return sum(p.lstat().st_blocks * 512 for p in root.rglob("*") if not p.is_symlink())


def compress(root):
    root = root.resolve()
    if not any(root.is_relative_to(p.resolve()) for p in ALLOWED):
        raise ValueError("Cache path is outside the allowed project roots")
    if (root / ".git").exists():
        raise ValueError("Source repositories are not cache targets")
    before = inventory(root)
    old_bytes = allocated(root)
    staging = CACHE / "compression-staging" / uuid.uuid4().hex
    backup = CACHE / "compression-backups" / staging.name
    staging.parent.mkdir(parents=True, exist_ok=True)
    backup.parent.mkdir(parents=True, exist_ok=True)
    print("COMPRESS", root, "allocated", old_bytes, flush=True)
    process = subprocess.Popen(["/usr/bin/ditto", "--hfsCompression", str(root), str(staging)],
                               start_new_session=True)
    try:
        while process.poll() is None:
            if shutil.disk_usage(CACHE).free < 3 * 1024**3:
                raise RuntimeError("Compression staging reached the 3 GiB disk reserve")
            time.sleep(1)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait()
    if process.returncode or inventory(staging) != before:
        raise ValueError("Compression copy failed verification; original retained")
    new_bytes = allocated(staging)
    if new_bytes >= old_bytes:
        shutil.rmtree(staging)
        return {"path": str(root), "files": len(before), "saved_bytes": 0, "changed": False}
    root.rename(backup)
    try:
        staging.rename(root)
        if inventory(root) != before:
            raise ValueError("Installed compressed cache failed verification")
    except BaseException:
        if root.exists():
            root.rename(staging)
        backup.rename(root)
        raise
    shutil.rmtree(backup)
    result = {"path": str(root), "files": len(before), "old_allocated_bytes": old_bytes,
              "new_allocated_bytes": new_bytes, "saved_bytes": old_bytes - new_bytes,
              "changed": True, "contents_and_modes_verified": True}
    print("SAVED", result["saved_bytes"], flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, action="append", required=True)
    parser.add_argument("--compiler-lock", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipts = []
    with args.compiler_lock.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            for path in args.path:
                if not path.is_dir():
                    raise ValueError("Cache directory missing: " + str(path))
                receipts.append(compress(path))
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                args.receipt.write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + "\n")
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
