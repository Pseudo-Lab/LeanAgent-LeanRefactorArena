"""Materialize exact compiler versions locally; reuse matching installed binaries."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

from bootstrap import REPO, ROOT, plan, write, command


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(archive, prefix, dest):
    """Extract one verified compiler subtree, rejecting paths outside that root."""
    stage = Path(tempfile.mkdtemp(prefix=".toolchain-stage-", dir=dest.parent))
    process = subprocess.Popen([shutil.which("zstd"), "-q", "-d", "-c", str(archive)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as tf:
            for member in tf:
                name = member.name.rstrip("/")
                if name == prefix:
                    continue
                if not name.startswith(prefix + "/"):
                    raise ValueError("Compiler archive contains an unexpected path")
                rel = name[len(prefix) + 1:]
                if ".." in PurePosixPath(rel).parts or PurePosixPath(rel).is_absolute():
                    raise ValueError("Unsafe archive member")
                entry = copy.copy(member)
                entry.name = rel
                tf.extract(entry, path=stage, filter="data")
        while process.stdout.read(1024 * 1024):
            pass
        if process.wait():
            raise ValueError("Toolchain decompression failed")
        if not (stage / "bin/lean").is_file():
            raise ValueError("Archive has no Lean executable")
        stage.rename(dest)
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
        process.wait()
        if stage.exists():
            shutil.rmtree(stage)


def download_release(version, destination):
    name = "lean-" + version[1:] + "-darwin_aarch64.tar.zst"
    url = "https://github.com/leanprover/lean4/releases/download/" + version + "/" + name
    downloads = ROOT / "downloads"
    downloads.mkdir(exist_ok=True)
    archive = downloads / name
    if not archive.exists():
        if shutil.disk_usage(ROOT).free < 20 * 1024**3:
            raise ValueError("Less than 20 GiB free before compiler download")
        print("DOWNLOAD COMPILER", version, flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "LeanAgent-Arena-environment-bootstrap"})
        partial = archive.with_suffix(".partial")
        with urllib.request.urlopen(request, timeout=120) as source, partial.open("wb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
        partial.rename(archive)
    digest = file_sha(archive)
    extract(archive, name.removesuffix(".tar.zst"), destination)
    rec = {"kind": "official-release-archive", "url": url, "archive_sha256": digest,
           "archive_bytes": archive.stat().st_size}
    archive.unlink()  # URL + digest retained; do not keep another compiler copy.
    return rec


def local_archive(version, destination):
    # Optional reuse of previously verified local archives; clean-machine fallback
    # is always the exact official release URL in download_release.
    if version not in {"v4.30.0", "v4.31.0"}:
        return None
    store = REPO.parent / "storage-cleanup-20261101/archives"
    identifier = "legacy-lean-" + version[1:].replace(".", "-")
    receipt, archive = store / (identifier + ".json"), store / (identifier + ".tar.zst")
    if not receipt.exists() or not archive.exists():
        return None
    rec = json.loads(receipt.read_text())
    if rec["roots"][0] + "/lib/lean/libLean.a" not in rec["files"]:
        # Historical measurement-only toolchains intentionally omitted static
        # archives. They cannot build native Cache/Lake executables.
        return None
    if archive.stat().st_size != rec["archive_bytes"] or file_sha(archive) != rec["archive_sha256"]:
        raise ValueError("Existing compiler archive integrity check failed")
    if len(rec["roots"]) != 1:
        raise ValueError("Unexpected archived compiler layout")
    print("RESTORE LOCAL COMPILER", version, flush=True)
    extract(archive, rec["roots"][0], destination)
    return {"kind": "verified-local-archive", "archive": str(archive),
            "archive_sha256": rec["archive_sha256"],
            "clean_machine_url": "https://github.com/leanprover/lean4/releases/download/" + version +
            "/lean-" + version[1:] + "-darwin_aarch64.tar.zst"}


def main():
    lock = plan()
    directory = ROOT / "toolchains"
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = ROOT / "toolchains.json"
    records = json.loads(receipt_path.read_text())["toolchains"] if receipt_path.exists() else {}
    for version in lock["toolchain_versions"]:
        dest = directory / version
        incomplete = None
        if dest.exists() and not (dest / "lib/lean/libLean.a").is_file():
            if dest.is_symlink():
                raise ValueError("Installed compiler lacks native build archives: " + version)
            incomplete = directory / (version + ".measurement-only")
            if incomplete.exists():
                raise ValueError("Interrupted compiler replacement requires inspection")
            print("REPLACE MEASUREMENT-ONLY COMPILER", version, flush=True)
            dest.rename(incomplete)
        if not dest.exists():
            installed = Path.home() / ".elan/toolchains" / ("leanprover--lean4---" + version)
            if installed.is_dir():
                dest.symlink_to(installed, target_is_directory=True)
                provenance = {"kind": "matching-installed-toolchain", "path": str(installed)}
            else:
                provenance = local_archive(version, dest) or download_release(version, dest)
        else:
            provenance = records.get(version, {}).get("provenance", {"kind": "existing-repository-toolchain"})
        output = command([dest / "bin/lean", "--version"]).strip()
        if not output.startswith("Lean (version " + version[1:] + ","):
            raise ValueError("Actual compiler version differs from requested pin: " + output)
        if not (dest / "lib/lean/libLean.a").is_file():
            raise ValueError("Compiler native build archive is missing")
        records[version] = {"version": version, "path": str(dest.relative_to(REPO)),
                            "actual_version": output, "lean_sha256": file_sha(dest / "bin/lean"),
                            "lake_sha256": file_sha(dest / "bin/lake"), "provenance": provenance}
        write(receipt_path, {"schema_version": 1, "toolchains": records})
        if incomplete is not None:
            shutil.rmtree(incomplete)
        print("COMPILER READY", version, flush=True)


if __name__ == "__main__":
    main()
