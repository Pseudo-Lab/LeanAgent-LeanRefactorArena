"""Code ZIP for the organizers: tracked runtime files, without historical proof artifacts.

`python -m lean_agent.final60 package --out code.zip`. The pack list is `git ls-files` of the
checkout, restricted to the submission runtime, its tests, pins and operating instructions.
Skills, solutions, dashboards, submissions, raw runs and historical experiments are omitted.
A tracked symlink or secret-looking content refuses the pack.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

EXCLUDED = re.compile(r"(^|/)(declaration-indexes|quarantine|competitors?|competitor-artifacts|third-party-indexes)(/|$)"
                      r"|(^|/)(skills|solutions|dashboard|submissions|runs|sources)(/|$)"
                      r"|(^|/)warmup_bank\.json$|(^|/)experiments/strategy-retriever/bank(/|$)"
                      r"|hrushi|lean-refactor-arena-indexes|vexorium|coco-refactor", re.IGNORECASE)
# Real key shapes only (OpenRouter sk-or-v1-<64 hex>, OpenAI sk-...): a hit names the file; leave a
# fixture-only file out with --exclude rather than packing it.
SECRET = re.compile(rb"\bsk-or-v1-[0-9a-f]{32,}|\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}")
README = "README.md"
SUBMISSION_FILES = frozenset({
    README, "LICENSE", "pyproject.toml",
    "configs/final-environments.lock.json",
    "docs/final60/RUNBOOK.md", "docs/final-run.md", "docs/measurements/final60-baselines.json",
    "scripts/final60_supervise.sh", "scripts/check_submission_rules.py",
    "scripts/check_submission_provenance.py", "experiments/proof-analyze/proof_tokens.py",
    "examples/actions/prompt.txt",
})
HISTORICAL_TESTS = frozenset({"test_assigned_routes.py", "test_route60.py"})


def submission_path(name):
    """Paths needed to run and test final60; experiment outputs are never runtime inputs."""
    path = Path(name)
    return (name in SUBMISSION_FILES or name.startswith(("src/", "refactor_eval/"))
            or (path.parent.as_posix() == "experiments/final-batch-next" and path.suffix == ".py"
                and path.name not in HISTORICAL_TESTS)
            or (path.parent.as_posix() == "tests" and path.name.startswith("test_final60_")
                and path.suffix == ".py"))


def tracked(repo):
    """(files, symlinks) tracked by git in repo, as repo-relative POSIX paths."""
    output = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "-s"],
                            capture_output=True, check=True).stdout
    files, symlinks = [], []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        name = path.decode("utf-8")
        (symlinks if meta.split()[0] == b"120000" else files).append(name)
    return files, symlinks


def excluded(name, extra=()):
    return (not submission_path(name) or EXCLUDED.search(name) is not None
            or any(pattern.search(name) for pattern in extra))


def assert_clean(names, extra=(), *, prefix=""):
    """Raise when any packed path is an excluded artifact (called on the pack list and on the ZIP)."""
    bad = [name for name in names if (prefix and not name.startswith(prefix))
           or excluded(name.removeprefix(prefix), extra)]
    if bad:
        raise ValueError("Packed paths include excluded artifacts: " + ", ".join(sorted(bad)[:8]))
    return True


def package_code(repo, out, *, name=None, extra_excludes=()):
    repo, out = Path(repo).resolve(), Path(out)
    extra = [re.compile(pattern, re.IGNORECASE) for pattern in extra_excludes]
    files, symlinks = tracked(repo)
    if symlinks:
        raise ValueError("Tracked symlinks cannot be packed (the organizers need plain files): " + ", ".join(symlinks[:8]))
    chosen, dropped = [], []
    for item in files:
        if excluded(item, extra):
            dropped.append(item)
            continue
        path = repo / item
        if path.is_symlink():
            raise ValueError("Symlink in the checkout cannot be packed: " + item)
        if path.is_file():
            chosen.append(item)
    if README not in chosen:
        raise ValueError("The code ZIP needs a top-level " + README)
    assert_clean(chosen, extra)
    prefix = (name or repo.name).strip("/") + "/"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(chosen):
            data = (repo / item).read_bytes()
            if SECRET.search(data):
                raise ValueError("Secret-looking content refuses the pack: " + item)
            info = zipfile.ZipInfo(prefix + item, date_time=(2026, 11, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
    assert_clean(names, extra, prefix=prefix)
    if any(not entry.startswith(prefix) for entry in names) or prefix + README not in names:
        raise ValueError("ZIP layout is not <name>/<tracked path> with a top-level README")
    manifest = {"zip": str(out), "prefix": prefix, "files": len(chosen), "excluded": sorted(dropped),
                "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "bytes": out.stat().st_size,
                "repo": str(repo), "head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                                          capture_output=True, text=True).stdout.strip()}
    out.with_name(out.name + ".manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
