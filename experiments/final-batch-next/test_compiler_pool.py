"""Cross-process admission, legacy compatibility, and immutable cache races."""
import errno
import fcntl
import multiprocessing as mp
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import resources
from evaluation_cache import EvaluationCache
from test_evaluation_cache import FixtureEvaluator


def worker(path, events, free=100, legacy=False):
    resources.memory_snapshot = lambda: {"free_percent": free}
    if legacy:
        with open(path, "a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            events.put(("in", time.monotonic()))
            time.sleep(.3)
            events.put(("out", time.monotonic()))
    else:
        with resources.compiler_slot(path, slots=2):
            events.put(("in", time.monotonic()))
            time.sleep(.3)
            events.put(("out", time.monotonic()))


class PoolTests(unittest.TestCase):
    def test_capacity_and_legacy_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = mp.get_context("spawn")
            q = ctx.Queue()
            path = str(Path(tmp) / "compiler.lock")
            jobs = [ctx.Process(target=worker, args=(path, q)) for _ in range(5)]
            for job in jobs: job.start()
            events = [q.get(timeout=15) for _ in range(10)]
            for job in jobs:
                job.join(10)
                self.assertEqual(job.exitcode, 0)
            active = peak = 0
            for event, _ in sorted(events, key=lambda x: x[1]):
                active += 1 if event == "in" else -1
                peak = max(peak, active)
            self.assertEqual(peak, 2)
            # A legacy exclusive holder prevents new shared leases.
            with open(path, "a+") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                job = ctx.Process(target=worker, args=(path, q))
                job.start()
                time.sleep(.4)
                self.assertTrue(q.empty())
            self.assertEqual(q.get(timeout=10)[0], "in")
            # Conversely a legacy compiler waits for shared parallel holders.
            legacy = ctx.Process(target=worker, args=(path, q, 100, True))
            legacy.start()
            self.assertEqual(q.get(timeout=10)[0], "out")
            self.assertEqual(q.get(timeout=10)[0], "in")
            self.assertEqual(q.get(timeout=10)[0], "out")
            job.join(10); legacy.join(10)
            self.assertEqual(legacy.exitcode, 0)

    def test_unavailable_monitor_and_exception_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            with patch.object(resources, "memory_snapshot", return_value={"free_percent": None}):
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    with resources.compiler_slot(path): pass
            with patch.object(resources, "memory_snapshot", return_value={"free_percent": 100}):
                with self.assertRaisesRegex(ValueError, "body"):
                    with resources.compiler_slot(path): raise ValueError("body")
            with path.open("a+") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_memory_headroom_blocks_an_extra_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            with patch.object(resources, "memory_snapshot", return_value={"free_percent": 100}):
                with resources.compiler_slot(path):
                    with patch.object(resources, "memory_snapshot", return_value={"free_percent": 24}), patch.object(resources.time, "monotonic", side_effect=[0, 1201]):
                        with self.assertRaisesRegex(RuntimeError, "safe compiler"):
                            with resources.compiler_slot(path): pass

    def test_publication_race_validates_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ev = FixtureEvaluator(root / "cache")
            code = "theorem test : True := by trivial\n"
            problem = {"id": "test", "statement": "theorem test : True", "name": "test", "reference": code, "environments": ["v1"]}
            ev.evaluate(code, problem, root / "source")
            entry = next((root / "cache").glob("*/receipt.json"))
            import json, shutil
            receipt = json.loads(entry.read_text())
            result = json.loads((entry.parent / "evidence/result.json").read_text())
            identity = receipt["identity"]
            source = root / "source/v1"
            shutil.rmtree(entry.parent)
            real_replace = __import__("os").replace
            def race(stage, target):
                real_replace(stage, target)
                raise OSError(errno.ENOTEMPTY, "another writer won")
            with patch("evaluation_cache.os.replace", side_effect=race):
                ev.cache.publish(identity, source, result)
            self.assertIsNotNone(ev.cache._read(identity))
            shutil.rmtree(entry.parent)
            def corrupt_race(stage, target):
                real_replace(stage, target)
                (target / "evidence/result.json").write_text("{}")
                raise OSError(errno.EEXIST, "another writer won")
            with patch("evaluation_cache.os.replace", side_effect=corrupt_race):
                with self.assertRaises(ValueError): ev.cache.publish(identity, source, result)

if __name__ == "__main__": unittest.main()
