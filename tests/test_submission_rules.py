import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_submission_rules import check, check_row  # noqa: E402

STATEMENT = "theorem t (n : Nat) : n + 0 = n :="


class SubmissionRulesTest(unittest.TestCase):
    def test_clean_proof(self):
        self.assertEqual(check_row(STATEMENT, STATEMENT + " by\n  simp"), [])

    def test_forbidden_and_statement(self):
        self.assertIn("forbidden: sorry", check_row(STATEMENT, STATEMENT + " by sorry"))
        self.assertIn("forbidden: native_decide", check_row(STATEMENT, STATEMENT + " by native_decide"))
        self.assertIn("statement differs from the benchmark statement",
                      check_row(STATEMENT, "theorem t (n : Nat) : n = n := rfl"))

    def test_unsafe_only_inside_aesop_add(self):
        self.assertEqual(check_row(STATEMENT, STATEMENT + " by\n  aesop (add unsafe (by simp))"), [])
        self.assertIn("unsafe outside `aesop (add unsafe ...)`", check_row(STATEMENT, STATEMENT + " by\n  exact unsafe"))

    def test_comments_and_cardinality_notation(self):
        self.assertEqual(check_row(STATEMENT, STATEMENT + " by\n  -- sorry later\n  simp [#(s)]"), [])

    def test_missing_and_unmatched_rows(self):
        bench = [{"name": "a", "statement": STATEMENT}, {"name": "b", "statement": STATEMENT}]
        result = check(bench, [{"name": "a", "proof": STATEMENT + " by simp"}, {"name": "x", "proof": ""}])
        self.assertEqual(result["missing"], ["b"])
        self.assertIn("x", result["problems"])


if __name__ == "__main__":
    unittest.main()
