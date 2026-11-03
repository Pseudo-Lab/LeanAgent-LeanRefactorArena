"""Exercise mixed coverage and propagation of winning proofs between rounds."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import route60


def single_row_fixture(repo, row=41):
    """A 60-row dataset whose row `row` alone has a prepared (mocked) environment."""
    data = [dict(name=f"t{n}", source="leanpool", statement=f"theorem t{n} : True",
                 src=f"theorem t{n} : True := by trivial", header="", version_info=[{"v4.fake": "pin"}])
            for n in range(1, 61)]
    ds = repo / "data.jsonl"
    ds.write_text("".join(json.dumps(r) + "\n" for r in data))
    digest = hashlib.sha256(ds.read_bytes()).hexdigest()
    env = "leanpool-v4.fake"
    state = repo / "sources/final/environments" / env / "environment.json"
    state.parent.mkdir(parents=True)
    (repo / "prepared.json").write_text("{}")
    state.write_text(json.dumps(dict(id=env, status="ready", revision="pin", prepared_environment="prepared.json",
                                     locations=[{"row": row}])))
    r = data[row - 1]
    p = dict(row=row, name=r["name"], source=r["source"], statement=r["statement"], reference=r["src"],
             header="", dataset_sha256=digest, environments=[env])
    packet = repo / f"sources/final/problems/F{row:03}.json"
    packet.parent.mkdir()
    packet.write_text(json.dumps(p))
    ev = Mock(registry={"dataset_sha256": digest, "environments": {env: {}}})
    ev.load_problem.return_value = p
    return ds, digest, ev, p


class Route60Tests(unittest.TestCase):
    def test_partial_coverage_and_next_round_receives_only_verified_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            data = [
                dict(
                    name=f"t{n}",
                    source="leanpool",
                    statement=f"theorem t{n} : True",
                    src=f"theorem t{n} : True := by trivial",
                    header="",
                    version_info=[{"v4.fake": "pin"}],
                )
                for n in range(1, 61)
            ]
            ds = repo / "data.jsonl"
            ds.write_text("".join(json.dumps(r) + "\n" for r in data))
            digest = hashlib.sha256(ds.read_bytes()).hexdigest()
            env = "leanpool-v4.fake"
            state = repo / "sources/final/environments" / env / "environment.json"
            state.parent.mkdir(parents=True)
            manifest = repo / "prepared.json"
            manifest.write_text("{}")
            state.write_text(
                json.dumps(
                    dict(
                        id=env,
                        status="ready",
                        revision="pin",
                        prepared_environment=manifest.name,
                        locations=[{"row": 41}],
                    )
                )
            )
            r = data[40]
            p = dict(
                row=41,
                name=r["name"],
                source=r["source"],
                statement=r["statement"],
                reference=r["src"],
                header="",
                dataset_sha256=digest,
                environments=[env],
            )
            packet = repo / "sources/final/problems/F041.json"
            packet.parent.mkdir()
            packet.write_text(json.dumps(p))
            ev = Mock(registry={"dataset_sha256": digest, "environments": {env: {}}})
            ev.load_problem.return_value = p
            winner = p["statement"] + " := by constructor"

            def run(*args, incumbent, explored, **kwargs):
                if incumbent:
                    self.assertEqual((incumbent, set(explored)), (winner, {"screened"}))
                return dict(
                    name=p["name"], proof=winner,
                    score=40,
                    controls={"previous-round": 40},
                    selected="winner",
                    attempts=1,
                    screened_hashes=["screened"],
                )

            with (
                patch.object(route60, "FinalEvaluator", return_value=ev) as factory,
                patch.object(route60, "DATASET_SHA", digest),
                patch.object(route60, "preflight") as sandbox,
                patch.object(route60, "compare", side_effect=run) as comp,
                self.assertRaises(SystemExit) as stopped,
            ):
                route60.main(
                    [
                        "--prepared-repo",
                        str(repo),
                        "--dataset",
                        str(ds),
                        "--out",
                        str(repo / "run"),
                        "--limit",
                        "1",
                    ]
                )
            # 59 of the 60 requested rows have no prepared environment: outputs, then status 1.
            self.assertEqual(stopped.exception.code, 1)
            sandbox.assert_called_once_with(repo.resolve())
            self.assertEqual(factory.call_args.kwargs["compiler_parallelism"], 1)
            self.assertEqual(comp.call_count, 2)
            self.assertFalse((repo / "run/submission.jsonl").exists())
            self.assertEqual(json.loads((repo / "run/partial.jsonl").read_text())["proof"], winner)
            self.assertIsNone(json.loads((repo / "run/report.json").read_text())["full60_mean"])

            carried = p["statement"] + " := by exact True.intro"
            carry = repo / "carry.jsonl"
            carry.write_text(json.dumps({"name": p["name"], "proof": carried}) + "\n")
            carried_second = p["statement"] + " := by trivial"
            carry_second = repo / "carry-second.jsonl"
            carry_second.write_text(json.dumps({"name": p["name"], "proof": carried_second}) + "\n")

            def compare_carried(*args, incumbent, explored, extra_seeds, **kwargs):
                self.assertEqual(incumbent, carried)
                self.assertEqual(explored, set())
                self.assertEqual(extra_seeds, [("carry-02", carried_second)])
                return dict(name=p["name"], proof=winner, score=40,
                            controls={"previous-round": 39}, selected="winner",
                            attempts=0, screened_hashes=[])

            with (
                patch.object(route60, "FinalEvaluator", return_value=ev) as factory,
                patch.object(route60, "DATASET_SHA", digest),
                patch.object(route60, "preflight"),
                patch.object(route60, "compare", side_effect=compare_carried) as comp,
            ):
                route60.main([
                    "--prepared-repo", str(repo), "--dataset", str(ds),
                    "--out", str(repo / "carry-run"), "--rows", "41",
                    "--rounds", "1", "--limit", "0", "--carry-jsonl", str(carry),
                    "--carry-jsonl", str(carry_second), "--compiler-parallelism", "2",
                ])
            self.assertEqual(comp.call_count, 1)
            self.assertEqual(factory.call_args.kwargs["compiler_parallelism"], 2)
            self.assertEqual(json.loads((repo / "carry-run/protocol.json").read_text())["compiler_parallelism"], 2)
            self.assertTrue(json.loads((repo / "carry-run/report.json").read_text())["assisted"])
            carried_inputs = json.loads((repo / "carry-run/report.json").read_text())["rows"]["41"]["carried_inputs"]
            self.assertEqual(carried_inputs, [
                {"source": f"carry-{n:02}", "proof_sha256": hashlib.sha256(code.encode()).hexdigest()}
                for n, code in enumerate((carried, carried_second), 1)
            ])
            self.assertEqual(json.loads((repo / "carry-run/partial.jsonl").read_text())["proof"], winner)
            self.assertEqual(json.loads((repo / "carry-run/protocol.json").read_text())["carry_sha256"],
                             hashlib.sha256(carry.read_bytes()).hexdigest())
            self.assertEqual(json.loads((repo / "carry-run/protocol.json").read_text())["carry_sha256s"],
                             [hashlib.sha256(path.read_bytes()).hexdigest() for path in (carry, carry_second)])

            duplicate = repo / "duplicate.jsonl"
            duplicate.write_text(carry.read_text() * 2)
            with (
                patch.object(route60, "FinalEvaluator", return_value=ev),
                patch.object(route60, "DATASET_SHA", digest),
                patch.object(route60, "preflight"),
                patch.object(route60, "compare") as comp,
                self.assertRaisesRegex(ValueError, "duplicate carried theorem"),
            ):
                route60.main([
                    "--prepared-repo", str(repo), "--dataset", str(ds),
                    "--out", str(repo / "invalid-run"), "--rows", "41",
                    "--carry-jsonl", str(duplicate),
                ])
            comp.assert_not_called()

            # A failed sandbox preflight stops before any output, so --out stays reusable.
            with (
                patch.object(route60, "FinalEvaluator", return_value=ev),
                patch.object(route60, "DATASET_SHA", digest),
                patch.object(route60, "preflight", side_effect=SystemExit("no bwrap")),
                patch.object(route60, "compare") as comp,
                self.assertRaisesRegex(SystemExit, "no bwrap"),
            ):
                route60.main(["--prepared-repo", str(repo), "--dataset", str(ds),
                              "--out", str(repo / "no-sandbox-run"), "--rows", "41"])
            comp.assert_not_called()
            self.assertFalse((repo / "no-sandbox-run").exists())

    def test_missing_prerequisites_fail_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            out = repo / "run"
            with patch("sys.stderr"), self.assertRaises(SystemExit) as stopped:
                route60.main(["--prepared-repo", str(repo), "--out", str(out), "--plan-only"])
            self.assertEqual(stopped.exception.code, 2)  # argparse error naming the dataset path
            self.assertFalse(out.exists())
            with (
                patch.object(route60.sys, "platform", "linux"),
                patch.object(route60.shutil, "which", return_value=None),
                self.assertRaisesRegex(SystemExit, "bwrap"),
            ):
                route60.preflight(repo)
            bundled = repo / "sources/final/bin/bwrap"
            bundled.parent.mkdir(parents=True)
            bundled.write_text("#!/bin/sh\n")
            bundled.chmod(0o755)
            with (
                patch.object(route60.sys, "platform", "linux"),
                patch.object(route60.shutil, "which", return_value=None),
                patch.dict(route60.os.environ, {"PATH": "/usr/bin"}),
                patch("builtins.print"),
            ):
                route60.preflight(repo)
                self.assertEqual(route60.os.environ["PATH"].split(route60.os.pathsep)[0], str(bundled.parent))
            # The probe runs bwrap with the evaluator's flags: a sandbox that cannot start fails here.
            bundled.write_text("#!/bin/sh\necho 'bwrap: setting up uid map: Permission denied' >&2\nexit 1\n")
            with (
                patch.object(route60.sys, "platform", "linux"),
                patch.object(route60.shutil, "which", return_value=str(bundled)),
                self.assertRaisesRegex(SystemExit, "Permission denied"),
            ):
                route60.preflight(repo)
            with (
                patch.object(route60.sys, "platform", "linux"),
                patch.object(route60.shutil, "which", return_value=str(bundled)),
                patch.object(route60.subprocess, "run", return_value=Mock(returncode=0)) as probe,
            ):
                route60.preflight(repo)
            command = probe.call_args.args[0]
            self.assertEqual(command[0], str(bundled))
            self.assertEqual(command[command.index("--") + 1:], ["true"])
            for flag in ("--die-with-parent", "--unshare-all", "--ro-bind"):
                self.assertIn(flag, command)

    def test_protocol_records_code_and_memory_bound_and_report_keeps_failure_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            ds, digest, ev, p = single_row_fixture(repo)
            env = p["environments"][0]
            cause = "libc++abi: lean::memory_exception: excessive memory consumption detected at 'interpreter'"

            def reference_fails(ev_, problem, root, *args, **kwargs):
                measure = root / "00-measure"
                measure.mkdir(parents=True)
                (measure / "result.json").write_text(json.dumps({
                    "valid": False, "environments": {env: {"valid": False, "error": {"kind": "compile", "message": cause}}},
                    "error": {"kind": "lean", "message": "One or more required environments failed"}}))
                raise RuntimeError("Reference failed in the prepared environment")

            with (
                patch.object(route60, "FinalEvaluator", return_value=ev),
                patch.object(route60, "DATASET_SHA", digest),
                patch.object(route60, "preflight"),
                patch.object(route60, "compare", side_effect=reference_fails),
                patch.dict(route60.os.environ, {"ARENA_LEAN_MEMORY_MIB": "16384"}),
                self.assertRaises(SystemExit) as stopped,
            ):
                route60.main(["--prepared-repo", str(repo), "--dataset", str(ds), "--out", str(repo / "run"),
                              "--rows", "41", "--rounds", "1", "--limit", "0"])
            self.assertEqual(stopped.exception.code, 1)
            protocol = json.loads((repo / "run/protocol.json").read_text())
            self.assertEqual(protocol["lean_memory_mib"], 16384)
            self.assertEqual(set(protocol["code_hashes"]), set(route60.HARNESS_FILES))
            here = Path(route60.__file__).parent
            for name, value in protocol["code_hashes"].items():
                self.assertEqual(value, hashlib.sha256((here / name).read_bytes()).hexdigest())
            failed = json.loads((repo / "run/report.json").read_text())["failed"]["41"]
            self.assertEqual(failed["error"], "Reference failed in the prepared environment")
            self.assertEqual(failed["evaluation"], "00-measure")
            self.assertEqual(failed["environments"][env]["kind"], "compile")
            self.assertIn("memory_exception", failed["environments"][env]["message"])
            incomplete = json.loads((repo / "run/round-01/F041/incomplete.json").read_text())
            self.assertEqual(incomplete["environments"], failed["environments"])

            with (
                patch.object(route60, "FinalEvaluator", return_value=ev),
                patch.object(route60, "DATASET_SHA", digest),
                patch.object(route60, "preflight"),
                patch.dict(route60.os.environ, {"ARENA_LEAN_MEMORY_MIB": "16G"}),
                patch("sys.stderr"),
                self.assertRaises(SystemExit) as stopped,
            ):
                route60.main(["--prepared-repo", str(repo), "--dataset", str(ds), "--out", str(repo / "bad-bound"),
                              "--rows", "41"])
            self.assertEqual(stopped.exception.code, 2)
            self.assertFalse((repo / "bad-bound").exists())
