"""Explicit, hash-pinned compiled libraries for the common Lean harness.

No downloads or builds. Large library files stay at their prepared locations;
the run archives their manifest and verifies it before each compiler invocation.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from .artifacts import canonical, read, sha, write
from .evaluator.lean import LeanEvaluator


def library_files(paths):
    files = {}
    for directory in paths:
        root = Path(directory)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("Prepared library path must be an existing absolute directory")
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files[str(path)] = sha(path.read_bytes())
    if not files:
        raise ValueError("Prepared libraries contain no files")
    return files


def freeze(paths, revision, output, *, sandbox="none"):
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("Set an explicit library revision")
    if sandbox not in ("none", "macos-readonly"):
        raise ValueError("Unknown prepared-environment sandbox")
    paths = [str(Path(p).expanduser().resolve()) for p in paths]
    if not paths or len(set(paths)) != len(paths) or any(os.pathsep in p for p in paths):
        raise ValueError("Set distinct compiled library directories")
    value = {"schema_version": 1, "revision": revision, "sandbox": sandbox,
             "library_paths": paths, "files": library_files(paths)}
    write(output, value)
    return {"manifest": str(output), "revision": revision, "files": len(value["files"])}


class PreparedLeanEvaluator(LeanEvaluator):
    def __init__(self, manifest, executor=None):
        super().__init__(executor)
        self.settings = read(manifest)
        data = self.settings
        if (data.get("schema_version") != 1 or not isinstance(data.get("revision"), str)
                or not data["revision"].strip() or not isinstance(data.get("library_paths"), list)
                or not data["library_paths"] or not isinstance(data.get("files"), dict)
                or data.get("sandbox", "none") not in ("none", "macos-readonly")):
            raise ValueError("Invalid prepared environment manifest")
        if not all(isinstance(p, str) and p and os.pathsep not in p for p in data["library_paths"]):
            raise ValueError("Invalid prepared library search paths")

    def verify(self):
        if library_files(self.settings["library_paths"]) != self.settings["files"]:
            raise ValueError("Prepared library files changed; prepare a new manifest")
        return sha(canonical(self.settings))

    def execute(self, command, *args, **kwargs):
        self.verify()
        if self.settings.get("sandbox") == "macos-readonly":
            sandbox = shutil.which("sandbox-exec")
            if not sandbox:
                raise ValueError("Requested macos-readonly sandbox is unavailable")
            command = [sandbox, "-p", "(version 1) (allow default) (deny network*) (deny file-write*)", *command]
        return super().execute(command, *args, lean_path=os.pathsep.join(self.settings["library_paths"]), **kwargs)

    def fingerprint(self, environment, *, executor=None):
        return {**super().fingerprint(environment, executor=executor),
                "prepared_libraries": {"revision": self.settings["revision"],
                    "library_paths": self.settings["library_paths"],
                    "files": len(self.settings["files"]), "manifest_sha256": self.verify()}}
