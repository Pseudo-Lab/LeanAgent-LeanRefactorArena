import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import report


class ReportTests(unittest.TestCase):
    def test_receipt_hash_and_cost_are_checked_before_export(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)

            def write(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))

            write(root / "authorization.json", {"rows": [1], "dataset_sha256": "test",
                  "per_problem_target_usd": "1.00"})
            problem = root / "problems/F001"
            write(problem / "input/problem.json", {"name": "test", "source": "test"})
            request = {"model": "fixture", "messages": []}
            canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            write(problem / "steps/0001/request.json", request)
            raw = {"id": "generation-one", "model": "gpt-6.1-sol", "service_tier": "default",
                   "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050,
                             "prompt_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 30}}}
            cost = report.compute_cost(raw)["cost_usd"]
            write(problem / "steps/0001/provider-response.json", raw)
            normalized = report.normalize(raw)
            write(problem / "steps/0001/response.json", normalized)
            write(root / "ledger.json", {"attempts": {"F001-0001": {"row": 1, "step": 1,
                  "status": "settled", "cost_usd": cost, "response_id": "generation-one",
                  "provider_response_sha256": normalized["_cost_receipt"]["provider_response_sha256"],
                  "request_sha256": report.sha(canonical)}}})
            result = report.build_report(root)
            self.assertTrue(result["audit_passed"])
            self.assertFalse(result["all_completed"])
            raw["choices"] = [{"message": {"content": "changed candidate with identical usage"}}]
            write(problem / "steps/0001/provider-response.json", raw)
            result = report.build_report(root)
            self.assertFalse(result["audit_passed"])
            self.assertTrue(any("raw provider receipt hash" in error for error in result["audit_errors"]))
            del raw["choices"]
            raw["usage"]["completion_tokens"] = 60
            raw["usage"]["total_tokens"] = 1060
            write(problem / "steps/0001/provider-response.json", raw)
            result = report.build_report(root)
            self.assertFalse(result["audit_passed"])
            self.assertIn("provider token accounting differs", result["audit_errors"][0])

    def test_cli_rejects_old_or_missing_policy_before_report_writes(self):
        for policy in (None, "candidate-cache-final-compatibility-v1"):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                authorization = {} if policy is None else {"verification_policy": policy}
                path = root / "authorization.json"
                path.write_text(json.dumps(authorization))
                before = path.read_bytes()
                with patch("sys.argv", ["report.py", "--root", str(root)]), patch.object(report, "build_report") as build:
                    with self.assertRaisesRegex(ValueError, "Different verification policy"):
                        report.main()
                    build.assert_not_called()
                self.assertEqual(list(root.iterdir()), [path])
                self.assertEqual(path.read_bytes(), before)

    def test_incomplete_batch_cannot_be_final_export(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "authorization.json").write_text(json.dumps({"rows": [1], "dataset_sha256": "test",
                    "per_problem_target_usd": "1.00"}))
            (root / "ledger.json").write_text('{"attempts":{}}')
            path = root / "problems/F001/input"
            path.mkdir(parents=True)
            (path / "problem.json").write_text('{"name":"test","source":"test"}')
            result = report.build_report(root, require_complete=True)
            self.assertFalse(result["audit_passed"])
            self.assertEqual(result["completed"], 0)


if __name__ == "__main__":
    unittest.main()
