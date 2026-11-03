from copy import deepcopy
from decimal import Decimal
import unittest

import openai_transport as t


def response():
    return {"id": "chatcmpl-test", "model": "gpt-6.1-sol", "service_tier": "default",
            "choices": [{"message": {"content": '{"action":"search","query":"foo"}'}}],
            "usage": {"prompt_tokens": 12000, "completion_tokens": 1000, "total_tokens": 13000,
                      "prompt_tokens_details": {"cached_tokens": 4000, "cache_write_tokens": 7000},
                      "completion_tokens_details": {"reasoning_tokens": 800}}}


class OpenAITransportTests(unittest.TestCase):
    def test_cache_categories_disjoint_and_reasoning_not_double_counted(self):
        result = t.compute_cost(response())
        self.assertEqual(result["ordinary_input_tokens"], 1000)
        self.assertEqual(Decimal(result["cost_usd"]), Decimal("0.0299"))
        self.assertFalse(result["invoice_verified"])

    def test_normalization_leaves_provider_response_untouched(self):
        original = response()
        saved = deepcopy(original)
        normalized = t.normalize(original)
        self.assertEqual(original, saved)
        self.assertNotIn("cost", original["usage"])
        self.assertEqual(normalized["usage"]["cost"], "0.0299")
        self.assertEqual(normalized["_cost_receipt"]["basis"], "provider-token-usage-times-frozen-public-list-prices")

    def test_optional_cache_counters_default_to_zero(self):
        raw = response()
        raw["usage"].pop("prompt_tokens_details")
        self.assertEqual(Decimal(t.compute_cost(raw)["cost_usd"]), Decimal("0.034"))

    def test_inconsistent_or_unknown_billing_fails_closed(self):
        cases = []
        raw = response(); raw["usage"]["prompt_tokens_details"]["cache_write_tokens"] = 9000; cases.append(raw)
        raw = response(); raw["usage"]["completion_tokens_details"]["reasoning_tokens"] = 1001; cases.append(raw)
        raw = response(); raw["service_tier"] = "priority"; cases.append(raw)
        raw = response(); raw["usage"]["completion_tokens"] = True; cases.append(raw)
        raw = response(); raw["usage"]["prompt_tokens_details"]["cache_write_tokens_details"] = {"ttl_30m_tokens": 6000, "ttl_12h_tokens": 1000}; cases.append(raw)
        raw = response(); raw["usage"]["completion_tokens_details"] = ["invalid"]; cases.append(raw)
        cases.extend(({"transport_error": "TimeoutError"}, {"usage": None}, []))
        for raw in cases:
            with self.subTest(raw=raw):
                normalized = t.normalize(raw)
                self.assertIsNone(normalized["usage"]["cost"])

    def test_direct_wire_schema_and_conservative_bound(self):
        model = {"id": "gpt-6.1-sol", "backend": "openai", "max_tokens": 8192, "seed": 42, "reasoning_effort": "high"}
        body = t.payload([{"role": "system", "content": "JSON instructions"}, {"role": "user", "content": "proof"}], model)
        self.assertEqual(body["max_completion_tokens"], 8192)
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["service_tier"], "default")
        self.assertEqual(body["prompt_cache_options"], {"mode": "explicit", "ttl": "30m"})
        self.assertEqual(body["messages"][0]["content"], [{"type": "text", "text": "JSON instructions",
                         "prompt_cache_breakpoint": {"mode": "explicit"}}])
        self.assertEqual(body["messages"][1]["content"], "proof")
        self.assertNotIn("provider", body)
        self.assertNotIn("tools", body)
        self.assertNotIn("plugins", body)
        bound = t.request_cost(body)
        expected = (Decimal(bound["input_token_bound"]) * Decimal("2.5") + 8192 * Decimal("10")) / 1000000
        self.assertEqual(Decimal(bound["reserved_usd"]), expected)

    def test_cache_wire_shape_preserves_text_and_rejects_other_content_parts(self):
        model = {"id": "gpt-6.1-sol", "backend": "openai", "max_tokens": 8192, "seed": 42, "reasoning_effort": "high"}
        messages = [{"role": "system", "content": "stable exact λ\nJSON instructions"},
                    {"role": "user", "content": "variable exact user suffix"}]
        original = deepcopy(messages)
        body = t.payload(messages, model)
        self.assertEqual(messages, original)
        self.assertEqual(body["messages"][0]["content"][0]["text"], original[0]["content"])
        cases = []
        changed = deepcopy(body); changed["messages"][0]["content"][0]["type"] = "image_url"; cases.append(changed)
        changed = deepcopy(body); changed["messages"][0]["content"][0]["image_url"] = "x"; cases.append(changed)
        changed = deepcopy(body); changed["messages"][0]["content"][0]["prompt_cache_breakpoint"]["ttl"] = "12h"; cases.append(changed)
        changed = deepcopy(body); changed["messages"][0]["content"].append({"type": "text", "text": "extra"}); cases.append(changed)
        changed = deepcopy(body); changed["messages"][1]["content"] = [{"type": "text", "text": "user"}]; cases.append(changed)
        changed = deepcopy(body); changed["prompt_cache_options"]["mode"] = "implicit"; cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "plain-text request"):
                    t.request_cost(changed)


if __name__ == "__main__":
    unittest.main()
