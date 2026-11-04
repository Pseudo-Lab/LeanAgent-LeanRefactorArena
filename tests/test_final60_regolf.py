"""final60 regolf: the second, API-free golf pass over published rows (Stage 10).

No network and no Lean: the orchestration tests patch the golf, selection and report hooks;
the end-to-end test drives the real golf/select/write_selection/report chain on the
synthetic FixtureEvaluator of test_final60_golf and then runs the row audit and the PR #70
provenance checker on the regolfed root.
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from lean_agent.final60 import evaladapter, golf, regolf, scoring, select
from lean_agent.final60.contracts import Candidate, EvalResult, RowState, Selection
from lean_agent.final60.orchestrator import Layout, atomic_json, json_bytes, load_rowstate, read_json, save_rowstate, sha_bytes, sha_text

import test_final60_golf as G

REPO = Path(__file__).resolve().parents[1]
FAR = "2030-01-01T00:00:00+00:00"
OPENROUTER = {"provider": "OpenRouter", "api_endpoint": "https://openrouter.ai/api/v1/chat/completions",
              "transport": "openrouter", "dry_run": False, "rows": [1], "dataset_sha256": "x",
              "per_problem_target_usd": "2.99"}
OPENAI_DEV = {**OPENROUTER, "provider": "OpenAI direct", "api_endpoint": "https://api.openai.com/v1/chat/completions",
              "transport": "openai", "submittable": False}
MOCK = {**OPENROUTER, "transport": "mock", "dry_run": True}


def sha(text):
    return sha_text(text)


class Fixture:
    """A minimal published row under <run>/rows/F001 (no driver evidence; hooks are patched)."""

    statement = "theorem t : True"
    reference = statement + " := by\n  have h : True := by\n    exact trivial\n  have u : True := trivial\n  exact h\n"
    incumbent = statement + " := by\n  have h : True := trivial\n  exact h\n"
    better = statement + " := by\n  trivial\n"

    def __init__(self, run_dir, *, authorization=OPENROUTER, status="published", origin="openrouter-run",
                 estimate=60.0):
        self.layout = Layout(run_dir)
        self.row = 1
        self.root = self.layout.row_root(1)
        self.folder = self.layout.row_folder(1)
        self.problem = {"id": "fixture-F001", "name": "t", "source": "synthetic", "row": 1,
                        "environments": ["primary", "secondary"], "statement": self.statement,
                        "reference": self.reference}
        atomic_json(self.folder / "input/problem.json", self.problem)
        atomic_json(self.folder / "input/route.json", {"golf": {"minutes": 5, "non_improving_stop": 2}})
        (self.folder / "selected.lean").write_text(self.incumbent)
        self.write_final(self.incumbent, 1000)
        atomic_json(self.folder / "summary.json", {"status": "completed", "selected": {"sha256": sha(self.incumbent)},
                                                   "golf": {"origin": "model", "label": "c003", "parent_sha256": None},
                                                   "baseline": {"tokens": 10, "raw_heartbeats": 2000}})
        atomic_json(self.root / "authorization.json", authorization)
        atomic_json(self.root / "ledger.json", {"schema_version": 1, "attempts": {}})
        report = self.report(sha(self.incumbent), estimate)
        report_bytes = json_bytes(report)
        (self.root / "report.json").write_bytes(report_bytes)
        self.published = {"row": 1, "name": "t", "at": "2026-11-04T00:00:00+00:00", "origin": origin,
                          "selected_sha256": sha(self.incumbent), "report_sha256": sha_bytes(report_bytes),
                          "audit_passed": True, "local_score_estimate": estimate, "cost_usd": "1.0", "calls": 3,
                          "status": "completed", "golf": {"accepted": [[]], "selected": "c003"}}
        atomic_json(self.root / "published.json", self.published)
        atomic_json(self.layout.worker_path(1), {"golf": self.published["golf"]})
        save_rowstate(self.layout, RowState(row=1, status=status, score_estimate=estimate,
                                            selected_sha256=sha(self.incumbent)))

    def write_final(self, code, heartbeats):
        final = self.folder / "final"
        final.mkdir(parents=True, exist_ok=True)
        atomic_json(final / "result.json", {"valid": True, "tokens": scoring.count_tokens(code, self.statement),
                                            "environments": {"primary": {"valid": True, "runs": [
                                                {"measurement": {"raw": heartbeats}} for _ in range(3)]}}})
        atomic_json(final / "evaluation-request.json", {"candidate_sha256": sha(code), "problem": self.problem,
                                                        "options": {"repetitions": 3, "trusted_reference": False,
                                                                    "fresh": True}})

    def report(self, digest, estimate, *, passed=True, errors=()):
        return {"audit_passed": passed, "audit_errors": list(errors), "rows": [
            {"row": 1, "name": "t", "status": "completed", "known_cost_usd": "1.0", "calls": 3,
             "selected_sha256": digest, "local_score_estimate": estimate,
             "baseline": {"tokens": 10, "raw_heartbeats": 2000}, "final": {"tokens": 5, "raw_heartbeats": 1000}}]}


class FakeAdapter:
    def __init__(self, fixture):
        self.fixture, self.compiles, self.environments = fixture, 7, ["primary", "secondary"]
        self.ev = type("Ev", (), {"compiler_parallelism": 2})()

    def to_eval(self, result, folder):
        samples = [run["measurement"]["raw"] for run in result["environments"]["primary"]["runs"]]
        return EvalResult(True, result["tokens"], samples[1], {"primary": True}, None, "", str(folder))


class Scripted(regolf.RegolfRow):
    """RegolfRow with every Lean/driver hook replaced; the script says what golf/select/report return."""

    script = {}

    def adapter(self):
        return FakeAdapter(Scripted.script["fixture"])

    def configure(self, packet):
        return {"tool_paths": []}

    def verify_frozen(self):
        if Scripted.script.get("frozen_error"):
            raise ValueError(Scripted.script["frozen_error"])

    def build_report(self):
        reports = Scripted.script["reports"]
        Scripted.script.setdefault("calls", []).append("build_report")
        return reports.pop(0) if len(reports) > 1 else reports[0]


def fake_write_selection(root, row, selection, *, stop_reason=None):
    """write_selection stand-in: selected.lean, a kept final-prev copy and a new final/ receipt."""
    fixture = Scripted.script["fixture"]
    Scripted.script.setdefault("calls", []).append(("write_selection", selection.candidate.sha256))
    folder = fixture.folder
    old = read_json(folder / "final/evaluation-request.json")["candidate_sha256"]
    (folder / "final").rename(folder / f"final-prev-{old[:12]}-{time.time_ns()}")
    fixture.write_final(selection.candidate.code, selection.validated.raw_heartbeats)
    (folder / "selected.lean").write_text(selection.candidate.code)
    return {"status": "completed"}


def golf_result(code, accepted=("G4:drop-have",)):
    screen = EvalResult(True, 3, 500, {"primary": True}, None, "", "")
    best = Candidate(code, sha(code), "golf", sha(Fixture.incumbent), "golf:selected:" + sha(code)[:12], screen)
    return golf.GolfResult(best=best, tried=3, accepted=list(accepted), log=[])


def selection_of(code, score, origin="golf"):
    validated = EvalResult(True, 3, 500, {"primary": True, "secondary": True}, None, "", "/evidence")
    return Selection(Candidate(code, sha(code), origin, None, "x", None), validated, score, True, ("selected", "x"))


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)

    def test_production_row_is_eligible_only_when_terminal_published_and_submittable(self):
        fixture = Fixture(self.run_dir)
        self.assertEqual(regolf.eligibility(fixture.layout, 1), (True, None))
        self.assertEqual(regolf.report_only(fixture.layout, [1, 2])[1]["reason"], "not terminal (status waiting_env)")
        save_rowstate(fixture.layout, RowState(row=1, status="exploring"))
        self.assertIn("not terminal", regolf.eligibility(fixture.layout, 1)[1])
        save_rowstate(fixture.layout, RowState(row=1, status="published"))
        atomic_json(fixture.root / "published.json", {**fixture.published, "origin": "original", "reason": "x"})
        self.assertIn("publishes the original", regolf.eligibility(fixture.layout, 1)[1])
        atomic_json(fixture.root / "published.json", {**fixture.published, "selected_sha256": "0" * 64})
        self.assertIn("selected.lean changed", regolf.eligibility(fixture.layout, 1)[1])
        atomic_json(fixture.root / "published.json", {**fixture.published, "report_sha256": "0" * 64})
        self.assertIn("report.json changed", regolf.eligibility(fixture.layout, 1)[1])

    def test_development_roots_need_the_testing_flag(self):
        for authorization in (OPENAI_DEV, MOCK):
            fixture = Fixture(self.run_dir, authorization=authorization)
            ok, reason = regolf.eligibility(fixture.layout, 1)
            self.assertFalse(ok)
            self.assertIn("development root", reason)
            self.assertEqual(regolf.eligibility(fixture.layout, 1, allow_dev_roots=True), (True, None))

    def test_golf_settings_put_the_whole_budget_on_the_incumbent(self):
        settings = regolf.golf_settings({"golf": {"minutes": 7, "non_improving_stop": 3, "simp_probe": False}}, 24, 30)
        self.assertEqual((settings["top_k"], settings["max_compiles_best"], settings["max_compiles_total"],
                          settings["max_compiles_other"], settings["minutes"], settings["non_improving_stop"]),
                         (1, 24, 24, 0, 30.0, 12))
        self.assertFalse(settings["simp_probe"])
        self.assertEqual(regolf.golf_settings({}, 4, 1)["non_improving_stop"], 4)


class PassTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)
        self.fixture = Fixture(self.run_dir)
        Scripted.script = {"fixture": self.fixture, "reports": [self.fixture.report(sha(Fixture.better), 70.0)]}
        incumbent = Candidate(Fixture.incumbent, sha(Fixture.incumbent), "model", None, "c003",
                              EvalResult(True, 5, 1000, {"primary": True}, None, "", ""))
        original = Candidate(Fixture.reference, sha(Fixture.reference), "original", None, "c000", None)
        self.pool = [incumbent, original]
        self.patches = [patch.object(select, "candidates_from_run", return_value=self.pool),
                        patch.object(select, "write_selection", side_effect=fake_write_selection),
                        patch.object(golf, "improve", return_value=[golf_result(Fixture.better)]),
                        patch.object(select, "select_final", return_value=selection_of(Fixture.better, 70.0))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def run_pass(self, **kwargs):
        return regolf.regolf(self.run_dir, [1], deadline=FAR, row_class=Scripted, **kwargs)["rows"][0]

    def published(self):
        return read_json(self.fixture.root / "published.json")

    def test_publishes_when_the_validated_gain_meets_the_margin(self):
        before = self.published()
        result = self.run_pass()
        self.assertEqual((result["action"], result["incumbent_estimate"], result["regolf_estimate"], result["compiles"]),
                         ("published", 60.0, 70.0, 7), result)
        self.assertEqual(Scripted.script["calls"], [("write_selection", sha(Fixture.better)), "build_report"])
        after = self.published()
        self.assertEqual((after["origin"], after["selected_sha256"], after["local_score_estimate"]),
                         ("openrouter-run", sha(Fixture.better), 70.0))
        self.assertEqual(after["report_sha256"], sha_bytes((self.fixture.root / "report.json").read_bytes()))
        self.assertEqual(after["golf"], before["golf"])
        self.assertEqual((after["regolf"]["previous_sha256"], after["regolf"]["previous_estimate"],
                          after["regolf"]["rolled_back"], after["regolf"]["accepted"]),
                         (sha(Fixture.incumbent), 60.0, False, ["G4:drop-have"]))
        self.assertGreater(after["at"], before["at"])
        self.assertEqual(read_json(self.fixture.root / "report.json")["rows"][0]["selected_sha256"], sha(Fixture.better))
        state = load_rowstate(self.fixture.layout, 1)
        self.assertEqual((state.status, state.selected_sha256, state.score_estimate), ("published", sha(Fixture.better), 70.0))
        self.assertEqual(state.history[-1]["event"], "regolf")
        worker = read_json(self.fixture.layout.worker_path(1))
        self.assertEqual(worker["golf"], before["golf"])
        self.assertEqual([item["action"] for item in worker["regolf"]], ["published"])
        self.assertEqual(len(list((self.fixture.root / "regolf").glob("*.json"))), 1)
        self.assertTrue(list(self.fixture.folder.glob("final-prev-" + sha(Fixture.incumbent)[:12] + "-*")))
        # The selection pool was the incumbent plus the golf winner only.
        pool = select.select_final.call_args.args[2]
        self.assertEqual([c.sha256 for c in pool], [sha(Fixture.incumbent), sha(Fixture.better)])
        self.assertEqual(golf.improve.call_args.args[2][0].label, "c003")
        self.assertEqual(golf.improve.call_args.args[3]["max_compiles_total"], regolf.DEFAULT_COMPILES)
        # The incumbent's text was saved before the publication window, for repair().
        saved = read_json(self.fixture.root / "regolf/incumbents" / (sha(Fixture.incumbent)[:12] + ".json"))
        self.assertEqual((saved["sha256"], saved["code"], saved["label"]), (sha(Fixture.incumbent), Fixture.incumbent, "c003"))
        with patch.object(select, "candidates_from_run", return_value=[]):
            found = regolf.published_candidate(self.fixture.layout, 1, sha(Fixture.incumbent))
        self.assertEqual((found.code, found.origin, found.label), (Fixture.incumbent, "model", "c003"))

    def test_repairs_a_publication_cut_between_write_selection_and_published_json(self):
        # The kill window: write_selection ran for the golf winner, published.json is still the old one.
        fake_write_selection(self.fixture.root, 1, selection_of(Fixture.better, 70.0))
        Scripted.script["calls"] = []
        Scripted.script["reports"] = [self.fixture.report(sha(Fixture.incumbent), 60.0)]
        self.assertIn("selected.lean changed", regolf.eligibility(self.fixture.layout, 1)[1])
        listed = regolf.regolf(self.run_dir, [1], report_only_mode=True, row_class=Scripted)["rows"][0]
        self.assertEqual((listed["eligible"], listed["interrupted"], listed["repairable"], listed["published_sha256"],
                          listed["current_sha256"]), (False, True, True, sha(Fixture.incumbent), sha(Fixture.better)))
        result = self.run_pass()
        self.assertEqual(result["action"], "repaired", result)
        self.assertFalse(golf.improve.called)
        self.assertEqual([call for call in Scripted.script["calls"] if isinstance(call, tuple)],
                         [("write_selection", sha(Fixture.incumbent))])
        self.assertEqual((self.fixture.folder / "selected.lean").read_text(), Fixture.incumbent)
        self.assertEqual(read_json(self.fixture.folder / "final/evaluation-request.json")["candidate_sha256"],
                         sha(Fixture.incumbent))
        after = self.published()
        self.assertEqual((after["origin"], after["selected_sha256"], after["local_score_estimate"]),
                         ("openrouter-run", sha(Fixture.incumbent), 60.0))
        self.assertEqual(after["report_sha256"], sha_bytes((self.fixture.root / "report.json").read_bytes()))
        self.assertEqual((after["regolf"]["repaired"], after["regolf"]["rolled_back"], after["regolf"]["previous_sha256"],
                          after["regolf"]["interrupted_sha256"]), (True, True, sha(Fixture.incumbent), sha(Fixture.better)))
        self.assertEqual(regolf.eligibility(self.fixture.layout, 1), (True, None))
        self.assertEqual(read_json(self.fixture.layout.worker_path(1))["regolf"][-1]["action"], "repaired")
        state = load_rowstate(self.fixture.layout, 1)
        self.assertEqual((state.status, state.selected_sha256), ("published", sha(Fixture.incumbent)))
        # The repaired row is eligible again: the next pass golfs it as usual.
        Scripted.script["reports"] = [self.fixture.report(sha(Fixture.better), 70.0)]
        self.assertEqual(self.run_pass()["action"], "published")
        self.assertEqual(self.published()["selected_sha256"], sha(Fixture.better))

    def test_interrupted_publication_without_kept_evidence_is_reported_not_guessed(self):
        fake_write_selection(self.fixture.root, 1, selection_of(Fixture.better, 70.0))
        for kept in self.fixture.folder.glob("final-prev-*"):
            shutil.rmtree(kept)
        before = self.published()
        result = self.run_pass()
        self.assertEqual(result["action"], "skipped")
        self.assertIn("no kept final-prev evidence", result["reason"])
        self.assertEqual(self.published(), before)
        self.assertEqual((self.fixture.folder / "selected.lean").read_text(), Fixture.better)
        self.assertFalse(golf.improve.called)
        listed = regolf.regolf(self.run_dir, [1], report_only_mode=True, row_class=Scripted)["rows"][0]
        self.assertEqual((listed["interrupted"], listed["repairable"]), (True, False))

    def test_repair_only_never_golfs_an_intact_row(self):
        before = (self.fixture.root / "published.json").read_bytes()
        result = self.run_pass(repair_only=True)
        self.assertEqual((result["action"], result["reason"]), ("skipped", "repair-only: publication intact"))
        self.assertFalse(golf.improve.called)
        self.assertEqual((self.fixture.root / "published.json").read_bytes(), before)
        from lean_agent.final60.__main__ import build_parser
        args = build_parser().parse_args(["regolf", "--run-dir", str(self.run_dir), "--rows", "1", "--repair-only"])
        self.assertTrue(args.repair_only)
        # An interrupted row is repaired and nothing else happens.
        fake_write_selection(self.fixture.root, 1, selection_of(Fixture.better, 70.0))
        Scripted.script["reports"] = [self.fixture.report(sha(Fixture.incumbent), 60.0)]
        self.assertEqual(self.run_pass(repair_only=True)["action"], "repaired")
        self.assertFalse(golf.improve.called)
        self.assertEqual(self.published()["selected_sha256"], sha(Fixture.incumbent))

    def test_keeps_the_incumbent_below_the_margin_and_restores_the_selection_record(self):
        record = self.fixture.folder / "golf/selection.json"
        atomic_json(record, {"selected": {"sha256": sha(Fixture.incumbent)}, "published": True})
        kept = record.read_bytes()
        select.select_final.return_value = selection_of(Fixture.better, 60.2)
        before = (self.fixture.root / "published.json").read_bytes()
        result = self.run_pass(margin=0.25)
        self.assertEqual(result["action"], "kept")
        self.assertIn("margin", result["reason"])
        self.assertEqual((self.fixture.root / "published.json").read_bytes(), before)
        self.assertEqual((self.fixture.folder / "selected.lean").read_text(), Fixture.incumbent)
        self.assertEqual(record.read_bytes(), kept)
        self.assertNotIn("write_selection", [call[0] for call in Scripted.script.get("calls", []) if isinstance(call, tuple)])
        self.assertEqual(read_json(self.fixture.layout.worker_path(1))["regolf"][-1]["action"], "kept")
        # With a smaller margin the same gain publishes.
        self.assertEqual(self.run_pass(margin=0.1)["action"], "published")

    def test_keeps_when_golf_finds_nothing_or_selection_keeps_the_incumbent(self):
        golf.improve.return_value = [golf.GolfResult(best=self.pool[0], tried=4, accepted=[], log=[])]
        result = self.run_pass()
        self.assertEqual((result["action"], result["reason"]), ("kept", "golf found no better variant"))
        self.assertFalse(select.select_final.called)
        golf.improve.return_value = [golf_result(Fixture.better)]
        select.select_final.return_value = selection_of(Fixture.incumbent, 60.0, origin="model")
        result = self.run_pass()
        self.assertEqual((result["action"], result["reason"]), ("kept", "incumbent stays the best validated"))

    def test_rolls_back_when_the_rebuilt_report_disagrees(self):
        Scripted.script["reports"] = [self.fixture.report(sha(Fixture.better), 70.0, passed=False, errors=["F001: x"]),
                                      self.fixture.report(sha(Fixture.incumbent), 60.0)]
        result = self.run_pass()
        self.assertEqual(result["action"], "rolled-back", result)
        self.assertEqual([call for call in Scripted.script["calls"] if isinstance(call, tuple)],
                         [("write_selection", sha(Fixture.better)), ("write_selection", sha(Fixture.incumbent))])
        after = self.published()
        self.assertEqual((after["origin"], after["selected_sha256"], after["local_score_estimate"]),
                         ("openrouter-run", sha(Fixture.incumbent), 60.0))
        self.assertEqual((after["regolf"]["rolled_back"], after["regolf"]["rejected_sha256"], after["regolf"]["audit_errors"]),
                         (True, sha(Fixture.better), ["F001: x"]))
        self.assertEqual((self.fixture.folder / "selected.lean").read_text(), Fixture.incumbent)
        self.assertEqual(read_json(self.fixture.folder / "final/evaluation-request.json")["candidate_sha256"],
                         sha(Fixture.incumbent))
        self.assertEqual(after["report_sha256"], sha_bytes((self.fixture.root / "report.json").read_bytes()))

    def test_skips_rows_that_are_busy_not_terminal_or_frozen_broken(self):
        lock = (self.fixture.root / "worker.lock").open("a+")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = self.run_pass()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        self.assertEqual(result["action"], "skipped")
        self.assertIn("worker holds", result["reason"])
        self.assertFalse(golf.improve.called)
        Scripted.script["frozen_error"] = "Frozen input/implementation changed: x"
        result = self.run_pass()
        self.assertEqual(result["action"], "skipped")
        self.assertIn("frozen code check failed", result["reason"])
        self.assertFalse(golf.improve.called)
        del Scripted.script["frozen_error"]
        # Busy and frozen-check skips happen under the lock of a terminal row and are recorded there.
        self.assertEqual(len(list((self.fixture.root / "regolf").glob("*.json"))), 1)
        self.assertEqual(read_json(self.fixture.layout.worker_path(1))["regolf"][-1]["action"], "skipped")
        save_rowstate(self.fixture.layout, RowState(row=1, status="golfing"))
        self.assertIn("not terminal", self.run_pass()["reason"])
        self.assertFalse(golf.improve.called)
        # A row that is not terminal is never touched: no record, no lock write.
        self.assertEqual(len(list((self.fixture.root / "regolf").glob("*.json"))), 1)
        self.assertEqual(len(read_json(self.fixture.layout.worker_path(1))["regolf"]), 1)

    def test_report_only_lists_eligibility_without_touching_anything(self):
        before = sorted(str(path) for path in self.run_dir.rglob("*"))
        value = regolf.regolf(self.run_dir, [1, 2], report_only_mode=True, row_class=Scripted)
        self.assertTrue(value["report_only"])
        self.assertEqual((value["rows"][0]["eligible"], value["rows"][0]["incumbent_estimate"], value["rows"][0]["busy"]),
                         (True, 60.0, False))
        self.assertFalse(value["rows"][1]["eligible"])
        self.assertEqual(sorted(str(path) for path in self.run_dir.rglob("*")), before)
        self.assertFalse(golf.improve.called)

    def test_errors_inside_the_pass_leave_the_row_untouched(self):
        golf.improve.side_effect = RuntimeError("boom")
        before = (self.fixture.root / "published.json").read_bytes()
        result = self.run_pass()
        self.assertEqual(result["action"], "error")
        self.assertIn("RuntimeError: boom", result["reason"])
        self.assertEqual((self.fixture.root / "published.json").read_bytes(), before)
        self.assertEqual((self.fixture.folder / "selected.lean").read_text(), Fixture.incumbent)

    def test_cli_parser_and_no_time_left(self):
        from lean_agent.final60.__main__ import build_parser
        args = build_parser().parse_args(["regolf", "--run-dir", str(self.run_dir), "--rows", "1,3", "--compiles", "6",
                                          "--margin", "0.5", "--report-only", "--allow-dev-roots"])
        self.assertEqual((args.command, args.rows, args.compiles, args.margin, args.report_only, args.allow_dev_roots),
                         ("regolf", "1,3", 6, 0.5, True, True))
        past = "2020-01-01T00:00:00+00:00"
        result = regolf.regolf(self.run_dir, [1], deadline=past, row_class=Scripted)["rows"][0]
        self.assertEqual((result["action"], result["reason"]), ("skipped", "no time left before the run deadline"))
        self.assertFalse(golf.improve.called)


class EndToEndTests(unittest.TestCase):
    """The driver fixture of test_final60_golf, published like the worker, then regolfed for real."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.layout = Layout(temp.name)
        self.fixture = G.PublicationTests("test_golf_winner_replaces_driver_selection_and_passes_audit")
        with patch.object(tempfile, "TemporaryDirectory", return_value=self.tmp(self.layout.row_root(1))):
            self.fixture.setUp()
        self.root, self.output, self.evaluator = self.fixture.root, self.fixture.output, self.fixture.evaluator
        self.assertEqual(self.root, self.layout.row_root(1))

    @staticmethod
    def tmp(path):
        path.mkdir(parents=True, exist_ok=True)
        return type("T", (), {"name": str(path), "cleanup": lambda self: None})()

    def provenance(self):
        """PR #70 check on the root as published (the report.json regolf wrote, not a rewritten one)."""
        spec = importlib.util.spec_from_file_location("final60_regolf_provenance",
                                                      REPO / "scripts/check_submission_provenance.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        proof = (self.output / "selected.lean").read_text()
        benchmark = [{"name": "test", "statement": self.fixture.statement, "reference": self.fixture.reference}]
        return checker.check(benchmark, [{"name": "test", "proof": proof}], [checker.RunRoot(self.root)], [], [],
                             checker.Decimal("3"))

    def publish_like_worker(self):
        report = self.fixture.report()
        report_bytes = json_bytes(report)
        (self.root / "report.json").write_bytes(report_bytes)
        entry = report["rows"][0]
        code = (self.output / "selected.lean").read_text()
        value = {"row": 1, "name": "test", "at": "2026-11-04T00:00:00+00:00", "origin": "openrouter-run",
                 "selected_sha256": sha(code), "report_sha256": sha_bytes(report_bytes), "audit_passed": True,
                 "local_score_estimate": entry["local_score_estimate"], "golf": {"selected": "driver"}}
        atomic_json(self.root / "published.json", value)
        save_rowstate(self.layout, RowState(row=1, status="published"))
        return value

    def test_regolf_publishes_a_golf_winner_that_passes_audit_and_provenance(self):
        summary = self.fixture.run_driver()
        self.assertEqual(summary["status"], "completed")
        before = self.publish_like_worker()
        fixture = self.fixture

        class Real(regolf.RegolfRow):
            def adapter(self):
                return evaladapter.EvalAdapter(self.root, 1, evaluator=fixture.evaluator, screen_mode="check-measure")

            def configure(self, packet):
                return {}

            def verify_frozen(self):
                pass

            def build_report(self):
                return fixture.report()

        with patch.object(regolf, "load_non_openrouter", return_value=[]):
            result = regolf.regolf(self.layout.run_dir, [1], compiles=8, deadline=FAR, row_class=Real)["rows"][0]
        self.assertEqual(result["action"], "published", result)
        self.assertGreaterEqual(result["regolf_estimate"], result["incumbent_estimate"] + regolf.DEFAULT_MARGIN)
        self.assertGreater(result["compiles"], 0)
        after = read_json(self.root / "published.json")
        self.assertEqual(after["origin"], "openrouter-run")
        self.assertNotEqual(after["selected_sha256"], before["selected_sha256"])
        self.assertEqual(after["selected_sha256"], sha((self.output / "selected.lean").read_text()))
        self.assertEqual(after["report_sha256"], sha_bytes((self.root / "report.json").read_bytes()))
        self.assertEqual(after["regolf"]["previous_sha256"], before["selected_sha256"])
        # The row audit and the PR #70 provenance checker accept the regolfed root as published.
        built = fixture.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual(built["rows"][0]["selected_sha256"], after["selected_sha256"])
        self.assertEqual(json_bytes(built), (self.root / "report.json").read_bytes())
        checked = self.provenance()
        self.assertEqual(checked["errors"], [])
        self.assertEqual(checked["rows"][0]["origin"], str(self.output))
        # The normal golf evidence is there: winners, improve report, selection record marked published.
        self.assertTrue(list((self.output / "golf").glob("improve-*.json")))
        self.assertTrue((self.output / "golf/winners.json").exists())
        selection = read_json(self.output / "golf/selection.json")
        self.assertEqual((selection["selected"]["sha256"], selection["published"]), (after["selected_sha256"], True))
        self.assertTrue(list(self.output.glob("final-prev-" + before["selected_sha256"][:12] + "-*")))
        summary = read_json(self.output / "summary.json")
        self.assertEqual(summary["golf"]["origin"], "golf")
        self.assertEqual(summary["selected"]["sha256"], after["selected_sha256"])
        # A second pass finds nothing new and leaves the publication unchanged.
        bytes_before = (self.root / "published.json").read_bytes()
        with patch.object(regolf, "load_non_openrouter", return_value=[]):
            again = regolf.regolf(self.layout.run_dir, [1], compiles=8, deadline=FAR, row_class=Real)["rows"][0]
        self.assertEqual(again["action"], "kept", again)
        self.assertEqual((self.root / "published.json").read_bytes(), bytes_before)
        self.assertEqual(len(read_json(self.layout.worker_path(1))["regolf"]), 2)


if __name__ == "__main__":
    unittest.main()
