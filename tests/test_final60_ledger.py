"""final60 CostLedger: reservations, settlement rules, crash recovery and concurrency."""
from decimal import Decimal
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from lean_agent.artifacts import read
from lean_agent.final60 import catalog, ledger as L, transport as t
from lean_agent.final60.contracts import CAP_USD, OPENROUTER_ENDPOINT, Bound, Receipt

BOUND = Bound(input_token_bound=10_000, output_token_bound=8192, reserved_usd=Decimal("0.25"), basis="fixture")


def reserve(ledger, attempt, *, problem="F017", bound=BOUND, root="/runs/F017"):
    ledger.reserve(problem=problem, attempt_id=attempt, bound=bound, run_root=root, model="openai/gpt-6.1-sol",
                   provider="openai", api_endpoint=OPENROUTER_ENDPOINT, request_sha256="0" * 64)


def receipt(attempt, status, cost):
    return Receipt(attempt_id=attempt, status=status, cost_usd=Decimal(cost), generation_id=None, model=None,
                   provider=None, api_endpoint=OPENROUTER_ENDPOINT, basis="fixture")


def _contend(path, worker, results):
    ledger = L.CostLedger(path)
    granted = 0
    for number in range(10):
        try:
            reserve(ledger, f"F017-{worker:02}{number:02}#r0")
            granted += 1
        except L.BudgetExceeded:
            pass
    results.put(granted)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "final60.sqlite"
        self.ledger = L.CostLedger(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_lifecycle_and_totals(self):
        reserve(self.ledger, "F017-0001#r0")
        self.assertEqual(self.ledger.committed("F017"), Decimal("0.25"))
        self.assertEqual(self.ledger.spent("F017"), 0)
        self.ledger.mark_sent("F017-0001#r0")
        self.ledger.settle(receipt("F017-0001#r0", "settled", "0.031"))
        self.assertEqual(self.ledger.spent("F017"), Decimal("0.031"))
        self.assertEqual(self.ledger.committed("F017"), Decimal("0.031"))
        self.assertEqual(self.ledger.headroom("F017"), CAP_USD - Decimal("0.031"))
        self.ledger.settle(receipt("F017-0001#r0", "settled", "0.031"))      # idempotent
        with self.assertRaises(ValueError):
            self.ledger.settle(receipt("F017-0001#r0", "settled", "0.05"))
        summary = self.ledger.summary()
        self.assertEqual(summary["problems"]["F017"]["spent_usd"], "0.031")
        self.assertEqual(summary["total_usd"], "0.031")
        self.assertTrue(summary["within_cap"])
        exported = Path(self.temporary.name) / "ledger-export.json"
        self.ledger.export_json(exported)
        self.assertEqual(read(exported)["attempts"][0]["attempt_id"], "F017-0001#r0")

    def test_cap_refusal_writes_nothing_and_duplicates_are_refused(self):
        for number in range(11):
            reserve(self.ledger, f"F017-{number:04}#r0")
        self.assertEqual(self.ledger.committed("F017"), Decimal("2.75"))
        with self.assertRaises(L.BudgetExceeded) as caught:
            reserve(self.ledger, "F017-0099#r0")
        self.assertEqual(caught.exception.reason, "cap")
        self.assertIsNone(self.ledger.get("F017-0099#r0"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            reserve(self.ledger, "F017-0000#r0")
        reserve(self.ledger, "F018-0001#r0", problem="F018")     # caps are per problem

    def test_prior_spend_counts_and_is_immutable(self):
        self.ledger.declare_prior("F017", "2.80", note="Smoke outside this root")
        self.ledger.declare_prior("F017", "2.80")
        with self.assertRaises(ValueError):
            self.ledger.declare_prior("F017", "1.00")
        with self.assertRaises(L.BudgetExceeded):
            reserve(self.ledger, "F017-0001#r0")
        self.assertEqual(self.ledger.spent("F017"), Decimal("2.80"))

    def test_settlement_rules(self):
        reserve(self.ledger, "F017-0001#r0")
        with self.assertRaises(ValueError):
            self.ledger.settle(receipt("F017-0001#r0", "unbilled", "0"))       # never sent
        self.ledger.settle(receipt("F017-0001#r0", "void", "0"))
        reserve(self.ledger, "F017-0002#r0")
        self.ledger.mark_sent("F017-0002#r0")
        with self.assertRaises(ValueError):
            self.ledger.settle(receipt("F017-0002#r0", "void", "0"))           # a sent call may be billed
        with self.assertRaises(ValueError):
            self.ledger.settle(receipt("F017-0002#r0", "unbilled", "0.01"))
        with self.assertRaises(ValueError):
            self.ledger.settle(receipt("F017-0002#r0", "lost_conservative", "0.10"))
        self.ledger.settle(receipt("F017-0002#r0", "lost_conservative", "0.25"))
        with self.assertRaises(ValueError):
            self.ledger.mark_sent("F017-0002#r0")
        self.assertEqual(self.ledger.spent("F017"), Decimal("0.25"))

    def test_cap_must_not_exceed_the_contract_cap(self):
        with self.assertRaises(ValueError):
            L.CostLedger(self.path, cap_usd=Decimal("3.00"))
        small = L.CostLedger(":memory:", cap_usd=Decimal("0.30"))
        reserve(small, "F017-0001#r0")
        with self.assertRaises(L.BudgetExceeded):
            reserve(small, "F017-0002#r0")

    def test_flags_block_reservations(self):
        self.ledger.flag("F017", "frozen", "bound violated")
        with self.assertRaises(L.BudgetExceeded) as caught:
            reserve(self.ledger, "F017-0001#r0")
        self.assertEqual(caught.exception.reason, "frozen")
        self.assertEqual(self.ledger.flags("F017"), {"frozen": "bound violated"})
        self.ledger.clear_flag("F017", "frozen")
        reserve(self.ledger, "F017-0001#r0")

    def test_eight_processes_never_exceed_the_cap(self):
        context = multiprocessing.get_context("spawn")
        results = context.Queue()
        workers = [context.Process(target=_contend, args=(str(self.path), number, results)) for number in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(120)
            self.assertEqual(worker.exitcode, 0)
        granted = sum(results.get(timeout=10) for _ in workers)
        self.assertEqual(granted, int(CAP_USD / Decimal("0.25")))
        self.assertLessEqual(self.ledger.committed("F017"), CAP_USD)
        self.assertEqual(len(self.ledger.attempts("F017")), granted)

    def test_recover_voids_unsent_and_charges_lost_at_the_bound(self):
        spec = catalog.spec("gen_primary")
        body = t.payload([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], spec)
        bound = t.request_bound(body, spec)
        step = Path(self.temporary.name) / "steps" / "0001"
        step.mkdir(parents=True)
        (step / "request.json").write_text(json.dumps(body))
        reserve(self.ledger, "F017-0001#r0", bound=bound)
        self.assertEqual(self.ledger.recover("F017-0001#r0", step_dir=step).status, "void")
        reserve(self.ledger, "F017-0001#r1", bound=bound)
        self.ledger.mark_sent("F017-0001#r1")
        lost = self.ledger.recover("F017-0001#r1", step_dir=step)
        self.assertEqual((lost.status, lost.cost_usd), ("lost_conservative", bound.reserved_usd))
        self.assertTrue((step / "http/r1/recovered.json").exists())
        self.assertEqual(read(step / "http/r1/provider-response.json")["transport_error"], "NoDurableResponse")
        reserve(self.ledger, "F017-0001#r2", bound=bound)
        self.ledger.mark_sent("F017-0001#r2")
        saved = {"id": "gen-saved-1", "model": spec.model_id, "provider": "OpenAI",
                 "choices": [{"message": {"role": "assistant", "content": "{}"}}],
                 "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55, "cost": 0.0002}}
        (step / "http/r2").mkdir(parents=True)
        (step / "http/r2/provider-response.json").write_text(json.dumps(saved))
        settled = self.ledger.recover("F017-0001#r2", step_dir=step)
        self.assertEqual((settled.status, settled.generation_id), ("settled", "gen-saved-1"))
        self.assertEqual(settled.cost_usd, Decimal("0.0002"))     # usage.cost above its 0.00015 list price
        self.assertEqual(self.ledger.open_attempts(), [])
        self.assertEqual(self.ledger.recover("F017-0001#r2", step_dir=step), settled)

    def test_reconcile_reports_disagreement_with_ledger_json(self):
        root = "/runs/F017"
        reserve(self.ledger, "F017-0001#r0", root=root)
        self.ledger.mark_sent("F017-0001#r0")
        self.ledger.settle(receipt("F017-0001#r0", "settled", "0.02"))
        good = {"attempts": {"F017-0001": {"status": "settled", "cost_usd": "0.02",
                                           "sub_attempts": [{"id": "F017-0001#r0"}]}}}
        self.assertEqual(self.ledger.reconcile(root, good), [])
        bad = {"attempts": {"F017-0001": {"status": "settled", "cost_usd": "0.03",
                                          "sub_attempts": [{"id": "F017-0001#r0"}]}}}
        self.assertTrue(any("cost" in message for message in self.ledger.reconcile(root, bad)))
        self.assertTrue(self.ledger.reconcile(root, {"attempts": {}}))
        self.assertEqual(L.split_attempt("F017-0005#r12"), ("F017-0005", 12))
        self.assertEqual(L.split_attempt("F017-0005"), ("F017-0005", 0))


if __name__ == "__main__":
    unittest.main()
