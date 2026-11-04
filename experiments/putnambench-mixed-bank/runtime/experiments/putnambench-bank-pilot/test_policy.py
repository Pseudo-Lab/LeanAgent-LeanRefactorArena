"""Regression checks for real final rows and executable-boundary rejection."""
import json
from pathlib import Path
import unittest

from policy import length_audit, public_intake_rejection, validate_declaration

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"


class FinalPolicyTests(unittest.TestCase):
    @unittest.skipUnless(DATA.is_file(), "Install the frozen final dataset for this integration check")
    def test_all_trusted_references_also_pass_candidate_text_policy(self):
        rows = [json.loads(line) for line in DATA.read_text().splitlines()]
        self.assertEqual(len(rows), 60)
        for index, row in enumerate(rows, 1):
            with self.subTest(row=index, name=row["name"]):
                validate_declaration(row["src"], row["statement"])

    @unittest.skipUnless(DATA.is_file(), "Install the frozen final dataset for this integration check")
    def test_actual_denominator_differences_are_explained(self):
        rows = [json.loads(line) for line in DATA.read_text().splitlines()]
        differing = []
        for index, row in enumerate(rows, 1):
            audit = length_audit(row)
            self.assertTrue(audit["historical_boundary_matches_dataset"])
            if not audit["local_matches_dataset"]:
                differing.append(index)
                self.assertEqual(audit["dataset_reference_tokens"] - audit["local_reference_tokens"], 1)
        self.assertEqual(differing, [53, 56])

    def test_statement_is_immutable(self):
        with self.assertRaisesRegex(ValueError, "statement"):
            validate_declaration("theorem p : False := by trivial", "theorem p : True")

    def test_new_declarations_and_options_are_rejected(self):
        statement = "theorem p : True"
        for extra in ("\nend X", "\ntheorem q : True := by trivial", "\nset_option maxRecDepth 9999"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_declaration(statement + " := by trivial" + extra, statement)

    def test_executable_and_measurement_constructs_are_rejected(self):
        for code in (
            "by run_tac pure ()", "#eval IO.println 1", "unsafe def x := 1", "by native_decide",
            "by run_meta pure ()", "by exact ofReduceBool _", "by exact Lean.getNumHeartbeats",
            "by exact getHeartbeats", "by decide +native", "by (simproc_decl x := _)"
        ):
            with self.subTest(code=code):
                self.assertIsNotNone(public_intake_rejection(code))

    def test_comments_do_not_hide_executable_constructs(self):
        self.assertIsNotNone(public_intake_rejection('by exact "--"; run_tac pure ()'))
        self.assertIsNone(public_intake_rejection("by trivial /- run_tac /- nested -/ IO -/"))


if __name__ == "__main__":
    unittest.main()
