"""Reuse a verified inventory; detect file and directory changes before Lean.

Full byte checks remain at experiment boundaries. Between them, stat each known
file once and each known directory twice. Directory stamps detect additions,
removals and symlink retargeting without recursively listing the tree per call.
A change triggers the original full verifier, never an unchecked cache hit.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import time

from lean_agent.artifacts import canonical, sha
from lean_agent.prepared import PreparedLeanEvaluator


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode)


def directory_stamp(path):
    info = os.lstat(path)
    return (stamp(info), stamp(os.stat(path)) if stat.S_ISLNK(info.st_mode) else None)


class FastPreparedLeanEvaluator(PreparedLeanEvaluator):
    def __init__(self, manifest, executor=None):
        super().__init__(manifest, executor)
        self._fast_files = None
        self._fast_directories = None
        self.layout_sha256 = None
        self.last_verification = None

    def _directories(self):
        roots = [Path(p) for p in self.settings["library_paths"]]
        directories = set()
        files = set()

        def onerror(error):
            raise error

        for root in roots:
            for directory, children, names in os.walk(root, followlinks=False, onerror=onerror):
                directories.add(str(Path(directory)))
                files.update(str(Path(directory) / name) for name in names)
                for child in children:
                    path = Path(directory) / child
                    if path.is_symlink():
                        # The original manifest hashes files, not directory-link
                        # routing. Refuse such layouts instead of caching an
                        # unpinned alias. All 17 final environments have none.
                        raise ValueError("Directory symlink in prepared libraries: " + str(path))
        if files != set(self.settings["files"]):
            raise ValueError("Prepared library file inventory changed")
        return {p: directory_stamp(p) for p in sorted(directories)}

    def _clear_inventory(self):
        self._fast_files = self._fast_directories = None
        self.layout_sha256 = None

    def _full_verify(self):
        before = self._directories()
        if self._fast_directories is not None and set(before) != set(self._fast_directories):
            raise ValueError("Prepared library directory layout changed")
        if any(not stat.S_ISREG(os.stat(p).st_mode) for p in self.settings["files"]):
            raise ValueError("Non-regular prepared library file")
        digest = super().verify(full=True)
        after = self._directories()
        if before != after:
            raise ValueError("Prepared library directories changed during full verification")
        # The original stat-cache verifier binds these stamps to actual bytes.
        if self.settings.get("verification", "full") == "stat-cache":
            files = {p: value[0] for p, value in self._verified_files.items()}
            if any(stamp(os.stat(p)) != expected for p, expected in files.items()):
                raise ValueError("Prepared library files changed during full verification")
            self._fast_files, self._fast_directories = files, after
            self.layout_sha256 = sha(canonical(sorted(after)))
        return digest

    def verify(self, *, full=True):
        started = time.monotonic()
        mode = "full" if full or self._fast_files is None else "inventory-stat"
        try:
            digest = sha(canonical(self.settings))
            if digest != self._manifest_sha256:
                self._verified_files = {}
                raise ValueError("Prepared environment manifest changed")
            if full or self._fast_files is None:
                return self._full_verify()
            directories = self._fast_directories
            if any(directory_stamp(p) != expected for p, expected in directories.items()):
                mode = "full-after-directory-change"
                return self._full_verify()
            if any(stamp(os.stat(p)) != expected for p, expected in self._fast_files.items()):
                mode = "full-after-file-change"
                return self._full_verify()
            if any(directory_stamp(p) != expected for p, expected in directories.items()):
                mode = "full-after-concurrent-directory-change"
                return self._full_verify()
            return digest
        except BaseException:
            self._clear_inventory()
            raise
        finally:
            self.last_verification = {"mode": mode,
                "seconds": time.monotonic() - started,
                "files": len(self._fast_files or {}),
                "directories": len(self._fast_directories or {})}
