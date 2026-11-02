"""Synthetic data only: plan integrity and development/evaluation separation."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/lean-arena-harness/scripts/plan.py"
spec = importlib.util.spec_from_file_location("arena_skill_plan", SCRIPT)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


def problem(name, source="sample", pins=None, statement=None):
    statement = statement or f"theorem {name} (n : Nat) : n = n"
    return {"name": name, "source": source, "statement": statement,
            "src": statement + " := by rfl", "proof_length": 1,
            "version_info": pins or [{"v4.31.0": "a" * 40}]}


class ArenaSkillPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, rows):
        path = self.root / name
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        return path

    def test_shared_environment_and_distinct_commit(self):
        rows = [problem("one", pins=[{"v4.31.0": "a" * 40}, {"v4.30.0": "b" * 40}]),
                problem("two"), problem("three", pins=[{"v4.31.0": "c" * 40}])]
        plan = planner.build_plan(self.write("benchmark.jsonl", rows))
        self.assertEqual(plan["counts"]["checks"], 4)
        self.assertEqual(plan["counts"]["environments"], 3)
        self.assertTrue(all(check["status"] == "not_run" for check in plan["checks"]))
        self.assertEqual(plan["development_check"], {"status": "not_checked"})
        self.assertEqual(plan, planner.build_plan(self.root / "benchmark.jsonl"))

    def test_filter_keeps_official_name_and_input_line(self):
        path = self.write("benchmark.jsonl", [problem("one"), problem("two", "other")])
        plan = planner.build_plan(path, ["other"])
        self.assertEqual(plan["input_problems"], 2)
        self.assertEqual([(p["name"], p["input_line"]) for p in plan["problems"]], [("two", 2)])
        with self.assertRaisesRegex(ValueError, "unknown source"):
            planner.build_plan(path, ["absent"])

    def test_rejects_duplicate_names_and_ambiguous_pins(self):
        for field, value in [("version_info", [{"v4.31.0": "a" * 40}, {"v4.31.0": "b" * 40}]),
                             ("version_info", [{"v4.31.0": "short"}]), ("proof_length", True)]:
            row = problem("one"); row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                planner.build_plan(self.write("bad.jsonl", [row]))
        with self.assertRaisesRegex(ValueError, "duplicate problem"):
            planner.build_plan(self.write("bad.jsonl", [problem("one"), problem("one")]))

    def test_overlap_in_filtered_out_source_still_rejected(self):
        rows = [problem("one"), problem("two", "other")]
        benchmark = self.write("benchmark.jsonl", rows)
        dev = self.write("dev.jsonl", [rows[0]])
        with self.assertRaisesRegex(ValueError, "development overlap"):
            planner.build_plan(benchmark, ["other"], dev)

    def test_renamed_commented_statement_is_not_an_independent_example(self):
        benchmark = self.write("benchmark.jsonl", [problem("one")])
        row = problem("renamed", "other", statement="lemma renamed /- note -/ (n: Nat): n=n")
        with self.assertRaisesRegex(ValueError, "development overlap"):
            planner.build_plan(benchmark, development=self.write("dev.jsonl", [row]))

    def test_string_contents_are_preserved_by_overlap_screen(self):
        first = 'theorem one : "a b" = "a b"'
        second = 'theorem two : "ab" = "ab"'
        self.assertNotEqual(planner.statement_key(first), planner.statement_key(second))

    def test_separated_development_has_no_generalization_claim(self):
        benchmark = self.write("benchmark.jsonl", [problem("one")])
        dev = self.write("dev.jsonl", [problem("dev", statement="theorem dev : 0 < 1")])
        plan = planner.build_plan(benchmark, development=dev)
        self.assertEqual(plan["development_check"]["status"], "no_lexical_overlap_found")
        self.assertEqual(plan["development_check"]["semantic_or_family_overlap"], "not_checked")

    def test_invalid_input_and_existing_output_never_replace_saved_file(self):
        benchmark = self.write("benchmark.jsonl", [problem("one")])
        output = self.root / "saved.json"; output.write_text("preserve me")
        run = subprocess.run([sys.executable, str(SCRIPT), "--benchmark", str(benchmark),
                              "--output", str(output)], capture_output=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(output.read_text(), "preserve me")
        bad = self.write("bad.jsonl", [problem("one"), problem("one")])
        fresh = self.root / "not-created.json"
        run = subprocess.run([sys.executable, str(SCRIPT), "--benchmark", str(bad),
                              "--output", str(fresh)], capture_output=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(fresh.exists())


if __name__ == "__main__":
    unittest.main()
