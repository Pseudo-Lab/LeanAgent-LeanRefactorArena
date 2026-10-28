from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from refactor_eval.session import Session, assess, load_config, run_search, write_json
from refactor_eval.tokens import proof_tokens, validate_declaration, without_comments

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/basic"
STATEMENT = "theorem add_zero (n : Nat) : n + 0 = n"


class FakeEvaluator:
    """Controlled measurements for selection/state-machine behavior tests."""
    def __init__(self):
        self.calls = []
        self.revision = "pinned"
        self.fail_final = set()
        self.interrupt = False

    def fingerprint(self, env):
        return {"id": env["id"], "revision": self.revision}

    def evaluate(self, code, config, environments, output, runs):
        output.mkdir(parents=True)
        self.calls.append((code, runs, [env["id"] for env in environments]))
        if self.interrupt:
            raise KeyboardInterrupt()
        result = {"valid": True, "tokens": 100, "environments": {}, "error": None}
        if "bad" in code:
            result.update(valid=False, error={"kind": "compile"})
            return result
        if "good" in code:
            result["tokens"], hb = 60, 50
        elif "tradeoff" in code:
            result["tokens"], hb = 10, 110
        elif "best" in code:
            result["tokens"], hb = 10, 20
        elif "worse" in code:
            result["tokens"], hb = 150, 150
        else:
            hb = 100
        for env in environments:
            valid = not (runs == 3 and any(tag in code for tag in self.fail_final))
            result["environments"][env["id"]] = {
                "valid": valid, "median_heartbeats": hb,
                "runs": [{"measurement": {"scaled": hb}} for _ in range(runs)]}
            result["valid"] &= valid
        return result


def candidate(tag):
    return STATEMENT + " := by\n  rfl\n-- " + tag + "\n"


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        raw = json.loads((EXAMPLE / "problem.json").read_text())
        for key in ("statement_file", "baseline_file"):
            raw[key] = str(EXAMPLE / raw[key])
        raw["environments"][0]["template_file"] = str(EXAMPLE / "context.lean.in")
        self.problem = self.root / "problem.json"
        write_json(self.problem, raw)
        self.evaluator = FakeEvaluator()
        self.session = Session(self.root / "run", self.evaluator)

    def start(self, *, policy=None, extra_environment=False):
        raw = json.loads(self.problem.read_text())
        if policy:
            raw["scoring"].update(policy)
        if extra_environment:
            other = copy.deepcopy(raw["environments"][0])
            other["id"] = "compatibility"
            raw["environments"].append(other)
        write_json(self.problem, raw)
        return self.session.initialize(self.problem)

    def test_final_selects_global_best_not_last_and_preserves_lineage(self):
        self.start()
        first = self.session.checkpoint(candidate("best"))
        self.session.checkpoint(candidate("good"), parent_id=first["candidate_id"])
        self.session.checkpoint(candidate("bad"))
        selected = self.session.finalize()
        self.assertEqual(selected["winner"]["candidate_id"], first["candidate_id"])
        self.assertEqual((self.session.directory / selected["source"]).read_text(), candidate("best"))
        manifest = self.session.status()
        self.assertEqual(manifest["candidates"][2]["parent_id"], first["candidate_id"])
        self.assertEqual(len(manifest["candidates"]), 4)
        self.assertEqual(sum(runs == 3 for _, runs, _ in self.evaluator.calls), 4)

    def test_proposer_gets_failure_feedback_before_next_call(self):
        self.start()
        observations = []
        def propose(feedback):
            observations.append(feedback)
            if len(observations) == 1:
                return {"code": candidate("bad"), "score": 999999}
            self.assertFalse(feedback["latest_evaluation"]["result"]["valid"])
            self.assertEqual(feedback["incumbent_id"], "baseline")
            return {"code": candidate("good"), "parent_id": feedback["latest_candidate_id"]}
        selected = run_search(self.session, propose, max_attempts=2)
        self.assertEqual(selected["winner"]["candidate_id"], "candidate-0002")
        self.assertEqual(self.session.status()["candidates"][2]["parent_id"], "candidate-0001")

    def test_final_requires_all_environments_and_rechecks_intermediate_winner(self):
        self.start(extra_environment=True)
        self.session.checkpoint(candidate("best"))
        second = self.session.checkpoint(candidate("good"))
        self.evaluator.fail_final.add("best")
        selected = self.session.finalize()
        self.assertEqual(selected["winner"]["candidate_id"], second["candidate_id"])
        self.assertEqual(self.evaluator.calls[1][2], ["lean-4-26"])
        self.assertTrue(all(len(envs) == 2 for _, runs, envs in self.evaluator.calls if runs == 3))

    def test_no_improvement_and_ties_keep_original(self):
        self.start()
        self.session.checkpoint(candidate("worse"))
        self.session.checkpoint(candidate("same"))
        self.assertEqual(self.session.finalize()["winner"]["candidate_id"], "baseline")

    def test_tradeoffs_allowed_by_default(self):
        self.start()
        self.assertTrue(self.session.checkpoint(candidate("tradeoff"))["accepted"])

    def test_non_regression_policy_rejects_tradeoff(self):
        self.start(policy={"require_non_regression": True})
        result = self.session.checkpoint(candidate("tradeoff"))
        self.assertFalse(result["assessment"]["eligible"])
        self.assertEqual(result["assessment"]["reason"], "metric_regression")
        self.assertEqual(self.session.finalize()["winner"]["candidate_id"], "baseline")

    def test_minimum_gain_threshold(self):
        self.start(policy={"minimum_gain": 50})
        self.assertFalse(self.session.checkpoint(candidate("good"))["accepted"])
        self.assertTrue(self.session.checkpoint(candidate("best"))["accepted"])

    def test_baseline_final_failure_does_not_select_unverified_original(self):
        self.start()
        self.evaluator.fail_final.add("induction")
        with self.assertRaisesRegex(ValueError, "baseline verification failed"):
            self.session.finalize()
        self.assertIsNone(self.session.status()["selection"])

    def test_snapshot_tampering_is_detected_before_finalization(self):
        self.start()
        row = self.session.checkpoint(candidate("good"))
        path = self.session.directory / "candidates" / (row["candidate_id"] + ".lean")
        path.write_text(candidate("best"))
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.session.finalize()

    def test_config_change_cannot_silently_change_scoring(self):
        self.start()
        path = self.session.directory / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["config"]["scoring"]["heartbeat_weight"] = 0
        write_json(path, manifest)
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            self.session.finalize()

    def test_environment_change_blocks_comparison(self):
        self.start()
        self.evaluator.revision = "modified"
        with self.assertRaisesRegex(ValueError, "environment changed"):
            self.session.checkpoint(candidate("good"))

    def test_interrupted_checkpoint_requires_recovery_and_is_never_a_score(self):
        self.start()
        self.evaluator.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            self.session.checkpoint(candidate("best"))
        with self.assertRaisesRegex(ValueError, "Interrupted measurement"):
            self.session.finalize()
        self.evaluator.interrupt = False
        self.session.recover()
        result = self.session.checkpoint(candidate("good"))
        self.assertTrue(result["accepted"])
        self.assertFalse(self.session.status()["candidates"][1]["evaluations"][0]["result"]["valid"])

    def test_interrupted_finalization_preserves_history_and_can_restart(self):
        self.start()
        self.session.checkpoint(candidate("good"))
        self.evaluator.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            self.session.finalize()
        self.evaluator.interrupt = False
        self.session.recover()
        selected = self.session.finalize()
        self.assertEqual(selected["batch"], "final-002")
        self.assertEqual(self.session.status()["finalizations"][0]["status"], "interrupted")

    def test_new_checkpoint_invalidates_current_selection(self):
        self.start()
        selected = self.session.finalize()
        self.session.checkpoint(candidate("good"))
        self.assertIsNone(self.session.status()["selection"])
        self.assertTrue((self.session.directory / selected["source"]).exists())

    def test_selected_export_tampering_is_detected(self):
        self.start()
        selected = self.session.finalize()
        (self.session.directory / selected["source"]).write_text("changed")
        with self.assertRaisesRegex(ValueError, "Selected artifact changed"):
            self.session.status()

    def test_earliest_candidate_wins_equal_scores(self):
        self.start()
        first = self.session.checkpoint(candidate("good first"))
        self.session.checkpoint(candidate("good second"))
        self.assertEqual(self.session.finalize()["winner"]["candidate_id"], first["candidate_id"])

    def test_extreme_and_invalid_policy_is_rejected_before_run_creation(self):
        for policy in ({"token_weight": 1e308, "heartbeat_weight": 1e308},
                       {"token_weight": 0, "heartbeat_weight": 0},
                       {"minimum_gain": -1}, {"require_non_regression": "false"}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.start(policy=policy)
        self.assertFalse(self.session.directory.exists())

    def test_concurrent_writer_is_rejected(self):
        self.start()
        with self.session._locked():
            with self.assertRaisesRegex(ValueError, "Another process"):
                Session(self.session.directory, self.evaluator).checkpoint(candidate("good"))

    def test_nonfinite_evaluation_cannot_win(self):
        self.start()
        original = self.evaluator.evaluate
        def malformed(*args):
            result = original(*args)
            result["environments"]["lean-4-26"]["median_heartbeats"] = float("nan")
            return result
        self.evaluator.evaluate = malformed
        # Bad backend data is retained only as a failure, not written as JSON NaN.
        result = self.session.checkpoint(candidate("best"))
        self.assertFalse(result["result"]["valid"])
        self.assertIsNone(result["assessment"]["score"])
        self.assertIsNone(self.session.status()["pending"])


class TokenAndPolicyTests(unittest.TestCase):
    def test_counts_proof_not_signature(self):
        self.assertEqual(proof_tokens(STATEMENT + " := by\n  rfl", STATEMENT), 2)
        statement = "theorem f : (let x := 1; x = 1)"
        self.assertEqual(proof_tokens(statement + " := by\n  rfl", statement), 2)

    def test_nested_comments_do_not_add_tokens_or_ban_words(self):
        code = STATEMENT + " := by\n /- outer /- sorry -/ comment -/\n rfl -- admit\n"
        self.assertEqual(proof_tokens(code, STATEMENT), 2)
        validate_declaration(code, STATEMENT)

    def test_strings_and_quoted_names_preserve_comment_markers(self):
        self.assertEqual(without_comments('"-- /- x -/" «--name» --gone'), '"-- /- x -/" «--name» ')
        with self.assertRaises(ValueError):
            without_comments("/- unclosed")

    def test_modified_statement_and_forbidden_constructs_rejected(self):
        for code in [STATEMENT.replace("n + 0", "0 + n") + " := by\n rfl",
                     *[STATEMENT + " := by\n " + body for body in (
                         "sorry", "exact sorryAx _ true", "native_decide", "set_option maxHeartbeats 0 in rfl",
                         "rfl\n theorem injected : True := by trivial", "run_tac pure ()")]]:
            with self.subTest(code=code), self.assertRaises(ValueError):
                validate_declaration(code, STATEMENT)

    def test_zero_heartbeat_baseline_is_finite_and_not_free_improvement(self):
        config, _ = load_config(EXAMPLE / "problem.json")
        base = {"valid": True, "tokens": 10, "environments": {"lean-4-26": {"median_heartbeats": 0}}}
        self.assertEqual(assess(base, base, config, original=True)["score"], 0)
        worse = copy.deepcopy(base)
        worse["environments"]["lean-4-26"]["median_heartbeats"] = 1
        self.assertLess(assess(worse, base, config)["score"], 0)


if __name__ == "__main__":
    unittest.main()
