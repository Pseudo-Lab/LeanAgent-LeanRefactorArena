import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_submission_provenance import (  # noqa: E402
    GENERATOR_FILES, HARNESS_CODE, ROUTE60_GENERATOR_FILES, HarnessRoot, RunRoot, check, sha)
import hashlib  # noqa: E402

STATEMENT = "theorem t (n : Nat) : n + 0 = n :="
REFERENCE = STATEMENT + " by\n  induction n with\n  | zero => rfl\n  | succ k ih => simp"
NEW = STATEMENT + " by\n  simp"
CODEX = STATEMENT + " by\n  exact Nat.add_zero n -- produced by an interactive agent outside OpenRouter"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
BENCHMARK = [{"name": "t", "statement": STATEMENT, "proof": REFERENCE}]


def make_root(base, proof, *, endpoint=OPENROUTER, costs=("0.50", "0.25"), prompt="", audit=True):
    root = Path(base)
    folder = root / "problems" / "F001"
    (folder / "input").mkdir(parents=True)
    (folder / "input" / "problem.json").write_text(json.dumps({"name": "t"}))
    (folder / "selected.lean").write_text(proof + "\n")
    attempts = {}
    for step, cost in enumerate(costs, 1):
        attempts[f"a{step}"] = {"row": 1, "step": step, "status": "settled", "cost_usd": cost}
        (folder / "steps" / f"{step:04}").mkdir(parents=True)
        packet = json.dumps({"parent": prompt, "statement": STATEMENT})
        request = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": packet}]}
        (folder / "steps" / f"{step:04}" / "request.json").write_text(json.dumps(request))
    (root / "authorization.json").write_text(json.dumps({"rows": [1], "api_endpoint": endpoint}))
    (root / "ledger.json").write_text(json.dumps({"attempts": attempts}))
    if audit:
        (root / "report.json").write_text(json.dumps({"audit_passed": True}))
    return RunRoot(root)


def current_hashes(route60=True):
    """The hashes a run made with this checkout's route code records in protocol.json."""
    return {name: hashlib.sha256((HARNESS_CODE / name).read_bytes()).hexdigest()
            for name in (ROUTE60_GENERATOR_FILES if route60 else GENERATOR_FILES)}


def make_route(base, proof, *, route60=True, seeds=False, carry=(), paid=False, call=None, hashes=None,
               label="reference/test-rule"):
    """A finished route60 (round-01/F001) or route20 (F001) output directory."""
    root = Path(base)
    folder = root / ("round-01/F001" if route60 else "F001")
    folder.mkdir(parents=True)
    (folder / "selected.json").write_text(json.dumps({"row": 1, "name": "t", "proof": proof, "call": call,
                                                      "selected": label}))
    code = current_hashes(route60) if hashes is None else hashes
    if route60:
        protocol = {"rounds": 1, "team_seeds": seeds, "carry_sha256": carry[0] if carry else None,
                    "carry_sha256s": list(carry), "code_hashes": code}
        report = {"official": False, "assisted": seeds or bool(carry), "api_calls": 0, "coverage": 1,
                  "failed": {}, "rows": {"1": {"score": 40, "chosen": label}}}
    else:
        protocol = {"rows": [1], "paid": paid, "team_seeds": "solutions" if seeds else None, "code_hashes": code}
        report = {"paid_enabled": paid, "assisted": seeds}
    if code is False:
        protocol.pop("code_hashes")
    (root / "protocol.json").write_text(json.dumps(protocol))
    (root / "report.json").write_text(json.dumps(report))
    return HarnessRoot(root)


def run(roots=(), submission=None, manifest=(), outside=(), cap=Decimal("3"), benchmark=None, harness=()):
    return check(benchmark or BENCHMARK, submission or [{"name": "t", "proof": NEW}], list(roots), list(manifest),
                 list(outside), cap, list(harness))


class ProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_openrouter_run_within_cap(self):
        result = run([make_root(self.base / "r", NEW)])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["rows"][0]["cost_usd"], "0.75")
        self.assertEqual(result["rows"][0]["calls"], 2)

    def test_reference_needs_no_run(self):
        self.assertEqual(run(submission=[{"name": "t", "proof": REFERENCE + "\n"}])["errors"], [])

    def test_direct_provider_run_fails(self):
        root = make_root(self.base / "r", NEW, endpoint="https://api.openai.com/v1/chat/completions")
        self.assertTrue(any("not OpenRouter" in e for e in run([root])["errors"]))

    def test_cost_over_cap_and_prior_spend(self):
        root = make_root(self.base / "r", NEW, costs=("2.00",))
        self.assertEqual(run([root])["errors"], [])
        prior = [{"name": "t", "prior_cost_usd": "1.50"}]
        self.assertTrue(any("exceeds" in e for e in run([root], manifest=prior)["errors"]))

    def test_unmatched_proof_fails(self):
        errors = run([make_root(self.base / "r", STATEMENT + " by omega")])["errors"]
        self.assertTrue(any("no OpenRouter run evidence" in e for e in errors))

    def test_missing_report_fails(self):
        errors = run([make_root(self.base / "r", NEW, audit=False)])["errors"]
        self.assertTrue(any("report.json" in e for e in errors))

    def test_non_openrouter_proof_submitted(self):
        errors = run(submission=[{"name": "t", "proof": CODEX}], outside=[("codex/F001.lean", CODEX)])["errors"]
        self.assertTrue(any("equals a non-OpenRouter proof" in e for e in errors))

    def test_non_openrouter_proof_used_as_seed(self):
        root = make_root(self.base / "r", NEW, prompt=CODEX)
        errors = run([root], outside=[("codex/F001.lean", CODEX)])["errors"]
        self.assertTrue(any("contains non-OpenRouter proof" in e for e in errors))
        clean = make_root(self.base / "c", NEW, prompt=REFERENCE)
        self.assertEqual(run([clean], outside=[("codex/F001.lean", CODEX)])["errors"], [])

    def test_manifest_entry(self):
        entry = {"name": "t", "proof_sha256": sha(NEW), "api_endpoint": OPENROUTER, "cost_usd": "2.10",
                 "evidence": "runs/route60/ledger.json"}
        result = run(manifest=[entry])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["rows"][0]["origin"], "manifest (self-declared)")
        direct = dict(entry, api_endpoint="https://api.openai.com/v1/responses")
        self.assertTrue(any("not OpenRouter" in e for e in run(manifest=[direct])["errors"]))

    def test_missing_problem_reported(self):
        self.assertEqual(run(submission=[{"name": "other", "proof": NEW}])["missing"], ["t"])

    def test_reference_from_official_src_field(self):
        # The official final and warm-up JSONL rows keep the original under `src` (no `proof` key).
        official = [{"name": "t", "statement": STATEMENT, "src": REFERENCE}]
        result = run(submission=[{"name": "t", "proof": REFERENCE}], benchmark=official,
                     outside=[("team/F001.lean", REFERENCE)])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["rows"][0]["origin"], "reference")
        # The original inside a model request is not a leak of an outside proof.
        root = make_root(self.base / "r", NEW, prompt=REFERENCE)
        self.assertEqual(run([root], benchmark=official, outside=[("team/F001.lean", REFERENCE)])["errors"], [])

    def test_unassisted_route60_proof_is_a_zero_cost_harness_transform(self):
        result = run(harness=[make_route(self.base / "h", NEW)])
        self.assertEqual(result["errors"], [])
        self.assertEqual((result["rows"][0]["origin"], result["rows"][0]["cost_usd"]), ("deterministic-harness", "0"))
        route20 = make_route(self.base / "h20", NEW, route60=False)
        self.assertEqual(run(harness=[route20])["errors"], [])

    def test_assisted_or_paid_harness_runs_certify_nothing(self):
        cases = {
            "seeds": make_route(self.base / "s", NEW, seeds=True),
            "carry": make_route(self.base / "c", NEW, carry=("ab" * 32,)),
            "paid": make_route(self.base / "p", NEW, route60=False, paid=True,
                               call={"status": "billed", "charged_usd": "0.10"}),
        }
        for label, root in cases.items():
            with self.subTest(label):
                self.assertTrue(any("cannot certify" in e or "records a model call" in e
                                    for e in run(harness=[root])["errors"]))
        self.assertTrue(any("equals a non-OpenRouter proof" in e for e in
                            run(harness=[make_route(self.base / "x", CODEX)],
                                submission=[{"name": "t", "proof": CODEX}],
                                outside=[("codex/F001.lean", CODEX)])["errors"]))

    def test_harness_certificate_records_label_and_code(self):
        row = run(harness=[make_route(self.base / "h", NEW, label="reference/delta-predicate")])["rows"][0]
        self.assertEqual(row["harness_label"], "reference/delta-predicate")
        self.assertEqual(row["code_hashes"], current_hashes())

    def test_harness_run_made_by_other_code_certifies_nothing(self):
        cases = {
            "no hashes": (make_route(self.base / "none", NEW, hashes=False), "records no code hashes"),
            "changed rule": (make_route(self.base / "other", NEW, hashes={**current_hashes(), "assigned_routes.py": "0" * 64}),
                             "assigned_routes.py differs"),
            "missing file": (make_route(self.base / "partial", NEW, hashes={
                k: v for k, v in current_hashes().items() if k != "route60.py"}), "no hash for route60.py"),
            "route20": (make_route(self.base / "r20", NEW, route60=False, hashes={
                **current_hashes(False), "reuse_scout.py": "1" * 64}), "reuse_scout.py differs"),
        }
        for label, (root, message) in cases.items():
            with self.subTest(label):
                self.assertTrue(any(message in e for e in run(harness=[root])["errors"]))

    def test_only_the_final_route60_selection_is_certified(self):
        later = STATEMENT + " by\n  omega"
        root = self.base / "rounds"
        make_route(root, NEW)
        second = root / "round-02/F001"
        second.mkdir(parents=True)
        (second / "selected.json").write_text(json.dumps({"row": 1, "name": "t", "proof": later, "call": None,
                                                          "selected": "previous-round/next"}))
        harness = HarnessRoot(root)
        self.assertEqual(run(harness=[harness], submission=[{"name": "t", "proof": later}])["errors"], [])
        self.assertTrue(any("no OpenRouter run evidence" in e for e in run(harness=[harness])["errors"]))
        # A later failed recheck revokes the row: report.json drops it and incomplete.json remains.
        revoked = self.base / "revoked"
        make_route(revoked, NEW)
        (revoked / "round-02/F001").mkdir(parents=True)
        (revoked / "round-02/F001/incomplete.json").write_text(json.dumps({"round": 2, "error": "recheck failed"}))
        report = json.loads((revoked / "report.json").read_text())
        report.update(rows={}, failed={"1": {"round": 2, "error": "recheck failed"}}, coverage=0)
        (revoked / "report.json").write_text(json.dumps(report))
        self.assertTrue(any("no OpenRouter run evidence" in e for e in run(harness=[HarnessRoot(revoked)])["errors"]))

    def test_spend_counts_every_run_root_for_every_origin(self):
        first = make_root(self.base / "a", NEW, costs=("2.00",))
        other = make_root(self.base / "b", STATEMENT + " by\n  omega", costs=("1.50",))
        result = run([first, other])
        self.assertEqual(result["rows"][0]["cost_usd"], "3.50")
        self.assertTrue(any("exceeds" in e for e in result["errors"]))
        reference = run([first, other], submission=[{"name": "t", "proof": REFERENCE}])
        self.assertEqual((reference["rows"][0]["origin"], reference["rows"][0]["cost_usd"]), ("reference", "3.50"))
        self.assertTrue(any("exceeds" in e for e in reference["errors"]))
        harness = run([other], harness=[make_route(self.base / "h", NEW)])
        self.assertEqual((harness["rows"][0]["origin"], harness["rows"][0]["cost_usd"]),
                         ("deterministic-harness", "1.50"))
        self.assertEqual(harness["errors"], [])
        # An unsettled call in any root leaves the spend unknown.
        ledger = json.loads((self.base / "b/ledger.json").read_text())
        ledger["attempts"]["a1"]["status"] = "pending"
        (self.base / "b/ledger.json").write_text(json.dumps(ledger))
        errors = run([first, RunRoot(self.base / "b")])["errors"]
        self.assertTrue(any("unsettled calls for F001" in e for e in errors))

    def test_leak_scan_skips_unchanged_originals_of_other_rows(self):
        # Two rows from one source file: the later row's prompt holds the earlier row's original.
        earlier = "theorem s (n : Nat) : 0 + n = n :="
        earlier_original = earlier + " by\n  induction n with\n  | zero => rfl\n  | succ k ih => omega"
        benchmark = [{"name": "s", "statement": earlier, "src": earlier_original},
                     {"name": "t", "statement": STATEMENT, "src": REFERENCE}]
        root = make_root(self.base / "r", NEW, prompt=earlier_original)
        outside = [("team/F001.lean", earlier_original), ("codex/F002.lean", CODEX)]
        result = run([root], benchmark=benchmark, outside=outside)
        self.assertEqual([e for e in result["errors"] if e.startswith("t:")], [])
        leaked = make_root(self.base / "x", NEW, prompt=CODEX)
        self.assertTrue(any("contains non-OpenRouter proof codex/F002.lean" in e
                            for e in run([leaked], benchmark=benchmark, outside=outside)["errors"]))

    def test_route_directory_as_run_root_is_a_clear_error(self):
        make_route(self.base / "h", NEW)
        with self.assertRaisesRegex(ValueError, "--harness-root"):
            RunRoot(self.base / "h")
        with self.assertRaisesRegex(ValueError, "missing report.json"):
            (self.base / "h" / "report.json").unlink()
            HarnessRoot(self.base / "h")


if __name__ == "__main__":
    unittest.main()
