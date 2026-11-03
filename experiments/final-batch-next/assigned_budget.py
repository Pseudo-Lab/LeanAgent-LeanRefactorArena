"""One budgeted proof proposal, sharing a durable per-theorem ledger across runs."""

from decimal import Decimal
import json
import os
import sqlite3
import time
from lean_agent import budgeting, models

CAP = Decimal("2.99")
MODEL = dict(
    backend="openrouter",
    id="openai/gpt-6.1-sol",
    provider="openai",
    max_tokens=4096,
    timeout_seconds=240,
    reasoning_effort="medium",
    max_price=dict(prompt=2.5, completion=10),
)


class ProblemBudgetError(ValueError):
    """This theorem's ledger cannot admit another paid call."""


def propose(db, name, prior, messages, *, dispatch=models.query):
    if dispatch is models.query:
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key.startswith("sk-or-"):
            raise ValueError("Set an OpenRouter-issued key")
    prior = Decimal(str(prior))
    if not prior.is_finite() or prior < 0:
        raise ValueError("Prior list-price spend must be a nonnegative amount")
    body = models.payload(messages, MODEL)
    reservation = budgeting.request_cost(body)
    maximum = Decimal(reservation["reserved_usd"])
    with sqlite3.connect(db, timeout=20) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS prior(name TEXT PRIMARY KEY, usd TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, name TEXT, stamp REAL, status TEXT, bound TEXT, charged TEXT, request TEXT, response TEXT)"
        )
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT usd FROM prior WHERE name=?", (name,)).fetchone()
        if existing and Decimal(existing[0]) != prior:
            raise ProblemBudgetError("Prior spend differs from the locked ledger")
        conn.execute("INSERT OR IGNORE INTO prior VALUES(?,?)", (name, str(prior)))
        history = conn.execute("SELECT status,charged FROM calls WHERE name=?", (name,)).fetchall()
        if any(status != "billed" for status, _ in history):
            raise ProblemBudgetError(
                "Unresolved prior request; reconcile its receipt before another call"
            )
        consumed = prior + sum(Decimal(cost) for _, cost in history)
        if consumed + maximum > CAP:
            raise ProblemBudgetError("Next worst-case call would exceed the per-problem cap")
        cur = conn.execute(
            "INSERT INTO calls(name,stamp,status,bound,request) VALUES(?,?,?,?,?)",
            (name, time.time(), "pending", str(maximum), json.dumps(body, ensure_ascii=False)),
        )
        call_id = cur.lastrowid
        conn.commit()  # Crash or timeout leaves a reservation that blocks a second dispatch.
        raw = dispatch(body, MODEL, call_id)
        rec = models.receipt(raw)
        usage = rec["usage"] or {}
        inp, out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if rec["cost_usd"] is None or any(type(v) is not int or v < 0 for v in (inp, out)):
            status, debit = "unresolved", None
        else:
            # Conservative list-price upper debit. Covers cache writes; no discounts assumed.
            debit = max(Decimal(rec["cost_usd"]), (Decimal("2.5") * inp + 10 * out) / 1_000_000)
            status = "billed" if debit <= maximum else "review"
        conn.execute(
            "UPDATE calls SET status=?,charged=?,response=? WHERE id=?",
            (
                status,
                str(debit) if debit is not None else None,
                json.dumps(raw, ensure_ascii=False),
                call_id,
            ),
        )
        conn.commit()
        if status != "billed":
            raise ProblemBudgetError(
                "Incomplete or unexpected bill; further requests for this problem are blocked"
            )
        return call_id, {**rec, "charged_usd": str(debit)}
