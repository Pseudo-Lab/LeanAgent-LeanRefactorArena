import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_submission_provenance import RunRoot, check, sha  # noqa: E402

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


def run(roots=(), submission=None, manifest=(), outside=(), cap=Decimal("3")):
    return check(BENCHMARK, submission or [{"name": "t", "proof": NEW}], list(roots), list(manifest),
                 list(outside), cap)


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


if __name__ == "__main__":
    unittest.main()
