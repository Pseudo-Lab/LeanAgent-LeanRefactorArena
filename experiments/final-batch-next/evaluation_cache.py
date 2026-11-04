"""Content-addressed, evidence-preserving cache for one problem/environment.

Verified warm-cache hits bypass the compiler lock. Cache misses and cold
inventory setup hold the global compiler lock across execution and publish.
Timeouts, resource failures and environment failures must be retried locally,
never treated as permanent proof rejections. Final measurements bypass this cache.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

SCHEMA = "candidate-environment-evidence-v2"
VERIFICATION_POLICY = "candidate-cache-final-compatibility-fast-inventory-v2"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cacheable(result):
    runs = result.get("runs", [])
    if not runs or any(r.get("timed_out") or (r.get("returncode") or 0) < 0 for r in runs):
        return False
    if result.get("valid"):
        return all(r.get("returncode") == 0 for r in runs)
    error = result.get("error") or {}
    if error.get("kind") not in ("compile", "axioms"):
        return False
    message = error.get("message", "").lower()
    if any(marker in message for marker in (
        "memory", "allocation failed", "resource", "interrupted", "killed",
        "no such file", "failed to open", "unknown module prefix", "object file",
        "permission denied", "input/output error", "stack overflow", "heartbeat",
        "maximum recursion depth", "timeout", "timed out",
        "operation not permitted", "sandbox-exec:", "sandbox_apply:",
    )):
        return False
    return (error["kind"] == "axioms" or any((r.get("returncode") or 0) > 0 for r in runs))


def inventory(root):
    if root.is_symlink():
        raise ValueError("Symlink in evaluation cache evidence")
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in evaluation cache evidence")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return files


class EvaluationCache:
    def __init__(self, root):
        self.root = Path(root)

    def key(self, identity):
        return sha(canonical({"schema": SCHEMA, "identity": identity}).encode())

    def contains(self, identity):
        return (self.root / self.key(identity)).exists()

    def _read(self, identity):
        key = self.key(identity)
        entry = self.root / key
        if not entry.exists():
            return None
        if entry.is_symlink():
            raise ValueError("Symlink in evaluation cache entry")
        try:
            receipt = json.loads((entry / "receipt.json").read_text())
            evidence = entry / "evidence"
            if (receipt["schema"] != SCHEMA or receipt["identity"] != identity
                    or receipt["key"] != key or inventory(evidence) != receipt["files"]):
                raise ValueError("Evaluation cache evidence/identity mismatch")
            result = json.loads((evidence / "result.json").read_text())
            if not cacheable(result):
                raise ValueError("Uncacheable evaluation result in cache")
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Incomplete or malformed evaluation cache") from exc
        return receipt, evidence, result

    def load(self, identity, destination):
        found = self._read(identity)
        if found is None:
            return None
        receipt, evidence, result = found
        key = receipt["key"]
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        if any(destination.iterdir()):
            raise ValueError("Cache destination must be empty")
        for name in receipt["files"]:
            source = evidence / name
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        # Keep original compiler command/timing as historical evidence. This hit
        # launched no compiler; consumers must not count historical run seconds.
        result["cache"] = {"hit": True, "key": key, "origin": receipt["origin"],
                           "compiler_invocations": 0, "execution_seconds": 0}
        (destination / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result

    def audit_reuse(self, result, *, problem, code, environment):
        """Offline export audit: cached measurements retain their original evidence."""
        usage = result.get("cache")
        if not usage:
            return
        try:
            key = usage["key"]
            if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                raise ValueError("Invalid evaluation cache key")
            receipt = json.loads((self.root / key / "receipt.json").read_text())
            identity = receipt["identity"]
            if (identity["problem"] != problem or identity["candidate_sha256"] != sha(code.encode())
                    or identity["environment"]["id"] != environment):
                raise ValueError("Cached evaluation belongs to a different candidate/problem/environment")
            found = self._read(identity)
            if found is None:
                raise ValueError("Missing evaluation cache evidence")
            receipt, _, original = found
            expected = {**original, "cache": {"hit": True, "key": key, "origin": receipt["origin"],
                        "compiler_invocations": 0, "execution_seconds": 0}}
            if result != expected:
                raise ValueError("Reused evaluation differs from original cached evidence")
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Malformed reused evaluation evidence") from exc

    def publish(self, identity, source, result):
        if not cacheable(result):
            return
        source = Path(source)
        key = self.key(identity)
        self.root.mkdir(parents=True, exist_ok=True)
        entry = self.root / key
        if entry.exists():
            return  # A completed entry is immutable; lookup verifies its evidence.
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=self.root) as temporary:
            stage = Path(temporary) / "entry"
            evidence = stage / "evidence"
            files = inventory(source)
            for name in files:
                target = evidence / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
            if inventory(evidence) != files:
                raise ValueError("Evaluation evidence changed during cache publication")
            if json.loads((evidence / "result.json").read_text()) != result:
                raise ValueError("Evaluation result differs from its saved evidence")
            receipt = {"schema": SCHEMA, "key": key, "identity": identity,
                       "origin": str(source.resolve()), "files": files}
            (stage / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
            try:
                os.replace(stage, entry)
            except OSError as exc:
                if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                    raise
                # A concurrent verifier won publication. Validate its immutable
                # evidence; never replace it or silently accept corruption.
                if self._read(identity) is None:
                    raise ValueError("Concurrent cache publication disappeared") from exc
