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
                            ("warm-start", d.warm_start.snapshot(None, self.problem, reason="portfolio_isolation")),
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

    def run_batch(self, actions=None):
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
                      "proof": proof + packet["portfolio"]["branch"]
                               + (f" round {packet['portfolio']['round']}" if "round" in packet["portfolio"] else "")
                               + (f" try {len(self.packets)}" if packet["portfolio"].get("stops_at") else "")}
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
        d.atomic(self.output / "input/prompt-policy.json", d.prompt_variants.policy())
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

    def use_settings(self, settings, cost_stop=None):
        self.config = d.configuration(self.problem, settings)
        if cost_stop is not None:
            self.config["limits"]["cost_stop_usd"] = cost_stop
        d.atomic(self.output / "input/config.json", self.config)
        d.atomic(self.output / "state.json", h.initial_state(self.problem, result(), self.config))

    def test_two_rounds_complete_and_pass_the_routing_audit(self):
        self.use_settings({"progress_guard": "bounded-v1", "scout_evaluations": 1, "merger_evaluations": 1, "rounds": 2})
        summary = self.run_batch()
        self.assertEqual([p["portfolio"]["branch"] for p in self.packets], list(h.portfolio.BRANCHES) * 2)
        self.assertEqual(summary["stop_reason"], "portfolio_complete")
        self.assertEqual(summary["status"], "completed")
        self.assertTrue(report.audit_portfolio(self.output, summary, self.attempts()))

    def test_budget_ended_merger_is_a_completed_portfolio(self):
        self.use_settings({"progress_guard": "bounded-v1", "scout_evaluations": 1, "merger_evaluations": 1,
                           "merger_until_budget": True},
                          cost_stop="0.15")
        summary = self.run_batch()
        branches = [p["portfolio"]["branch"] for p in self.packets]
        self.assertEqual(branches[:3], ["scout-a", "scout-b", "scout-c"])
        self.assertGreater(branches.count("merge"), 1)
        # Stops before a call whose worst-case reservation could cross the cap, so actual spend stays under it.
        self.assertLessEqual(d.Decimal(summary["cost_usd"]), d.Decimal("0.15"))
        self.assertLess(d.Decimal(summary["cost_usd"]), d.Decimal("0.15") - d.Decimal("0.05"))
        self.assertEqual(summary["stop_reason"], "portfolio_budget_complete")
        self.assertEqual(summary["status"], "completed")
        self.assertTrue(report.audit_portfolio(self.output, summary, self.attempts()))

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

    def test_current_policy_requires_warm_start_snapshot_even_for_cold_portfolio(self):
        self.run_batch()
        (self.output / "input/warm-start.json").unlink()
        exported = self.export_report()
        self.assertFalse(exported["audit_passed"])
        self.assertTrue(any("invalid warm-start evidence" in error for error in exported["audit_errors"]))

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
            # Omitted options preserve the entire strict treatment policy, not
            # just portfolio mode; explicit conflicting flags still fail.
            treatment = self.root / "treatment"
            d.prepare_inputs(treatment, [1], portfolio_settings=None,
                             prompt_variant="structure-repair-v1", strict_cap=True)
            inputs = d.folder(treatment, 1) / "input"
            before = {path.name: path.read_bytes() for path in inputs.iterdir()}
            d.prepare_inputs(treatment, [1])
            self.assertEqual(before, {path.name: path.read_bytes() for path in inputs.iterdir()})
            for options in ({"prompt_variant": "baseline"}, {"strict_cap": False}):
                with self.assertRaisesRegex(ValueError, "fresh batch root"):
                    d.prepare_inputs(treatment, [1], **options)
            implementation = repository / "fixture.py"
            implementation.write_text("# fixture")
            with patch.object(d, "implementation_files", return_value=[implementation]):
                d.seal_inputs(treatment, [1])
                d.prepare(treatment, [1])
                self.assertEqual(before, {path.name: path.read_bytes() for path in inputs.iterdir()})
                for options in ({"prompt_variant": "baseline"}, {"strict_cap": False},
                                {"portfolio_settings": d.DEFAULT_PORTFOLIO}):
                    with self.assertRaisesRegex(ValueError, "fresh batch root"):
                        d.prepare(treatment, [1], **options)

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
