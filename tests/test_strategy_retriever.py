import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/strategy-retriever"))
import retriever as rt  # noqa: E402

STMT = "theorem t (xs : List Nat) : f xs = g xs"
CASES = STMT + """ := by
  induction xs with
  | nil => simp [f, g]
  | cons x xs ih =>
    cases x
    · simp_all [f, g]
    · simp_all [f, g]
    cases xs
    · simp_all [f, g]
    · simp_all [f, g]
    simp_all
"""
HAVES = STMT + " := by\n" + "".join(f"  have h{i} : True := trivial\n" for i in range(6)) + "  rfl\n"


class Retriever(unittest.TestCase):
    def setUp(self):
        self.bank = rt.load_bank()

    def test_bank_is_warmup_only(self):
        for e in self.bank:
            self.assertEqual(e["evidence"]["source_set"], "warm-up")
            self.assertEqual(e["evidence"]["source_problem_ids"], [])

    def test_route_cue_ranks_split_first(self):
        r = rt.retrieve(STMT, CASES, self.bank)
        self.assertIn("route_cue", r["features"]["tags"])
        self.assertEqual(r["strategies"][0]["id"], "S01")
        self.assertLessEqual(len(r["strategies"]), 3)

    def test_have_chain(self):
        ids = [s["id"] for s in rt.retrieve(STMT, HAVES, self.bank)["strategies"]]
        self.assertEqual(ids[0], "S04")

    def test_general_moves_fill_up(self):
        ids = [s["id"] for s in rt.retrieve(STMT, STMT + " := by rfl", self.bank)["strategies"]]
        self.assertEqual(ids, ["S10", "S11"])

    def test_leave_one_out(self):
        bank = json.loads(json.dumps(self.bank))
        bank[3]["evidence"]["source_problem_ids"] = ["P"]
        ids = [s["id"] for s in rt.retrieve(STMT, HAVES, bank, problem="P")["strategies"]]
        self.assertNotIn("S04", ids)
        ids = [s["id"] for s in rt.retrieve(STMT, HAVES, bank, problem="Q")["strategies"]]
        self.assertIn("S04", ids)
        bank[3]["evidence"]["source_problem_ids"] = ["P", "Q"]
        ids = [s["id"] for s in rt.retrieve(STMT, HAVES, bank, problem="P")["strategies"]]
        self.assertIn("S04", ids)

    def test_render_has_no_problem_name(self):
        text = rt.render(rt.retrieve(STMT, CASES, self.bank, problem="SECRET_NAME"))
        self.assertNotIn("SECRET_NAME", text)


if __name__ == "__main__":
    unittest.main()
