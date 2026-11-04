"""Historical sources seed a fresh, unpaid state only after current checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_agent import artifacts as a, harness as h
import driver as d
import warm_start as w


def result(tokens=4, hb=40, all_versions=False):
    env = {"valid": True, "runs": [{"measurement": {"raw": hb}} for _ in range(3)]}
    return {"valid": True, "tokens": tokens,
            "environments": {"primary": env, **({"secondary": copy.deepcopy(env)} if all_versions else {})}}


class WarmStartTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.problem = {"id": "F002", "row": 2, "name": "test", "source": "strata", "dataset_sha256": d.DATASET_SHA,
                        "statement": "theorem test : True", "reference": "theorem test : True := by trivial\n",
                        "environments": ["primary", "secondary"]}
        self.code = "theorem test : True := by exact True.intro\n"
        self.manifest = {"schemaVersion": 1, "auditPassed": True, "datasetSha256": d.DATASET_SHA,
            "problems": [{"row": 2, "name": "test", "source": "strata", "proof": self.code,
                          "candidateHash": a.sha(self.code), "runId": "historical-best",
                          "versions": [{"environment": e, "status": "pass"} for e in self.problem["environments"]]}]}
        self.path = self.root / "manifest.json"
        d.atomic(self.path, self.manifest)
        self.seed = w.snapshot(self.path, self.problem)
        self.config = d.configuration(self.problem, None)
        self.output = d.folder(self.root, 2)
        for name, data in (("problem.json", self.problem), ("config.json", self.config), ("warm-start.json", self.seed)):
            d.atomic(self.output / "input" / name, data)

    def state(self):
        return h.initial_state(self.problem, result(10, 100), self.config)

    def test_seed_is_incumbent_parent_without_replacing_original_or_spend(self):
        state = w.seed_state(self.state(), self.seed, self.problem, result(), result(all_versions=True))
        self.assertEqual(state["best"]["code"], self.code)
        self.assertEqual(state["baseline"], {"tokens": 10, "raw_heartbeats": 100})
        self.assertEqual(state["exploration"]["candidates"]["c000"]["code"], self.problem["reference"])
        self.assertEqual((state["calls"], state["step"], state["cost_usd"]), (0, 0, "0"))
        packet = json.loads(d.make_request(state, self.problem, self.config, "JSON actions")["messages"][1]["content"])
        self.assertEqual(packet["exploration"]["best_candidate_id"], "seed-best")
        self.assertEqual(packet["best"]["code"], self.code)
        # The first real proposal remains c001; it can branch directly from seed-best.
        raw = {"choices": [{"message": {"content": json.dumps({"action": "propose", "parent_id": "seed-best",
            "strategy": "improve incumbent", "proof": "by trivial"})}}], "usage": {"cost": "0.01"}}
        from lean_agent import actions
        action, code, observation = actions.prepare(raw, state, self.problem, self.config, {"entries": []}, h.parse_proof)
        advanced = h.advance(state, raw, code, result(3, 30), None, state["baseline"], self.config, str(self.output),
                             action=action, observation=observation)
        self.assertEqual(advanced["exploration"]["candidates"]["c001"]["parent_id"], "seed-best")
        self.assertEqual(advanced["calls"], 1)
        self.assertEqual(advanced["cost_usd"], "0.01")

    def test_worse_seed_cannot_replace_original(self):
        state = w.seed_state(self.state(), self.seed, self.problem, result(20, 200), result(all_versions=True))
        self.assertEqual(state["exploration"]["best_candidate_id"], "c000")
        self.assertIn("seed-best", state["exploration"]["candidates"])

    def test_seed_id_cannot_hide_recent_failure_after_sorted_checkpoint(self):
        from lean_agent import actions
        state = w.seed_state(self.state(), self.seed, self.problem, result(), result(all_versions=True))
        state["exploration"]["candidates"]["c001"] = {
            "step": 1, "code": "broken proof", "parent_id": "seed-best", "strategy": "failed rewrite", "valid": False,
            "feedback": {"status": "proof_rejected", "valid": False, "details": "unknown constant", "issues": []}}
        # Canonical checkpoint ordering places seed-best last lexically.
        state = json.loads(a.canonical(state))
        self.assertEqual(list(state["exploration"]["candidates"])[-1], "seed-best")
        self.assertEqual(actions.view(state, self.config)["repair_context"]["candidate_id"], "c001")

    def test_identity_hash_statement_and_versions_are_checked(self):
        mutations = [lambda x: x.update(datasetSha256="different"), lambda x: x.update(auditPassed=False),
            lambda x: x["problems"][0].update(name="different"),
            lambda x: x["problems"][0].update(candidateHash="wrong"),
            lambda x: x["problems"][0].update(versions=[])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                d.atomic(self.path, manifest)
                with self.assertRaises(ValueError):
                    w.snapshot(self.path, self.problem)
        changed = {**self.problem, "statement": "theorem another : False"}
        with self.assertRaisesRegex(ValueError, "identity"):
            w.validate(self.seed, changed)

    def test_historical_metrics_are_not_trusted_and_seed_must_pass_now(self):
        self.manifest["problems"][0]["candidate"] = {"tokens": 0, "raw_heartbeats": 0}
        d.atomic(self.path, self.manifest)
        self.assertNotIn("candidate", w.snapshot(self.path, self.problem)["candidate"])
        failed = result(all_versions=True)
        failed["environments"]["secondary"]["valid"] = False
        with self.assertRaisesRegex(ValueError, "paid dispatch blocked"):
            w.seed_state(self.state(), self.seed, self.problem, result(), failed)
        cached = result()
        cached["environments"]["primary"]["cache"] = {"hit": True}
        with self.assertRaisesRegex(ValueError, "fresh"):
            w.seed_state(self.state(), self.seed, self.problem, cached, result(all_versions=True))
        short = result()
        short["environments"]["primary"]["runs"].pop()
        with self.assertRaisesRegex(ValueError, "three"):
            w.seed_state(self.state(), self.seed, self.problem, short, result(all_versions=True))

    def test_preflight_restart_preserves_advanced_state_and_does_not_repeat_checks(self):
        calls = []
        class Fake:
            def evaluate(inner, code, problem, path, **kwargs):
                calls.append(kwargs)
                return result(10, 100) if code == problem["reference"] else result(all_versions=kwargs.get("all_versions", False))
        with patch.object(d.transport, "query", side_effect=AssertionError("No paid call")):
            initial = d.ensure_baseline(self.root, 2, Fake())
            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[1], {"repetitions": 3, "fresh": True})
            self.assertEqual(calls[2], {"repetitions": 1, "all_versions": True})
            saved = copy.deepcopy(initial)
            saved.update(step=4, calls=4, cost_usd="0.04")
            d.atomic(self.output / "state.json", saved)
            self.assertEqual(d.ensure_baseline(self.root, 2, Fake()), initial)
            self.assertEqual(len(calls), 3)
            self.assertEqual(a.read(self.output / "state.json"), saved)

    def test_invalid_seed_prevents_ready_preflight_and_api_dispatch(self):
        class Fake:
            def evaluate(inner, code, problem, path, **kwargs):
                value = result(10, 100) if code == problem["reference"] else result(all_versions=kwargs.get("all_versions", False))
                if kwargs.get("all_versions") and code != problem["reference"]:
                    value["valid"] = False
                return value
        with patch.object(d, "verify_frozen"), patch.object(d, "evaluator", return_value=Fake()), \
                patch.object(d, "run_problem") as paid:
            with self.assertRaisesRegex(ValueError, "Preflight failed"):
                d.run_with_preflight(self.root, 2, True)
            paid.assert_not_called()
        self.assertEqual(a.read(self.output / "preflight.json")["status"], "failed")
        self.assertFalse((self.output / "initial-state.json").exists())

    def test_missing_row_and_explicit_cold_start_are_recorded(self):
        missing = {**self.problem, "row": 3}
        self.assertIsNone(w.snapshot(self.path, missing)["candidate"])
        cold = w.snapshot(None, self.problem, reason="explicit_cold_start")
        self.assertIsNone(cold["candidate"])
        self.assertEqual(cold["reason"], "explicit_cold_start")

    def test_changed_input_or_seed_evidence_rejected_on_resume(self):
        class Fake:
            def evaluate(inner, code, problem, path, **kwargs):
                return result(10, 100) if code == problem["reference"] else result(all_versions=kwargs.get("all_versions", False))
        d.ensure_baseline(self.root, 2, Fake())
        self.seed["candidate"]["code"] += "-- changed\n"
        self.seed["candidate"]["sha256"] = a.sha(self.seed["candidate"]["code"])
        d.atomic(self.output / "input/warm-start.json", self.seed)
        with self.assertRaisesRegex(ValueError, "different candidate"):
            d.ensure_baseline(self.root, 2, Fake())

    def test_existing_old_policy_is_rejected_without_reseal(self):
        d.atomic(self.root / "authorization.json", {"verification_policy": "candidate-cache-final-compatibility-v1"})
        with self.assertRaisesRegex(ValueError, "new batch root"):
            d.prepare(self.root, [2])

    def test_no_portfolio_prepare_snapshots_best_without_api_or_lean_and_freezes_it(self):
        repo, batch = self.root / "repo", self.root / "batch"
        d.atomic(repo / "sources/final/problems/F002.json", self.problem)
        d.atomic(repo / "dashboard/public/data/final-results.json", self.manifest)
        prompt = repo / "examples/actions/prompt.txt"
        prompt.parent.mkdir(parents=True)
        prompt.write_text("JSON actions")
        implementation = repo / "controller.py"
        implementation.write_text("# fixture implementation")
        problem = self.problem
        class Fake:
            def load_problem(inner, row):
                return problem
            def source_context(inner, problem):
                return {"corpus": {"schema_version": 1, "entries": []}, "prompt_context": "context"}
            def evaluate(inner, *args, **kwargs):
                raise AssertionError("Input preparation must not execute Lean")
        with patch.object(d, "REPO", repo), patch.object(d, "implementation_files", return_value=[implementation]), \
                patch.object(d, "evaluator", return_value=Fake()), \
                patch.object(d.transport, "query", side_effect=AssertionError("No paid call")):
            d.prepare(batch, [2], workers=1, portfolio_settings=None)
            stored = a.read(d.folder(batch, 2) / "input/warm-start.json")
            self.assertEqual(stored["candidate"]["code"], self.code)
            self.assertEqual(a.read(batch / "ledger.json")["attempts"], {})
            self.assertFalse((d.folder(batch, 2) / "baseline").exists())
            d.verify_frozen(batch)
            (repo / "dashboard/public/data/final-results.json").unlink()
            d.verify_frozen(batch)  # The run owns its frozen source snapshot.
            stored["candidate"]["code"] += "-- changed"
            d.atomic(d.folder(batch, 2) / "input/warm-start.json", stored)
            with self.assertRaisesRegex(ValueError, "Frozen input"):
                d.verify_frozen(batch)

    def test_audit_detects_seed_metrics_and_compiler_log_tampering(self):
        class Fake:
            def evaluate(inner, code, problem, path, **kwargs):
                value = result(10, 100) if code == problem["reference"] else result(all_versions=kwargs.get("all_versions", False))
                for env, details in value["environments"].items():
                    destination = path / env
                    destination.mkdir(parents=True)
                    for i, record in enumerate(details["runs"]):
                        source, log = f"measure-{i}.lean", f"measure-{i}.log"
                        (destination / source).write_text(code)
                        (destination / log).write_text("verified fixture")
                        record.update(source=source, source_sha256=a.sha(code), log=log, log_sha256=a.sha("verified fixture"))
                return value
        d.ensure_baseline(self.root, 2, Fake())
        w.audit(self.output)
        saved = a.read(self.output / "initial-state.json")
        saved["best"]["tokens"] = 1
        d.atomic(self.output / "initial-state.json", saved)
        with self.assertRaisesRegex(ValueError, "initial state differs"):
            w.audit(self.output)
        (self.output / "warm-start/primary/primary/measure-0.log").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "compiler evidence"):
            w.audit(self.output)
