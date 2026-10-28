import json
import os
from pathlib import Path
import tempfile
import unittest
from lean_agent import usage_cost as a
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
