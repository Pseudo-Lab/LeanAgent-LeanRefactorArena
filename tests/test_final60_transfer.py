"""final60 transfer repair: deprecated-alias renames between a row's listed toolchains.

No Lean and no network: the alias-map builder runs on synthetic library sources, the
selection tests use an environment-aware fake adapter, and the provenance test drives the
real select_final/write_selection/report chain on the driver fixture of test_final60_golf
(PublicationTests pattern) with a FixtureEvaluator that fails the secondary toolchain on
the new name only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent.final60 import evaladapter, regolf, scoring, select, transfer
from lean_agent.final60.contracts import Candidate, EvalResult
from lean_agent.final60.orchestrator import Layout, RowState, atomic_json, json_bytes, read_json, save_rowstate, sha_bytes

import test_final60_golf as G
import test_final60_regolf as R

sha = evaladapter.sha
NEW, OLD = "Finset.card_univ_sdiff", "Finset.card_univ_diff"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class SyntheticRepo:
    """A prepared repo with two toolchains: ``new`` (aliases) and ``old`` (old names only)."""

    def __init__(self, root: Path, *, envs=("lib-v4.31.0", "lib-v4.30.0"), old_has=("Finset.card_univ_diff", "Nat.foo_old",
                                                                                     "Nat.keep_old", "Nat.keep_new",
                                                                                     "Foo.Bar.qux_old", "shared")):
        self.root, self.envs = root, list(envs)
        projects = {}
        for index, env in enumerate(self.envs):
            projects[env] = f"sources/final/checkouts/{env}/proj"
        write(root / "configs/final-environments.local.json",
              json.dumps({"schema_version": 1, "environments": {
                  env: {"id": env, "project": projects[env], "revision": "r" + env} for env in self.envs}}))
        new = root / projects[self.envs[0]]
        write(new / "lakefile.toml", "name = \"proj\"\n")
        # The project itself declares a lemma; the Mathlib package (a sibling checkout reached through
        # .lake/packages) holds the aliases, like the prepared ArkLib checkouts.
        write(new / "Proj/Main.lean", "theorem Proj.main : True := trivial\n")
        mathlib = root / f"sources/final/checkouts/{self.envs[0]}/mathlib"
        write(mathlib / "Mathlib/Data/Fintype/Card.lean", "\n".join([
            "/-! A doc block that mentions",
            "end of nothing and namespace Fake -/",
            "namespace Finset",
            "theorem card_univ_sdiff (s : Finset α) : True := trivial  -- renamed lemma",
            "end Finset",
            "@[deprecated (since := \"2026-06-03\")] alias Finset.card_univ_diff := Finset.card_univ_sdiff",
            "namespace Nat",
            "theorem foo_new : True := trivial",
            "@[deprecated (since := \"2026-01-01\")]",
            "alias foo_old := foo_new",
            "theorem keep_new : True := trivial",
            "@[deprecated (since := \"2026-01-01\")] alias keep_old := keep_new   -- NEW exists in old too: excluded",
            "theorem gone_new : True := trivial",
            "@[simp, deprecated (since := \"2026-02-02\")] alias gone_old := gone_new  -- OLD missing in old: excluded",
            "end Nat",
            "namespace Foo.Bar",
            "theorem qux_new : True := trivial",
            "@[deprecated qux_new (since := \"2026-03-03\")]",
            "theorem qux_old : True := qux_new",
            "end Foo.Bar",
            "theorem shared : True := trivial",
            "@[deprecated (since := \"2026-04-04\")] alias shared := shared  -- self alias: excluded",
            "@[deprecated (since := \"2026-05-05\")] alias ⟨iff_a, iff_b⟩ := Iff.rfl",
            ""]))
        packages = new / ".lake/packages"
        packages.mkdir(parents=True, exist_ok=True)
        os.symlink("../../../mathlib", packages / "mathlib")
        for env in self.envs[1:]:
            old = root / projects[env]
            write(old / "lakefile.toml", "name = \"proj\"\n")
            write(old / "Proj/Main.lean", "theorem Proj.main : True := trivial\n")
            lines = []
            for name in old_has:
                namespace, _, short = name.rpartition(".")
                lines += ([f"namespace {namespace}"] if namespace else []) + [f"theorem {short} : True := trivial"] + \
                         ([f"end {namespace}"] if namespace else [])
            write(old / "Lib/Old.lean", "\n".join(lines) + "\n")


class AliasMapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = SyntheticRepo(self.root)

    def test_builds_new_to_old_pairs_that_transfer(self):
        value = transfer.build_alias_map(self.root, self.repo.envs)
        self.assertEqual(value["map"], {NEW: OLD, "Nat.foo_new": "Nat.foo_old", "Foo.Bar.qux_new": "Foo.Bar.qux_old"})
        self.assertEqual(value["counts"]["kept"], 3)
        # Pairs seen in the newest sources: the five alias/theorem forms above (the iff alias is not a rename).
        self.assertEqual(value["counts"]["deprecated_pairs"], 6)
        per = value["counts"]["per_pair"]["lib-v4.30.0"]
        self.assertEqual((per["kept"], per["old_exists"], per["new_missing"]), (3, 4, 4))
        self.assertEqual(value["evidence"][NEW]["missing_in"], ["lib-v4.30.0"])
        self.assertTrue(value["evidence"][NEW]["source"].endswith("Mathlib/Data/Fintype/Card.lean"))

    def test_cache_is_written_once_and_reused(self):
        cache = self.root / "alias-maps"
        first = transfer.load_or_build(self.root, self.repo.envs, cache)
        files = list(cache.glob("alias-map-*.json"))
        self.assertEqual(len(files), 1)
        stamp = files[0].stat().st_mtime_ns
        with patch.object(transfer, "build_alias_map", side_effect=AssertionError("rebuilt")):
            again = transfer.load_or_build(self.root, self.repo.envs, cache)
        self.assertEqual(again["map"], first["map"])
        self.assertEqual(files[0].stat().st_mtime_ns, stamp)
        # Another environment set is another map file; a single toolchain has nothing to transfer.
        single = transfer.load_or_build(self.root, self.repo.envs[:1], cache)
        self.assertEqual(single["map"], {})
        self.assertEqual(len(list(cache.glob("alias-map-*.json"))), 2)
        # The cache lives next to rows/ of a final60 run dir, else under the row root.
        self.assertEqual(transfer.cache_dir_for(self.root / "run/rows/F036"), self.root / "run/alias-maps")
        self.assertEqual(transfer.cache_dir_for(self.root / "legacy"), self.root / "legacy/alias-maps")
        with patch.dict(os.environ, {"FINAL60_ALIAS_MAP_DIR": str(self.root / "shared")}):
            self.assertEqual(transfer.cache_dir_for(self.root / "run/rows/F036"), self.root / "shared")

    def test_warning_as_error_is_read_from_the_lakefile(self):
        self.assertFalse(transfer.warning_as_error(self.root, self.repo.envs[0]))
        project = transfer.project_dir(self.root, self.repo.envs[0])
        (project / "lakefile.toml").write_text("name = \"proj\"\n[leanOptions]\nwarningAsError = true\n")
        self.assertTrue(transfer.warning_as_error(self.root, self.repo.envs[0]))
        self.assertFalse(transfer.warning_as_error(self.root, "missing-env"))

    def test_scan_file_tracks_namespaces_sections_and_comments(self):
        text = "\n".join(["namespace A", "section", "/- theorem fake : True := trivial", "-/ theorem real : True := trivial",
                          "-- theorem commented : True := trivial", "end", "theorem B.c : True := trivial",
                          "theorem _root_.top : True := trivial", "end A", "theorem last : True := trivial", ""])
        found = [(transfer.qualify(ns, name), kw) for ns, attr, kw, name, rest in transfer.scan_file(text)]
        self.assertEqual(found, [("A.real", "theorem"), ("A.B.c", "theorem"), ("top", "theorem"), ("last", "theorem")])
        self.assertEqual(transfer.candidates("A.B", "x"), ["A.B.x", "A.x", "x"])


class SubstitutionTests(unittest.TestCase):
    statement = "theorem t : True"

    def test_replaces_identifiers_outside_comments_and_strings_only(self):
        code = (self.statement + " := by\n  -- Finset.card_univ_sdiff in a comment\n  /- Finset.card_univ_sdiff -/\n"
                "  have h := Finset.card_univ_sdiff s\n  rw [card_univ_sdiff, s.card_univ_sdiff, Finset.card_univ_sdiff']\n"
                "  trace \"Finset.card_univ_sdiff\"\n  exact Finset.card_univ_sdiff_other\n")
        fixed, edits = transfer.substitute(code, self.statement, {NEW: OLD})
        self.assertEqual(fixed, (self.statement + " := by\n  -- Finset.card_univ_sdiff in a comment\n  /- Finset.card_univ_sdiff -/\n"
                                 "  have h := Finset.card_univ_diff s\n  rw [card_univ_diff, s.card_univ_diff, Finset.card_univ_sdiff']\n"
                                 "  trace \"Finset.card_univ_sdiff\"\n  exact Finset.card_univ_sdiff_other\n"))
        self.assertEqual([(edit["from"], edit["to"]) for edit in edits],
                         [(NEW, OLD), ("card_univ_sdiff", "card_univ_diff"), ("s.card_univ_sdiff", "s.card_univ_diff")])
        self.assertTrue(fixed.startswith(self.statement))
        self.assertEqual(scoring.count_tokens(fixed, self.statement), scoring.count_tokens(code, self.statement))
        # The statement is never touched, even when it mentions the name.
        statement = "theorem t (h : Finset.card_univ_sdiff = 0) : True"
        fixed, edits = transfer.substitute(statement + " := by\n  exact Finset.card_univ_sdiff\n", statement, {NEW: OLD})
        self.assertTrue(fixed.startswith(statement))
        self.assertEqual(len(edits), 1)
        # Different namespaces: a suffix spelling is replaced by the full old name.
        fixed, _ = transfer.substitute(self.statement + " := by\n  exact foo_new\n", self.statement, {"Nat.foo_new": "Int.foo_old"})
        self.assertEqual(fixed, self.statement + " := by\n  exact Int.foo_old\n")
        self.assertEqual(transfer.substitute(self.statement + " := by\n  trivial\n", self.statement, {NEW: OLD})[1], [])

    def test_repair_text_applies_the_static_rules(self):
        parent = Candidate(self.statement + " := by\n  exact Finset.card_univ_sdiff\n", "x", "model", None, "c1", None)
        fixed, edits, rejection = transfer.repair_text(parent, self.statement, {NEW: OLD})
        self.assertEqual((rejection, len(edits)), (None, 1))
        self.assertEqual(fixed, self.statement + " := by\n  exact Finset.card_univ_diff\n")
        repaired = transfer.repair_candidate(parent, fixed)
        self.assertEqual((repaired.origin, repaired.parent_sha256, repaired.label, repaired.sha256), ("golf", "x", "repair:c1", sha(fixed)))
        bad = Candidate(self.statement + " := by\n  exact Finset.card_univ_sdiff\n  sorry\n", "y", "model", None, "c2", None)
        self.assertIsNone(transfer.repair_text(bad, self.statement, {NEW: OLD})[0])
        self.assertIn("sorry", transfer.repair_text(bad, self.statement, {NEW: OLD})[2])
        self.assertEqual(transfer.repair_text(parent, self.statement, {"other": "x"})[2], "no identifier to replace")


def log_for(code: str, env: str, *, names=(NEW,)) -> str:
    """A check log with one unknown-constant error per unknown name (v4.31 and older formats)."""
    lines = []
    for index, name in enumerate(names):
        if index % 2 == 0:
            lines.append(f"/x/{env}/check.lean:578:16: error(lean.unknownIdentifier): Unknown constant `{name}`")
        else:
            lines.append(f"/x/{env}/check.lean:580:4: error: unknown identifier '{name}'")
    lines.append("/x/check.lean:578:4: error: Type mismatch: After simplification, term\n  foo\n has type\n  bar")
    return "\n".join(lines) + "\n"


class TriggerTests(unittest.TestCase):
    def test_unknown_names_from_both_message_formats(self):
        self.assertEqual(transfer.unknown_names(log_for("", "s", names=(NEW, "Nat.foo_new", NEW))), [NEW, "Nat.foo_new"])
        self.assertEqual(transfer.unknown_names("/x/check.lean:1:1: warning: unknown identifier 'x' in a warning\n"), [])
        self.assertEqual(transfer.unknown_names(""), [])

    def test_plan_requires_primary_pass_and_fully_mapped_unknowns(self):
        alias_map = {NEW: OLD}
        failed = EvalResult(False, 10, None, {"p": True, "s": False}, "compile", "x", "")
        logs = {"s": (log_for("", "s"), "src")}
        self.assertEqual(transfer.plan(failed, "p", logs, alias_map),
                         {"envs": ["s"], "names": {"s": [NEW]}, "mapping": {NEW: OLD}})
        # An unknown name outside the map, a failing primary, a missing log, or no unknown error: no plan.
        self.assertIsNone(transfer.plan(failed, "p", {"s": (log_for("", "s", names=(NEW, "Other.x")), "src")}, alias_map))
        self.assertIsNone(transfer.plan(EvalResult(False, 10, None, {"p": False, "s": False}, "compile", "", ""), "p", logs, alias_map))
        self.assertIsNone(transfer.plan(failed, "p", {}, alias_map))
        self.assertIsNone(transfer.plan(failed, "p", {"s": ("/x/check.lean:1:1: error: type mismatch\n", "src")}, alias_map))
        self.assertIsNone(transfer.plan(EvalResult(True, 10, 5, {"p": True, "s": True}, None, "", ""), "p", logs, alias_map))
        self.assertIsNone(transfer.plan(failed, "p", logs, {}))
        # Three toolchains: every failing one must be repairable.
        wide = EvalResult(False, 10, None, {"p": True, "s": False, "t": False}, "compile", "", "")
        self.assertIsNone(transfer.plan(wide, "p", logs, alias_map))
        both = {"s": (log_for("", "s"), ""), "t": (log_for("", "t", names=("Nat.foo_new",)), "")}
        self.assertEqual(transfer.plan(wide, "p", both, {NEW: OLD, "Nat.foo_new": "Nat.foo_old"})["envs"], ["s", "t"])


class PartialAdapter(G.FakeAdapter):
    """FakeAdapter whose secondary toolchain rejects texts containing the new name (with a check log)."""

    def __init__(self, statement, reference, *, alias_map=None, hb=10):
        super().__init__(statement, reference, lambda code: (True, hb), environments=["p", "s"])
        self.alias_map = alias_map if alias_map is not None else {NEW: OLD}
        self.hb = hb

    def transfers(self, code):
        return NEW not in code

    def validate(self, code, label, *, as_final=False):
        self.validations.append(label)
        ok = self.transfers(code)
        envs = {"p": True, "s": ok}
        return EvalResult(ok, self.tokens(code), self.hb if ok else None, envs, None if ok else "compile",
                          "" if ok else "error", str(self.folder / ("v-" + sha(code)[:8])))

    def version_logs(self, code):
        if self.transfers(code):
            return {"p": ("", code), "s": ("", code)}
        return {"p": ("", code), "s": (log_for(code, "s"), code)}


class SelectionTests(unittest.TestCase):
    statement = "theorem t : True"
    reference = statement + " := by\n  have h : True := trivial\n  have g : True := trivial\n  exact h\n"
    broken = statement + " := by\n  exact Finset.card_univ_sdiff\n"
    repaired = statement + " := by\n  exact Finset.card_univ_diff\n"

    def problem(self, source="arklib"):
        return {"statement": self.statement, "reference": self.reference, "environments": ["p", "s"], "source": source}

    def test_select_final_repairs_a_transfer_failure_and_records_provenance(self):
        adapter = PartialAdapter(self.statement, self.reference)
        pool = [G.candidate(self.broken, "model", "c1", adapter), G.candidate(self.reference, "original", "c000", adapter)]
        selection = select.select_final(adapter, self.problem(), pool)
        self.assertTrue(selection.beat_original)
        self.assertEqual(selection.candidate.code, self.repaired)
        self.assertEqual((selection.candidate.origin, selection.candidate.label, selection.candidate.parent_sha256),
                         ("golf", "repair:c1", sha(self.broken)))
        self.assertEqual(adapter.validations, ["c1", "repair:c1"])
        self.assertEqual(list(selection.considered), ["c1", "repair:c1"])
        record = json.loads((adapter.golf_dir / "selection.json").read_text())
        self.assertEqual(record["selected"]["label"], "repair:c1")
        entry = record["repairs"][0]
        self.assertEqual((entry["label"], entry["parent_sha256"], entry["envs"], entry["mapping"], entry["valid"]),
                         ("repair:c1", sha(self.broken), ["s"], {NEW: OLD}, True))
        self.assertEqual([(edit["from"], edit["to"]) for edit in entry["edits"]], [(NEW, OLD)])
        self.assertEqual(record["validation_errors"][0]["label"], "c1")
        # Persisted like a golf winner: candidates_from_run would offer it again.
        winners = json.loads((adapter.golf_dir / "winners.json").read_text())["winners"]
        self.assertEqual((winners[0]["label"], winners[0]["parent_sha256"], winners[0]["accepted"]),
                         ("repair:c1", sha(self.broken), [f"repair:{NEW}->{OLD}"]))
        self.assertEqual((adapter.golf_dir / "winners" / winners[0]["code_path"]).read_text(), self.repaired)
        from lean_agent.final60 import golf
        loaded = golf.load_winners(adapter.golf_dir)
        self.assertEqual([(c.label, c.origin, c.code) for c in loaded], [("repair:c1", "golf", self.repaired)])

    def test_repairs_are_bounded_and_skip_unmapped_failures(self):
        adapter = PartialAdapter(self.statement, self.reference, alias_map={})
        pool = [G.candidate(self.broken, "model", "c1", adapter)]
        selection = select.select_final(adapter, self.problem(), pool)
        self.assertEqual(selection.candidate.origin, "original")
        self.assertEqual(adapter.validations, ["c1", "c000"])
        self.assertEqual(json.loads((adapter.golf_dir / "selection.json").read_text())["repairs"], [])
        adapter = PartialAdapter(self.statement, self.reference)
        variants = [self.statement + " := by\n  exact " + "(id " * i + "Finset.card_univ_sdiff" + ")" * i + "\n" for i in range(3)]
        pool = [G.candidate(text, "model", f"c{i}", adapter) for i, text in enumerate(variants, 1)]
        selection = select.select_final(adapter, self.problem(), pool, repairs=1)
        self.assertEqual(selection.candidate.label, "repair:c1")
        self.assertEqual(adapter.validations, ["c1", "repair:c1"])   # c2/c3 cannot beat the repaired estimate
        self.assertEqual(select.select_final(PartialAdapter(self.statement, self.reference), self.problem(), pool,
                                             repairs=0).candidate.origin, "original")

    def test_warning_as_error_and_warning_gate_skip_the_repair(self):
        # Strata rows are gated (FINAL60_WARNING_GATE reject by default): never repaired.
        adapter = PartialAdapter(self.statement, self.reference)
        pool = [G.candidate(self.broken, "model", "c1", adapter)]
        selection = select.select_final(adapter, self.problem(source="strata"), pool)
        self.assertEqual((selection.candidate.origin, adapter.validations), ("original", ["c1", "c000"]))
        with patch.dict(os.environ, {"FINAL60_WARNING_GATE": "demote"}):
            adapter = PartialAdapter(self.statement, self.reference)
            selection = select.select_final(adapter, self.problem(source="strata"), [G.candidate(self.broken, "model", "c1", adapter)])
        self.assertEqual(selection.candidate.origin, "original")
        with patch.dict(os.environ, {"FINAL60_WARNING_GATE": "off"}):
            adapter = PartialAdapter(self.statement, self.reference)
            selection = select.select_final(adapter, self.problem(source="strata"), [G.candidate(self.broken, "model", "c1", adapter)])
        self.assertEqual(selection.candidate.label, "repair:c1")
        # A primary checkout that sets warningAsError blocks the repair on any source.
        adapter = PartialAdapter(self.statement, self.reference)
        with patch.object(transfer, "warning_as_error", return_value=True):
            adapter.d = type("D", (), {"REPO": "/nonexistent"})()
            self.assertEqual(transfer.gate_blocks(adapter, self.problem()), "primary checkout sets warningAsError")
            selection = select.select_final(adapter, self.problem(), [G.candidate(self.broken, "model", "c1", adapter)])
        self.assertEqual(selection.candidate.origin, "original")

    def test_golf_parents_skip_known_transfer_failures_unless_repaired(self):
        adapter = PartialAdapter(self.statement, self.reference)
        other = self.statement + " := by\n  exact trivial\n"
        pool = [G.candidate(self.broken, "model", "c1", adapter), G.candidate(other, "model", "c2", adapter),
                G.candidate(self.reference, "original", "c000", adapter)]
        # No saved all-version check: every parent is kept as before.
        self.assertEqual([c.label for c in select.golf_parents(adapter, self.problem(), pool, 2)], ["c1", "c2"])
        # A saved failing check (the driver's skipped.json + result) turns c1 into its validated repair.
        base = adapter.folder / "compatibility" / sha(self.broken)
        base.mkdir(parents=True)
        (base / "result.json").write_text(json.dumps({"valid": False, "tokens": 5, "environments": {
            "p": {"valid": True, "runs": [], "error": None}, "s": {"valid": False, "runs": [], "error": {"kind": "compile", "message": "x"}}}}))
        (base / "skipped.json").write_text(json.dumps({"rank": 0, "reason": "not all-version compatible (skip)"}))
        adapter.to_eval = lambda result, folder: EvalResult(False, 5, None, {e: v["valid"] for e, v in result["environments"].items()},
                                                            "compile", "x", str(folder))
        parents = select.golf_parents(adapter, self.problem(), pool, 2)
        self.assertEqual([(c.label, c.origin, c.code) for c in parents], [("repair:c1", "golf", self.repaired), ("c2", "model", other)])
        self.assertIsNotNone(parents[0].screen)
        self.assertEqual(adapter.validations, ["repair:c1"])
        self.assertEqual(transfer.compat_status(adapter.folder, sha(self.broken)), "invalid")
        self.assertEqual(transfer.compat_status(adapter.folder, sha(other)), "unknown")
        # Unrepairable (no alias): the known failure is simply not golfed; a budget of 0 skips it too.
        adapter.alias_map = {}
        self.assertEqual([c.label for c in select.golf_parents(adapter, self.problem(), pool, 2)], ["c2", "c000"])
        self.assertEqual([c.label for c in select.golf_parents(adapter, self.problem(), pool, 2, repairs=0)], ["c2", "c000"])
        # An environment failure of the saved check says nothing about the text: kept.
        (base / "result.json").write_text(json.dumps({"valid": False, "tokens": 5, "environments": {
            "p": {"valid": False, "runs": [], "error": {"kind": "environment", "message": "x"}}}}))
        self.assertEqual(transfer.compat_status(adapter.folder, sha(self.broken)), "unknown")


class PartialFixtureEvaluator(G.FixtureEvaluator):
    """The driver-fixture evaluator, failing the secondary toolchain on the new name with a real log."""

    def __init__(self):
        super().__init__(lambda code: ("BROKEN" not in code, 1000 * scoring.count_tokens(code, PublicationTests.statement)),
                         log_for=lambda code, env: log_for(code, env) if (env == "secondary" and NEW in code)
                         else "Synthetic evidence; Lean was not invoked.")

    def evaluate(self, code, problem, path, **kwargs):
        result = super().evaluate(code, problem, path, **kwargs)
        if kwargs.get("all_versions") and NEW in code and result["valid"]:
            env = result["environments"]["secondary"]
            env.update(valid=False, error={"kind": "compile", "message": "error: Unknown constant `" + NEW + "`"})
            env["runs"] = env["runs"][:1]
            env["runs"][0]["returncode"] = 1
            result.update(valid=False, error={"kind": "lean", "message": "One or more required environments failed"})
            (Path(path) / "result.json").write_text(json.dumps(result))
        return result


class PublicationTests(unittest.TestCase):
    """The repaired finalist is published, audited and certified like a golf winner."""

    statement = G.PublicationTests.statement

    def setUp(self):
        self.fixture = G.PublicationTests("test_golf_winner_replaces_driver_selection_and_passes_audit")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.output = self.fixture.root, self.fixture.output

    def test_repaired_finalist_passes_report_audit_and_provenance(self):
        summary = self.fixture.run_driver()
        self.assertEqual(summary["status"], "completed")
        evaluator = PartialFixtureEvaluator()
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=evaluator, screen_mode="check-measure")
        adapter.alias_map = {NEW: OLD}
        broken = self.statement + " := by\n  exact (Finset.card_univ_sdiff : True)\n"
        pool = [Candidate(broken, sha(broken), "model", None, "c009", adapter.screen(broken, "c009"))] + \
            select.candidates_from_run(self.root, 1)
        self.assertTrue(pool[0].screen.valid)
        selection = select.select_final(adapter, self.fixture.problem, pool)
        self.assertEqual(selection.candidate.label, "repair:c009")
        self.assertEqual(selection.candidate.code, self.statement + " := by\n  exact (Finset.card_univ_diff : True)\n")
        self.assertTrue(selection.beat_original)
        self.assertEqual(adapter.version_logs(broken)["secondary"][0], log_for(broken, "secondary"))
        published = select.write_selection(self.root, 1, selection)
        self.assertEqual((published["golf"]["origin"], published["golf"]["label"], published["golf"]["parent_sha256"]),
                         ("golf", "repair:c009", sha(broken)))
        self.assertEqual(published["selected"]["sha256"], selection.candidate.sha256)
        built = self.fixture.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual(built["rows"][0]["selected_sha256"], selection.candidate.sha256)
        checked = self.fixture.provenance(built)
        self.assertEqual(checked["errors"], [])
        self.assertEqual(checked["rows"][0]["origin"], str(self.output))
        record = read_json(self.output / "golf/selection.json")
        self.assertEqual((record["published"], record["repairs"][0]["valid"]), (True, True))
        self.assertEqual([c.label for c in select.candidates_from_run(self.root, 1) if c.origin == "golf"], ["repair:c009"])


class RegolfTransferTests(unittest.TestCase):
    """``regolf --transfer-repair`` on a published row of the driver fixture (no Lean)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.layout = Layout(temp.name)
        self.fixture = G.PublicationTests("test_golf_winner_replaces_driver_selection_and_passes_audit")
        with patch.object(tempfile, "TemporaryDirectory", return_value=R.EndToEndTests.tmp(self.layout.row_root(1))):
            self.fixture.setUp()
        self.root, self.output = self.fixture.root, self.fixture.output

    def publish_original(self):
        """Publish the original like the worker does when nothing validated above the margin."""
        report = self.fixture.report()
        report_bytes = json_bytes(report)
        (self.root / "report.json").write_bytes(report_bytes)
        code = (self.output / "selected.lean").read_text()
        value = {"row": 1, "name": "test", "at": "2026-11-04T00:00:00+00:00", "origin": "original",
                 "selected_sha256": sha(code), "report_sha256": sha_bytes(report_bytes), "audit_passed": True,
                 "local_score_estimate": scoring.ORIGINAL_SCORE, "reason": "no validated improvement", "golf": {"selected": "c000"}}
        atomic_json(self.root / "published.json", value)
        save_rowstate(self.layout, RowState(row=1, status="published"))
        return value

    def test_transfer_repair_publishes_the_repaired_candidate_of_an_original_row(self):
        self.fixture.run_driver()
        fixture, statement = self.fixture, self.fixture.statement
        broken = statement + " := by\n  exact (Finset.card_univ_sdiff : True)\n"
        # The row published the original; the driver's own all-version check recorded the transfer failure.
        evaluator = PartialFixtureEvaluator()
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=evaluator, screen_mode="check-measure")
        adapter.alias_map = {NEW: OLD}
        original = select.candidates_from_run(self.root, 1)[-1]
        self.assertEqual(original.origin, "original")
        checked = adapter.validate(broken, "c009")
        self.assertEqual((checked.valid, checked.envs), (False, {"primary": True, "secondary": False}))
        state = read_json(self.output / "state.json")
        state["exploration"]["candidates"]["c009"] = {**state["exploration"]["candidates"]["c001"], "code": broken,
                                                      "sha256": sha(broken), "valid": True, "step": 9,
                                                      "tokens": scoring.count_tokens(broken, statement),
                                                      "raw_heartbeats": 1000 * scoring.count_tokens(broken, statement)}
        atomic_json(self.output / "state.json", state)
        selection = select.select_final(adapter, fixture.problem, [original], repairs=0)
        select.write_selection(self.root, 1, selection)
        before = self.publish_original()
        self.assertEqual(regolf.eligibility(self.layout, 1)[1][:22], "publishes the original")
        self.assertEqual(regolf.eligibility(self.layout, 1, allow_original=True), (True, None))

        class Real(regolf.RegolfRow):
            def adapter(self):
                value = evaladapter.EvalAdapter(self.root, 1, evaluator=evaluator, screen_mode="check-measure")
                value.alias_map = {NEW: OLD}
                return value

            def configure(self, packet):
                return {}

            def verify_frozen(self):
                pass

            def build_report(self):
                return fixture.report()

        with patch.object(regolf, "load_non_openrouter", return_value=[]):
            listed = regolf.regolf(self.layout.run_dir, [1], report_only_mode=True, transfer_repair=True, row_class=Real)
            self.assertTrue(listed["rows"][0]["eligible"])
            result = regolf.regolf(self.layout.run_dir, [1], deadline=R.FAR, row_class=Real, transfer_repair=True)["rows"][0]
        self.assertEqual((result["action"], result["mode"], result["label"]), ("published", "transfer-repair", "repair:c009"), result)
        self.assertGreaterEqual(result["regolf_estimate"], scoring.ORIGINAL_SCORE + regolf.DEFAULT_MARGIN)
        self.assertEqual(result["repairs"][0]["label"], "repair:c009")
        after = read_json(self.root / "published.json")
        self.assertEqual((after["origin"], after["regolf"]["previous_sha256"]), ("openrouter-run", before["selected_sha256"]))
        self.assertEqual(after["selected_sha256"], sha((self.output / "selected.lean").read_text()))
        self.assertEqual((self.output / "selected.lean").read_text(), statement + " := by\n  exact (Finset.card_univ_diff : True)\n")
        built = fixture.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual(json_bytes(built), (self.root / "report.json").read_bytes())
        # A second pass has nothing left to repair.
        with patch.object(regolf, "load_non_openrouter", return_value=[]):
            again = regolf.regolf(self.layout.run_dir, [1], deadline=R.FAR, row_class=Real, transfer_repair=True)["rows"][0]
        self.assertEqual((again["action"], again["reason"]), ("kept", "no transfer failure repaired"))
        # The PR #70 provenance checker certifies the published root (this helper rewrites report.json; last).
        self.assertEqual(fixture.provenance(built)["errors"], [])

    def test_cli_flag(self):
        from lean_agent.final60.__main__ import build_parser
        args = build_parser().parse_args(["regolf", "--run-dir", "x", "--rows", "36,38", "--transfer-repair", "--allow-dev-roots"])
        self.assertTrue(args.transfer_repair)


if __name__ == "__main__":
    unittest.main()
