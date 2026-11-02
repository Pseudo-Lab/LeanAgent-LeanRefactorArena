#!/usr/bin/env python3
"""Install one official pinned compiler with resumable, verified downloads.

Admission is based on the asset size and inspected unpacked size, retaining an
8 GiB reserve. The original full-environment installer's guard is unchanged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "experiments/final-environment"))
import toolchains
from bootstrap import write

ACCOUNT = "/Users/jwkweon/00_work/00_project/.git-accounts/account.py"
GIB = 1024 ** 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    lock = json.loads((REPO / "configs/final-environments.lock.json").read_text())
    if args.version not in lock["toolchain_versions"]:
        raise ValueError("Compiler version is not in the fixed Final lock")
    version = args.version
    name = f"lean-{version[1:]}-darwin_aarch64.tar.zst"
    query = f'.assets[] | select(.name == "{name}") | {{name,size,digest,browser_download_url}}'
    asset = json.loads(subprocess.check_output([
        "/usr/bin/python3", ACCOUNT, "gh", "--", "api", f"repos/leanprover/lean4/releases/tags/{version}",
        "--jq", query], text=True))
    expected_url = f"https://github.com/leanprover/lean4/releases/download/{version}/{name}"
    if asset["browser_download_url"] != expected_url or not asset["digest"].startswith("sha256:"):
        raise ValueError("Official asset identity/digest missing")
    expected = asset["digest"].split(":", 1)[1]
    size = asset["size"]
    cache = Path(os.environ["PROJECT_STORAGE_ROOT"]) / "cache/_shared/lean-releases"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / name
    prefix = cache / (name + ".partial")
    dest = Path(os.environ["PROJECT_ENV_DIR"]) / "toolchains" / version
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() and not dest.exists():
        if shutil.disk_usage(REPO).free < 2 * size + 8 * GIB:
            raise RuntimeError("Insufficient space for download/staging plus 8 GiB reserve")
        start = prefix.stat().st_size if prefix.exists() else 0
        if not 0 <= start < size:
            raise ValueError("Unexpected partial download length")
        pieces = cache / (version + "-pieces")
        pieces.mkdir(exist_ok=True)
        ranges = [(a, min(size - 1, a + 16 * 1024**2 - 1))
                  for a in range(start, size, 16 * 1024**2)]

        def download(bounds):
            a, b = bounds
            path = pieces / f"{a}-{b}.part"
            if path.exists() and path.stat().st_size == b - a + 1:
                return path
            path.unlink(missing_ok=True)
            command = ["/usr/bin/curl", "--fail", "--location", "--silent", "--show-error",
                       "--range", f"{a}-{b}", "--max-filesize", str(b - a + 1),
                       "--connect-timeout", "15", "--max-time", "180", "--speed-time", "20",
                       "--speed-limit", "10240", "--retry", "2", "--retry-delay", "1",
                       "--output", str(path), "--write-out", "%{http_code}", expected_url]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode or result.stdout != "206" or path.stat().st_size != b - a + 1:
                raise RuntimeError("Release chunk failed: " + result.stderr[-400:])
            return path

        completed = start
        with ThreadPoolExecutor(max_workers=6) as pool:
            for future in as_completed([pool.submit(download, bounds) for bounds in ranges]):
                completed += future.result().stat().st_size
                print("DOWNLOADED", version, completed, "/", size, flush=True)
        with archive.open("wb") as output:
            if prefix.exists():
                with prefix.open("rb") as source:
                    shutil.copyfileobj(source, output)
            for a, b in ranges:
                with (pieces / f"{a}-{b}.part").open("rb") as source:
                    shutil.copyfileobj(source, output)
        if archive.stat().st_size != size or toolchains.file_sha(archive) != expected:
            raise ValueError("Official release SHA256 mismatch")
        shutil.rmtree(pieces)
        prefix.unlink(missing_ok=True)
    if not dest.exists():
        if toolchains.file_sha(archive) != expected:
            raise ValueError("Cached release SHA256 mismatch")
        # Inspect the actual tar members instead of assuming a fixed compiler size.
        process = subprocess.Popen([shutil.which("zstd"), "-q", "-d", "-c", str(archive)], stdout=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as stream:
                expanded = sum(entry.size for entry in stream if entry.isfile())
            while process.stdout.read(1024 * 1024):
                pass
            if process.wait():
                raise RuntimeError("Compiler size inspection failed")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
            process.wait()
        required = int(expanded * 1.10) + 8 * GIB
        if shutil.disk_usage(REPO).free < required:
            raise RuntimeError(f"Need {required/GIB:.2f} GiB before unpacking; verified archive retained")
        print("UNPACK", version, "logical_bytes", expanded, flush=True)
        toolchains.extract(archive, name.removesuffix(".tar.zst"), dest)
        archive.unlink()
    actual = subprocess.check_output([str(dest / "bin/lean"), "--version"], text=True).strip()
    if not actual.startswith("Lean (version " + version[1:] + ",") or not (dest / "lib/lean/libLean.a").is_file():
        raise ValueError("Installed compiler is incomplete or has wrong version")
    compat = REPO / "sources/final/toolchains" / version
    if not compat.exists():
        compat.symlink_to(dest, target_is_directory=True)
    receipt_path = REPO / "sources/final/toolchains.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {"schema_version": 1, "toolchains": {}}
    receipt["toolchains"][version] = {
        "version": version, "path": str(compat.relative_to(REPO)), "actual_version": actual,
        "lean_sha256": toolchains.file_sha(dest / "bin/lean"), "lake_sha256": toolchains.file_sha(dest / "bin/lake"),
        "provenance": {"kind": "official-release-archive", "url": expected_url,
                       "archive_sha256": expected, "archive_bytes": size}}
    write(receipt_path, receipt)
    print("COMPILER_READY", actual, flush=True)


if __name__ == "__main__":
    main()
