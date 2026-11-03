"""Exercise shared portfolio routing through the durable batch without API/Lean."""
import json
import contextlib
import io
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

    def run_batch(self, actions=None):
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
            if actions is not None:
                action = actions[len(self.packets) - 1]
            response = raw(action)
            response["id"] += str(len(self.packets))
            return response

        with patch.object(d, "verify_frozen"), patch.object(d, "evaluator", return_value=Evaluator()), \
                patch.object(d.transport, "model_metadata", return_value={}), \
                patch.object(d.transport, "query", side_effect=query):
            return d.run_problem(self.root, 1)

    def attempts(self):
        return sorted(a.read(self.root / "ledger.json")["attempts"].items(), key=lambda item: item[1]["step"])

    def test_guard_stalled_batch_is_auditable_and_never_claims_quota_completion(self):
        self.config["agent"]["portfolio"]["progress_guard"] = "bounded-v1"
        d.atomic(self.output / "input/config.json", self.config)
        d.atomic(self.output / "state.json", h.initial_state(self.problem, result(), self.config))
        summary = self.run_batch([{"action": "search", "query": "same"}] * 32)
        self.assertEqual(summary["stop_reason"], "portfolio_stalled")
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(summary["calls"], 32)
        self.assertFalse(report.audit_portfolio(self.output, summary, self.attempts()))
        forged = json.loads(a.canonical(summary))
        forged["status"] = "completed"
        with self.assertRaisesRegex(ValueError, "Incomplete portfolio"):
            report.audit_portfolio(self.output, forged, self.attempts())
        packet_path = self.output / "steps/0008/request.json"
        body = a.read(packet_path)
        packet = json.loads(body["messages"][1]["content"])
        packet["portfolio"]["branch"] = "scout-b"
        body["messages"][1]["content"] = a.canonical(packet)
        d.atomic(packet_path, body)
        with self.assertRaisesRegex(ValueError, "barrier"):
            report.audit_portfolio(self.output, summary, self.attempts())

    def test_new_configuration_defaults_to_portfolio_and_explicit_legacy_stays_off(self):
        config = d.configuration(self.problem)
        self.assertEqual(config["agent"]["portfolio"], d.DEFAULT_PORTFOLIO)
        self.assertEqual(config["agent"]["approach_policy"], "exchange-v1")
        config["agent"]["portfolio"]["scout_evaluations"] = 1
        self.assertEqual(d.configuration(self.problem)["agent"]["portfolio"]["scout_evaluations"], 6)
        legacy = d.configuration(self.problem, None)
        self.assertNotIn("portfolio", legacy["agent"])
        self.assertNotIn("approach_policy", legacy["agent"])

    def test_cli_defaults_opt_out_and_custom_quotas(self):
        for flags, expected in [([], d.DEFAULT_PORTFOLIO), (["--portfolio"], d.DEFAULT_PORTFOLIO),
                                (["--no-portfolio"], None),
                                (["--scout-evaluations", "2", "--merger-evaluations", "3"],
                                 {"scout_evaluations": 2, "merger_evaluations": 3, "progress_guard": "bounded-v1"})]:
            with self.subTest(flags=flags), patch.object(d.sys, "argv", ["driver.py", "inputs", "--root", str(self.root), "--rows", "1", *flags]), \
                    patch.object(d, "prepare_inputs") as prepare:
                d.main()
                settings = prepare.call_args.kwargs["portfolio_settings"]
                actual = d.configuration(self.problem, settings)["agent"].get("portfolio")
                self.assertEqual(actual, expected)

    def test_cli_refuses_policy_changes_during_run_or_conflicting_opt_out(self):
        for args in [["run", "--portfolio"], ["run", "--no-portfolio"],
                     ["inputs", "--no-portfolio", "--scout-evaluations", "2"]]:
            with self.subTest(args=args), patch.object(d.sys, "argv", ["driver.py", *args, "--root", str(self.root)]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                d.main()

    def test_prompt_uses_runtime_budget_instead_of_a_hard_coded_dollar_amount(self):
        prompt = d.prompt_text("types only")
        self.assertIn("budget.stop_at_usd", prompt)
        self.assertNotIn("reaches $1", prompt)

    def test_sealed_legacy_resume_keeps_its_exact_configuration(self):
        config_path = self.output / "input/config.json"
        d.atomic(config_path, d.configuration(self.problem, None))
        before = config_path.read_bytes()
        d.atomic(self.root / "frozen.json", {})
        d.atomic(self.root / "authorization.json", {"rows": [1], "verification_policy": d.VERIFICATION_POLICY})
        with patch.object(d, "verify_frozen") as verify:
            d.prepare(self.root, [1])
            verify.assert_called_once_with(self.root.resolve())
            self.assertEqual(config_path.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "fresh batch root"):
                d.prepare(self.root, [1], portfolio_settings=d.DEFAULT_PORTFOLIO)

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
        (repository / "examples/actions").mkdir(parents=True)
        (repository / "examples/actions/prompt.txt").write_text((d.REPO / "examples/actions/prompt.txt").read_text())
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
            legacy = self.root / "legacy"
            d.prepare_inputs(legacy, [1], portfolio_settings=None)
            old_bytes = (d.folder(legacy, 1) / "input/config.json").read_bytes()
            d.prepare_inputs(legacy, [1])
            self.assertEqual((d.folder(legacy, 1) / "input/config.json").read_bytes(), old_bytes)
            self.assertNotIn("portfolio", a.read(d.folder(legacy, 1) / "input/config.json")["agent"])
            d.validate_inputs(legacy, 1)
            with self.assertRaisesRegex(ValueError, "fresh batch root"):
                d.prepare_inputs(legacy, [1], portfolio_settings=d.DEFAULT_PORTFOLIO)
            with self.assertRaisesRegex(ValueError, "fresh batch root"):
                d.prepare_inputs(root, [1], portfolio_settings=None)


if __name__ == "__main__":
    unittest.main()
