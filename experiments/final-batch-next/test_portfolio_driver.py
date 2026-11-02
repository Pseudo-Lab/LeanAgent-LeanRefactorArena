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
        self.inspections = []
        self.automatic_signal = False

    def run_batch(self):
        class Evaluator:
            def evaluate(evaluator, code, problem, path, **kwargs):
                measured = json.loads(a.canonical(result(2, 50, all_versions=kwargs.get("all_versions", False))))
                if "missing_auto_" in code:
                    measured["valid"] = False
                    for value in measured["environments"].values():
                        value.update(valid=False, error={"kind": "compile", "message": "unknown identifier"})
                for environment, row in measured["environments"].items():
                    destination = Path(path) / environment
                    destination.mkdir(parents=True, exist_ok=True)
                    log = "Synthetic compiler evidence for control-flow tests; Lean was not invoked."
                    (destination / "source.lean").write_text(code)
                    (destination / "compile.log").write_text(log)
                    for run in row["runs"]:
                        run.update(source="source.lean", source_sha256=a.sha(code),
                                   log="compile.log", log_sha256=a.sha(log))
                    if self.automatic_signal and Path(path).parent.name == "autosolver":
                        measured["valid"] = False
                        row.update(valid=False, error={"kind": "compile", "message": "process died"})
                        row["runs"][0]["returncode"] = -9
                return measured
            def inspect_native(evaluator, code, problem, path, *, timeout, memory):
                self.inspections.append(code)
                start = code.index("by")
                end = len(code.rstrip())
                goal = {"target": "True", "local_context": []}
                closed = "missing_auto_" not in code
                # The closed report contains the replacement by-block; the
                # failed report contains the original tactic's native state.
                pos = code.index("by", code.index("exact (")) if closed else start + 3
                observation = {"kind": "proof", "source_sha256": a.sha(code),
                    "errors": [] if closed else [{"position": pos, "message": "unknown identifier"}],
                    "blocks": [{"start": start, "end": end}],
                    "tactics": [{"start": pos, "end": end, "depth": 0,
                        "syntax_kind": "Lean.Parser.Term.byTactic" if closed else "Lean.Parser.Tactic.exact",
                        "before": [goal], "after": [] if closed else [goal]}]}
                a.write(path / "result.json", observation)
                return observation
            def verify_environments(self, problem, *, full):
                return {"primary": "verified"}

        def query(body, *args):
            packet = json.loads(body["messages"][1]["content"])
            self.packets.append(packet)
            proof = ("by exact missing_auto_" if "autosolver" in self.config["agent"] else "by trivial -- ")
            action = {"action": "propose", "parent_id": "c000", "strategy": packet["portfolio"]["route"],
                      "proof": proof + packet["portfolio"]["branch"]}
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

    def test_autosolver_preserves_quotas_billing_scope_and_auditable_resume(self):
        self.config["agent"]["autosolver"] = {"tactics": ["trivial"], "max_attempts": 1}
        d.atomic(self.output / "input/config.json", self.config)
        summary = self.run_batch()
        self.assertEqual(summary["cost_usd"], "0.020")
        self.assertEqual(summary["calls"], 4)
        self.assertEqual(summary["autosolver"]["verified_candidates"], 4)
        self.assertEqual(summary["autosolver"]["model_calls"], 0)
        self.assertEqual(len(self.inspections), 8)
        state = a.read(self.output / "state.json")
        self.assertEqual(list(state["portfolio"]["evaluations"].values()), [1, 1, 1, 1])
        for index in range(1, 5):
            parent = f"c{index:03}"
            self.assertFalse(state["exploration"]["candidates"][parent]["valid"])
            self.assertTrue(state["exploration"]["candidates"][parent + "-auto"]["valid"])
            self.assertEqual(state["portfolio"]["owners"][parent], state["portfolio"]["owners"][parent + "-auto"])
        exported = self.export_report()
        self.assertTrue(exported["audit_passed"], exported["audit_errors"])
        with patch.object(d, "verify_frozen"), patch.object(d, "dispatch", side_effect=AssertionError("No repeat call")):
            self.assertEqual(d.run_problem(self.root, 1), summary)
        path = self.output / "steps/0001/autosolver/search.json"
        record = a.read(path)
        record["outcome"]["sites_closed"] += 1
        d.atomic(path, record)
        with self.assertRaisesRegex(ValueError, "differs from replay"):
            report.audit_autosolver(self.output, summary, self.attempts())

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
            d.prepare_inputs(root, [1], portfolio_settings=settings, autosolver_settings={})
            self.assertEqual(a.read(d.folder(root, 1) / "input/config.json")["agent"]["portfolio"], settings)
            self.assertEqual(a.read(d.folder(root, 1) / "input/config.json")["agent"]["autosolver"], {})
            d.validate_inputs(root, 1)
            with self.assertRaisesRegex(ValueError, "fresh batch root"):
                d.prepare_inputs(root, [1], portfolio_settings={"scout_evaluations": 2})
            with self.assertRaisesRegex(ValueError, "fresh batch root"):
                d.prepare_inputs(root, [1], autosolver_settings={"max_attempts": 2})
            # A no-flag retry reuses the frozen prepared policy.
            d.prepare_inputs(root, [1])

    def test_automatic_verification_signal_stops_before_next_model_dispatch(self):
        self.config["agent"]["autosolver"] = {"tactics": ["trivial"], "max_attempts": 1}
        d.atomic(self.output / "input/config.json", self.config)
        self.automatic_signal = True
        with self.assertRaisesRegex(ValueError, "evaluator environment failure"):
            self.run_batch()
        self.assertEqual(len(self.packets), 1)
        state = a.read(self.output / "state.json")
        self.assertEqual(state["cost_usd"], "0.005")
        self.assertFalse(state["exploration"]["candidates"]["c001-auto"]["valid"])
        measured = a.read(self.output / "steps/0001/autosolver/evaluation/result.json")
        self.assertTrue(h.environment_failed(measured))


if __name__ == "__main__":
    unittest.main()
