"""Offline tests for the Try-this parser of minimize.py (no Lean)."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("hb_minimize", Path(__file__).with_name("minimize.py"))
minimize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(minimize)
parse = minimize.parse_try_this


class TryThisTest(unittest.TestCase):
    def test_same_line(self):
        log = "F.lean:3:2: info: Try this: simp only [a, b]\nF.lean:9:0: info: done"
        self.assertEqual(parse(log), ["simp only [a, b]"])

    def test_apply_on_next_line_without_position(self):
        # Lean v4.33/v4.34 output seen in physlib/cslib probes
        log = "Try this:\n  [apply] simp only [Int.reduceNeg, one_mul, zero_add]\nREFACTOR_EVAL x {}"
        self.assertEqual(parse(log), ["simp only [Int.reduceNeg, one_mul, zero_add]"])

    def test_apply_on_next_line_with_position(self):
        log = "F.lean:3:2: info: Try this:\n  [apply] simp_all only [h]\nF.lean:9:0: error: x"
        self.assertEqual(parse(log), ["simp_all only [h]"])

    def test_multiline_keeps_relative_indent(self):
        log = "F.lean:3:2: info: Try this:\n  [apply] constructor\n    · simp\n    · simp only [x]\n"
        self.assertEqual(parse(log), ["constructor\n  · simp\n  · simp only [x]"])

    def test_two_apply_entries_and_two_messages(self):
        log = ("Try this:\n  [apply] simp only [a]\n  [apply] simp only [b]\n"
               "F.lean:5:2: info: Try this: aesop_cat\n")
        self.assertEqual(parse(log), ["simp only [a]", "simp only [b]", "aesop_cat"])

    def test_no_suggestion(self):
        self.assertEqual(parse("F.lean:1:0: error: unknown identifier"), [])


if __name__ == "__main__":
    unittest.main()
