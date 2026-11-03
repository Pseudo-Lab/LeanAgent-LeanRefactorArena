"""final60 transport: pinned payloads, bounds, receipts, guarded dispatch and the driver adapter.

Fixture transports only: no test opens a network connection or spends money.
"""
from copy import deepcopy
from decimal import Decimal
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock
from urllib import error

from lean_agent.artifacts import canonical, read, sha
from lean_agent.final60 import catalog, ledger as cost_ledger, money, transport as t
from lean_agent.final60.contracts import CAP_USD, OPENROUTER_ENDPOINT, Bound

REPO = Path(__file__).resolve().parents[1]
BATCH = REPO / "experiments/final-batch-next"
if str(BATCH) not in sys.path:
    sys.path.insert(0, str(BATCH))

FAKE_KEY = "sk-or-v1-" + "f1x7ure" * 8
ACTION = '{"action":"search","query":"simp"}'
MESSAGES = [{"role": "system", "content": "Return one JSON action."},
            {"role": "user", "content": '{"problem":"fixture","step":1}'}]


def primary(max_tokens=None):
    return catalog.spec_for_model(catalog.driver_model(max_tokens=max_tokens))


def body_for(spec=None, user=None):
    spec = spec or primary()
    messages = deepcopy(MESSAGES)
    if user is not None:
        messages[1]["content"] = user
    return t.payload(messages, spec)


def no_sleep(seconds):
    return None


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


def evidence_text(folder):
    return b"".join(path.read_bytes() for path in Path(folder).rglob("*") if path.is_file())


def ledger_item(body, result, row=17, step=1):
    spec = catalog.spec_for_body(body)
    return {"row": row, "step": step, "request_sha256": sha(canonical(body)),
            "maximum_request_cost_usd": t.usd(t.request_bound(body, spec).reserved_usd), **result.ledger_fields()}


class Workspace:
    def __init__(self, cap=CAP_USD):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.ledger = cost_ledger.CostLedger(self.base / "final60.sqlite", cap_usd=cap)
        self.root = self.base / "rows" / "F017"
        self.root.mkdir(parents=True)

    def step(self, number=1):
        return self.root / "problems" / "F017" / "steps" / f"{number:04}"

    def dispatch(self, body, transport, *, step=1, sleep=no_sleep, **kwargs):
        spec = catalog.spec_for_body(body)
        return money.dispatch_guarded(body, spec, ledger=self.ledger, problem="F017",
                                      attempt_id=f"F017-{step:04}", run_root=self.root, step_dir=self.step(step),
                                      key=FAKE_KEY, transport=transport, sleep=sleep, **kwargs)

    def close(self):
        self.temporary.cleanup()


def usage_response(spec, *, prompt, completion, cached=0, written=0, reasoning=0, cost=None, identity="gen-fixture-1"):
    usage = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
             "prompt_tokens_details": {"cached_tokens": cached, "cache_write_tokens": written},
             "completion_tokens_details": {"reasoning_tokens": reasoning}}
    if cost is not None:
        usage["cost"] = cost
    return {"id": identity, "model": spec.model_id, "provider": "OpenAI",
            "choices": [{"message": {"role": "assistant", "content": ACTION}, "finish_reason": "stop"}],
            "usage": usage}


class PayloadTests(unittest.TestCase):
    def test_primary_payload_is_pinned(self):
        body = body_for()
        self.assertEqual(body["model"], "openai/gpt-6.1-sol")
        self.assertEqual(body["provider"], {"only": ["openai"], "order": ["openai"], "allow_fallbacks": False,
                                            "require_parameters": True, "max_price": {"prompt": 2, "completion": 10}})
        self.assertEqual(body["usage"], {"include": True})
        self.assertEqual(body["reasoning"], {"effort": "high"})
        self.assertEqual(body["plugins"], [])
        self.assertEqual(body["seed"], 42)
        self.assertEqual(body["max_tokens"], 8192)
        self.assertIs(body["stream"], False)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        for field in ("max_completion_tokens", "service_tier", "prompt_cache_options", "store", "n", "tools",
                      "temperature"):
            self.assertNotIn(field, body)
        self.assertEqual(body["messages"], MESSAGES)

    def test_claude_alt_never_sends_seed(self):
        spec = catalog.spec("gen_alt")
        body = t.payload(deepcopy(MESSAGES), spec)
        self.assertNotIn("seed", body)
        self.assertEqual(body["provider"]["only"], ["anthropic"])
        t.request_bound(body, spec)

    def test_driver_model_round_trip_and_drift_refused(self):
        model = catalog.driver_model(max_tokens=16384)
        self.assertEqual(model["backend"], "openrouter")
        self.assertEqual(model["catalog_key"], "gen_primary")
        self.assertEqual(catalog.spec_for_model(model).max_tokens, 16384)
        for field, value in (("id", "openai/gpt-6.1-sol-pro"), ("provider", "azure"), ("seed", 7),
                             ("reasoning_effort", "low"), ("max_price", {"prompt": 4, "completion": 20}),
                             ("service_tier", "flex")):
            changed = dict(model, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                catalog.spec_for_model(changed)

    def test_unpinned_or_direct_bodies_are_refused(self):
        spec = primary()
        cases = []
        changed = body_for(); changed["provider"]["allow_fallbacks"] = True; cases.append(changed)
        changed = body_for(); changed["provider"]["only"] = ["openai", "azure"]; cases.append(changed)
        changed = body_for(); changed["provider"].pop("max_price"); cases.append(changed)
        changed = body_for(); changed["service_tier"] = "default"; cases.append(changed)
        changed = body_for(); changed["max_completion_tokens"] = 8192; cases.append(changed)
        changed = body_for(); changed["plugins"] = [{"id": "web"}]; cases.append(changed)
        changed = body_for(); changed["model"] = "openai/gpt-6.1-sol-pro"; cases.append(changed)
        changed = body_for(); changed["max_tokens"] = 4096; cases.append(changed)
        changed = body_for(); changed.pop("usage"); cases.append(changed)
        changed = body_for(); changed["stream"] = True; cases.append(changed)
        for changed in cases:
            with self.subTest(body=changed), self.assertRaises(ValueError):
                t.request_bound(changed, spec)

    def test_request_size_stays_below_long_context_tier(self):
        spec = primary()
        t.request_bound(body_for(user="x" * 200_000), spec)
        with self.assertRaisesRegex(ValueError, "272K"):
            t.request_bound(body_for(user="x" * 236_000), spec)
        with self.assertRaisesRegex(ValueError, "272K"):
            t.request_bound(body_for(user="λ" * 118_000), spec)   # two UTF-8 bytes each

    def test_bound_formula(self):
        spec = primary()
        body = body_for()
        bound = t.request_bound(body, spec)
        count = len(json.dumps(body, ensure_ascii=False).encode()) + 4096
        self.assertEqual(bound.input_token_bound, count)
        self.assertEqual(bound.reserved_usd, (Decimal(count) * Decimal("2.5") + 8192 * Decimal(10)) / 1_000_000)
        self.assertEqual(t.ENDPOINT, OPENROUTER_ENDPOINT)
        self.assertEqual(t.parse.urlparse(t.ENDPOINT).hostname, "openrouter.ai")

    def test_bound_covers_twenty_fixture_usages(self):
        generator = random.Random(20261104)
        for number in range(20):
            spec = primary(max_tokens=generator.choice((8192, 16384)))
            body = t.payload(deepcopy(MESSAGES[:1]) + [{"role": "user", "content": "y" * generator.randint(10, 150_000)}],
                             spec)
            bound = t.request_bound(body, spec)
            prompt = generator.randint(1, bound.input_token_bound)     # a token is at least one byte
            cached = generator.randint(0, prompt)
            written = generator.randint(0, prompt - cached)
            completion = generator.randint(0, spec.max_tokens)
            reasoning = generator.randint(0, completion)
            listed = (Decimal(prompt - cached - written) * 2 + Decimal(cached) * Decimal("0.1")
                      + Decimal(written) * Decimal("2.5") + Decimal(completion) * 10) / 1_000_000
            reported = float(listed * Decimal(generator.choice(("0.5", "1", "1.0"))))
            raw = usage_response(spec, prompt=prompt, completion=completion, cached=cached, written=written,
                                 reasoning=reasoning, cost=reported if number % 4 else None)
            with self.subTest(number=number):
                receipt = t.compute_cost(raw, spec)
                self.assertLessEqual(Decimal(receipt["cost_usd"]), bound.reserved_usd)
                self.assertGreaterEqual(Decimal(receipt["cost_usd"]), listed)
                record = t.sub_attempt_cost(raw, spec, bound)
                self.assertFalse(record["bound_violated"])


class ReceiptTests(unittest.TestCase):
    def test_debit_is_max_of_usage_cost_and_list_price(self):
        spec = primary()
        raw = usage_response(spec, prompt=12000, completion=1000, cached=4000, written=7000, reasoning=900)
        self.assertEqual(Decimal(t.compute_cost(raw, spec)["cost_usd"]), Decimal("0.0299"))
        raw["usage"]["cost"] = 0.01
        receipt = t.compute_cost(raw, spec)
        self.assertEqual(Decimal(receipt["cost_usd"]), Decimal("0.0299"))
        self.assertEqual(receipt["basis"], "cache-aware-list-price")
        raw["usage"]["cost"] = 0.05
        receipt = t.compute_cost(raw, spec)
        self.assertEqual(Decimal(receipt["cost_usd"]), Decimal("0.05"))
        self.assertEqual(receipt["basis"], "openrouter-usage-cost")
        self.assertFalse(receipt["invoice_verified"])

    def test_unusable_usage_fails_closed_to_the_bound(self):
        spec = primary()
        bound = t.request_bound(body_for(), spec)
        cases = []
        raw = usage_response(spec, prompt=100, completion=10, cached=90, written=20); cases.append(raw)
        raw = usage_response(spec, prompt=100, completion=10, reasoning=11); cases.append(raw)
        raw = usage_response(spec, prompt=100, completion=10); raw["usage"]["total_tokens"] = 5; cases.append(raw)
        raw = usage_response(spec, prompt=100, completion=10); raw["usage"]["prompt_tokens_details"]["image_tokens"] = 3; cases.append(raw)
        raw = usage_response(spec, prompt=100, completion=True); cases.append(raw)
        raw = usage_response(spec, prompt=100, completion=10); raw["usage"]["cost"] = "NaN-ish"; cases.append(raw)
        raw = usage_response(spec, prompt=100, completion=10); del raw["usage"]; cases.append(raw)
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    t.compute_cost(raw, spec)
                record = t.sub_attempt_cost(raw, spec, bound)
                self.assertEqual(Decimal(record["cost_usd"]), bound.reserved_usd)
                self.assertEqual(record["basis"], "conservative-bound-unusable-usage")

    def test_billing_classes(self):
        for status in (400, 401, 402, 403, 404, 429):
            self.assertEqual(t.classify(t.MockOpenRouter.http_error(status)), "unbilled")
        for status in (408, 500, 502, 503, 504):
            self.assertEqual(t.classify(t.MockOpenRouter.http_error(status)), "lost")
        self.assertEqual(t.classify(t.MockOpenRouter.timeout()), "lost")
        self.assertEqual(t.classify({"transport_error": "InvalidJSON", "http_status": 200}), "lost")
        self.assertEqual(t.classify({"error": {"code": 429, "message": "slow down"}}), "unbilled")
        self.assertEqual(t.classify({"error": {"code": 429}, "usage": {"prompt_tokens": 1}}), "lost")
        self.assertEqual(t.classify({"id": "gen-x", "choices": []}), "lost")
        self.assertEqual(t.classify(usage_response(primary(), prompt=1, completion=1)), "ok")

    def test_lost_response_is_charged_its_bound_or_generation_total(self):
        spec = primary()
        bound = t.request_bound(body_for(), spec)
        lost = t.sub_attempt_cost(t.MockOpenRouter.timeout(), spec, bound)
        self.assertEqual((lost["status"], Decimal(lost["cost_usd"])), ("lost_conservative", bound.reserved_usd))
        raw = {"transport_error": "InvalidJSON", "http_status": 200, "generation_id": "gen-lost-1"}
        exact = t.sub_attempt_cost(raw, spec, bound, {"data": {"total_cost": 0.0123, "native_tokens_prompt": 100,
                                                                "native_tokens_completion": 10}})
        self.assertEqual((exact["status"], exact["cost_usd"], exact["settlement_basis"]),
                         ("settled", "0.0123", "generation-api"))
        self.assertEqual(t.sub_attempt_cost(t.MockOpenRouter.http_error(429), spec, bound)["cost_usd"], "0")

    def test_normalize_sets_step_total_and_never_mutates_raw(self):
        spec = primary()
        bound = t.request_bound(body_for(), spec)
        raw = usage_response(spec, prompt=100, completion=10, cost=0.02)
        before = deepcopy(raw)
        earlier = {"id": "F017-0001#r0", **t.sub_attempt_cost(t.MockOpenRouter.timeout(), spec, bound)}
        normalized = t.normalize(raw, spec, bound, sub_attempts=[earlier], attempt_id="F017-0001",
                                 final_id="F017-0001#r1")
        self.assertEqual(raw, before)
        self.assertEqual(Decimal(normalized["usage"]["cost"]), bound.reserved_usd + Decimal("0.02"))
        self.assertEqual(normalized["choices"], raw["choices"])
        self.assertEqual([item["id"] for item in normalized["_cost_receipt"]["sub_attempts"]],
                         ["F017-0001#r0", "F017-0001#r1"])
        lost = t.normalize(t.MockOpenRouter.timeout(), spec, bound, attempt_id="F017-0002")
        self.assertEqual((lost["id"], lost["choices"]), ("lost-F017-0002", []))
        self.assertEqual(Decimal(lost["usage"]["cost"]), bound.reserved_usd)


class _FakeResponse:
    def __init__(self, status, payload):
        self.status, self.payload = status, payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Opener:
    def __init__(self, outcome):
        self.outcome, self.requests = outcome, []

    def open(self, call, timeout=None):
        self.requests.append(call)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class HttpTests(unittest.TestCase):
    def run_query(self, outcome):
        opener = _Opener(outcome)
        with mock.patch.object(t.request, "build_opener", return_value=opener):
            raw = t.query(body_for(), primary(), key=FAKE_KEY)
        return raw, opener

    def test_success_goes_to_openrouter_once(self):
        payload = json.dumps(usage_response(primary(), prompt=10, completion=2, cost=0.001)).encode()
        raw, opener = self.run_query(_FakeResponse(200, payload))
        self.assertEqual(len(opener.requests), 1)
        call = opener.requests[0]
        self.assertEqual(t.parse.urlparse(call.full_url).hostname, "openrouter.ai")
        self.assertEqual(call.get_method(), "POST")
        self.assertEqual(json.loads(call.data), body_for())
        self.assertEqual(raw["id"], "gen-fixture-1")

    def test_failures_are_one_shot_and_never_carry_the_key(self):
        body = json.dumps({"error": {"code": 429, "message": "rate limited for key " + FAKE_KEY,
                                     "metadata": {"provider_name": "OpenAI", "raw": "Bearer " + FAKE_KEY}}}).encode()
        failure = error.HTTPError(t.ENDPOINT, 429, "Too Many Requests", {"Retry-After": "7"}, io.BytesIO(body))
        raw, opener = self.run_query(failure)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual((raw["http_status"], raw["billing_hint"], raw["retry_after_s"]), (429, "unbilled", 7))
        self.assertNotIn("sk-or-", json.dumps(raw))
        for outcome in (TimeoutError(), error.URLError("reset"), ConnectionResetError()):
            raw, opener = self.run_query(outcome)
            self.assertEqual(len(opener.requests), 1)
            self.assertEqual((raw["billing_hint"], t.classify(raw)), ("unknown", "lost"))
        raw, _ = self.run_query(_FakeResponse(200, b'{"id": "gen-trunc-1", "choices": [ ...'))
        self.assertEqual((raw["transport_error"], raw["generation_id"]), ("InvalidJSON", "gen-trunc-1"))

    def test_query_refuses_a_missing_or_foreign_key_before_any_io(self):
        opener = _Opener(TimeoutError())
        with mock.patch.object(t.request, "build_opener", return_value=opener):
            for key in (None, "", "sk-proj-openai-direct-key-0000"):
                with self.assertRaises(ValueError):
                    t.query(body_for(), primary(), key=key)
        self.assertEqual(opener.requests, [])

    def test_redirects_are_never_followed(self):
        self.assertIsNone(t._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.com"))

    def test_load_key_accepts_openrouter_names_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "openrouter.env"
            path.write_text("# comment\nexport OPENROUTER_API_KEY='" + FAKE_KEY + "'\n")
            self.assertEqual(t.load_key(path), FAKE_KEY)
            path.write_text("OPENAI_API_KEY=" + FAKE_KEY + "\n")
            with self.assertRaises(ValueError) as caught:
                t.load_key(path)
            self.assertNotIn(FAKE_KEY, str(caught.exception))
            path.write_text("OPENROUTER_API_KEY=sk-proj-not-openrouter-000000\n")
            with self.assertRaises(ValueError) as caught:
                t.load_key(path)
            self.assertNotIn("sk-proj", str(caught.exception))

    def test_key_status_keeps_numbers_only(self):
        documents = [_FakeResponse(200, json.dumps({"data": {"label": FAKE_KEY[:12] + "...", "limit": None, "usage": 3.5,
                                                             "limit_remaining": None, "is_free_tier": False}}).encode()),
                     _FakeResponse(200, json.dumps({"data": {"total_credits": 900, "total_usage": 12.25}}).encode())]

        class Sequence:
            def __init__(self):
                self.calls = []

            def open(self, call, timeout=None):
                self.calls.append(call)
                return documents[len(self.calls) - 1]

        opener = Sequence()
        with mock.patch.object(t.request, "build_opener", return_value=opener):
            status = t.key_status(key=FAKE_KEY)
        self.assertTrue(status["valid"])
        self.assertEqual(status["credits"]["remaining"], "887.75")
        self.assertNotIn("sk-or-", json.dumps(status))
        self.assertNotIn("label", status["key"])
        self.assertTrue(all(t.parse.urlparse(call.full_url).hostname == "openrouter.ai" for call in opener.calls))

    def test_endpoint_check_reports_tag_prices_parameters_and_variants(self):
        def endpoint(tag, prompt, completion, parameters, status=0):
            return {"tag": tag, "status": status, "provider_name": "OpenAI", "max_completion_tokens": 128000,
                    "pricing": {"prompt": prompt, "completion": completion, "input_cache_read": "0.0000001",
                                "input_cache_write": "0.0000025"}, "supported_parameters": parameters}
        full = ["max_tokens", "reasoning", "response_format", "seed"]
        doc = {"data": {"endpoints": [endpoint("openai", "0.000002", "0.00001", full),
                                      endpoint("openai/flex", "0.000001", "0.000005", full, status=-2),
                                      endpoint("openai/fast", "0.000004", "0.00002", full),
                                      endpoint("azure", "0.000002", "0.00001", full)]}}
        report = t.check_endpoints(doc, primary())
        self.assertTrue(report["ok"])
        self.assertEqual(report["eligible_variants"], ["openai/flex"])
        doc["data"]["endpoints"][0]["supported_parameters"] = ["max_tokens", "reasoning", "response_format"]
        report = t.check_endpoints(doc, primary())
        self.assertFalse(report["ok"])
        self.assertIn("seed", report["problems"][0])
        self.assertFalse(t.check_endpoints({"data": {"endpoints": []}}, primary())["ok"])


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.work = Workspace()

    def tearDown(self):
        self.work.close()

    def assert_clean(self, body, result, step=1):
        self.assertEqual(t.audit_step(self.work.step(step), ledger_item(body, result, step=step)), [])
        self.assertNotIn(b"sk-or-", evidence_text(self.work.root))

    def test_success_writes_audited_evidence_without_credentials(self):
        body = body_for()
        transport = t.MockOpenRouter([{"id": "gen-ok-1", "model": "openai/gpt-6.1-sol", "provider": "OpenAI",
                                       "note": "echo " + FAKE_KEY,
                                       "choices": [{"message": {"role": "assistant", "content": ACTION}}],
                                       "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                                                 "cost": 0.004}}])
        result = self.work.dispatch(body, transport)
        self.assertEqual((result.http_calls, result.lost, result.stopped), (1, False, None))
        self.assertEqual(result.receipt.status, "settled")
        self.assertEqual(result.receipt.api_endpoint, OPENROUTER_ENDPOINT)
        self.assertEqual(result.normalized["id"], "gen-ok-1")
        for name in ("request.json", "cost-bound.json", "endpoint.json", "provider-response.json", "response.json",
                     "cost-receipt.json", "http/r0/sent.json", "http/r0/receipt.json"):
            self.assertTrue((self.work.step() / name).is_file(), name)
        self.assertEqual(read(self.work.step() / "endpoint.json")["host"], "openrouter.ai")
        fields = result.ledger_fields()
        self.assertEqual(fields["status"], "settled")
        self.assertEqual(fields["sub_attempts"], [{"id": "F017-0001#r0", "http_status": 200, "status": "settled",
                                                   "cost_usd": "0.004", "basis": "usage"}])
        self.assert_clean(body, result)
        self.assertEqual(self.work.ledger.spent("F017"), Decimal(fields["cost_usd"]))

    def test_cap_refuses_before_anything_is_written_or_sent(self):
        body = body_for()
        bound = t.request_bound(body, primary())
        self.work.ledger.declare_prior("F017", CAP_USD - bound.reserved_usd + Decimal("0.000001"), note="fixture")
        transport = t.MockOpenRouter(ACTION)
        with self.assertRaises(cost_ledger.BudgetExceeded):
            self.work.dispatch(body, transport)
        self.assertEqual(transport.http_calls, 0)
        self.assertFalse(self.work.step().exists())
        self.assertEqual(self.work.ledger.attempts("F017"), [])

    def test_unbilled_retries_are_recorded_at_zero(self):
        body = body_for()
        sleeps = Sleeps()
        transport = t.MockOpenRouter([t.MockOpenRouter.http_error(429), t.MockOpenRouter.http_error(403), ACTION])
        result = self.work.dispatch(body, transport, sleep=sleeps)
        self.assertEqual(result.http_calls, 3)
        self.assertEqual(sleeps, [15, 30])
        self.assertEqual([row["status"] for row in self.work.ledger.sub_attempts("F017-0001")],
                         ["unbilled", "unbilled", "settled"])
        self.assertEqual([item["cost_usd"] for item in result.sub_attempts], ["0", "0", "0.01"])
        self.assert_clean(body, result)

    def test_key_or_credit_refusal_disables_globally_without_spend(self):
        body = body_for()
        with self.assertRaises(money.ApiDisabled) as caught:
            self.work.dispatch(body, t.MockOpenRouter([t.MockOpenRouter.http_error(402)]))
        self.assertEqual(caught.exception.scope, "global")
        self.assertTrue((self.work.base / money.GLOBAL_MARKER).exists())
        follow = t.MockOpenRouter(ACTION)
        with self.assertRaises(money.ApiDisabled):
            self.work.dispatch(body_for(user="other"), follow, step=2)
        self.assertEqual(follow.http_calls, 0)
        self.assertEqual(self.work.ledger.spent("F017"), 0)

    def test_lost_response_charged_at_bound_then_same_body_resent(self):
        body = body_for()
        bound = t.request_bound(body, primary())
        sleeps = Sleeps()
        transport = t.MockOpenRouter([t.MockOpenRouter.timeout(), ACTION])
        result = self.work.dispatch(body, transport, sleep=sleeps)
        self.assertEqual(transport.calls[0], transport.calls[1])
        self.assertEqual(sleeps, [60])
        self.assertEqual(result.step_cost_usd, bound.reserved_usd + Decimal("0.01"))
        self.assertEqual(result.settlement_basis, "usage")      # mock usage.cost 0.01 > its list price
        self.assertEqual([item["basis"] for item in result.sub_attempts], ["lost-bound", "usage"])
        self.assert_clean(body, result)

    def test_lost_response_settled_exactly_via_generation_api(self):
        body = body_for()
        lost = {"transport_error": "InvalidJSON", "http_status": 200, "billing_hint": "unknown",
                "generation_id": "gen-cut-1"}
        transport = t.MockOpenRouter([lost, ACTION], generations={"gen-cut-1": {"data": {"total_cost": 0.0042}}})
        result = self.work.dispatch(body, transport)
        self.assertEqual(result.step_cost_usd, Decimal("0.0142"))
        self.assertEqual(result.sub_attempts[0]["basis"], "generation-api")
        self.assert_clean(body, result)

    def test_fully_lost_step_closes_with_a_lost_id_and_audits(self):
        body = body_for()
        bound = t.request_bound(body, primary())
        transport = t.MockOpenRouter([t.MockOpenRouter.timeout()] * 3)
        result = self.work.dispatch(body, transport)
        self.assertEqual((result.lost, result.stopped, result.http_calls), (True, "lost_limit", 3))
        self.assertEqual(result.normalized["id"], "lost-F017-0001")
        self.assertEqual(result.normalized["choices"], [])
        self.assertEqual(result.step_cost_usd, 3 * bound.reserved_usd)
        self.assert_clean(body, result)

    def test_budget_stop_after_a_lost_charge_keeps_the_spend(self):
        body = body_for()
        bound = t.request_bound(body, primary())
        work = Workspace(cap=bound.reserved_usd * Decimal("1.5"))
        try:
            transport = t.MockOpenRouter([t.MockOpenRouter.timeout(), ACTION])
            result = work.dispatch(body, transport)
            self.assertEqual((result.stopped, result.lost, transport.http_calls), ("budget", True, 1))
            self.assertEqual(result.step_cost_usd, bound.reserved_usd)
            self.assertEqual(t.audit_step(work.step(), ledger_item(body, result)), [])
        finally:
            work.close()

    def test_persistent_refusals_stall_then_disable_the_row(self):
        body = body_for()
        sleeps = Sleeps()
        transport = t.MockOpenRouter(lambda body, spec, index: t.MockOpenRouter.http_error(429))
        with self.assertRaises(money.ApiDisabled) as caught:
            self.work.dispatch(body, transport, sleep=sleeps)
        self.assertEqual(caught.exception.scope, "row")
        self.assertEqual(transport.http_calls, 18)
        self.assertEqual(sleeps.count(600), 2)
        self.assertEqual(sleeps[:5], [15, 30, 60, 120, 240])
        self.assertIn("api_disabled", self.work.ledger.flags("F017"))
        self.assertTrue((self.work.root / money.ROW_MARKER).exists())
        self.assertEqual(self.work.ledger.spent("F017"), 0)

    def test_bound_violation_is_settled_and_freezes_the_row(self):
        body = body_for()
        spec = primary()
        oversized = usage_response(spec, prompt=100, completion=spec.max_tokens + 1, identity="gen-big-1")
        result = self.work.dispatch(body, t.MockOpenRouter([oversized]))
        self.assertTrue(result.bound_violated)
        self.assertEqual(result.ledger_fields()["status"], "settled")
        self.assertIn("frozen", self.work.ledger.flags("F017"))
        self.assert_clean(body, result)
        with self.assertRaises(money.ApiDisabled):
            self.work.dispatch(body_for(user="next"), t.MockOpenRouter(ACTION), step=2)

    def test_crash_after_reserve_voids_the_unsent_reservation(self):
        body = body_for()
        spec = primary()
        bound = t.request_bound(body, spec)
        self.work.ledger.reserve(problem="F017", attempt_id="F017-0001#r0", bound=bound, run_root=str(self.work.root),
                                 model=spec.model_id, provider=spec.provider, api_endpoint=t.ENDPOINT,
                                 request_sha256=sha(canonical(body)))
        result = self.work.dispatch(body, t.MockOpenRouter(ACTION))
        self.assertEqual([row["status"] for row in self.work.ledger.sub_attempts("F017-0001")], ["void", "settled"])
        self.assertEqual([item["id"] for item in result.sub_attempts], ["F017-0001#r1"])
        self.assertEqual(result.step_cost_usd, Decimal("0.01"))
        self.assert_clean(body, result)

    def test_crash_during_the_call_is_charged_its_bound_once(self):
        body = body_for()
        bound = t.request_bound(body, primary())

        class Killed(Exception):
            pass

        with self.assertRaises(Killed):
            self.work.dispatch(body, t.MockOpenRouter([Killed()]))
        self.assertEqual(self.work.ledger.sub_attempts("F017-0001")[0]["status"], "sent")
        restart = t.MockOpenRouter(ACTION)
        result = self.work.dispatch(body, restart)
        self.assertEqual(restart.http_calls, 1)
        self.assertEqual(result.step_cost_usd, bound.reserved_usd + Decimal("0.01"))
        self.assertTrue((self.work.step() / "http/r0/recovered.json").exists())
        self.assert_clean(body, result)

    def test_crash_after_the_response_never_sends_twice(self):
        body = body_for()
        original = cost_ledger.CostLedger.settle
        with mock.patch.object(cost_ledger.CostLedger, "settle", side_effect=OSError("killed before settle")):
            with self.assertRaises(OSError):
                self.work.dispatch(body, t.MockOpenRouter(ACTION))
        self.assertIs(cost_ledger.CostLedger.settle, original)
        restart = t.MockOpenRouter(ACTION)
        result = self.work.dispatch(body, restart)
        self.assertEqual(restart.http_calls, 0)
        self.assertEqual(result.step_cost_usd, Decimal("0.01"))
        self.assert_clean(body, result)
        again = t.MockOpenRouter(ACTION)
        repeat = self.work.dispatch(body, again)
        self.assertEqual((again.http_calls, repeat.normalized), (0, result.normalized))

    def test_resume_after_the_last_allowed_lost_attempt_sends_nothing(self):
        body = body_for()
        bound = t.request_bound(body, primary())
        with mock.patch.object(money, "_finish", side_effect=OSError("killed before closing the step")):
            with self.assertRaises(OSError):
                self.work.dispatch(body, t.MockOpenRouter([t.MockOpenRouter.timeout()] * 3))
        restart = t.MockOpenRouter(ACTION)
        result = self.work.dispatch(body, restart)
        self.assertEqual((restart.http_calls, result.stopped, result.lost), (0, "lost_limit", True))
        self.assertEqual(result.step_cost_usd, 3 * bound.reserved_usd)
        self.assert_clean(body, result)

    def test_real_transport_requires_a_key_before_reserving(self):
        with self.assertRaises(ValueError):
            money.dispatch_guarded(body_for(), primary(), ledger=self.work.ledger, problem="F017",
                                   attempt_id="F017-0001", run_root=self.work.root, step_dir=self.work.step(),
                                   key=None)
        self.assertEqual(self.work.ledger.attempts(), [])

    def test_audit_detects_tampering(self):
        body = body_for()
        result = self.work.dispatch(body, t.MockOpenRouter(ACTION))
        item = ledger_item(body, result)
        tampered = dict(item, cost_usd="0.001")
        self.assertIn("ledger cost differs from the sum of HTTP sub-attempts", t.audit_step(self.work.step(), tampered))
        response = read(self.work.step() / "response.json")
        response["usage"]["cost"] = "0.001"
        (self.work.step() / "response.json").write_text(json.dumps(response))
        self.assertIn("normalized response differs from raw provider evidence", t.audit_step(self.work.step(), item))


def _load_checker():
    spec = importlib.util.spec_from_file_location("final60_provenance_checker",
                                                  REPO / "scripts/check_submission_provenance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AdapterTests(unittest.TestCase):
    def setUp(self):
        import driver
        import openrouter_transport
        self.driver, self.adapter = driver, openrouter_transport
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "rows" / "F017"
        inputs = self.root / "problems" / "F017" / "input"
        inputs.mkdir(parents=True)
        authorization = {"dataset_sha256": driver.DATASET_SHA, "rows": [17], "problem_count": 1,
                         "verification_policy": driver.VERIFICATION_POLICY,
                         **openrouter_transport.seal_fields(cost_ledger_path="../../final60.sqlite")}
        (self.root / "authorization.json").write_text(json.dumps(authorization))
        (self.root / "frozen.json").write_text("{}")
        (self.root / "ledger.json").write_text(json.dumps({"schema_version": 1, "attempts": {}}))
        (inputs / "config.json").write_text(json.dumps({"limits": {"cost_cap_usd": "2.99"}}))
        self.model = catalog.driver_model()
        self.adapter.use_transport(None)
        self.addCleanup(self.adapter.use_transport, None)
        self.addCleanup(self.temporary.cleanup)

    def step_dir(self, step):
        path = self.root / "problems" / "F017" / "steps" / f"{step:04}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ledger_json(self):
        return read(self.root / "ledger.json")

    def test_adapter_exposes_the_openai_transport_names(self):
        import openai_transport
        names = ("ENDPOINT", "PRICING", "MODEL_ID", "payload", "request_cost", "model_metadata", "query",
                 "normalize", "compute_cost", "load_key")
        for name in names:
            self.assertTrue(hasattr(openai_transport, name), name)
            self.assertTrue(hasattr(self.adapter, name), name)
            self.assertEqual(callable(getattr(openai_transport, name)), callable(getattr(self.adapter, name)), name)
        self.assertTrue(callable(self.adapter.audit_step))
        self.assertEqual(t.parse.urlparse(self.adapter.ENDPOINT).hostname, "openrouter.ai")
        self.assertEqual(self.adapter.PRICING["api_endpoint"], OPENROUTER_ENDPOINT)
        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        cost = self.adapter.request_cost(body)
        self.assertEqual(set(cost) >= {"request_sha256", "input_token_bound", "output_token_bound", "reserved_usd"}, True)
        self.assertEqual(self.adapter.model_metadata()["api_endpoint"], OPENROUTER_ENDPOINT)
        self.assertEqual(self.adapter.ledger_path(self.root), (self.base / "final60.sqlite").resolve())

    def test_driver_steps_keep_one_settled_item_each_and_pass_both_audits(self):
        self.adapter.use_transport(t.MockOpenRouter([t.MockOpenRouter.http_error(429), ACTION, ACTION]),
                                   sleep=no_sleep)
        first = self.adapter.payload(deepcopy(MESSAGES), self.model)
        second = self.adapter.payload([MESSAGES[0], {"role": "user", "content": '{"step":2}'}], self.model)
        with mock.patch("builtins.print"):
            raw1 = self.adapter.dispatch(self.root, 17, 1, first, self.model, self.step_dir(1), driver=self.driver)
            raw2 = self.adapter.dispatch(self.root, 17, 2, second, self.model, self.step_dir(2), driver=self.driver)
        attempts = self.ledger_json()["attempts"]
        self.assertEqual(sorted(attempts), ["F017-0001", "F017-0002"])
        self.assertTrue(all(item["status"] == "settled" for item in attempts.values()))
        self.assertEqual(len(attempts["F017-0001"]["sub_attempts"]), 2)
        self.assertEqual(attempts["F017-0001"]["response_id"], raw1["id"])
        self.assertEqual(self.driver.problem_spend(self.ledger_json(), 17), Decimal("0.02"))
        self.assertEqual(Decimal(raw1["usage"]["cost"]) + Decimal(raw2["usage"]["cost"]), Decimal("0.02"))
        self.assertEqual(self.adapter.audit_root(self.root), [])
        problems = self.root / "problems" / "F017"
        statement = "theorem fixture_thm : True"
        (problems / "input/problem.json").write_text(json.dumps({"name": "fixture_thm", "statement": statement}))
        (problems / "selected.lean").write_text(statement + " := by\n  trivial\n")
        (self.root / "report.json").write_text(json.dumps({"audit_passed": True}))
        checker = _load_checker()
        benchmark = [{"name": "fixture_thm", "statement": statement, "proof": statement + " := by\n  exact True.intro\n"}]
        submission = [{"name": "fixture_thm", "proof": statement + " := by\n  trivial\n"}]
        outcome = checker.check(benchmark, submission, [checker.RunRoot(self.root)], [], [], Decimal("3"))
        self.assertEqual(outcome["errors"], [])
        self.assertEqual(Decimal(outcome["rows"][0]["cost_usd"]), Decimal("0.02"))

    def test_crashed_step_is_recovered_without_duplicate_attempts(self):
        class Killed(Exception):
            pass

        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        bound = Decimal(self.adapter.request_cost(body)["reserved_usd"])
        self.adapter.use_transport(t.MockOpenRouter([Killed()]), sleep=no_sleep)
        with mock.patch("builtins.print"), self.assertRaises(Killed):
            self.adapter.dispatch(self.root, 17, 1, body, self.model, self.step_dir(1), driver=self.driver)
        self.assertEqual(self.ledger_json()["attempts"]["F017-0001"]["status"], "pending")
        restart = t.MockOpenRouter(ACTION)
        self.adapter.use_transport(restart, sleep=no_sleep)
        recovered = self.adapter.recover_pending(self.root, 17, 1, self.step_dir(1), driver=self.driver)
        self.assertEqual(restart.http_calls, 1)
        item = self.ledger_json()["attempts"]["F017-0001"]
        self.assertEqual(item["status"], "settled")
        self.assertEqual(Decimal(item["cost_usd"]), bound + Decimal("0.01"))
        self.assertEqual(recovered["id"], item["response_id"])
        self.assertIsNone(self.adapter.recover_pending(self.root, 17, 1, self.step_dir(1), driver=self.driver))
        self.assertEqual(restart.http_calls, 1)
        self.assertEqual(self.adapter.audit_root(self.root), [])
        with mock.patch("builtins.print"), self.assertRaisesRegex(ValueError, "already dispatched"):
            self.adapter.dispatch(self.root, 17, 1, body, self.model, self.step_dir(1), driver=self.driver)

    def test_refused_step_is_voided_so_the_audit_counts_stay_equal(self):
        self.adapter.use_transport(t.MockOpenRouter([t.MockOpenRouter.http_error(401)]), sleep=no_sleep)
        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        with mock.patch("builtins.print"), self.assertRaises(self.adapter.ApiDisabled):
            self.adapter.dispatch(self.root, 17, 1, body, self.model, self.step_dir(1), driver=self.driver)
        self.assertEqual(self.ledger_json()["attempts"], {})
        self.assertTrue((self.step_dir(1) / "voided.json").exists())
        self.assertEqual(self.adapter.audit_root(self.root), [])
        self.assertIsNone(self.adapter.recover_pending(self.root, 17, 1, self.step_dir(1), driver=self.driver))

    def test_sealed_target_replaces_the_one_dollar_constant(self):
        ledger = self.ledger_json()
        ledger["attempts"]["F017-0001"] = {"row": 17, "step": 1, "status": "settled", "cost_usd": "1.50"}
        (self.root / "ledger.json").write_text(json.dumps(ledger))
        self.adapter.use_transport(t.MockOpenRouter(ACTION), sleep=no_sleep)
        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        with mock.patch("builtins.print"):
            raw = self.adapter.dispatch(self.root, 17, 2, body, self.model, self.step_dir(2), driver=self.driver)
        self.assertEqual(raw["usage"]["cost"], "0.01")
        ledger = self.ledger_json()
        ledger["attempts"]["F017-0001"]["cost_usd"] = "2.95"
        (self.root / "ledger.json").write_text(json.dumps(ledger))
        third = self.adapter.payload([MESSAGES[0], {"role": "user", "content": "3"}], self.model)
        with mock.patch("builtins.print"), self.assertRaises(self.adapter.BudgetExceeded):
            self.adapter.dispatch(self.root, 17, 3, third, self.model, self.step_dir(3), driver=self.driver)

    def test_sealed_prior_spend_counts_against_the_target(self):
        authorization = read(self.root / "authorization.json")
        authorization.update(self.adapter.seal_fields(cost_ledger_path="../../final60.sqlite", prior_usd=Decimal("2.90")))
        (self.root / "authorization.json").write_text(json.dumps(authorization))
        self.adapter.use_transport(t.MockOpenRouter(ACTION), sleep=no_sleep)
        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        with mock.patch("builtins.print"), self.assertRaises(self.adapter.BudgetExceeded):
            self.adapter.dispatch(self.root, 17, 1, body, self.model, self.step_dir(1), driver=self.driver)
        self.assertEqual(self.adapter.ledger_for_root(self.root).prior("F017"), Decimal("2.90"))
        self.assertEqual(self.ledger_json()["attempts"], {})
        self.assertEqual(self.adapter.config_cap(Decimal("2.99"), Decimal("2.90")), "0.09")
        with self.assertRaises(ValueError):
            self.adapter.seal_fields(cost_ledger_path="x.sqlite", prior_usd=Decimal("3"))

    def test_smoke_summary_and_offline_cli(self):
        self.adapter.use_transport(t.MockOpenRouter([t.MockOpenRouter.http_error(429), ACTION]), sleep=no_sleep)
        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        with mock.patch("builtins.print"):
            self.adapter.dispatch(self.root, 17, 1, body, self.model, self.step_dir(1), driver=self.driver)
        summary = self.adapter.smoke_summary(self.root)
        self.assertEqual((summary["completed_calls"], summary["all_json_objects"], summary["within_max_tokens"]),
                         (1, True, True))
        self.assertEqual(summary["providers"], ["OpenAI"])
        self.assertEqual(summary["calls"][0]["sub_attempt_statuses"], ["unbilled", "settled"])
        self.assertEqual(summary["audit_errors"], [])
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self.adapter.main(["audit", "--root", str(self.root)]), 0)
            self.assertEqual(self.adapter.main(["ledger-summary", "--ledger", str(self.base / "final60.sqlite")]), 0)
        self.assertNotIn("sk-or-", "".join(str(call) for call in printed.call_args_list))

    def test_non_openrouter_root_is_refused(self):
        authorization = read(self.root / "authorization.json")
        authorization.update(provider="OpenAI direct", api_endpoint="https://api.openai.com/v1/chat/completions")
        (self.root / "authorization.json").write_text(json.dumps(authorization))
        self.adapter.use_transport(t.MockOpenRouter(ACTION))
        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        with self.assertRaisesRegex(ValueError, "not authorized for OpenRouter"):
            self.adapter.dispatch(self.root, 17, 1, body, self.model, self.step_dir(1), driver=self.driver)


if __name__ == "__main__":
    unittest.main()
