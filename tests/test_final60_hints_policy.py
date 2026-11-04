"""Hint policy for the final run: no warm-up bank cards in prompts (PR #75 review)."""
import unittest
from unittest import mock

from lean_agent.final60 import package, prompts, routing


class WarmupBankOffTests(unittest.TestCase):
    def test_route_rules_turn_warmup_bank_cards_off(self):
        self.assertEqual(routing.rules()["hints"]["bank_cards"], 0)

    def test_route_rules_have_no_per_row_priority(self):
        # Row lists measured on the final benchmark would be benchmark-specific tuning.
        self.assertEqual(routing.rules()["priority"]["weak_rows"], [])

    def test_routes_and_prompt_profiles_need_no_warmup_material(self):
        problem = {"row": 3, "name": "Test.f", "source": "strata",
                   "statement": "theorem f_eq (xs : List Nat) : f xs = g xs",
                   "reference": "theorem f_eq (xs : List Nat) : f xs = g xs := by\n"
                                "  induction xs with\n  | nil => simp [f, g]\n"
                                "  | cons x xs ih => simp_all [f, g]",
                   "environments": ["strata-v4.31.0", "strata-v4.27.0"]}
        self.assertFalse((routing.DATA / "warmup_bank.json").exists())
        routing.data_sha256.cache_clear()
        original_read = routing.Path.read_bytes

        def read_without_warmup(path):
            self.assertNotIn("warmup", path.name.lower())
            return original_read(path)

        with mock.patch.object(routing.Path, "read_bytes", autospec=True, side_effect=read_without_warmup):
            for profile in getattr(prompts, "PROFILES", {"baseline": None}):
                options = {"prompt_profile": profile} if profile != "baseline" else {}
                value = routing.route(problem, None, non_openrouter_proofs=[], **options)
                data = routing.route_json(value)
                self.assertNotIn("warmup_bank", data)
                self.assertTrue(all(not source.startswith("warmup-bank:") for source in value.hint_sources))
                text = data["prompt_addendum"].lower()
                self.assertNotIn("warmup", text)
                self.assertNotIn("warm-up", text)

    def test_code_zip_excludes_warmup_bank_copies(self):
        for path in ("src/lean_agent/final60/data/warmup_bank.json",
                     "experiments/strategy-retriever/bank/strategies.json"):
            with self.subTest(path=path):
                self.assertTrue(package.excluded(path))
                with self.assertRaises(ValueError):
                    package.assert_clean(["submission/" + path], prefix="submission/")


if __name__ == "__main__":
    unittest.main()
