"""Independent financial-contract regressions using fixtures only."""
from copy import deepcopy
from decimal import Decimal
import json
import os
import unittest
from unittest.mock import patch

import driver
import openai_transport as transport
from lean_agent import harness


def response():
    return {
        "id": "review-fixture", "model": transport.MODEL_ID, "service_tier": "default",
        "choices": [{"message": {"role": "assistant", "content": '{"action":"search","query":"deriv"}'}}],
        "usage": {
            "prompt_tokens": 12000, "completion_tokens": 1000, "total_tokens": 13000,
            "prompt_tokens_details": {"cached_tokens": 4000, "cache_write_tokens": 7000},
            "completion_tokens_details": {"reasoning_tokens": 900},
        },
    }


class TransportReviewTests(unittest.TestCase):
    def test_nonoverlapping_input_categories_and_reasoning_counted_once(self):
        receipt = transport.compute_cost(response())
        self.assertEqual(receipt["ordinary_input_tokens"], 1000)
        self.assertEqual(Decimal(receipt["cost_usd"]), Decimal("0.0299"))
        self.assertEqual(receipt["completion_tokens_including_reasoning"], 1000)
        self.assertFalse(receipt["invoice_verified"])

    def test_documented_optional_cache_counters_default_to_zero(self):
        raw = response()
        del raw["usage"]["prompt_tokens_details"]
        self.assertEqual(Decimal(transport.compute_cost(raw)["cost_usd"]), Decimal("0.034"))

    def test_normalization_does_not_mutate_original_provider_json(self):
        raw = response()
        before = deepcopy(raw)
        normalized = transport.normalize(raw)
        self.assertEqual(raw, before)
        self.assertNotIn("cost", raw["usage"])
        self.assertIn("cost", normalized["usage"])
        self.assertEqual(normalized["choices"], raw["choices"])

    def test_unknown_model_tier_and_usage_fail_closed(self):
        for key, value in (("model", "other-model"), ("service_tier", "priority"), ("usage", None)):
            raw = response()
            raw[key] = value
            with self.subTest(key=key):
                self.assertIsNone(transport.normalize(raw)["usage"]["cost"])

    def test_cache_overlaps_and_twelve_hour_writes_fail_closed(self):
        raw = response()
        raw["usage"]["prompt_tokens_details"]["cached_tokens"] = 6000
        self.assertIsNone(transport.normalize(raw)["usage"]["cost"])
        raw = response()
        raw["usage"]["prompt_tokens_details"]["cache_write_tokens_details"] = {
            "ttl_30m_tokens": 6000, "ttl_12h_tokens": 1000}
        self.assertIsNone(transport.normalize(raw)["usage"]["cost"])

    def test_malformed_falsy_token_details_fail_closed(self):
        for key in ("prompt_tokens_details", "completion_tokens_details"):
            for value in ([], 0, False, ""):
                raw = response()
                raw["usage"][key] = value
                with self.subTest(key=key, value=value):
                    self.assertIsNone(transport.normalize(raw)["usage"]["cost"])

    def test_unexpected_image_tokens_fail_closed_for_plain_text_contract(self):
        raw = response()
        raw["usage"]["prompt_tokens_details"]["image_tokens"] = 100
        self.assertIsNone(transport.normalize(raw)["usage"]["cost"])

    def test_timeout_never_retries(self):
        class Opener:
            count = 0

            def open(self, *args, **kwargs):
                self.count += 1
                raise TimeoutError()

        opener = Opener()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-not-a-real-key"}), \
                patch.object(transport.request, "build_opener", return_value=opener):
            raw = transport.query({"fixture": True}, driver.MODEL, 1)
        self.assertEqual(opener.count, 1)
        self.assertEqual(raw["transport_error"], "TimeoutError")

    def test_common_request_transforms_to_direct_provider_contract(self):
        problem = {"id": "fixture", "statement": "theorem test : True",
                   "reference": "theorem test : True := by trivial\n"}
        baseline = {"valid": True, "tokens": 2,
                    "environments": {"primary": {"valid": True, "runs": [{"measurement": {"raw": 100}}]}}}
        config = {"model": driver.MODEL,
                  "limits": {"max_calls": None, "cost_stop_usd": "1.00", "max_request_characters": 190000},
                  "agent": {"mode": "actions-v1", "corpus": "fixture.json", "allow_finish": False}}
        state = harness.initial_state(problem, baseline, config)
        body = driver.make_request(state, problem, config, "Return a JSON action.")
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["seed"], 42)
        self.assertEqual(body["max_completion_tokens"], driver.MODEL["max_tokens"])
        self.assertEqual(body["service_tier"], "default")
        self.assertEqual(body["prompt_cache_options"], {"mode": "explicit", "ttl": "30m"})
        self.assertEqual(body["messages"][0]["content"], [{"type": "text", "text": "Return a JSON action.",
                         "prompt_cache_breakpoint": {"mode": "explicit"}}])
        self.assertFalse(set(body) & {"provider", "plugins", "reasoning", "max_tokens", "temperature"})
        packet = json.loads(body["messages"][1]["content"])
        self.assertEqual(packet["budget"]["stop_at_usd"], "1.00")
        self.assertNotIn("finish", packet["exploration"]["actions"])
        self.assertGreater(Decimal(transport.request_cost(body)["reserved_usd"]), 0)


if __name__ == "__main__":
    unittest.main()
