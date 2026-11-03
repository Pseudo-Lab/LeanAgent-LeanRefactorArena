"""final60 golf component: scoring, static rules, rewrites, golf, selection and publication.

No network and no Lean, except the opt-in real-Lean check (FINAL60_REAL_LEAN=1).
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from lean_agent.final60 import evaladapter, golf, rewrites as rw, rules, scoring, select
from lean_agent.final60.contracts import Candidate, EvalResult, Selection

REPO = Path(__file__).resolve().parents[1]
d = evaladapter.driver()


def sha(text):
    return evaladapter.sha(text)


def at(code, needle, nth=0):
    """(1-based line, 0-based column) of the nth occurrence of needle in code."""
    index = -1
    for _ in range(nth + 1):
        index = code.index(needle, index + 1)
    return code.count("\n", 0, index) + 1, index - (code.rfind("\n", 0, index) + 1)


class ScoringTests(unittest.TestCase):
    def test_reproduces_dashboard_f001(self):
        self.assertAlmostEqual(scoring.problem_score(85, 258508, 3, 3, 224, 4182543), 85.29, places=2)

    def test_original_and_failures(self):
        self.assertAlmostEqual(scoring.problem_score(224, 4182543, 3, 3, 224, 4182543), 100 / 3)
        self.assertEqual(scoring.problem_score(10, 10, 0, 2, 224, 4182543), 0.0)
        self.assertAlmostEqual(scoring.problem_score(224, 4182543, 1, 2, 224, 4182543), 50 / 3)
        # Negative axes are not clipped (official formula shows no clipping).
        self.assertLess(scoring.problem_score(448, 8365086, 1, 1, 224, 4182543), 0)

    def test_bounds_and_improvement(self):
        self.assertAlmostEqual(scoring.max_possible(224, 224), 200 / 3)
        self.assertGreaterEqual(scoring.max_possible(100, 224), scoring.screen_score(100, 1, 224, 4182543))
        self.assertTrue(scoring.improves(40.0, 39.9))
        self.assertFalse(scoring.improves(40.0, 40.0))
        with self.assertRaises(ValueError):
            scoring.problem_score(1, 1, 1, 1, 0, 1)

    def test_arena_tokenizer(self):
        statement = "theorem t : True"
        self.assertEqual(scoring.count_tokens(statement + " := by trivial", statement), 2)
        self.assertEqual(scoring.count_tokens(statement + " := by\n  -- comment\n  trivial", statement), 2)
        # The empty remainder of a line ending in ":=" is one phantom token (official code).
        self.assertEqual(scoring.count_tokens(statement + " :=\n  by\n  trivial", statement), 3)

    def test_self_check(self):
        statement = "theorem t : True"
        rows = [{"name": "ok", "statement": statement, "src": statement + " := by trivial", "proof_length": 2},
                {"name": "off", "statement": statement, "src": statement + " := by trivial", "proof_length": 99}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rows.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            report = scoring.self_check(path)
        self.assertEqual(report["rows"], 2)
        self.assertEqual(report["mismatches"], [{"row": 2, "name": "off", "official": 99, "local": 2}])
        dataset = REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"
        if dataset.exists():  # gitignored; 60/60 reproduced on 2026-11-04
            report = scoring.self_check(dataset)
            self.assertEqual(report["rows"], 60)
            self.assertEqual(report["mismatches"], [])


class RulesTests(unittest.TestCase):
    statement = "theorem t : True"

    def proof(self, body):
        return self.statement + " := by\n  " + body

    def test_clean_proof_and_comments(self):
        self.assertEqual(rules.check_static(self.proof("trivial"), self.statement), [])
        self.assertEqual(rules.check_static(self.proof("trivial -- sorry admit #eval"), self.statement), [])

    def test_every_official_pattern(self):
        samples = {"#eval": "#eval 1", "#reduce": "#reduce 1", "IO": "exact (IO.println 1)",
                   "unsafe def/fun/theorem": "exact (unsafe fun x => x)", "extern": "extern",
                   "initialize": "initialize", "@[implemented_by]": "@[implemented_by f]", "@[extern]": "@[extern x]",
                   "sorry": "sorry", "sorryAx": "exact sorryAx _", "admit": "admit", "axiom": "axiom",
                   "native_decide": "native_decide", "ofReduceBool": "exact ofReduceBool",
                   "ofReduceNat": "exact ofReduceNat", "run_cmd": "run_cmd", "run_elab": "run_elab",
                   "run_tac": "run_tac", "by_elab": "by_elab", "run_meta": "run_meta", "simproc": "simproc",
                   "eval%": "exact eval% 1", "unsafe IO": "unsafeIO", "decide +native": "decide +native",
                   "#exit": "#exit", "#count_heartbeats": "#count_heartbeats", "attribute command": "\nattribute [simp] t",
                   "macro/elab/notation": "notation", "deriving instance": "deriving instance",
                   "auxiliary declaration": "\ndef helper := 1"}
        for label, pattern in rules._FORBIDDEN_PATTERNS:
            with self.subTest(label=label):
                snippet = samples[label]
                self.assertTrue(pattern.search(snippet), label)
                self.assertTrue(rules.check_static(self.proof(snippet), self.statement), label)
                self.assertIsNotNone(rules.official_rejection(self.proof(snippet)))

    def test_heartbeat_identifiers(self):
        self.assertIn("heartbeat", rules.official_rejection(self.proof("exact getNumHeartbeats")))
        self.assertEqual(rules.official_rejection(self.proof("exact IO.getNumHeartbeats")), "IO")
        self.assertIsNone(rules.official_rejection(self.proof("simp (config := {maxHeartbeats := 9})")))

    def test_pr64_rules(self):
        top = rules.check_static(self.proof("trivial\ntheorem extra : True := trivial"), self.statement)
        self.assertTrue(any("extra top-level command: theorem" in issue for issue in top))
        unsafe = rules.check_static(self.proof("exact unsafe_thing"), self.statement)
        self.assertEqual(unsafe, [])  # word boundary: unsafe_thing is an identifier
        flagged = rules.check_static(self.proof("unsafe trivial"), self.statement)
        self.assertTrue(any("unsafe outside" in issue for issue in flagged))
        allowed = rules.check_static(self.proof("aesop (add unsafe 50% apply And.intro)"), self.statement)
        self.assertFalse(any("unsafe" in issue for issue in allowed))

    def test_statement_and_policy(self):
        self.assertTrue(rules.check_static("theorem u : True := by trivial", self.statement))
        self.assertTrue(any(issue.startswith("policy:") for issue in
                            rules.check_static(self.statement + " := trivial", self.statement)))
        self.assertTrue(rules.check_static(self.proof("set_option maxRecDepth 10 in trivial"), self.statement))


class LinterEditTests(unittest.TestCase):
    statement = "theorem t (h : a = b) : P"

    def code(self, body):
        return self.statement + " := by\n" + body

    def warn(self, code, needle, text, nth=0, offset=0):
        line, col = at(code, needle, nth)
        return f"/tmp/x/check.lean:{line + offset}:{col}: warning: {text}\n"

    def test_unused_simp_argument_pr63_format(self):
        code = self.code("  simp only [foo, bar, baz] at h\n  exact h\n")
        log = ("/tmp/x/check.lean:1:0: warning: unrelated\n" +
               self.warn(code, "bar", "This simp argument is unused:\n  bar\n\nHint: Omit it from the simp argument list."))
        edits = rw.linter_edits(code, self.statement, log, 1)
        self.assertEqual(edits, [("G1:unused-simp-arg", self.code("  simp only [foo, baz] at h\n  exact h\n"))])

    def test_simp_argument_positions(self):
        cases = [("  simp only [foo, ← bar]\n", "bar", "  simp only [foo]\n"),
                 ("  simp [foo]\n", "foo", "  simp\n"),
                 ("  simp only [foo,\n    bar]\n", "bar", "  simp only [foo]\n"),
                 ("  simp only [f (g x), bar]\n", "f (g", "  simp only [bar]\n")]
        for body, needle, expected in cases:
            with self.subTest(body=body):
                code = self.code(body)
                log = self.warn(code, needle, "This simp argument is unused:\n  " + needle)
                self.assertEqual([new for _, new in rw.linter_edits(code, self.statement, log, 1)], [self.code(expected)])

    def test_offset_window_and_other_warnings(self):
        code = self.code("  have h2 : a = a := rfl\n  skip\n  simp only [foo, bar]\n")
        # The compiled file has 10 prefix lines before the declaration.
        log = (self.warn(code, "h2", "unused variable `h2`\n\nNote: This linter can be disabled with `set_option linter.unusedVariables false`", offset=10) +
               self.warn(code, "skip", "'skip' tactic does nothing\n\nNote: This linter can be disabled", offset=10) +
               self.warn(code, "bar", "This simp argument is unused:\n  bar", offset=0))  # outside window
        names = sorted(name for name, _ in rw.linter_edits(code, self.statement, log, 11))
        self.assertEqual(names, ["G1:anonymous-have", "G1:drop-unused-have", "G1:unused-tactic"])
        variants = dict((name, new) for name, new in rw.linter_edits(code, self.statement, log, 11))
        self.assertEqual(variants["G1:drop-unused-have"], self.code("  skip\n  simp only [foo, bar]\n"))
        self.assertEqual(variants["G1:anonymous-have"], self.code("  have : a = a := rfl\n  skip\n  simp only [foo, bar]\n"))
        self.assertEqual(variants["G1:unused-tactic"], self.code("  have h2 : a = a := rfl\n  simp only [foo, bar]\n"))

    def test_unreachable_segment_and_errors_ignored(self):
        code = self.code("  cases h <;> simp <;> omega\n")
        log = (self.warn(code, "omega", "this tactic is never executed") +
               self.warn(code, "simp", "unknown identifier").replace("warning", "error"))
        self.assertEqual([new for _, new in rw.linter_edits(code, self.statement, log, 1)],
                         [self.code("  cases h <;> simp\n")])

    def test_declaration_start_line(self):
        source = "import X\n\nopen Y\n" + self.code("  simp\n") + "\nexample : True := trivial\n"
        self.assertEqual(rw.declaration_start_line(source, self.code("  simp\n")), 4)
        self.assertIsNone(rw.declaration_start_line(source, "absent"))


class LocalRewriteTests(unittest.TestCase):
    statement = "theorem t : P"

    def code(self, body):
        return self.statement + " := by\n" + body

    def rewrites(self, body):
        return {name: new for name, new in rw.local_rewrites(self.code(body), self.statement)}

    def check(self, name, body, expected):
        found = self.rewrites(body)
        self.assertIn(name, found, found)
        self.assertEqual(found[name], self.code(expected))

    def absent(self, name, body):
        self.assertNotIn(name, self.rewrites(body))

    def test_by_exact_term(self):
        self.check("G3:by-exact-term", "  have h : Q := by exact foo\n  exact h\n", "  have h : Q := foo\n  exact h\n")
        self.check("G3:by-exact-term", "  exact ⟨by exact a, b⟩\n", "  exact ⟨a, b⟩\n")
        self.absent("G3:by-exact-term", "  exact foo\n")
        top = self.statement + " := by exact foo\n"
        self.assertNotIn("G3:by-exact-term", dict(rw.local_rewrites(top, self.statement)))

    def test_merge_rw(self):
        self.check("G3:merge-rw", "  rw [a]\n  rw [b, c]\n  simp\n", "  rw [a, b, c]\n  simp\n")
        self.check("G3:merge-rw", "  rw [a] at h\n  rwa [b] at h\n", "  rwa [a, b] at h\n")
        self.absent("G3:merge-rw", "  rw [a] at h\n  rw [b]\n")
        self.absent("G3:merge-rw", "  rw [a]\n  -- rw [b]\n")

    def test_merge_intro(self):
        self.check("G3:merge-intro", "  intro a\n  intro b c\n  exact x\n", "  intro a b c\n  exact x\n")
        self.absent("G3:merge-intro", "  intro a\n  exact x\n")

    def test_simpa_using(self):
        self.check("G3:simpa-using", "  simp only [f] at h\n  exact h\n", "  simpa only [f] using h\n")
        self.check("G3:simpa-using", "  simp at h\n  exact h\n", "  simpa using h\n")
        self.absent("G3:simpa-using", "  simp only [f] at h\n  exact h2\n")

    def test_identical_bullets(self):
        self.check("G3:identical-bullets", "  constructor\n  · simp\n  · simp\n", "  constructor <;> simp\n")
        self.absent("G3:identical-bullets", "  constructor\n  · simp\n  · omega\n")
        self.absent("G3:identical-bullets", "  constructor\n  · simp\n  · simp\n  exact x\n")

    def test_eta(self):
        self.check("G3:eta", "  exact foo (fun x => g x) y\n", "  exact foo g y\n")
        self.check("G3:eta", "  exact Exists.elim h fun x => g x\n", "  exact Exists.elim h g\n")
        self.absent("G3:eta", "  exact foo (fun x => g x y)\n")
        self.absent("G3:eta", "  exact foo (fun x => x.g x)\n")

    def test_small_rewrites(self):
        self.check("G3:exact-rfl", "  exact rfl\n", "  rfl\n")
        self.absent("G3:exact-rfl", "  exact rfl.symm\n")
        self.check("G3:constructor", "  refine ⟨?_, ?_⟩\n  · a\n  · b\n", "  constructor\n  · a\n  · b\n")
        self.check("G3:apply-exact", "  apply f\n  exact h\n", "  exact f h\n")
        self.check("G3:apply-exact", "  apply f x\n  exact h\n", "  exact (f x) h\n")
        self.absent("G3:apply-exact", "  apply f\n  exact h\n  simp\n")
        self.check("G3:merge-simp-only", "  simp only [a]\n  simp only [b]\n", "  simp only [a, b]\n")
        self.check("G3:simp-only-to-simp", "  simp only [a, b] at h\n  exact h\n", "  simp at h\n  exact h\n")

    def test_join_by(self):
        split = self.statement + " :=\n  by \n  trivial\n"
        joined = self.statement + " := by \n  trivial\n"
        self.assertEqual(dict(rw.local_rewrites(split, self.statement))["G3:join-by"], joined)
        self.assertEqual(scoring.count_tokens(split, self.statement) - scoring.count_tokens(joined, self.statement), 1)
        self.absent("G3:join-by", "  have h : Q :=\n    by simp\n  exact h\n")
        self.assertNotIn("G3:join-by", dict(rw.local_rewrites(self.statement + " := by trivial\n", self.statement)))

    def test_warning_helpers(self):
        self.assertEqual(rw.unknown_options("f.lean:3:0: error: Unknown option `linter.unusedTactic`\n"
                                            "f.lean:4:0: error: unknown option 'linter.foo'\n"),
                         ["linter.unusedTactic", "linter.foo"])
        code = self.code("  have u : Q := p\n  exact h\n")
        source = "import X\n\n" + code + "\ntheorem other : True := by\n  simp\n"
        log = ("f.lean:4:7: warning: unused variable `u`\n\nNote: this linter can be disabled\n"
               "f.lean:1:0: warning: outside\n"
               "f.lean:7:2: warning: declaration uses 'sorry'\n"
               "f.lean:5:2: error: not a warning\n")
        self.assertEqual(rw.declaration_warnings(log, source, code), [(1, "unused variable `u`")])
        self.assertEqual(rw.declaration_warnings(log, "elsewhere", code), [])

    def test_span_edits_compose(self):
        code = self.code("  intro a\n  intro b\n  rw [x]\n  rw [y]\n  exact rfl\n")
        edits = rw.non_overlapping(rw.local_span_edits(code, self.statement))
        self.assertEqual(rw.apply_edits(code, edits), self.code("  intro a b\n  rw [x, y]\n  rfl\n"))
        self.assertIsNone(rw.apply_edits(code, [rw.Edit("a", 0, 5, ""), rw.Edit("b", 3, 7, "")]))


class DeletionTests(unittest.TestCase):
    statement = "theorem t : P"

    def code(self, body):
        return self.statement + " := by\n" + body

    def test_targets(self):
        code = self.code("  clear h1\n  show P\n  have u : Q := by\n    simp\n  have v : R := w\n  exact v\n")
        names = sorted(edit.name for edit in rw.deletion_span_edits(code, self.statement))
        self.assertEqual(names, ["G4:drop-clear", "G4:drop-show", "G4:drop-unreferenced-have"])
        edits = {edit.name: rw.apply_edits(code, [edit]) for edit in rw.deletion_span_edits(code, self.statement)}
        self.assertEqual(edits["G4:drop-unreferenced-have"], self.code("  clear h1\n  show P\n  have v : R := w\n  exact v\n"))

    def test_ddmin_plan(self):
        edits = [rw.Edit(str(i), 10 * i, 10 * i + 1, "") for i in range(4)]
        plan = rw.ddmin_plan(edits, 7)
        self.assertEqual([len(batch) for batch in plan], [4, 2, 2, 1, 1, 1, 1])
        code = self.code("  clear a\n  clear b\n  exact x\n")
        variants = rw.ddmin_batches(code, self.statement, 3)
        self.assertEqual([name for name, _ in variants], ["G4:ddmin-2", "G4:ddmin-1", "G4:ddmin-1"])
        self.assertEqual(variants[0][1], self.code("  exact x\n"))


class CloserTests(unittest.TestCase):
    statement = "theorem t : P"
    code = statement + " := by\n  constructor\n  · simp only [a, b]\n    omega\n  · have h : Q := by\n      nlinarith [sq_nonneg x, sq_nonneg y]\n    exact h\n"

    def test_probe_and_inline_suggestions(self):
        probe, blocks = rw.closer_probe(self.code, self.statement)
        self.assertEqual([b["kind"] for b in blocks], ["bullet", "bullet"])
        self.assertEqual(probe.count("try?"), 2)
        lines = probe.split("\n")
        first, second = blocks[0]["probe_line"], blocks[1]["probe_line"]
        self.assertEqual(lines[first].strip(), "· try?")
        log = (f"/tmp/p/probe.lean:{first + 5}:4: info: Try this: simp_all\n"
               f"/tmp/p/probe.lean:{second + 5}:4: info: Try these:\n  [apply] nlinarith [sq_nonneg x]\n  [apply] exact?\n"
               f"/tmp/p/probe.lean:{second + 5}:4: error: unsolved goals\n")
        variants = rw.apply_suggestions(self.code, blocks, log, decl_start_line=5)
        self.assertEqual(len(variants), 2)
        self.assertIn("  · simp_all\n  · have h", variants[0][1])
        self.assertTrue(variants[1][1].endswith("  · nlinarith [sq_nonneg x]\n"))

    def test_root_probe_and_markup(self):
        probe, blocks = rw.closer_probe(self.code, self.statement, scope="root")
        self.assertEqual(probe, self.statement + " := by\n  try?\n")
        log = (f"f.lean:{blocks[0]['probe_line'] + 1}:2: info: Try this:\n  [apply] t̵r̵y̵?̵ grind\n"
               "  -- Remaining subgoals:\n  -- ⊢ P\n")
        variants = rw.apply_suggestions(self.code, blocks, log)
        self.assertEqual(variants, [("G2:try?:root@1", self.statement + " := by\n  grind\n")])

    def test_portfolio_probe_markers(self):
        probe, blocks = rw.closer_probe(self.code, self.statement, closers=rw.CORE_CLOSERS)
        self.assertNotIn("try?", probe)
        self.assertIn('first | (rfl; trace "G2M:0:rfl") | (assumption; trace "G2M:0:assumption") | '
                      '(omega; trace "G2M:0:omega") | (decide; trace "G2M:0:decide")', probe)
        self.assertIn('(grind; trace "G2M:1:grind")', probe)
        log = ('probe.lean:9:6: info: G2M:1:grind\n'
               'probe.lean:7:4: error: unsolved goals\n'
               'probe.lean:3:2: info: G2M:7:omega\n')
        variants = rw.apply_suggestions(self.code, blocks, log)
        self.assertEqual(len(variants), 1)
        self.assertTrue(variants[0][0].startswith("G2:closer:grind:bullet"))
        self.assertTrue(variants[0][1].endswith("  · grind\n"))
        root, root_map = rw.closer_probe(self.code, self.statement, scope="root", closers=("omega",))
        self.assertEqual(root, self.statement + ' := by\n  first | (omega; trace "G2M:0:omega")\n')

    def test_cheap_first_closer_lists(self):
        # Research item 6: one ordered list per row kind, cheap closers first, grind last.
        self.assertEqual(rw.CORE_CLOSERS, ("rfl", "assumption", "omega", "decide", "simp", "simp_all", "grind"))
        self.assertEqual(rw.MATHLIB_CLOSERS[:4], rw.CORE_CLOSERS[:4])
        self.assertEqual(rw.MATHLIB_CLOSERS[-1], "grind")
        self.assertLess(rw.MATHLIB_CLOSERS.index("positivity"), rw.MATHLIB_CLOSERS.index("simp_all"))
        self.assertLess(rw.MATHLIB_CLOSERS.index("linarith"), rw.MATHLIB_CLOSERS.index("aesop"))
        self.assertTrue(set(rw.CORE_CLOSERS) <= set(rw.MATHLIB_CLOSERS))
        for closer in rw.MATHLIB_CLOSERS:
            self.assertFalse(rw.SUGGESTION_BLOCKLIST.search(closer), closer)

    def test_simp_probe_and_suggestions(self):
        code = (self.statement + " := by\n  simp [a] at h\n  · simp\n  simp only [b]\n  cases x <;> simp\n"
                "  conv_lhs =>\n    simp\n  simpa using h\n")
        probe, sites = rw.simp_probe(code, self.statement)
        self.assertEqual([site["tactic"] for site in sites], ["simp", "simp", "simpa"])
        self.assertIn("  simp? [a] at h\n  · simp?\n  simp only [b]\n  cases x <;> simp\n", probe)
        self.assertIn("    simp\n  simpa? using h", probe)
        log = (f"probe.lean:{sites[0]['line'] + 1}:{sites[0]['col']}: info: Try this: simp only [a, c] at h\n"
               f"probe.lean:{sites[2]['line'] + 1}:{sites[2]['col']}: info: Try this:\n  [apply] simpa only [d] using h\n"
               f"probe.lean:{sites[1]['line'] + 1}:0: info: Try this: unrelated column\n")
        edits = rw.simp_suggestion_edits(code, sites, log)
        new = rw.apply_edits(code, edits)
        self.assertIn("  simp only [a, c] at h\n  · simp\n", new)
        self.assertIn("  simpa only [d] using h", new)

    def test_suggestion_parser(self):
        message = rw.Message(1, 0, "info", "Try these:\n• simp\n• simp_all\n• exact?")
        self.assertEqual(rw.suggestions(message), ["simp", "simp_all"])
        wrapped = rw.Message(1, 0, "info", "Try this:\n  [apply] simp only [a,\n    b] at h\n  -- Remaining subgoals:\n  --   x")
        self.assertEqual(rw.suggestions(wrapped), ["simp only [a, b] at h"])
        self.assertEqual(rw.suggestions(rw.Message(1, 0, "info", "unsolved goals")), [])
        self.assertEqual(rw.suggestions(rw.Message(1, 0, "info", "Try this: sorry")), [])


class HeartbeatSwapTests(unittest.TestCase):
    statement = "theorem t : P"

    def test_sites(self):
        code = (self.statement + " := by\n  simp [decide]\n  · norm_cast\n  linarith [h, sq_nonneg x]\n"
                "  norm_num at h\n  decide\n  simp (config := {decide := true})\n  exact (by decide +kernel)\n")
        edits = rw.heartbeat_span_edits(code, self.statement, max_sites=9)
        self.assertEqual([e.name for e in edits], ["G6:norm_cast-to-omega", "G6:linarith-to-omega", "G6:decide-kernel"])
        self.assertEqual(rw.apply_edits(code, edits),
                         self.statement + " := by\n  simp [decide]\n  · omega\n  omega\n  norm_num at h\n"
                         "  decide +kernel\n  simp (config := {decide := true})\n  exact (by decide +kernel)\n")
        self.assertEqual(len(rw.heartbeat_span_edits(code, self.statement, max_sites=2)), 2)
        self.assertEqual(rw.heartbeat_span_edits(self.statement + " := by\n  simp\n", self.statement), [])

    def test_golf_pass_keeps_the_passing_half(self):
        code = self.statement + " := by\n  constructor\n  · linarith\n  · norm_num\n"

        def oracle(text):   # omega closes the first goal only; fewer heartbeats when it does
            if "· omega\n  · omega" in text:
                return False, None
            return True, 50 if "omega" in text else 100
        adapter = FakeAdapter(self.statement, code, oracle)
        result, = golf.improve(adapter, {"statement": self.statement}, [candidate(code, "model", "c001", adapter)],
                               {"max_compiles_best": 8, "simp_probe": False})
        self.assertEqual(result.best.code, self.statement + " := by\n  constructor\n  · omega\n  · norm_num\n")
        self.assertEqual([name for name in result.accepted if name.startswith("G6:")], ["G6:linarith-to-omegax1"])
        off, = golf.improve(FakeAdapter(self.statement, code, oracle), {"statement": self.statement},
                            [candidate(code, "model", "c001")], {"max_compiles_best": 8, "heartbeat_swaps": False})
        self.assertFalse(any(name.startswith("G6:") for name in off.accepted))


class DecideTests(unittest.TestCase):
    statement = "lemma q : (I : Config) →\n    IsClosed I.charges (viable I)"

    def test_variants_are_generic(self):
        code = self.statement + " := by\n  refine fun I => closed_of ?_\n  revert I\n  decide +kernel"
        variants = dict(rw.decide_variants(code, self.statement))
        self.assertEqual(variants["G5:unfold-decide-kernel"], self.statement + " := by\n  unfold IsClosed\n  decide +kernel")
        self.assertEqual(variants["G5:merge-revert"],
                         self.statement + " := by\n  refine fun I => closed_of ?_\n  decide +kernel +revert")
        self.assertIn("G5:plain-decide", variants)
        self.assertEqual(rw.decide_variants(self.statement + " := by\n  simp", self.statement), [])


class FakeAdapter:
    """Compile oracle: oracle(code) -> (valid, raw_heartbeats)."""

    def __init__(self, statement, reference, oracle, *, folder=None, probe_log="", environments=("p", "s"),
                 mathlib=None, logs=None):
        self.statement, self.reference, self.oracle = statement, reference, oracle
        self.compiles, self.screens, self.validations = 0, [], []
        # One probe log, or a list consumed in order (the last one repeats).
        self.probe_logs = list(probe_log) if isinstance(probe_log, list) else [probe_log]
        self.probe_options = []
        self.logs = dict(logs or {})          # code -> {env: (log, source)} for version_logs
        self.environments = list(environments)
        self.folder = Path(folder) if folder else Path(tempfile.mkdtemp())
        self.golf_dir = self.folder / "golf"
        self.t0 = scoring.count_tokens(reference, statement)
        if mathlib is not None:
            self.imports_mathlib = lambda: mathlib

    def baseline(self):
        return self.t0, 1000

    def tokens(self, code):
        return scoring.count_tokens(code, self.statement)

    def screen_score(self, result):
        if not result.valid:
            return None
        return scoring.screen_score(result.tokens, result.raw_heartbeats, *self.baseline())

    def _eval(self, code, envs):
        valid, hb = self.oracle(code)
        return EvalResult(valid, self.tokens(code), hb if valid else None, {e: valid for e in envs},
                          None if valid else "compile", "" if valid else "error", str(self.folder))

    def screen(self, code, label):
        self.compiles += 1
        self.screens.append(code)
        return self._eval(code, self.environments[:1])

    def reference_result(self):
        return self._eval(self.reference, self.environments[:1])

    def validate(self, code, label, *, as_final=False):
        self.validations.append(label)
        valid, hb = self.oracle(code, all_versions=True) if "all_versions" in self.oracle.__code__.co_varnames else self.oracle(code)
        return EvalResult(valid, self.tokens(code), hb if valid else None, {e: valid for e in self.environments},
                          None if valid else "compile", "", str(self.folder / ("v-" + sha(code)[:8])))

    def diagnostics(self, result):
        return []

    def probe(self, text, label, *, timeout_s=300, options=()):
        self.compiles += 1
        self.probed = text
        self.probe_options.append(tuple(options))
        log = self.probe_logs.pop(0) if len(self.probe_logs) > 1 else self.probe_logs[0]
        return 1, log

    def probe_start_line(self, text, options=()):
        return 1

    def version_logs(self, code):
        return dict(self.logs.get(code, {}))

    def verify_environments(self):
        return None

    def to_eval(self, result, folder):
        raise AssertionError("not used")


def candidate(code, origin="model", label="c001", adapter=None):
    screen = adapter.screen(code, label) if adapter else None
    return Candidate(code, sha(code), origin, None, label, screen)


class GolfTests(unittest.TestCase):
    statement = "theorem t : True"
    reference = statement + " := by\n  have h : True := by\n    exact trivial\n  have u : True := trivial\n  exact h\n"

    def adapter(self, oracle=None, **kwargs):
        return FakeAdapter(self.statement, self.reference,
                           oracle or (lambda code: ("BROKEN" not in code, 10 * scoring.count_tokens(code, self.statement))),
                           **kwargs)

    def test_accepts_only_score_improvements(self):
        adapter = self.adapter()
        start = candidate(self.reference, "original", "c000", adapter)
        result, = golf.improve(adapter, {"statement": self.statement}, [start], {"original_compiles": 6})
        self.assertEqual(result.best.origin, "golf")
        self.assertEqual(result.best.parent_sha256, start.sha256)
        self.assertLess(result.best.screen.tokens, start.screen.tokens)
        self.assertEqual(result.best.code, self.statement + " := by\n  have h : True := trivial\n  exact h\n")
        self.assertTrue(all(entry.get("accepted") in (None, True, False) for entry in result.log))
        self.assertLessEqual(adapter.compiles - 1, 6)

    def test_non_improving_stop_and_budget(self):
        adapter = self.adapter(lambda code: (code == self.reference, 10_000))
        start = candidate(self.reference, "original", "c000", adapter)
        result, = golf.improve(adapter, {"statement": self.statement}, [start],
                               {"original_compiles": 20, "non_improving_stop": 2})
        self.assertEqual(result.best, start)
        self.assertEqual(result.accepted, [])
        # Two failing screens stop the candidate; probes use budget but are not screens.
        self.assertEqual(len(adapter.screens) - 1, 2)
        self.assertLessEqual(adapter.compiles - 1, 20)

    def test_search_edits_finds_passing_subset(self):
        statement = "theorem t : P"
        code = statement + " := by\n  clear a\n  clear b\n  clear c\n  clear d\n  exact x\n"
        oracle = lambda text: ("clear c" in text, 10 * scoring.count_tokens(text, statement))
        adapter = FakeAdapter(statement, code, oracle)
        session = golf._Session(adapter, statement, candidate(code, "original", "c000", adapter),
                                budget=golf._Budget(20), deadline=1e18, settings=dict(golf.DEFAULTS))
        self.assertTrue(session.ready())
        golf.search_edits(session, rw.deletion_span_edits(code, statement), "G4")
        self.assertEqual(session.code, statement + " := by\n  clear c\n  exact x\n")

    def test_score_bound_prunes_without_compiling(self):
        adapter = self.adapter(lambda code: (True, 0))
        start = candidate(self.reference, "original", "c000", adapter)
        session = golf._Session(adapter, self.statement, start, budget=golf._Budget(5), deadline=1e18,
                                settings=dict(golf.DEFAULTS))
        self.assertTrue(session.ready())
        before = adapter.compiles
        longer = self.reference.replace("exact h", "exact (id (id h))")
        self.assertFalse(session.try_variant("G3:test", longer))
        self.assertEqual(adapter.compiles, before)
        self.assertEqual(session.log[-1]["skipped"], "score-bound")

    def test_closer_suggestion_flow(self):
        statement = "theorem t : P"
        code = statement + " := by\n  constructor\n  · simp only [a, b, c]\n    omega\n  · exact y\n"
        probe, blocks = rw.closer_probe(code, statement)
        log = f"probe.lean:{blocks[0]['probe_line'] + 1}:4: info: Try this: omega\n"
        adapter = FakeAdapter(statement, code, lambda text: ("BROKEN" not in text, 100), probe_log=log)
        result, = golf.improve(adapter, {"statement": statement}, [candidate(code, "model", "c004", adapter)],
                               {"max_compiles_best": 6, "root_probe_max_tokens": 0})
        self.assertIn("  · omega\n  · exact y", result.best.code)
        self.assertTrue(any(name.startswith("G2:") for name in result.accepted))

    def test_blocked_variants_are_skipped_and_winners_persist(self):
        adapter = self.adapter()
        start = candidate(self.reference, "original", "c000", adapter)
        target = self.statement + " := by\n  have h : True := trivial\n  exact h\n"
        blocked = {golf.provenance_sha(target + "\n")}
        result, = golf.improve(adapter, {"statement": self.statement}, [start], {"original_compiles": 6},
                               non_openrouter_sha256=blocked)
        self.assertEqual(result.best.origin, "golf")
        self.assertNotEqual(golf.provenance_sha(result.best.code), golf.provenance_sha(target))
        self.assertTrue(any(entry.get("skipped") == "equals-non-openrouter-proof" for entry in result.log))
        winners = golf.load_winners(adapter.golf_dir)
        self.assertEqual([w.sha256 for w in winners], [result.best.sha256])
        self.assertEqual(winners[0].screen.tokens, result.best.screen.tokens)
        golf.improve(adapter, {"statement": self.statement}, [start], {"original_compiles": 6},
                     non_openrouter_sha256=blocked)
        self.assertEqual(len(golf.load_winners(adapter.golf_dir)), 1)

    def test_candidate_budgets(self):
        adapter = self.adapter(lambda code: (True, 10 * scoring.count_tokens(code, self.statement)))
        pool = [candidate(self.reference, "model", f"c00{i}", adapter) for i in range(1, 2)]
        results = golf.improve(adapter, {"statement": self.statement}, pool,
                               {"max_compiles_total": 3, "max_compiles_best": 3})
        self.assertEqual(len(results), 1)
        self.assertLessEqual(adapter.compiles - 1, 3)

    def test_linter_probe_auto_best_candidate_on_mathlib_rows(self):
        code = self.statement + " := by\n  have u : True := trivial\n  trivial\n"
        line, col = at(code, "u :")
        log = f"/p/probe.lean:{line}:{col}: warning: unused variable `u`\n\nNote: this linter can be disabled\n"
        oracle = lambda text: (True, 100)
        adapter = FakeAdapter(self.statement, code, oracle, probe_log=log, mathlib=True)
        result, = golf.improve(adapter, {"statement": self.statement}, [candidate(code, "model", "c001", adapter)],
                               {"max_compiles_best": 6})
        self.assertEqual(result.best.code, self.statement + " := by\n  trivial\n")
        self.assertTrue(result.accepted[0].startswith("G1:"), result.accepted)
        self.assertEqual(adapter.probe_options[0], golf.LINTER_OPTIONS)
        # Core-only rows, later candidates and tight budgets get no probe (G4 still finds the have).
        for kwargs, pool_size, settings in ((dict(mathlib=False), 1, {"max_compiles_best": 6}),
                                            (dict(mathlib=True), 2, {"max_compiles_best": 6, "max_compiles_other": 6,
                                                                     "max_compiles_total": 12, "top_k": 2}),
                                            (dict(mathlib=True), 1, {"max_compiles_best": 2})):
            adapter = FakeAdapter(self.statement, code, oracle, probe_log=log, **kwargs)
            pool = [candidate(code if i == 0 else code.replace("trivial\n", "exact trivial\n", 1), "model",
                              f"c00{i}", adapter) for i in range(pool_size)]
            results = golf.improve(adapter, {"statement": self.statement}, pool, settings)
            probes = [options for options in adapter.probe_options if options == golf.LINTER_OPTIONS]
            self.assertEqual(len(probes), 1 if (pool_size == 2) else 0, (kwargs, settings))
            if pool_size == 1:
                self.assertFalse(any(name.startswith("G1:") for name in results[0].accepted))

    def test_linter_probe_drops_unknown_options(self):
        code = self.statement + " := by\n  have u : True := trivial\n  trivial\n"
        line, col = at(code, "u :")
        logs = ["/p/probe.lean:1:0: error: Unknown option `linter.unusedTactic`\n",
                f"/p/probe.lean:{line}:{col}: warning: unused variable `u`\n"]
        adapter = FakeAdapter(self.statement, code, lambda text: (True, 100), probe_log=logs, mathlib=True)
        result, = golf.improve(adapter, {"statement": self.statement}, [candidate(code, "model", "c001", adapter)],
                               {"max_compiles_best": 8})
        self.assertTrue(result.accepted[0].startswith("G1:"), result.accepted)
        self.assertEqual(adapter.probe_options[0], golf.LINTER_OPTIONS)
        self.assertEqual(adapter.probe_options[1], tuple(o for o in golf.LINTER_OPTIONS if "unusedTactic" not in o))
        self.assertTrue(any(entry.get("event") == "probe-unknown-options" for entry in result.log))


class SelectTests(unittest.TestCase):
    statement = "theorem t : True"
    reference = statement + " := by\n  have h : True := trivial\n  exact h\n"

    def test_prefers_validated_higher_score_and_drops_provenance(self):
        short = self.statement + " := by\n  trivial\n"
        shorter = self.statement + " := by trivial\n"
        blocked = self.statement + " := by\n  exact trivial\n"
        # The shortest text passes the primary screen but fails another listed version.
        oracle = lambda code, all_versions=False: (not (all_versions and code == shorter), 10)
        adapter = FakeAdapter(self.statement, self.reference, oracle)
        pool = [candidate(c, "model", f"c{i}", adapter) for i, c in enumerate([shorter, short, blocked], 1)]
        pool.append(candidate(self.reference, "original", "c000", adapter))
        selection = select.select_final(adapter, {"statement": self.statement, "reference": self.reference,
                                                  "environments": ["p", "s"]}, pool,
                                        non_openrouter_sha256={select.provenance_sha(blocked + "\n\n")})
        self.assertTrue(selection.beat_original)
        self.assertEqual(selection.candidate.code, short)
        self.assertIn("c1", selection.considered)
        record = json.loads((adapter.golf_dir / "selection.json").read_text())
        self.assertEqual(record["dropped"][0]["reason"], "equals-non-openrouter-proof")

    def test_past_deadline_still_validates_the_top_candidate_only(self):
        short = self.statement + " := by\n  trivial\n"
        shorter = self.statement + " := by trivial\n"
        adapter = FakeAdapter(self.statement, self.reference, lambda code, all_versions=False: (True, 10))
        pool = [candidate(c, "model", f"c{i}", adapter) for i, c in enumerate([shorter, short], 1)]
        selection = select.select_final(adapter, {"statement": self.statement, "reference": self.reference,
                                                  "environments": ["p"]}, pool, deadline=0)
        self.assertEqual(selection.candidate.code, shorter)
        self.assertEqual(adapter.validations, ["c1"])
        # golf leaves the validation reserve free before a caller deadline.
        start = candidate(self.reference, "original", "c000", adapter)
        import time as clock
        result, = golf.improve(adapter, {"statement": self.statement}, [start], {"validation_reserve_s": 600},
                               deadline=clock.time() + 300)
        self.assertEqual(result.tried, 0)

    def test_validation_depth_on_wide_toolchain_rows(self):
        depth = select.validation_depth
        self.assertEqual(depth({"environments": ["strata-v4.31.0", "strata-v4.27.0"]}), 5)       # span 4
        self.assertEqual(depth({"environments": ["physlib-v4.34.1", "physlib-v4.34.0"]}), 3)
        self.assertEqual(depth({"environments": ["cslib-v4.34.1", "cslib-v4.33.1", "cslib-v4.31.0"]}), 5)
        self.assertEqual(depth({"environments": ["a", "b"], "version_info": [{"v4.34.1": "x"}, {"v4.31.0": "y"}]}), 5)
        self.assertEqual(depth({"environments": ["a", "b"]}, base=2), 2)
        self.assertEqual(select.version_span({"environments": ["p-v4.35.0-rc3", "p-v4.34.0"]}), (2, 1))
        # Five candidates in screening order; the first four fail another listed version.
        variants = [self.statement + " := by\n  exact " + "(id " * i + "trivial" + ")" * i + "\n" for i in range(5)]
        oracle = lambda code, all_versions=False: (not (all_versions and code in variants[:4]), 10)
        for environments, expected in ((["p"], "original"), (["p", "s", "t"], "model")):
            adapter = FakeAdapter(self.statement, self.reference, oracle, environments=environments)
            pool = [candidate(text, "model", f"c{i}", adapter) for i, text in enumerate(variants, 1)]
            selection = select.select_final(adapter, {"statement": self.statement, "reference": self.reference,
                                                      "environments": environments}, pool)
            self.assertEqual(selection.candidate.origin, expected, environments)
            self.assertEqual(len([v for v in adapter.validations if v != "c000"]), 3 if expected == "original" else 5)
            record = json.loads((adapter.golf_dir / "selection.json").read_text())
            self.assertEqual(record["validations"], 3 if expected == "original" else 5)
        adapter = FakeAdapter(self.statement, self.reference, oracle, environments=["p", "s", "t"])
        pool = [candidate(text, "model", f"c{i}", adapter) for i, text in enumerate(variants, 1)]
        selection = select.select_final(adapter, {"statement": self.statement, "reference": self.reference,
                                                  "environments": ["p", "s", "t"]}, pool, deep_k=None)
        self.assertEqual(selection.candidate.origin, "original")

    def test_warning_gate_rejects_demotes_or_fixes(self):
        problem = {"statement": self.statement, "reference": self.reference, "environments": ["p", "s"],
                   "source": "strata"}
        deprecated = self.statement + " := by\n  exact old_lemma\n"
        unused = self.statement + " := by\n  have u : True := trivial\n  trivial\n"

        def warn(code, needle, text):
            line, col = at(code, needle)
            return f"/x/check.lean:{line}:{col}: warning: {text}\n"
        logs = {deprecated: {"p": (warn(deprecated, "old_lemma", "`old_lemma` has been deprecated: use `new_lemma`"),
                                   deprecated)},
                unused: {"s": (warn(unused, "u :", "unused variable `u`\n\nNote: this linter can be disabled"), unused)},
                self.reference: {"p": ("", self.reference), "s": ("", self.reference)}}
        oracle = lambda code, all_versions=False: (True, 10)

        def run(code, label, mode="reject", source="strata", logs=logs):
            adapter = FakeAdapter(self.statement, self.reference, oracle, logs=logs)
            pool = [candidate(code, "model", label, adapter)]
            with patch.dict(os.environ, {"FINAL60_WARNING_GATE": mode}):
                selection = select.select_final(adapter, {**problem, "source": source}, pool)
            return selection, adapter, json.loads((adapter.golf_dir / "selection.json").read_text())
        # An unfixable new warning rejects the finalist; the original is published.
        selection, adapter, record = run(deprecated, "c1")
        self.assertEqual(selection.candidate.origin, "original")
        self.assertEqual(record["warning_gate"]["mode"], "reject")
        self.assertEqual(record["warning_gate"]["entries"][0]["warnings"],
                         {"p": ["`old_lemma` has been deprecated: use `new_lemma`"]})
        self.assertEqual(record["validation_errors"][0]["error_kind"], "warning-gate")
        # demote keeps it when nothing clean beats the original; off and other sources ignore warnings.
        self.assertEqual(run(deprecated, "c1", mode="demote")[0].candidate.code, deprecated)
        self.assertEqual(run(deprecated, "c1", mode="off")[0].candidate.code, deprecated)
        self.assertEqual(run(deprecated, "c1", source="physlib")[2]["warning_gate"]["mode"], "off")
        with patch.dict(os.environ, {"FINAL60_WARNING_GATE_SOURCES": "physlib, cslib"}):
            self.assertEqual(select.warning_gate_mode({"source": "physlib"}), "reject")
            self.assertEqual(select.warning_gate_mode({"source": "strata"}), "off")
        # A fixable warning (unused have) gets one G1 fix that is re-validated and selected.
        selection, adapter, record = run(unused, "c2")
        self.assertEqual(selection.candidate.code, self.statement + " := by\n  trivial\n")
        self.assertEqual((selection.candidate.origin, selection.candidate.label), ("golf", "golf:G1fix:c2"))
        self.assertEqual(selection.candidate.parent_sha256, sha(unused))
        self.assertEqual(adapter.validations, ["c2", "golf:G1fix:c2"])
        self.assertEqual(record["warning_gate"]["entries"][0]["fix"]["valid"], True)
        # The same warning shown by the original in that version is tolerated.
        tolerant = {**logs, self.reference: {"s": (warn(self.reference, "h :", "unused variable `u`"), self.reference)}}
        selection, adapter, record = run(unused, "c3", logs=tolerant)
        self.assertEqual((selection.candidate.code, selection.candidate.origin), (unused, "model"))
        self.assertEqual(record["warning_gate"]["entries"], [])

    def test_never_below_original(self):
        worse = self.statement + " := by\n  have h : True := trivial\n  have g : True := h\n  exact g\n"
        adapter = FakeAdapter(self.statement, self.reference, lambda code, all_versions=False: (True, 5000))
        pool = [candidate(worse, "model", "c001", adapter), candidate(self.reference, "original", "c000", adapter)]
        selection = select.select_final(adapter, {"statement": self.statement, "reference": self.reference,
                                                  "environments": ["p"]}, pool)
        self.assertFalse(selection.beat_original)
        self.assertEqual(selection.candidate.origin, "original")
        self.assertAlmostEqual(selection.score, 100 / 3)
        transfer = self.statement + " := by trivial\n"
        adapter = FakeAdapter(self.statement, self.reference,
                              lambda code, all_versions=False: (code != transfer or not all_versions, 10))
        pool = [candidate(transfer, "model", "c002", adapter)]
        selection = select.select_final(adapter, {"statement": self.statement, "reference": self.reference,
                                                  "environments": ["p", "s"]}, pool)
        self.assertEqual(selection.candidate.origin, "original")


# ---- integration: driver fixture root, golf, write_selection, report.py, PR #70 checker ----------
class FixtureEvaluator:
    """FinalEvaluator stand-in with saved source/log evidence (Lean is not invoked)."""

    def __init__(self, oracle, log_for=None):
        self.oracle, self.calls, self.log_for = oracle, [], log_for

    def evaluate(self, code, problem, path, **kwargs):
        self.calls.append((sha(code)[:8], kwargs))
        envs = problem["environments"] if kwargs.get("all_versions") else problem["environments"][:1]
        repetitions = kwargs.get("repetitions", 1)
        valid, heartbeats = self.oracle(code)
        tokens = scoring.count_tokens(code, problem["statement"])
        result = {"valid": valid, "tokens": tokens, "environments": {}, "error": None,
                  "timing": {"new_compiler_invocations": len(envs) * (1 + repetitions)}}
        for env in envs:
            folder = Path(path) / env
            folder.mkdir(parents=True, exist_ok=True)
            log = self.log_for(code, env) if self.log_for else "Synthetic evidence; Lean was not invoked."
            (folder / "check.lean").write_text(code)
            (folder / "check.log").write_text(log)
            runs = [{"source": "check.lean", "source_sha256": sha(code), "log": "check.log", "log_sha256": sha(log),
                     "returncode": 0 if valid else 1}]
            if valid:
                runs += [{"source": "check.lean", "source_sha256": sha(code), "log": "check.log",
                          "log_sha256": sha(log), "returncode": 0, "measurement": {"raw": heartbeats}}
                         for _ in range(repetitions)]
            result["environments"][env] = {"valid": valid, "runs": runs,
                                           "error": None if valid else {"kind": "compile", "message": "error: x"}}
        if not valid:
            result["error"] = {"kind": "lean", "message": "One or more required environments failed"}
        Path(path).mkdir(parents=True, exist_ok=True)
        (Path(path) / "result.json").write_text(json.dumps(result))
        return result

    def verify_environments(self, problem, *, full):
        return {env: "verified" for env in problem["environments"]}


class PublicationTests(unittest.TestCase):
    statement = "theorem test : True"
    reference = statement + " := by\n  have h : True := by\n    exact trivial\n  have u : True := trivial\n  exact h\n"
    proposal = "by\n  have h : True := by exact trivial\n  exact h"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = d.folder(self.root, 1)
        self.problem = {"id": "fixture-F001", "name": "test", "source": "synthetic fixture",
                        "environments": ["primary", "secondary"], "statement": self.statement,
                        "reference": self.reference}
        self.config = d.configuration(self.problem, {"scout_evaluations": 1, "merger_evaluations": 1})
        for name, value in (("problem", self.problem), ("config", self.config),
                            ("warm-start", d.warm_start.snapshot(None, self.problem, reason="explicit_cold_start")),
                            ("action-corpus", {"schema_version": 1, "entries": []})):
            d.atomic(self.output / "input" / (name + ".json"), value)
        (self.output / "input/prompt.txt").write_text("fixture")
        self.evaluator = FixtureEvaluator(lambda code: ("BROKEN" not in code,
                                                        1000 * scoring.count_tokens(code, self.statement)))
        d.evaluate_cached(self.evaluator, self.reference, self.problem, self.output / "baseline",
                          repetitions=3, trusted_reference=True)
        from lean_agent import harness as h
        d.atomic(self.output / "state.json", h.initial_state(self.problem, d.guard_compiler_signal(
            json.loads((self.output / "baseline/result.json").read_text())), self.config))
        d.atomic(self.output / "preflight.json", {"status": "ready"})
        d.atomic(self.root / "ledger.json", {"schema_version": 1, "attempts": {}})
        d.atomic(self.root / "authorization.json", {
            "rows": [1], "dataset_sha256": "synthetic", "per_problem_target_usd": "2.99",
            "verification_policy": d.VERIFICATION_POLICY, "provider": "OpenRouter",
            "api_endpoint": "https://openrouter.ai/api/v1/chat/completions"})

    def run_driver(self):
        sys_test = evaladapter.final_batch_module("test_driver")
        count = []

        def query(body, *args):
            packet = json.loads(body["messages"][1]["content"])
            count.append(packet["portfolio"]["branch"])
            action = {"action": "propose", "parent_id": "c000", "strategy": "golfable",
                      "proof": self.proposal + f"\n  -- {packet['portfolio']['branch']} {len(count)}"}
            if packet["portfolio"]["branch"] == "merge":
                action["source_candidate_ids"] = ["c001", "c002", "c003"]
            response = sys_test.raw(action)
            response["id"] += str(len(count))
            return response

        with patch.object(d, "verify_frozen"), patch.object(d, "evaluator", return_value=self.evaluator), \
                patch.object(d.transport, "model_metadata", return_value={}), \
                patch.object(d.transport, "query", side_effect=query):
            return d.run_problem(self.root, 1)

    def report(self):
        report = evaladapter.final_batch_module("report")
        return report.build_report(self.root)

    def provenance(self, built):
        (self.root / "report.json").write_text(json.dumps(built))
        spec = importlib.util.spec_from_file_location("final60_test_provenance",
                                                      REPO / "scripts/check_submission_provenance.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        proof = (self.output / "selected.lean").read_text()
        benchmark = [{"name": "test", "statement": self.statement, "reference": self.reference}]
        return checker.check(benchmark, [{"name": "test", "proof": proof}], [checker.RunRoot(self.root)], [], [],
                             checker.Decimal("3"))

    def test_golf_winner_replaces_driver_selection_and_passes_audit(self):
        summary = self.run_driver()
        self.assertEqual(summary["status"], "completed")
        before = self.report()
        self.assertTrue(before["audit_passed"], before["audit_errors"])
        driver_sha = summary["selected"]["sha256"]
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=self.evaluator, screen_mode="check-measure")
        pool = select.candidates_from_run(self.root, 1)
        self.assertEqual(pool[-1].origin, "original")
        self.assertIsNotNone(pool[0].screen)
        results = golf.improve(adapter, self.problem, [c for c in pool if c.origin == "model"],
                               {"max_compiles_best": 6, "top_k": 1})
        winner = results[0].best
        self.assertEqual(winner.origin, "golf")
        selection = select.select_final(adapter, self.problem, pool + [winner])
        self.assertEqual(selection.candidate.sha256, winner.sha256)
        self.assertTrue(selection.beat_original)
        published = select.write_selection(self.root, 1, selection)
        self.assertEqual(published["status"], "completed")
        self.assertEqual(published["stop_reason"], summary["stop_reason"])
        self.assertEqual(published["cost_usd"], summary["cost_usd"])
        self.assertEqual(published["golf"]["origin"], "golf")
        self.assertTrue(list(self.output.glob("final-prev-" + driver_sha[:12] + "-*")))
        built = self.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual(built["rows"][0]["selected_sha256"], winner.sha256)
        self.assertGreater(built["rows"][0]["local_score_estimate"], 33.4)
        checked = self.provenance(built)
        self.assertEqual(checked["errors"], [])
        # Publishing again is idempotent with respect to the audit.
        select.write_selection(self.root, 1, selection)
        self.assertTrue(self.report()["audit_passed"])

    def test_skip_llm_row_gets_auditable_synthesized_summary(self):
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=self.evaluator, screen_mode="check-measure")
        original = select.candidates_from_run(self.root, 1)
        self.assertEqual([c.origin for c in original], ["original"])
        results = golf.improve(adapter, self.problem, original, {"original_compiles": 4})
        selection = select.select_final(adapter, self.problem, original + [r.best for r in results])
        self.assertTrue(selection.beat_original)
        summary = select.write_selection(self.root, 1, selection, stop_reason="skip_llm")
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(summary["calls"], 0)
        built = self.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual(self.provenance(built)["errors"], [])

    def test_warning_gate_reads_version_logs_and_publishes_the_fix(self):
        unused = self.statement + " := by\n  have u : True := trivial\n  trivial\n"
        line, col = at(unused, "u :")

        def log_for(code, env):
            if code == unused and env == "secondary":
                return f"/x/check.lean:{line}:{col}: warning: unused variable `u`\n"
            return "Synthetic evidence; Lean was not invoked."
        self.evaluator.log_for = log_for
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=self.evaluator, screen_mode="check-measure")
        pool = [candidate(unused, "model", "c001", adapter)] + select.candidates_from_run(self.root, 1)
        with patch.dict(os.environ, {"FINAL60_WARNING_GATE_SOURCES": "synthetic fixture"}):
            selection = select.select_final(adapter, self.problem, pool)
        self.assertEqual(adapter.version_logs(unused).keys(), {"primary", "secondary"})
        self.assertEqual(select.new_warnings(adapter, unused, self.reference), {"secondary": ["unused variable `u`"]})
        self.assertEqual((selection.candidate.origin, selection.candidate.label), ("golf", "golf:G1fix:c001"))
        self.assertEqual(selection.candidate.code, self.statement + " := by\n  trivial\n")
        select.write_selection(self.root, 1, selection, stop_reason="skip_llm")
        built = self.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual(self.provenance(built)["errors"], [])

    def test_original_fallback_publishes_reference(self):
        self.evaluator.oracle = lambda code: (code == self.reference, 5000)
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=self.evaluator, screen_mode="check-measure")
        pool = select.candidates_from_run(self.root, 1)
        selection = select.select_final(adapter, self.problem, pool)
        self.assertFalse(selection.beat_original)
        select.write_selection(self.root, 1, selection, stop_reason="api_disabled")
        built = self.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual((self.output / "selected.lean").read_text(), self.reference)

    def test_finalize_row_entry_points(self):
        self.run_driver()
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=self.evaluator, screen_mode="check-measure")
        early = select.golf_original(self.root, 1, {"original_compiles": 3}, adapter=adapter)
        self.assertEqual(len(early), 1)
        outcome = select.finalize_row(self.root, 1, {"max_compiles_best": 6, "top_k": 1}, adapter=adapter)
        self.assertTrue(outcome["beat_original"])
        self.assertIn(outcome["origin"], ("golf", "model"))
        self.assertEqual(outcome["status"], "completed")
        built = self.report()
        self.assertTrue(built["audit_passed"], built["audit_errors"])
        self.assertEqual(built["rows"][0]["selected_sha256"], outcome["selected_sha256"])
        # A restarted worker sees the persisted golf winners again.
        labels = [c.label for c in select.candidates_from_run(self.root, 1)]
        self.assertTrue(any(label.startswith("golf:") for label in labels))
        self.assertEqual(labels[-1], "c000")

    def test_pool_guard_never_uses_exclusive_lock(self):
        class Exclusive:
            compiler_parallelism = 1
        built = []

        def factory(**kwargs):
            built.append(kwargs["compiler_parallelism"])
            if kwargs["compiler_parallelism"] > 3:
                raise ValueError("Expected one to three compiler slots")
            return Exclusive()
        with patch.object(d, "evaluator", return_value=Exclusive()), \
                patch.object(d, "evaluator_class", return_value=factory), \
                patch.dict(os.environ, {"FINAL60_COMPILER_SLOTS": "3"}):
            evaladapter.EvalAdapter(self.root, 1)
        self.assertEqual(built, [3])
        with patch.object(d, "evaluator", return_value=Exclusive()), \
                patch.object(d, "evaluator_class", return_value=factory), \
                patch.dict(os.environ, {"FINAL60_COMPILER_SLOTS": "6"}):
            with self.assertRaisesRegex(ValueError, "compiler pool"):
                evaladapter.EvalAdapter(self.root, 1)

    def test_screen_timeout_bounds(self):
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=self.evaluator, screen_mode="check-measure")
        self.assertEqual(adapter.screen_timeout(), 120)
        with patch.dict(os.environ, {"FINAL60_GOLF_SCREEN_TIMEOUT_S": "45"}):
            self.assertEqual(adapter.screen_timeout(), 45)

    def test_screen_cache_is_content_addressed(self):
        adapter = evaladapter.EvalAdapter(self.root, 1, evaluator=self.evaluator, screen_mode="check-measure")
        variant = self.statement + " := by\n  trivial\n"
        first = adapter.screen(variant, "a")
        count = len(self.evaluator.calls)
        second = adapter.screen(variant, "b")
        self.assertEqual(first, second)
        self.assertEqual(len(self.evaluator.calls), count)
        self.assertTrue((adapter.golf_dir / "screen" / sha(variant)[:12] / "result.json").exists())
        broken = adapter.screen(self.statement + " := by\n  sorry\n", "c")
        self.assertEqual(broken.error_kind, "validation")
        self.assertEqual(len(self.evaluator.calls), count)
        self.assertEqual(adapter.screen(self.reference, "c000").tokens, adapter.baseline()[0])


@unittest.skipUnless(os.environ.get("FINAL60_REAL_LEAN") == "1", "real Lean check is opt-in (FINAL60_REAL_LEAN=1)")
class RealLeanTests(unittest.TestCase):
    """One ready row: preflight baseline, one single-pass screen and one closer probe."""

    def test_real_row(self):
        row = int(os.environ.get("FINAL60_REAL_LEAN_ROW", "14"))
        keep = os.environ.get("FINAL60_REAL_LEAN_ROOT")
        root = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="final60-golf-real-"))
        evaluator = d.evaluator(root)
        problem = evaluator.load_problem(row)
        output = d.folder(root, row)
        d.atomic(output / "input/problem.json", problem)
        if not (output / "baseline/result.json").exists():
            d.evaluate_cached(evaluator, problem["reference"], problem, output / "baseline",
                              repetitions=3, trusted_reference=True)
        adapter = evaladapter.EvalAdapter(root, row, evaluator=evaluator)
        t0, hb0 = adapter.baseline()
        self.assertGreater(hb0, 0)
        variants = rw.local_rewrites(problem["reference"], problem["statement"])
        name, variant = variants[0]
        screened = adapter.screen(variant, name)
        print(json.dumps({"row": row, "variant": name, "valid": screened.valid, "tokens": screened.tokens,
                          "raw_heartbeats": screened.raw_heartbeats, "t0": t0, "hb0": hb0,
                          "error_kind": screened.error_kind, "evidence": screened.evidence_dir}))
        self.assertIn(screened.error_kind, (None, "compile"))
        probe, blocks = rw.closer_probe(problem["reference"], problem["statement"])
        if blocks:
            returncode, log = adapter.probe(probe, "G2:blocks")
            start = adapter.probe_start_line(probe)
            offered = rw.apply_suggestions(problem["reference"], blocks, log, decl_start_line=start)
            print(json.dumps({"probe_returncode": returncode, "suggestion_variants": len(offered),
                              "messages": len(rw.parse_messages(log))}))
        if not keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
