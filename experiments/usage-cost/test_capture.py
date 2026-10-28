import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import accounting as a
import live_check as live
from test_accounting import PRICES, event


class UsageRegressions(unittest.TestCase):
    def test_multimodal_tokens_keep_reported_cost_but_do_not_use_text_rates(self):
        record = event("api")
        record["response"]["usage"].update(cost="0.4", input_tokens_details={"audio_tokens": 100})
        result = a.make_receipt(record, "api", PRICES)
        self.assertEqual(result["reported_cost_usd"], "0.4")
        self.assertIsNone(result["estimated_token_cost_usd"])
        self.assertEqual(result["estimate_unavailable_reason"], "unsupported_multimodal_usage")

    def test_partial_codex_tail_keeps_unknown_spend_after_last_completed_turn(self):
        stream = b'{"type":"turn.started"}\n' + json.dumps({"type": "turn.completed", "usage": event()["usage"]}).encode() + b'\n{"type":'
        events, partial = a.parse_codex_jsonl(stream)
        self.assertTrue(partial)
        records = a.codex_turn_records(events, run_id="r", agent_id="a", model="test-model", partial_tail=partial)
        report = a.build_report(records, "subagent", PRICES)
        self.assertEqual(report["summary"]["estimated_token_cost_known_subtotal_usd"], "0.0027")
        self.assertIsNone(report["summary"]["accounted_cost_usd"])
        with self.assertRaises(ValueError):
            a.parse_codex_jsonl(b'{broken}\n')

    def test_alias_types_and_detail_conflicts(self):
        for usage in ({"input_tokens": 1, "prompt_tokens": True},
                      {"prompt_tokens_details": []},
                      {"input_tokens_details": {"cached_tokens": 2}, "prompt_tokens_details": {"cached_tokens": 3}}):
            with self.subTest(usage=usage), self.assertRaises(ValueError):
                a.normalize_usage(usage)

    def test_reported_cost_survives_malformed_usage(self):
        record = event("api", response={"usage": {"cost": "0.4", "prompt_tokens": -1}})
        receipt = a.make_receipt(record, "api", PRICES)
        self.assertEqual(receipt["reported_cost_usd"], "0.4")
        self.assertIsNone(receipt["estimated_token_cost_usd"])
        self.assertIsNotNone(receipt["usage_error"])

    def test_malformed_cost_does_not_erase_usage_or_claim_reported_cost(self):
        record = event("api")
        record["response"]["usage"]["cost"] = "not-money"
        receipt = a.make_receipt(record, "api", PRICES)
        self.assertIsNone(receipt["reported_cost_usd"])
        self.assertEqual(receipt["estimated_token_cost_usd"], "0.0027")
        self.assertIsNotNone(receipt["reported_cost_error"])

    def test_provider_id_cannot_be_reassigned_and_counted_twice(self):
        record = event("api"); record["response"]["id"] = "generation-1"
        first = a.make_receipt(record, "api", PRICES)
        record["event_id"] = "renamed"
        with self.assertRaisesRegex(ValueError, "provider request"):
            a.summarize([first, a.make_receipt(record, "api", PRICES)])

    def test_token_totals_and_agent_breakdown_preserve_unknowns(self):
        rows = [event(), event(event_id="2", agent_id="a2", usage=None, status="failed")]
        result = a.build_report(rows, "subagent", PRICES)
        tokens = result["summary"]["tokens"]["input_tokens"]
        self.assertEqual(tokens, {"total": None, "known_subtotal": 1000, "unknown_entries": 1})
        self.assertEqual(result["by_agent_id"]["a1"]["estimated_token_cost_usd"], "0.0027")
        self.assertIsNone(result["by_agent_id"]["a2"]["accounted_cost_usd"])
        with self.assertRaises(ValueError):
            a.summarize([])

    def test_parent_rollups_and_mixed_runtime_models_are_rejected(self):
        streams = [[{"type": "thread.started", "thread_id": "a"}, {"type": "thread.started", "thread_id": "b"}],
                   [{"type": "item.completed", "item": {"type": "collab_tool_call"}}],
                   [{"type": "turn.started", "model": "different-model"}]]
        for stream in streams:
            with self.subTest(stream=stream), self.assertRaises(ValueError):
                a.codex_turn_records(stream, run_id="r", agent_id="a", model="test-model")

    def test_receipt_hash_handles_unpaired_unicode_without_copying_content(self):
        record = event("api"); record["response"]["content"] = "\ud800"
        receipt = a.make_receipt(record, "api", PRICES)
        self.assertEqual(len(receipt["evidence_sha256"]), 64)
        self.assertNotIn("content", receipt)

    def test_harness_import_includes_failed_proofs_and_pending_calls(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("PROJECT_CACHE_DIR")) as directory:
            root = Path(directory)
            for n in (1, 2):
                folder = root / "steps" / f"{n:03}"
                folder.mkdir(parents=True)
                (folder / "request.json").write_text('{"model":"test-model"}')
            (root / "steps/001/response.json").write_text(json.dumps({"id": "r1", "usage": {"cost": "0.1"}, "choices": []}))
            (root / "steps/001/event.json").write_text('{"rejection":"invalid proof"}')
            records, sources = a.harness_records(root, run_id="run", agent_id="agent")
            report = a.build_report(records, "api", PRICES)
            self.assertEqual(len(sources), 3)
            self.assertEqual(report["summary"]["reported_cost_known_subtotal_usd"], "0.1")
            self.assertIsNone(report["summary"]["reported_cost_usd"])
            self.assertEqual(records[1]["status"], "incomplete")
            self.assertEqual(report["summary"]["unknown_cost_entries"], 1)


class LiveCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ.get("PROJECT_CACHE_DIR")); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "run"
        self.metadata = {"data": {"endpoints": [{"tag": "openai", "provider_name": "OpenAI", "pricing": {
            "prompt": "0.000002", "completion": "0.00001", "input_cache_read": "0.0000001", "input_cache_write": "0.0000025"}}]}}
        self.calls = []
        self.raw = {"model": live.MODEL, "id": "fake-generation", "provider": "OpenAI", "choices": [],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": "0.00035",
                              "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 100}}}

    def network(self, url, body=None, key=None):
        self.calls.append(url)
        if url == live.METADATA_URL:
            self.assertIsNone(key)
            return json.dumps(self.metadata).encode()
        self.assertTrue((self.root / "attempt.json").is_file())
        self.assertEqual(key, "test-key")
        return json.dumps(self.raw).encode()

    def execute(self, network=None):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            return live.run(self.root, network=network or self.network)

    def test_one_call_and_offline_replay(self):
        report = self.execute()
        self.assertEqual(self.calls, [live.METADATA_URL, live.ENDPOINT])
        self.assertEqual(report["summary"]["reported_cost_usd"], "0.00035")
        self.assertEqual(report["summary"]["estimated_token_cost_usd"], "0.0003500")
        with patch.object(live, "fetch", side_effect=AssertionError("network called")):
            self.assertTrue(live.replay(self.root)["replay_passed"])
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"test-key", path.read_bytes())
        with self.assertRaises(FileExistsError):
            self.execute()

    def test_timeout_records_unknown_and_never_retries(self):
        def timeout(url, body=None, key=None):
            if url == live.ENDPOINT:
                self.calls.append(url)
                raise TimeoutError("contains-secret-test-key")
            return self.network(url, body, key)
        report = self.execute(timeout)
        self.assertEqual(self.calls.count(live.ENDPOINT), 1)
        self.assertIsNone(report["summary"]["accounted_cost_usd"])
        self.assertTrue(live.replay(self.root)["replay_passed"])
        self.assertNotIn("contains-secret", (self.root / "call-result.json").read_text())

    def test_price_guard_blocks_generation(self):
        self.metadata["data"]["endpoints"][0]["pricing"]["prompt"] = "1"
        with self.assertRaisesRegex(ValueError, "price guard"):
            self.execute()
        self.assertEqual(self.calls, [live.METADATA_URL])

    def test_replay_detects_receipt_tampering(self):
        self.execute()
        (self.root / "response.json").write_text('{}')
        with self.assertRaisesRegex(ValueError, "integrity"):
            live.replay(self.root)

    def test_keyboard_interrupt_keeps_dispatched_attempt(self):
        def interrupt(url, body=None, key=None):
            if url == live.ENDPOINT:
                raise KeyboardInterrupt()
            return self.network(url, body, key)
        with self.assertRaises(KeyboardInterrupt):
            self.execute(interrupt)
        self.assertEqual(live.recorded_report(self.root)["summary"]["unknown_cost_entries"], 1)
        self.assertTrue((self.root / "attempt.json").exists())

class ObservedUsageTests(unittest.TestCase):
    def test_usage_only_projections_match_actual_reported_costs(self):
        base = Path(__file__).parent / "examples"
        prices = a.read_json((base / "observed-prices.json").read_text())
        records = a.read_json((base / "observed-api-records.json").read_text())
        for record in records:
            with self.subTest(event=record["event_id"]):
                receipt = a.make_receipt(record, "api", prices)
                self.assertEqual(a.money(receipt["reported_cost_usd"]), a.money(receipt["estimated_token_cost_usd"]))
        sub = a.build_report(a.read_json((base / "observed-subagent-records.json").read_text()), "subagent", prices)
        self.assertEqual(sub["summary"]["estimated_token_cost_usd"], "0.1259104")
        self.assertIsNone(sub["summary"]["reported_cost_usd"])


if __name__ == "__main__":
    unittest.main()
