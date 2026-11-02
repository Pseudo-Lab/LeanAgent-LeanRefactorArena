"""Compiler error location and action-specific repair context regressions."""
import unittest

from lean_agent import diagnostics


class RepairFeedbackTests(unittest.TestCase):
    def test_candidate_lines_and_context_warnings_are_separated(self):
        code = "theorem sample : True := by\n  aesop\n  intro x\n"
        source = "-- context\n-- more context\n" + code
        text = ("/run/check.lean:1:1: warning: declaration uses 'sorry'\n"
                "/run/check.lean:4:3: error: unknown tactic\n"
                "/run/check.lean:5:3: error: No goals to be solved\n")
        issues, warnings = diagnostics.lean_issues(text, source, code)
        self.assertEqual(warnings, 1)
        self.assertEqual([row["kind"] for row in issues], ["unknown_tactic", "no_goals"])
        self.assertEqual([row["candidate_line"] for row in issues], [2, 3])
        self.assertEqual(issues[0]["candidate_text"].strip(), "aesop")

    def test_unrelated_context_error_has_no_candidate_line(self):
        code = "theorem x : True := by trivial\n"
        issues, _ = diagnostics.lean_issues("/run/check.lean:1:1: error: unknown identifier\n",
                                            "-- context\n" + code, code)
        self.assertIsNone(issues[0]["candidate_line"])
        self.assertIsNone(issues[0]["candidate_text"])

    def test_repeated_no_goal_messages_are_counted_once_per_location(self):
        issues, _ = diagnostics.lean_issues("/run/check.lean:5:3: error: No goals to be solved\n" * 5)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["occurrences"], 5)

    def test_long_log_cannot_hide_first_structured_error(self):
        text = "/run/check.lean:4:3: error: unknown tactic\n" + "many unrelated lines\n" * 500
        issues, count = diagnostics.lean_issues(text)
        report = diagnostics.diagnosis("candidate", "proof", "lean_check_rejected", excerpt=text)
        report.update(issues=issues, warning_count=count)
        feedback = diagnostics.enrich({"details": "", "valid": False}, report, 200, "/run")
        self.assertNotIn("unknown tactic", feedback["details"])
        self.assertEqual(feedback["issues"][0]["kind"], "unknown_tactic")
        self.assertLessEqual(len(feedback["details"]), 200)


if __name__ == "__main__":
    unittest.main()
