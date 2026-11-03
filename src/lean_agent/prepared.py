"""Explicit, hash-pinned compiled libraries for the common Lean harness.

No downloads or builds. Large library files stay at their prepared locations;
the run archives their manifest and verifies it before each compiler invocation.
An opt-in stat cache reuses content hashes within one evaluator process; full
content verification still runs at both environment fingerprint boundaries.
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
            if path.is_file() and str(path) not in files:
                files[str(path)] = sha(path.read_bytes())
    if not files:
        raise ValueError("Prepared libraries contain no files")
    return files


def freeze(paths, revision, output, *, sandbox="none", verification="full"):
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("Set an explicit library revision")
    if sandbox not in ("none", "macos-readonly"):
        raise ValueError("Unknown prepared-environment sandbox")
    if verification not in ("full", "stat-cache"):
        raise ValueError("Unknown prepared-environment verification policy")
    paths = [str(Path(p).expanduser().resolve()) for p in paths]
    if not paths or len(set(paths)) != len(paths) or any(os.pathsep in p for p in paths):
        raise ValueError("Set distinct compiled library directories")
    value = {"schema_version": 1, "revision": revision, "sandbox": sandbox,
             "library_paths": paths, "files": library_files(paths)}
    if verification != "full":
        value["verification"] = verification
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
                or data.get("verification", "full") not in ("full", "stat-cache")
                or data.get("sandbox", "none") not in ("none", "macos-readonly")):
            raise ValueError("Invalid prepared environment manifest")
        if not all(isinstance(p, str) and p and os.pathsep not in p for p in data["library_paths"]):
            raise ValueError("Invalid prepared library search paths")
        self._verified_files = {}
        self._manifest_sha256 = sha(canonical(data))

    def verify(self, *, full=True):
        # settings are public for existing adapters; never trust cached hashes
        # after an in-memory manifest edit.
        digest = sha(canonical(self.settings))
        if digest != self._manifest_sha256:
            self._verified_files = {}
            raise ValueError("Prepared environment manifest changed")
        if self.settings.get("verification", "full") == "full":
            files = library_files(self.settings["library_paths"])
        else:
            files, verified = {}, {}
            for directory in self.settings["library_paths"]:
                root = Path(directory)
                if not root.is_absolute() or not root.is_dir():
                    raise ValueError("Prepared library path must be an existing absolute directory")
                for path in sorted(root.rglob("*")):
                    if not path.is_file():
                        continue
                    key = str(path)
                    if key in files:
                        if self._stamp(path) != verified[key][0]:
                            self._verified_files = {}
                            raise ValueError("Prepared library changed during verification")
                        continue
                    before = self._stamp(path)
                    prior = self._verified_files.get(key)
                    content_hash = (prior[1] if not full and prior and prior[0] == before
                                    else sha(path.read_bytes()))
                    if self._stamp(path) != before:
                        self._verified_files = {}
                        raise ValueError("Prepared library changed during verification")
                    files[key] = content_hash
                    verified[key] = (before, content_hash)
            # Commit only a complete, successful inventory. A failed attempt
            # cannot seed the cache used for a subsequent invocation.
            if files == self.settings["files"]:
                self._verified_files = verified
        if files != self.settings["files"]:
            self._verified_files = {}
            raise ValueError("Prepared library files changed; prepare a new manifest")
        return digest

    @staticmethod
    def _stamp(path):
        info = path.stat()
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_mode)

    def execute(self, command, *args, **kwargs):
        self.verify(full=False)
        if self.settings.get("sandbox") == "macos-readonly":
            sandbox = shutil.which("sandbox-exec")
            if not sandbox:
                raise ValueError("Requested macos-readonly sandbox is unavailable")
            command = [sandbox, "-p", "(version 1) (allow default) (deny network*) (deny file-write*)", *command]
        return super().execute(command, *args, lean_path=os.pathsep.join(self.settings["library_paths"]), **kwargs)

    def fingerprint(self, environment, *, executor=None):
        # Both the start and final fingerprint must read actual bytes, even
        # when candidate invocations opt into the local filesystem stat cache.
        manifest_hash = self.verify()
        return {**super().fingerprint(environment, executor=executor),
                "prepared_libraries": {"revision": self.settings["revision"],
                    "library_paths": self.settings["library_paths"],
                    "files": len(self.settings["files"]), "manifest_sha256": manifest_hash}}
