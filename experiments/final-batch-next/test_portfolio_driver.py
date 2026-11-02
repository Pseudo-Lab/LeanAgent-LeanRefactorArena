"""Exercise shared portfolio routing through the durable batch without API/Lean."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_driver import d, raw, result
from lean_agent import artifacts as a, harness as h
import report


class PortfolioBatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = d.folder(self.root, 1)
        self.problem = {"id": "test", "name": "test", "source": "synthetic fixture",
                        "environments": ["primary", "secondary"], "statement": "theorem test : True",
                        "reference": "theorem test : True := by trivial\n"}
        self.config = d.configuration(self.problem, {"scout_evaluations": 1, "merger_evaluations": 1})
        for name, value in (("problem", self.problem), ("config", self.config),
                            ("action-corpus", {"schema_version": 1, "entries": []})):
            d.atomic(self.output / "input" / (name + ".json"), value)
        (self.output / "input/prompt.txt").write_text("test")
        d.atomic(self.output / "baseline/result.json", result())
        d.atomic(self.output / "state.json", h.initial_state(self.problem, result(), self.config))
        d.atomic(self.output / "preflight.json", {"status": "ready"})
        d.atomic(self.root / "ledger.json", {"schema_version": 1, "attempts": {}})
        self.packets = []

    def run_batch(self):
        class Evaluator:
            def evaluate(self, code, problem, path, **kwargs):
                measured = json.loads(a.canonical(result(2, 50, all_versions=kwargs.get("all_versions", False))))
                for environment, row in measured["environments"].items():
                    destination = Path(path) / environment
                    destination.mkdir(parents=True, exist_ok=True)
                    log = "Synthetic compiler evidence for control-flow tests; Lean was not invoked."
                    (destination / "source.lean").write_text(code)
                    (destination / "compile.log").write_text(log)
                    for run in row["runs"]:
                        run.update(source="source.lean", source_sha256=a.sha(code),
                                   log="compile.log", log_sha256=a.sha(log))
                return measured
            def verify_environments(self, problem, *, full):
                return {"primary": "verified"}

        def query(body, *args):
            packet = json.loads(body["messages"][1]["content"])
            self.packets.append(packet)
            action = {"action": "propose", "parent_id": "c000", "strategy": packet["portfolio"]["route"],
                      "proof": "by trivial -- " + packet["portfolio"]["branch"]}
            if packet["portfolio"]["branch"] == "merge":
                action["source_candidate_ids"] = ["c001", "c002", "c003"]
            response = raw(action)
            response["id"] += str(len(self.packets))
            return response

        with patch.object(d, "verify_frozen"), patch.object(d, "evaluator", return_value=Evaluator()), \
                patch.object(d.transport, "model_metadata", return_value={}), \
                patch.object(d.transport, "query", side_effect=query):
            return d.run_problem(self.root, 1)

    def attempts(self):
        return sorted(a.read(self.root / "ledger.json")["attempts"].items(), key=lambda item: item[1]["step"])

    def export_report(self):
        d.atomic(self.root / "authorization.json", {"rows": [1], "dataset_sha256": "synthetic",
                 "per_problem_target_usd": "1.00", "verification_policy": d.VERIFICATION_POLICY})
        return report.build_report(self.root, require_complete=True)

    def test_batch_finishes_below_threshold_after_merger_and_resumes_without_calls(self):
        summary = self.run_batch()
        self.assertEqual(summary["stop_reason"], "portfolio_complete")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["cost_usd"], "0.020")
        self.assertEqual([p["portfolio"]["branch"] for p in self.packets], list(h.portfolio.BRANCHES))
        self.assertNotIn("reference", self.packets[0]["problem"])
        self.assertEqual(self.packets[-1]["approach_policy"]["approach"], "merge")
        self.assertTrue(report.audit_portfolio(self.output, summary, self.attempts()))
        exported = self.export_report()
        self.assertTrue(exported["audit_passed"], exported["audit_errors"])
        self.assertTrue(exported["all_completed"])
        state = a.read(self.output / "state.json")
        self.assertEqual(state["exploration"]["candidates"]["c004"]["source_candidate_ids"], ["c001", "c002", "c003"])
        with patch.object(d, "verify_frozen"), patch.object(d, "dispatch", side_effect=AssertionError("No repeat call")):
            self.assertEqual(d.run_problem(self.root, 1), summary)
        # Recounted receipts detect a premature merger even if a summary claims success.
        path = self.output / "steps/0002/request.json"
        body = a.read(path)
        packet = json.loads(body["messages"][1]["content"])
        packet["portfolio"]["branch"] = "merge"
        body["messages"][1]["content"] = a.canonical(packet)
        d.atomic(path, body)
        with self.assertRaisesRegex(ValueError, "crossed evaluation barrier"):
            report.audit_portfolio(self.output, summary, self.attempts())

    def test_threshold_before_merger_exports_verified_best_as_stopped(self):
        # Test the controller threshold without seeding fictitious settled calls.
        self.config["limits"]["cost_stop_usd"] = "0.005"
        d.atomic(self.output / "input/config.json", self.config)
        summary = self.run_batch()
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(summary["stop_reason"], "cost_limit")
        self.assertEqual(len(self.packets), 1)
        self.assertFalse(report.audit_portfolio(self.output, summary, self.attempts()))
        self.assertFalse(summary["portfolio"]["complete"])
        self.assertTrue(summary["all_versions_valid"])
        exported = self.export_report()
        self.assertFalse(exported["all_completed"])
        self.assertFalse(exported["audit_passed"])
        self.assertEqual(exported["completed"], 0)
        self.assertIn("All authorized problems must complete before final export", exported["audit_errors"])

    def test_prepared_inputs_freeze_policy_and_reject_mode_changes(self):
        repository = self.root / "repo"
        problem = {**self.problem, "row": 1, "dataset_sha256": d.DATASET_SHA, "environments": ["fixture"]}
        a.write(repository / "sources/final/problems/F001.json", problem)
        class Evaluator:
            def load_problem(self, row):
                return problem
            def source_context(self, problem):
                return {"corpus": {"schema_version": 1, "entries": []}, "prompt_context": "types only"}
        root = self.root / "prepared"
        settings = {"scout_evaluations": 1, "merger_evaluations": 1}
        with patch.object(d, "REPO", repository), patch.object(d, "evaluator", return_value=Evaluator()):
            d.prepare_inputs(root, [1], portfolio_settings=settings)
            self.assertEqual(a.read(d.folder(root, 1) / "input/config.json")["agent"]["portfolio"], settings)
            d.validate_inputs(root, 1)
            with self.assertRaisesRegex(ValueError, "fresh batch root"):
                d.prepare_inputs(root, [1], portfolio_settings={"scout_evaluations": 2})
            # A no-flag retry reuses the frozen prepared policy.
            d.prepare_inputs(root, [1])


if __name__ == "__main__":
    unittest.main()
