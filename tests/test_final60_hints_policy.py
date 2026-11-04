"""Hint policy for the final run: no warm-up bank cards in prompts (PR #75 review)."""
import unittest

from lean_agent.final60 import routing


class WarmupBankOffTests(unittest.TestCase):
    def test_route_rules_turn_warmup_bank_cards_off(self):
        self.assertEqual(routing.rules()["hints"]["bank_cards"], 0)


if __name__ == "__main__":
    unittest.main()
