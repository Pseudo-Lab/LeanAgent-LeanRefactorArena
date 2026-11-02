"""Prepare exact public source/dependency checkouts for the final benchmark.

Only repository-owned sources/final is mutated. Never updates a dependency pin,
installs a global toolchain, executes candidate text, or calls a model API.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"
ROOT = REPO / "sources/final"
LOCK = REPO / "configs/final-environments.lock.json"
EXPECTED = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"
URLS = {"strata": "https://github.com/strata-org/Strata.git",
        "physlib": "https://github.com/leanprover-community/physlib.git",
        "cslib": "https://github.com/leanprover/cslib.git",
        "arklib": "https://github.com/Verified-zkEVM/ArkLib.git",
        "leanpool": "https://github.com/Vilin97/lean-pool.git",
        "putnambench": "https://github.com/leanprover-community/mathlib4.git"}


def package_name(name):
    # Lake serializes escaped Lean identifiers (e.g. «doc-gen4»), but its package
    # directory uses Name.toString(escape := false).
    return name[1:-1] if name.startswith("«") and name.endswith("»") else name


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def command(argv, cwd=None, timeout=600, env=None):
    started = time.monotonic()
    result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Command failed: " + repr(list(map(str, argv))) + "\n" + result.stdout.decode(errors="replace")[-5000:])
    return result.stdout.decode(errors="replace")


def dataset():
    if digest(DATA) != EXPECTED:
        raise ValueError("Dataset differs from inspected snapshot")
    return [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]


def checkout_path(url, version, revision):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.query or parsed.fragment:
        raise ValueError("Only pinned public GitHub dependencies are supported: " + url)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Dependency revision must be a full SHA")
    owner, name = parsed.path.strip("/").removesuffix(".git").split("/")
    return ROOT / "checkouts" / version / (owner + "--" + name + "--" + revision)


def plan():
    envs = {}
    for index, row in enumerate(dataset(), 1):
        for pin in row["version_info"]:
            for version, revision in pin.items():
                key = row["source"] + "-" + version
                path = checkout_path(URLS[row["source"]], version, revision)
                rec = envs.setdefault(key, {"id": key, "source": row["source"], "version": version,
                    "revision": revision, "url": URLS[row["source"]],
                    "project": str(path.relative_to(REPO)), "problem_rows": []})
                if rec["revision"] != revision:
                    raise ValueError("Conflicting pins")
                rec["problem_rows"].append(index)
    lock = {"schema_version": 1, "dataset": str(DATA.relative_to(REPO)), "dataset_sha256": EXPECTED,
            "platform": "darwin_aarch64", "environments": sorted(envs.values(), key=lambda r: r["id"]),
            "toolchain_versions": sorted({r["version"] for r in envs.values()}),
            "scope": "Environment preparation only; no model/API calls or proof search."}
    if LOCK.exists() and json.loads(LOCK.read_text()) != lock:
        raise ValueError("Existing environment lock differs")
    write(LOCK, lock)
    return lock


def fetch(url, version, revision):
    path = checkout_path(url, version, revision)
    if not (path / ".git").exists():
        path.mkdir(parents=True, exist_ok=True)
        command(["git", "init", "-q", path])
        command(["git", "-C", path, "remote", "add", "origin", url])
    remote = command(["git", "-C", path, "remote", "get-url", "origin"]).strip()
    if remote.removesuffix(".git").lower() != url.removesuffix(".git").lower():
        raise ValueError("Checkout origin mismatch")
    head = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode or head.stdout.strip() != revision:
        print("FETCH", version, url, revision[:12], flush=True)
        command(["git", "-C", path, "fetch", "--depth=1", "origin", revision], timeout=1200)
        command(["git", "-C", path, "checkout", "--detach", "-q", "FETCH_HEAD"])
    if command(["git", "-C", path, "rev-parse", "HEAD"]).strip() != revision:
        raise ValueError("Checkout revision mismatch")
    if command(["git", "-C", path, "diff", "--name-only", "HEAD", "--"]).strip():
        raise ValueError("Pinned source has tracked edits: " + str(path))
    return path


def fetch_all(lock):
    completed, active = {}, set()

    def visit(url, version, revision):
        path = checkout_path(url, version, revision)
        key = str(path)
        if key in completed or key in active:
            return path
        active.add(key)
        path = fetch(url, version, revision)
        manifest_path = path / "lake-manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"packages": []}
        dependencies = []
        packages_dir = path / manifest.get("packagesDir", ".lake/packages")
        if not packages_dir.resolve().is_relative_to(path.resolve()):
            raise ValueError("Package directory escapes checkout")
        packages_dir.mkdir(parents=True, exist_ok=True)
        for entry in manifest["packages"]:
            if entry["type"] != "git":
                raise ValueError("Unsupported pinned dependency: " + repr(entry))
            dep = visit(entry["url"], version, entry["rev"])
            link = packages_dir / package_name(entry["name"])
            if link.is_symlink():
                if link.resolve() != dep.resolve():
                    raise ValueError("Dependency link conflict")
            elif link.exists():
                raise ValueError("Unexpected materialized dependency: " + str(link))
            else:
                link.symlink_to(os.path.relpath(dep, link.parent), target_is_directory=True)
            dependencies.append({"name": entry["name"], "url": entry["url"], "revision": entry["rev"],
                                 "path": str(dep.relative_to(REPO))})
        record = {"url": url, "version_context": version, "revision": revision,
                  "path": str(path.relative_to(REPO)), "dependencies": dependencies,
                  "manifest_sha256": digest(manifest_path) if manifest_path.exists() else None,
                  "lean_toolchain": (path / "lean-toolchain").read_text().strip() if (path / "lean-toolchain").exists() else None}
        completed[key] = record
        active.remove(key)
        write(ROOT / "source-lock.json", {"schema_version": 1, "dataset_sha256": EXPECTED,
                                          "checkouts": list(completed.values())})
        return path

    for env in lock["environments"]:
        path = visit(env["url"], env["version"], env["revision"])
        toolchain = (path / "lean-toolchain").read_text().strip()
        if toolchain != "leanprover/lean4:" + env["version"]:
            raise ValueError("Root toolchain differs from benchmark pin: " + env["id"] + " / " + toolchain)
        print("SOURCES READY", env["id"], flush=True)
    print("SOURCE CHECKOUTS", len(completed), flush=True)
    fetch_widget_tags()


def fetch_widget_tags():
    """Lake's ProofWidgets release lookup needs the real tag at the locked SHA."""
    url = "https://github.com/leanprover-community/ProofWidgets4"
    output = command(["git", "ls-remote", "--tags", url])
    tags, peeled = {}, {}
    for line in output.splitlines():
        revision, ref = line.split()
        tag = ref.removeprefix("refs/tags/")
        if tag.endswith("^{}"):
            peeled[tag[:-3]] = revision
        else:
            tags[tag] = revision
    tags.update(peeled)
    records = []
    for project in sorted((ROOT / "checkouts").glob("*/leanprover-community--ProofWidgets4--*")):
        revision = project.name.rsplit("--", 1)[1]
        candidates = sorted(tag for tag, commit in tags.items() if commit == revision)
        if not candidates:
            # Recent clients need no ProofWidgets release. Never invent a tag.
            records.append({"path": str(project.relative_to(REPO)), "revision": revision, "tag": None})
            continue
        tag = candidates[-1]
        command(["git", "-C", project, "fetch", "--depth=1", "origin", "tag", tag])
        actual = command(["git", "-C", project, "rev-parse", tag + "^{commit}"]).strip()
        if actual != revision:
            raise ValueError("ProofWidgets tag does not resolve to the locked SHA")
        records.append({"path": str(project.relative_to(REPO)), "revision": revision, "tag": tag})
        print("RELEASE TAG READY", project.parent.name, tag, flush=True)
    write(ROOT / "proofwidgets-tags.json", records)


def normalize_package_links():
    """Deduplicate Lake-created copies after all builds have stopped."""
    records = []
    source_lock = json.loads((ROOT / "source-lock.json").read_text())
    for checkout in source_lock["checkouts"]:
        project = REPO / checkout["path"]
        manifest = project / "lake-manifest.json"
        if not manifest.exists():
            continue
        data = json.loads(manifest.read_text())
        directory = project / data.get("packagesDir", ".lake/packages")
        for entry in data["packages"]:
            expected = checkout_path(entry["url"], checkout["version_context"], entry["rev"])
            if not (expected / ".git").is_dir():
                raise ValueError("Shared dependency checkout is missing")
            link = directory / package_name(entry["name"])
            if link.is_symlink():
                if link.resolve() != expected.resolve():
                    raise ValueError("Dependency points to an unexpected checkout")
            else:
                if link.exists():
                    if not link.resolve().is_relative_to(ROOT.resolve()) or not (link / ".git").is_dir():
                        raise ValueError("Unexpected materialized dependency; preserved")
                    if command(["git", "-C", link, "rev-parse", "HEAD"]).strip() != entry["rev"]:
                        raise ValueError("Duplicate checkout has another revision; preserved")
                    if command(["git", "-C", link, "diff", "--name-only", "HEAD", "--"]).strip():
                        raise ValueError("Duplicate checkout has edits; preserved")
                    if command(["git", "-C", link, "ls-files", "--others", "--exclude-standard"]).strip():
                        raise ValueError("Duplicate checkout has new source files; preserved")
                    library = link / ".lake/build/lib"
                    if library.exists() and any(p.is_file() for p in library.rglob("*")):
                        records.append({"retained_built_duplicate": str(link.relative_to(REPO)),
                                        "revision": entry["rev"], "reason": "Existing runtime artifacts retained."})
                        continue
                    records.append({"removed_duplicate": str(link.relative_to(REPO)), "revision": entry["rev"],
                                    "retained_checkout": str(expected.relative_to(REPO))})
                    shutil.rmtree(link)
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(os.path.relpath(expected, link.parent), target_is_directory=True)
            old = directory / entry["name"]
            if old != link and old.is_symlink() and old.resolve() == expected.resolve():
                old.unlink()
    write(ROOT / "dependency-deduplication.json", records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "fetch"])
    args = parser.parse_args()
    lock = plan()
    if args.action == "fetch":
        fetch_all(lock)
    else:
        print(json.dumps(lock, ensure_ascii=False, indent=2))
