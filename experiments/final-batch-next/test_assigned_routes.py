import sqlite3
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assigned_budget import ProblemBudgetError, propose
from assigned_routes import assigned_mean, compare, diagnosed_edits, family, maximum_score, portfolio_edits, proposals
from reuse_scout import body_reuse, use_scout, scout_packet


class AssignedRouteTests(unittest.TestCase):
    def test_serial_candidate_requires_all_versions_before_promotion(self):
        statement = "theorem t : True"
        original = statement + " := by trivial"
        alternative = statement + " := by constructor"
        calls = []

        class Evaluator:
            def evaluate(self, code, p, folder, **options):
                folder.mkdir()
                calls.append((code, tuple(p["environments"]), options["repetitions"]))
                ok = code == original or p["environments"] == ["primary"]
                return {"valid": ok, "tokens": 8 if code == original else 2,
                        "environments": {v: {"median_raw_heartbeats": 100 if code == original else 1,
                                             "error": None} for v in p["environments"]}}

        with (tempfile.TemporaryDirectory() as tmp,
              patch("assigned_routes.focus", return_value=("test", "")),
              patch("assigned_routes.diagnosed_edits", return_value=()),
              patch("assigned_routes.proposals", return_value=[("alt", alternative)])):
            p = dict(row=11, name="t", reference=original, statement=statement,
                     environments=["primary", "secondary"])
            result = compare(Evaluator(), p, Path(tmp), None, 1)
        self.assertEqual(result["proof"], original)
        self.assertEqual([(env, n) for code, env, n in calls if code == alternative],
                         [(("primary",), 1), (("primary",), 3), (("secondary",), 1)])

    def test_full20_mean_requires_all_assigned_rows(self):
        rows = [dict(row=n,score=n+50) for n in range(1,31)]
        self.assertIsNone(assigned_mean(rows[:-1]))
        self.assertEqual(assigned_mean(rows), 70.5)
    def test_zero_cost_score_bound_for_four_token_reference(self):
        self.assertAlmostEqual(maximum_score(8,4), 100/3)
        self.assertLess(maximum_score(9,4), 100/3)
        self.assertGreater(maximum_score(2,4), 80)

    def test_portfolio_interleaves_independent_roots_with_provenance(self):
        statement = "theorem t : True"
        packet = scout_packet(statement, "")
        alternative = statement + " := by\n  have h := And.imp id h₁\n  trivial"
        stream = portfolio_edits("best", [("a","edit1"),("b","edit2")], packet,
                                 [("peer",alternative)], statement, "local-tactics")
        first = [next(stream) for _ in range(4)]
        self.assertEqual([label for label,_ in first], ["best/a","statement-only/scout","peer/and-right","best/b"])
        self.assertNotIn("h₁", first[1][1])

    def test_cslib_trace_edits_match_verified_preview_inputs(self):
        seeds = Path(__file__).resolve().parents[2] / "solutions/team-shared-20261102/seongwoo"
        seed = (seeds / "F028.lean").read_text(encoding="utf-8").rstrip("\n")
        statement = seed.split(" := by", 1)[0]
        options = dict(proposals(seed, statement, family(seed)))
        expected = {
            "segment-one-rewrite": "ce441e6e50706b0b2474b59ab553b90110e01fd6d2cc629864a1bd95db573dd5",
        }
        for label, sha in expected.items():
            self.assertEqual(hashlib.sha256(options[label].encode()).hexdigest(), sha)
        choice = (seeds / "F023.lean").read_text(encoding="utf-8").rstrip("\n")
        statement = choice.split(" := by", 1)[0]
        self.assertIn("direct-choice-step", dict(proposals(choice, statement, family(choice))))

    def test_overlap_and_scout_boundary(self):
        statement = "theorem t (h : Demo.Fact) : Demo.Fact"
        self.assertAlmostEqual(
            body_reuse(statement + " a b c d", statement + " a b c z", statement), 0.75
        )
        self.assertEqual(body_reuse(statement + " a b c d", statement + " a b z", statement), 0)
        self.assertTrue(use_scout("issue61", "cslib", 0.95))
        self.assertFalse(use_scout("issue61", "physlib", 1))
        self.assertFalse(use_scout("local", "cslib", 1))
        packet = scout_packet(statement, "lemma known : Demo.Fact := by private_step\n")
        self.assertEqual(packet["premises"], ["known"])
        self.assertNotIn("private_step", str(packet))

    def test_only_target_diagnostics_supply_rewrites(self):
        statement = "theorem test : True"
        proof = statement + " := by\n  simp only [foo, bar]"
        source = "import Lean\n" + proof
        log = (
            "check.lean:1:2: warning: This simp argument is unused:\n  bar\n"
            "check.lean:3:14: warning: This simp argument is unused:\n  foo\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "src").write_bytes(source.encode())
            (folder / "log").write_bytes(log.encode())
            (folder / "result.json").write_text(
                json.dumps(
                    {
                        "runs": [
                            {
                                "source": "src",
                                "log": "log",
                                "log_sha256": hashlib.sha256(log.encode()).hexdigest(),
                                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                            }
                        ]
                    }
                )
            )
            self.assertEqual(
                list(diagnosed_edits(folder, proof, statement)),
                [("unused-simp", proof.replace("foo, bar", "bar"))],
            )

    def test_primary_gain_cannot_replace_multiversion_control(self):
        statement = "theorem t : True"
        reference = statement + " := by\n  have h : True := by grind\n  exact h"

        # Substitute the offline strategy table only; evaluate as a two-version problem.
        class Evaluator:
            def evaluate(self, code, p, folder, **options):
                folder.mkdir()
                stats = {
                    v: {
                        "valid": code == reference or v == "primary",
                        "median_raw_heartbeats": 100 if code == reference else 1,
                        "error": None,
                    }
                    for v in p["environments"]
                }
                return {
                    "valid": all(s["valid"] for s in stats.values()),
                    "environments": stats,
                    "tokens": 12 if code == reference else 2,
                }

        with (
            tempfile.TemporaryDirectory() as root,
            patch("assigned_routes.focus", return_value=("test", "")),
            patch("assigned_routes.diagnosed_edits", return_value=()),
        ):
            p = dict(
                row=11,
                name="t",
                reference=reference,
                statement=statement,
                environments=["primary", "secondary"],
            )
            result = compare(Evaluator(), p, Path(root), None, 2)
            self.assertEqual(result["proof"], reference)
            self.assertEqual(result["gain_over_control"], 0)
            self.assertAlmostEqual(sum(result["metrics"].values())/3, result["score"])

    def test_multiple_carried_candidates_require_all_versions_before_selection(self):
        statement = "theorem t : True"
        reference = statement + " := by\n  have h : True := by grind\n  exact h"
        incumbent = statement + " := by trivial"
        incompatible = statement + " := by exact True.intro"
        improved = statement + " := by constructor"

        class Evaluator:
            def evaluate(self, code, p, folder, **options):
                folder.mkdir()
                stats = {v: {"valid": not (code == incompatible and v == "secondary"),
                             "median_raw_heartbeats": {reference: 100, incumbent: 30,
                                                       incompatible: 1, improved: 10}[code],
                             "error": None} for v in p["environments"]}
                return {"valid": all(s["valid"] for s in stats.values()), "environments": stats,
                        "tokens": {reference: 12, incumbent: 6, incompatible: 1, improved: 4}[code]}

        with tempfile.TemporaryDirectory() as root, patch("assigned_routes.focus", return_value=("test", "")):
            p = dict(row=11, name="t", reference=reference, statement=statement,
                     environments=["primary", "secondary"])
            result = compare(Evaluator(), p, Path(root), None, 0, incumbent=incumbent,
                             extra_seeds=[("carry-02", incompatible), ("carry-03", improved)])
            self.assertIsNone(result["controls"]["carry-02"])
            self.assertEqual(result["selected"], "carry-03")
            self.assertEqual(result["proof"], improved)

    def test_pending_receipt_and_prior_spend_prevent_dispatch(self):
        messages = [{"role": "system", "content": "Test"}, {"role": "user", "content": "Test"}]
        with tempfile.TemporaryDirectory() as root:
            ledger = Path(root) / "cost.sqlite"
            with self.assertRaisesRegex(ProblemBudgetError, "cap"):
                propose(ledger, "a", "2.98", messages, dispatch=lambda *_: self.fail())
            with self.assertRaisesRegex(ProblemBudgetError, "Incomplete"):
                propose(ledger, "b", "0", messages, dispatch=lambda *_: {})
            with self.assertRaisesRegex(ProblemBudgetError, "Unresolved"):
                propose(ledger, "b", "0", messages, dispatch=lambda *_: self.fail())
            with sqlite3.connect(ledger) as conn:
                self.assertEqual(conn.execute("select count(*) from calls").fetchone()[0], 1)
