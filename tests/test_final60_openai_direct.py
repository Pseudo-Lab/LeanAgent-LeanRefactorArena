"""final60 OpenAI-direct development transport: wire, registry, adapter, refusal at submission.

Fixture transports and mocked HTTP only: no test opens a network connection or spends money.
"""
from copy import deepcopy
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib import error

from lean_agent.artifacts import canonical, read, sha
from lean_agent.final60 import catalog, ledger as cost_ledger, money, openai_direct as o, transport as t, transports
from lean_agent.final60.contracts import CAP_USD, OPENROUTER_ENDPOINT

REPO = Path(__file__).resolve().parents[1]
BATCH = REPO / "experiments/final-batch-next"
if str(BATCH) not in sys.path:
    sys.path.insert(0, str(BATCH))

OPENAI_KEY = "sk-proj-" + "d3v3l0pm3nt" * 5
OPENROUTER_KEY = "sk-or-v1-" + "f1x7ure" * 8
ACTION = '{"action":"search","query":"simp"}'
MESSAGES = [{"role": "system", "content": "Return one JSON action."},
            {"role": "user", "content": '{"problem":"fixture","step":1}'}]


def no_sleep(seconds):
    return None


def spec():
    return o.spec_for_model(o.driver_model())


def body_for(user=None):
    messages = deepcopy(MESSAGES)
    if user is not None:
        messages[1]["content"] = user
    return o.payload(messages, spec())


def evidence_text(folder):
    return b"".join(path.read_bytes() for path in Path(folder).rglob("*") if path.is_file())


def _load_checker():
    path = REPO / "scripts" / "check_submission_provenance.py"
    module_spec = importlib.util.spec_from_file_location("check_submission_provenance_openai_test", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class _FakeResponse(io.BytesIO):
    def __init__(self, status, payload):
        super().__init__(payload)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


class _Opener:
    def __init__(self, outcome):
        self.outcome, self.requests = outcome, []

    def open(self, call, timeout=None):
        self.requests.append((call, timeout))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        status, payload = self.outcome
        return _FakeResponse(status, payload)


class WireTests(unittest.TestCase):
    def test_payload_is_the_pinned_direct_shape(self):
        body = body_for()
        self.assertEqual(body["model"], "gpt-6.1-sol")
        self.assertEqual((body["max_completion_tokens"], body["reasoning_effort"], body["seed"]), (8192, "high", 42))
        self.assertEqual((body["service_tier"], body["store"], body["stream"], body["n"]), ("default", False, False, 1))
        self.assertNotIn("provider", body)
        self.assertNotIn("max_tokens", body)
        self.assertEqual(o.spec_for_body(body), spec())
        self.assertEqual(o.spec_for_model(o.driver_model(max_tokens=16384)).max_tokens, 16384)

    def test_other_transports_bodies_and_models_are_refused(self):
        openrouter_body = t.payload(deepcopy(MESSAGES), catalog.spec_for_model(catalog.driver_model()))
        with self.assertRaises(ValueError):
            o.request_bound(openrouter_body, spec())
        with self.assertRaises(ValueError):
            o.spec_for_body(openrouter_body)
        with self.assertRaises(ValueError):
            o.spec_for_model(catalog.driver_model())
        with self.assertRaises(ValueError):
            o.spec_for_model({**o.driver_model(), "max_price": {"prompt": 2, "completion": 10}})
        with self.assertRaises(ValueError):
            catalog.spec_for_model(o.driver_model())

    def test_bound_is_the_frozen_list_price_worst_case_and_covers_receipts(self):
        body = body_for()
        bound = o.request_bound(body, spec())
        price = o.pricing()
        expected = (Decimal(bound.input_token_bound) * Decimal(price["cache_write_30m"])
                    + Decimal(8192) * Decimal(price["output_including_reasoning"])) / Decimal(1_000_000)
        self.assertEqual(bound.reserved_usd, expected)
        self.assertEqual(o.bound_json(bound, body, spec())["transport"], "openai")
        for prompt, completion, cached, written in ((bound.input_token_bound, 8192, 0, 0), (4000, 8192, 3000, 0),
                                                    (4000, 100, 0, 4000), (1, 1, 0, 0), (4500, 8000, 500, 4000)):
            raw = {"id": "chatcmpl-1", "model": "gpt-6.1-sol", "service_tier": "default",
                   "choices": [{"message": {"role": "assistant", "content": ACTION}}],
                   "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
                             "prompt_tokens_details": {"cached_tokens": cached, "cache_write_tokens": written},
                             "completion_tokens_details": {"reasoning_tokens": completion // 2}}}
            cost = o.compute_cost(raw, spec())
            self.assertLessEqual(Decimal(cost["cost_usd"]), bound.reserved_usd)
            self.assertEqual(cost["returned_provider"], "OpenAI direct")
            self.assertIsNone(cost["usage_cost"])
        with self.assertRaises(ValueError):
            o.compute_cost({**raw, "service_tier": "flex"}, spec())

    def test_keys_scrubbing_and_dotenv(self):
        with self.assertRaises(ValueError):
            o.require_key(OPENROUTER_KEY)
        with self.assertRaises(ValueError):
            o.require_key(None)
        self.assertEqual(o.require_key(OPENAI_KEY), OPENAI_KEY)
        scrubbed = o.scrub({"headers": "Bearer " + OPENAI_KEY, "note": "key " + OPENAI_KEY, "ok": "sk-or-short"}, OPENAI_KEY)
        self.assertNotIn(OPENAI_KEY, json.dumps(scrubbed))
        with tempfile.TemporaryDirectory() as folder:
            dotenv = Path(folder) / "openai.env"
            dotenv.write_text("OPENROUTER_API_KEY=" + OPENROUTER_KEY + "\nexport OPENAI_API_KEY='" + OPENAI_KEY + "'\n")
            self.assertEqual(o.load_key(dotenv), OPENAI_KEY)
            dotenv.write_text("OPENROUTER_API_KEY=" + OPENROUTER_KEY + "\n")
            with self.assertRaises(ValueError):
                o.load_key(dotenv)

    def test_query_posts_once_to_openai_and_never_carries_the_key(self):
        body = body_for()
        ok = json.dumps(o.MockOpenAI(ACTION).response(ACTION, spec(), body)).encode()
        opener = _Opener((200, ok))
        with mock.patch.object(t.request, "build_opener", return_value=opener):
            raw = o.query(body, spec(), key=OPENAI_KEY)
        self.assertEqual(o.classify(raw), "ok")
        self.assertEqual(len(opener.requests), 1)
        call = opener.requests[0][0]
        self.assertEqual(call.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(call.get_header("Authorization"), "Bearer " + OPENAI_KEY)
        self.assertEqual(json.loads(call.data), body)
        failure = error.HTTPError(o.ENDPOINT, 429, "slow", {"Retry-After": "7"},
                                  io.BytesIO(json.dumps({"error": {"type": "rate_limit", "code": "insufficient_quota",
                                                                   "message": "key " + OPENAI_KEY}}).encode()))
        with mock.patch.object(t.request, "build_opener", return_value=_Opener(failure)):
            refused = o.query(body, spec(), key=OPENAI_KEY)
        self.assertEqual((refused["http_status"], refused["billing_hint"], refused["retry_after_s"]), (429, "unbilled", 7))
        self.assertNotIn(OPENAI_KEY, json.dumps(refused))
        with mock.patch.object(t.request, "build_opener", return_value=_Opener(TimeoutError("slow"))):
            lost = o.query(body, spec(), key=OPENAI_KEY)
        self.assertEqual((o.classify(lost), lost["billing_hint"]), ("lost", "unknown"))
        with self.assertRaises(ValueError):
            o.query(body, spec(), key=OPENROUTER_KEY)
        self.assertIsNone(t._NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example/"))


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.ledger = cost_ledger.CostLedger(self.base / "final60.sqlite")
        self.root = self.base / "rows" / "F017"
        self.root.mkdir(parents=True)
        self.addCleanup(self.temporary.cleanup)

    def step(self, number=1):
        return self.root / "problems" / "F017" / "steps" / f"{number:04}"

    def dispatch(self, body, transport, *, step=1, key=OPENAI_KEY, **kwargs):
        return money.dispatch_guarded(body, o.spec_for_body(body), ledger=self.ledger, problem="F017",
                                      attempt_id=f"F017-{step:04}", run_root=self.root, step_dir=self.step(step),
                                      key=key, transport=transport, sleep=no_sleep, wire=o, **kwargs)

    def item(self, body, result):
        bound = o.request_bound(body, o.spec_for_body(body))
        return {"row": 17, "step": 1, "request_sha256": sha(canonical(body)),
                "maximum_request_cost_usd": o.usd(bound.reserved_usd), **result.ledger_fields()}

    def test_every_record_says_openai_direct_and_audits_clean(self):
        body = body_for()
        transport = o.MockOpenAI([o.MockOpenAI.http_error(429), o.MockOpenAI.timeout(), ACTION])
        result = self.dispatch(body, transport)
        bound = o.request_bound(body, o.spec_for_body(body))
        self.assertEqual(result.http_calls, 3)
        self.assertEqual(result.step_cost_usd, bound.reserved_usd + Decimal(result.normalized["_cost_receipt"]["final_sub_attempt"]["cost_usd"]))
        self.assertEqual([sub["status"] for sub in result.sub_attempts], ["unbilled", "lost_conservative", "settled"])
        fields = result.ledger_fields()
        self.assertEqual((fields["api_endpoint"], fields["provider"]), (o.ENDPOINT, "OpenAI direct"))
        self.assertEqual(fields["cost_basis"], o.COST_BASIS)
        receipt = result.normalized["_cost_receipt"]
        self.assertEqual((receipt["api_endpoint"], receipt["provider"]), (o.ENDPOINT, "OpenAI direct"))
        self.assertEqual(result.normalized["provider"], "OpenAI direct")
        endpoint = read(self.step() / "endpoint.json")
        self.assertEqual((endpoint["api_endpoint"], endpoint["provider"], endpoint["submittable"]),
                         (o.ENDPOINT, "OpenAI direct", False))
        for index in range(3):
            self.assertEqual(read(self.step() / "http" / f"r{index}" / "sent.json")["api_endpoint"], o.ENDPOINT)
        for row in self.ledger.attempts("F017"):
            self.assertEqual(row["api_endpoint"], o.ENDPOINT)
        self.assertEqual(self.ledger.spent("F017"), result.step_cost_usd)
        self.assertEqual(o.audit_step(self.step(), self.item(body, result)), [])
        self.assertTrue(any("not pinned to an OpenRouter" in message for message in t.audit_step(self.step(), self.item(body, result))))
        self.assertNotIn(OPENAI_KEY.encode(), evidence_text(self.step()))
        self.assertNotIn(b"openrouter.ai", evidence_text(self.step()))

    def test_same_cap_refuses_before_anything_is_written(self):
        ledger = cost_ledger.CostLedger(self.base / "tiny.sqlite", cap_usd=Decimal("0.05"))
        body = body_for()
        with self.assertRaises(cost_ledger.BudgetExceeded):
            money.dispatch_guarded(body, o.spec_for_body(body), ledger=ledger, problem="F017", attempt_id="F017-0001",
                                   run_root=self.root, step_dir=self.step(), key=OPENAI_KEY,
                                   transport=o.MockOpenAI(ACTION), sleep=no_sleep, wire=o)
        self.assertFalse(self.step().exists())
        self.assertEqual(ledger.attempts("F017"), [])
        self.assertLessEqual(CAP_USD, Decimal("2.99"))

    def test_lost_responses_settle_at_the_bound_without_a_generation_api(self):
        body = body_for()
        result = self.dispatch(body, o.MockOpenAI([o.MockOpenAI.timeout()] * 3))
        bound = o.request_bound(body, o.spec_for_body(body))
        self.assertTrue(result.lost)
        self.assertEqual((result.stopped, result.step_cost_usd), ("lost_limit", 3 * bound.reserved_usd))
        self.assertEqual(result.normalized["id"], "lost-F017-0001")
        self.assertEqual(result.normalized["choices"], [])
        self.assertEqual(o.audit_step(self.step(), self.item(body, result)), [])

    def test_real_wire_needs_an_openai_key_and_refuses_openrouter_keys(self):
        body = body_for()
        for key in (None, OPENROUTER_KEY):
            with self.assertRaises(ValueError):
                self.dispatch(body, None, key=key)
        self.assertEqual(self.ledger.attempts("F017"), [])

    def test_crash_mid_call_is_recovered_at_the_bound_with_the_openai_wire(self):
        class Killed(Exception):
            pass

        body = body_for()
        with self.assertRaises(Killed):
            self.dispatch(body, o.MockOpenAI([Killed()]))
        self.assertEqual(self.ledger.get("F017-0001#r0")["status"], "sent")
        result = self.dispatch(body, o.MockOpenAI([ACTION]))
        bound = o.request_bound(body, o.spec_for_body(body))
        self.assertEqual(self.ledger.get("F017-0001#r0")["status"], "lost_conservative")
        self.assertEqual(self.ledger.get("F017-0001#r0")["api_endpoint"], o.ENDPOINT)
        self.assertGreaterEqual(result.step_cost_usd, bound.reserved_usd)
        self.assertEqual(o.audit_step(self.step(), self.item(body, result)), [])

    def test_audit_detects_tampering_and_endpoint_swaps(self):
        body = body_for()
        result = self.dispatch(body, o.MockOpenAI(ACTION))
        item = self.item(body, result)
        self.assertEqual(o.audit_step(self.step(), item), [])
        self.assertTrue(any("provider is not OpenAI direct" in message
                            for message in o.audit_step(self.step(), {**item, "provider": "OpenRouter"})))
        self.assertTrue(any("endpoint is not api.openai.com" in message
                            for message in o.audit_step(self.step(), {**item, "api_endpoint": OPENROUTER_ENDPOINT})))
        endpoint = read(self.step() / "endpoint.json")
        (self.step() / "endpoint.json").write_text(json.dumps({**endpoint, "api_endpoint": OPENROUTER_ENDPOINT}))
        self.assertTrue(any("endpoint evidence" in message for message in o.audit_step(self.step(), item)))


class RegistryTests(unittest.TestCase):
    def test_names_default_and_cli_flag(self):
        import argparse
        self.assertEqual(transports.NAMES, ("openrouter", "openai", "mock"))
        parser = argparse.ArgumentParser()
        transports.add_argument(parser)
        self.assertEqual(parser.parse_args([]).transport, "openrouter")
        self.assertEqual(parser.parse_args(["--transport", "openai"]).transport, "openai")
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            parser.parse_args(["--transport", "codex"])
        with self.assertRaises(ValueError):
            transports.profile("codex")

    def test_sealed_fields_round_trip_and_submittability(self):
        for name in transports.NAMES:
            profile = transports.profile(name)
            fields = profile.seal_fields(cost_ledger_path="../../final60.sqlite")
            self.assertEqual(transports.profile_for_authorization(fields).name, name)
            self.assertEqual(fields["per_problem_target_usd"], "2.99")
            self.assertEqual(transports.is_submittable(fields)[0], name == "openrouter")
        openai_fields = transports.profile("openai").seal_fields(cost_ledger_path="x")
        self.assertEqual((openai_fields["provider"], openai_fields["api_endpoint"], openai_fields["submittable"]),
                         ("OpenAI direct", "https://api.openai.com/v1/chat/completions", False))
        self.assertIn("never submitted", openai_fields["development_only"])
        legacy = {"provider": "OpenAI direct", "api_endpoint": "https://api.openai.com/v1/chat/completions"}
        with self.assertRaisesRegex(ValueError, "legacy"):
            transports.profile_for_authorization(legacy)
        self.assertFalse(transports.is_submittable(legacy)[0])
        forged = {**openai_fields, "transport": "openrouter"}
        with self.assertRaises(ValueError):
            transports.profile_for_authorization(forged)
        self.assertFalse(transports.is_submittable({**openai_fields, "submittable": True})[0])
        self.assertEqual(transports.profile_for_model(o.driver_model()).name, "openai")
        self.assertEqual(transports.profile_for_model(catalog.driver_model()).name, "openrouter")
        self.assertEqual(transports.profile("openai").driver_model()["backend"], "openai")
        self.assertFalse(transports.profile("openai").pricing_json()["submittable"])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        import driver
        import openai_direct_transport
        import openrouter_transport
        self.driver, self.adapter, self.base_adapter = driver, openai_direct_transport, openrouter_transport
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "rows" / "F017"
        inputs = self.root / "problems" / "F017" / "input"
        inputs.mkdir(parents=True)
        self.authorization = {"dataset_sha256": driver.DATASET_SHA, "rows": [17], "problem_count": 1,
                              "verification_policy": driver.VERIFICATION_POLICY,
                              **openai_direct_transport.seal_fields(cost_ledger_path="../../final60.sqlite")}
        (self.root / "authorization.json").write_text(json.dumps(self.authorization))
        (self.root / "frozen.json").write_text("{}")
        (self.root / "ledger.json").write_text(json.dumps({"schema_version": 1, "attempts": {}}))
        (inputs / "config.json").write_text(json.dumps({"limits": {"cost_cap_usd": "2.99"}}))
        self.model = o.driver_model()
        self.base_adapter.use_transport(None)
        self.addCleanup(self.base_adapter.use_transport, None)
        self.addCleanup(self.temporary.cleanup)

    def step_dir(self, step):
        path = self.root / "problems" / "F017" / "steps" / f"{step:04}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ledger_json(self):
        return read(self.root / "ledger.json")

    def test_adapter_exposes_the_openai_transport_names(self):
        import openai_transport
        for name in ("ENDPOINT", "PRICING", "MODEL_ID", "payload", "request_cost", "model_metadata", "query",
                     "normalize", "compute_cost", "load_key"):
            self.assertTrue(hasattr(self.adapter, name), name)
            self.assertEqual(callable(getattr(openai_transport, name)), callable(getattr(self.adapter, name)), name)
        self.assertEqual(self.adapter.ENDPOINT, openai_transport.ENDPOINT)
        self.assertEqual(self.adapter.MODEL_ID, openai_transport.MODEL_ID)
        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        self.assertEqual(body, openai_transport.payload(deepcopy(MESSAGES), self.driver.MODEL))
        self.assertEqual(Decimal(self.adapter.request_cost(body)["reserved_usd"]),
                         Decimal(openai_transport.request_cost(body)["reserved_usd"]))
        self.assertEqual(self.adapter.model_metadata()["provider"], "OpenAI direct")
        raw = o.MockOpenAI(ACTION).response(ACTION, spec(), body)
        self.assertEqual(Decimal(self.adapter.compute_cost(raw)["cost_usd"]), Decimal(openai_transport.compute_cost(raw)["cost_usd"]))
        self.assertEqual(self.adapter.normalize(raw)["provider"], "OpenAI direct")
        self.assertFalse(self.adapter.SUBMITTABLE)

    def test_driver_steps_record_openai_direct_and_are_refused_at_submission(self):
        self.base_adapter.use_transport(o.MockOpenAI([o.MockOpenAI.http_error(429), ACTION, ACTION]), sleep=no_sleep)
        first = self.adapter.payload(deepcopy(MESSAGES), self.model)
        second = self.adapter.payload([MESSAGES[0], {"role": "user", "content": '{"step":2}'}], self.model)
        with mock.patch("builtins.print"):
            raw1 = self.adapter.dispatch(self.root, 17, 1, first, self.model, self.step_dir(1), driver=self.driver)
            self.adapter.dispatch(self.root, 17, 2, second, self.model, self.step_dir(2), driver=self.driver)
        attempts = self.ledger_json()["attempts"]
        self.assertEqual(sorted(attempts), ["F017-0001", "F017-0002"])
        for item in attempts.values():
            self.assertEqual((item["status"], item["api_endpoint"], item["provider"], item["transport"]),
                             ("settled", o.ENDPOINT, "OpenAI direct", "openai"))
        self.assertEqual(raw1["provider"], "OpenAI direct")
        self.assertEqual(self.adapter.audit_root(self.root), [])
        summary = self.adapter.smoke_summary(self.root)
        self.assertEqual((summary["transport"], summary["submittable"]), ("openai", False))
        self.assertIn("never submitted", summary["submission_refusal"])
        self.assertEqual(summary["providers"], ["OpenAI direct"])
        problems = self.root / "problems" / "F017"
        statement = "theorem fixture_thm : True"
        (problems / "input/problem.json").write_text(json.dumps({"name": "fixture_thm", "statement": statement}))
        (problems / "selected.lean").write_text(statement + " := by\n  trivial\n")
        (self.root / "report.json").write_text(json.dumps({"audit_passed": True}))
        checker = _load_checker()
        benchmark = [{"name": "fixture_thm", "statement": statement, "proof": statement + " := by\n  exact True.intro\n"}]
        submission = [{"name": "fixture_thm", "proof": statement + " := by\n  trivial\n"}]
        outcome = checker.check(benchmark, submission, [checker.RunRoot(self.root)], [], [], Decimal("3"))
        self.assertTrue(any("not OpenRouter" in message for message in outcome["errors"]), outcome["errors"])
        self.assertFalse(transports.is_submittable(read(self.root / "authorization.json"))[0])
        proofs = self.adapter.dev_proofs(self.root)
        self.assertEqual([(proof["name"], proof["path"]) for proof in proofs], [("fixture_thm", "problems/F017/selected.lean")])
        outside = [(proof["path"], proof["proof"]) for proof in proofs]
        leaked = checker.check(benchmark, submission, [], [], outside, Decimal("3"))
        self.assertTrue(any("non-OpenRouter proof" in message for message in leaked["errors"]), leaked["errors"])

    def test_openrouter_models_and_roots_never_mix_with_the_openai_wire(self):
        self.base_adapter.use_transport(o.MockOpenAI(ACTION), sleep=no_sleep)
        openrouter_model = catalog.driver_model()
        body = self.base_adapter.payload(deepcopy(MESSAGES), openrouter_model)
        with self.assertRaises(ValueError):
            self.adapter.dispatch(self.root, 17, 1, body, openrouter_model, self.step_dir(1), driver=self.driver)
        self.assertEqual(self.ledger_json()["attempts"], {})
        sealed = {**self.authorization, **self.base_adapter.seal_fields(cost_ledger_path="../../final60.sqlite")}
        (self.root / "authorization.json").write_text(json.dumps(sealed))
        openai_body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        with self.assertRaises(ValueError):
            self.base_adapter.dispatch(self.root, 17, 1, openai_body, self.model, self.step_dir(1), driver=self.driver)
        self.assertEqual(self.ledger_json()["attempts"], {})
        legacy = {key: value for key, value in self.authorization.items() if key not in ("transport", "submittable", "dry_run")}
        (self.root / "authorization.json").write_text(json.dumps(legacy))
        with self.assertRaisesRegex(ValueError, "not authorized"):
            self.adapter.dispatch(self.root, 17, 1, openai_body, self.model, self.step_dir(1), driver=self.driver)

    def test_crashed_openai_step_is_recovered_without_a_second_call(self):
        class Killed(Exception):
            pass

        body = self.adapter.payload(deepcopy(MESSAGES), self.model)
        self.base_adapter.use_transport(o.MockOpenAI([Killed()]), sleep=no_sleep)
        with self.assertRaises(Killed), mock.patch("builtins.print"):
            self.adapter.dispatch(self.root, 17, 1, body, self.model, self.step_dir(1), driver=self.driver)
        restart = o.MockOpenAI([ACTION])
        self.base_adapter.use_transport(restart, sleep=no_sleep)
        with mock.patch("builtins.print"):
            recovered = self.adapter.recover_pending(self.root, 17, 1, self.step_dir(1), driver=self.driver)
        item = self.ledger_json()["attempts"]["F017-0001"]
        self.assertEqual((item["status"], item["api_endpoint"], item["provider"]), ("settled", o.ENDPOINT, "OpenAI direct"))
        self.assertEqual(len(item["sub_attempts"]), 2)
        self.assertEqual(restart.http_calls, 1)
        self.assertEqual(recovered["provider"], "OpenAI direct")
        self.assertEqual(self.adapter.audit_root(self.root), [])

    def test_openrouter_adapter_is_unchanged_for_openrouter_roots(self):
        sealed = {**self.authorization, **self.base_adapter.seal_fields(cost_ledger_path="../../final60.sqlite")}
        (self.root / "authorization.json").write_text(json.dumps(sealed))
        self.assertEqual((sealed["provider"], sealed["transport"], sealed["submittable"]), ("OpenRouter", "openrouter", True))
        self.base_adapter.use_transport(t.MockOpenRouter(ACTION), sleep=no_sleep)
        model = catalog.driver_model()
        body = self.base_adapter.payload(deepcopy(MESSAGES), model)
        with mock.patch("builtins.print"):
            self.base_adapter.dispatch(self.root, 17, 1, body, model, self.step_dir(1), driver=self.driver)
        item = self.ledger_json()["attempts"]["F017-0001"]
        self.assertEqual((item["api_endpoint"], item["provider"], item["transport"]), (OPENROUTER_ENDPOINT, "OpenRouter", "openrouter"))
        self.assertEqual(self.base_adapter.audit_root(self.root), [])
        self.assertTrue(transports.is_submittable(sealed)[0])


class CheckerTests(unittest.TestCase):
    """scripts/check_submission_provenance.py refuses OpenAI-direct steps even under an OpenRouter seal."""

    def test_per_call_endpoints_are_checked(self):
        checker = _load_checker()
        statement = "theorem fixture_thm : True"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            problem = root / "problems" / "F017"
            (problem / "input").mkdir(parents=True)
            (problem / "input" / "problem.json").write_text(json.dumps({"name": "fixture_thm"}))
            (problem / "selected.lean").write_text(statement + " := by\n  trivial\n")
            (root / "authorization.json").write_text(json.dumps({"rows": [17], "api_endpoint": OPENROUTER_ENDPOINT}))
            attempts = {"F017-0001": {"row": 17, "step": 1, "status": "settled", "cost_usd": "0.01",
                                      "api_endpoint": OPENROUTER_ENDPOINT, "provider": "OpenRouter"},
                        "F017-0002": {"row": 17, "step": 2, "status": "settled", "cost_usd": "0.01",
                                      "api_endpoint": o.ENDPOINT, "provider": "OpenAI direct"}}
            (root / "ledger.json").write_text(json.dumps({"attempts": attempts}))
            (root / "report.json").write_text(json.dumps({"audit_passed": True}))
            benchmark = [{"name": "fixture_thm", "statement": statement, "proof": statement + " := by\n  exact True.intro\n"}]
            submission = [{"name": "fixture_thm", "proof": statement + " := by\n  trivial\n"}]
            outcome = checker.check(benchmark, submission, [checker.RunRoot(root)], [], [], Decimal("3"))
            self.assertTrue(any("api.openai.com" in message and "not OpenRouter" in message
                                for message in outcome["errors"]), outcome["errors"])
            attempts["F017-0002"].update(api_endpoint=OPENROUTER_ENDPOINT, provider="OpenRouter")
            (root / "ledger.json").write_text(json.dumps({"attempts": attempts}))
            clean = checker.check(benchmark, submission, [checker.RunRoot(root)], [], [], Decimal("3"))
            self.assertEqual(clean["errors"], [])


if __name__ == "__main__":
    unittest.main()
