"""Shared SQLite cost ledger for final60 (WAL, busy_timeout 30 s, BEGIN IMMEDIATE).

One row per HTTP sub-attempt ("F017-0005#r0"); the driver step ("F017-0005") is
the row's ``step_attempt``. Before any request is sent its worst-case bound is
reserved, and the reservation is refused unless

    prior + settled + open reservations + bound <= cap        (per problem)

so the cap holds across processes, retries and discarded responses. Statuses:
``reserved`` -> ``sent`` -> ``settled`` | ``unbilled`` | ``lost_conservative``, or
``reserved`` -> ``void`` (never sent). A settled row is never rewritten.

Within one run root this is a mirror of the root's ``ledger.json`` (the file
report.py and the PR #70 checker read); ``reconcile`` reports any disagreement.
Across roots it is the only place that sees all spend for a problem (Smoke,
continuation roots), which is why every reservation checks it.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

from .contracts import CAP_USD, SCHEMA, Bound, Receipt

OPEN = ("reserved", "sent")
FINAL = ("settled", "unbilled", "lost_conservative", "void")
CHARGED = ("settled", "lost_conservative")
FLAGS = ("frozen", "api_disabled")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prior(problem TEXT PRIMARY KEY, usd TEXT NOT NULL, note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS flags(problem TEXT NOT NULL, flag TEXT NOT NULL, reason TEXT, created_at REAL,
                                 PRIMARY KEY(problem, flag));
CREATE TABLE IF NOT EXISTS attempts(
  attempt_id TEXT PRIMARY KEY, step_attempt TEXT NOT NULL, sub_index INTEGER NOT NULL, problem TEXT NOT NULL,
  run_root TEXT NOT NULL, step_dir TEXT, status TEXT NOT NULL, reserved_usd TEXT NOT NULL,
  input_token_bound INTEGER, output_token_bound INTEGER, cost_usd TEXT, model TEXT, provider TEXT,
  api_endpoint TEXT, request_sha256 TEXT, generation_id TEXT, returned_model TEXT, returned_provider TEXT,
  http_status INTEGER, basis TEXT, owner_pid INTEGER, created_at REAL, sent_at REAL, settled_at REAL);
CREATE INDEX IF NOT EXISTS attempts_problem ON attempts(problem);
CREATE INDEX IF NOT EXISTS attempts_step ON attempts(step_attempt);
"""


class BudgetExceeded(Exception):
    """A reservation was refused: the cap would be crossed, or the problem's API is frozen/disabled."""

    def __init__(self, message, *, problem=None, committed=None, bound=None, cap=None, reason="cap"):
        super().__init__(message)
        self.problem, self.committed, self.bound, self.cap, self.reason = problem, committed, bound, cap, reason


def _usd(value) -> str:
    amount = Decimal(value)
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "0") else text


def _amount(value, label) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid USD amount: " + label) from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("Expected a finite nonnegative USD amount: " + label)
    return amount


def split_attempt(attempt_id: str) -> tuple[str, int]:
    """"F017-0005#r2" -> ("F017-0005", 2); an id without "#r" is sub-attempt 0 of itself."""
    if not isinstance(attempt_id, str) or not attempt_id:
        raise ValueError("Attempt id must be a nonempty string")
    step, marker, index = attempt_id.rpartition("#r")
    if marker and step and index.isdigit():
        return step, int(index)
    return attempt_id, 0


class CostLedger:
    def __init__(self, path, *, cap_usd: Decimal = CAP_USD):
        cap = _amount(cap_usd, "cap_usd")
        if cap <= 0 or cap > CAP_USD:
            raise ValueError(f"Per-problem cap must be in (0, {CAP_USD}]")
        self.cap = cap
        self.memory = str(path) == ":memory:"
        self.path = Path(path) if not self.memory else None
        self._lock = threading.RLock()
        self._conn = None
        if self.memory:
            self._conn = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:   # idempotent DDL in autocommit mode (executescript would commit an open transaction)
                conn.executescript(_SCHEMA_SQL)
                conn.execute("INSERT OR IGNORE INTO meta VALUES('schema', ?)", (SCHEMA,))
            finally:
                if not self.memory:
                    conn.close()

    # ------------------------------------------------------------ connections

    def _connect(self):
        if self.memory:
            return self._conn
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @contextmanager
    def _tx(self, immediate=True):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
                try:
                    yield conn
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                conn.execute("COMMIT")
            finally:
                if not self.memory:
                    conn.close()

    # ------------------------------------------------------------ totals

    @staticmethod
    def _totals(conn, problem):
        prior = conn.execute("SELECT usd FROM prior WHERE problem=?", (problem,)).fetchone()
        spent = Decimal(prior["usd"]) if prior else Decimal(0)
        held = Decimal(0)
        for row in conn.execute("SELECT status, cost_usd, reserved_usd FROM attempts WHERE problem=?", (problem,)):
            if row["status"] in CHARGED:
                spent += Decimal(row["cost_usd"])
            elif row["status"] in OPEN:
                held += Decimal(row["reserved_usd"])
        return spent, held

    def spent(self, problem: str) -> Decimal:
        """Declared prior + settled + lost_conservative."""
        with self._tx(immediate=False) as conn:
            return self._totals(conn, problem)[0]

    def committed(self, problem: str) -> Decimal:
        """spent + open reservations."""
        with self._tx(immediate=False) as conn:
            spent, held = self._totals(conn, problem)
            return spent + held

    def headroom(self, problem: str) -> Decimal:
        return self.cap - self.committed(problem)

    def fits(self, problem: str, bound: Bound) -> bool:
        return self.committed(problem) + Decimal(bound.reserved_usd) <= self.cap

    # ------------------------------------------------------------ prior spend and flags

    def declare_prior(self, problem: str, usd, *, note: str = "") -> None:
        """Spend outside this ledger that counts against the problem's cap (immutable once set)."""
        amount = _amount(usd, "prior")
        with self._tx() as conn:
            row = conn.execute("SELECT usd FROM prior WHERE problem=?", (problem,)).fetchone()
            if row is not None:
                if Decimal(row["usd"]) != amount:
                    raise ValueError("Prior spend differs from the locked ledger for " + problem)
                return
            spent, held = self._totals(conn, problem)
            if spent + held + amount > self.cap:
                raise BudgetExceeded(f"{problem}: declared prior spend would exceed the cap", problem=problem,
                                     committed=spent + held, cap=self.cap)
            conn.execute("INSERT INTO prior VALUES(?,?,?,?)", (problem, _usd(amount), note, time.time()))

    def prior(self, problem: str) -> Decimal:
        with self._tx(immediate=False) as conn:
            row = conn.execute("SELECT usd FROM prior WHERE problem=?", (problem,)).fetchone()
            return Decimal(row["usd"]) if row else Decimal(0)

    def flag(self, problem: str, flag: str, reason: str) -> None:
        if flag not in FLAGS:
            raise ValueError("Unknown ledger flag: " + flag)
        with self._tx() as conn:
            conn.execute("INSERT OR IGNORE INTO flags VALUES(?,?,?,?)", (problem, flag, reason[:500], time.time()))

    def flags(self, problem: str) -> dict:
        with self._tx(immediate=False) as conn:
            return {row["flag"]: row["reason"] for row in
                    conn.execute("SELECT flag, reason FROM flags WHERE problem=?", (problem,))}

    def clear_flag(self, problem: str, flag: str) -> None:
        """Operator action only (e.g. after a Smoke fix); never called by the dispatch path."""
        with self._tx() as conn:
            conn.execute("DELETE FROM flags WHERE problem=? AND flag=?", (problem, flag))

    # ------------------------------------------------------------ reservation lifecycle

    def reserve(self, *, problem: str, attempt_id: str, bound: Bound, run_root: str, model: str,
                provider: str, api_endpoint: str, request_sha256: str, step_dir: str | None = None) -> None:
        """Reserve one HTTP call; BudgetExceeded (nothing written) unless committed + bound <= cap."""
        amount = _amount(bound.reserved_usd, "bound")
        if amount <= 0:
            raise ValueError("A reservation needs a positive bound")
        step, index = split_attempt(attempt_id)
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone():
                raise ValueError("Duplicate attempt id; refusing a second reservation: " + attempt_id)
            flag = conn.execute("SELECT flag, reason FROM flags WHERE problem=? ORDER BY flag", (problem,)).fetchone()
            if flag is not None:
                raise BudgetExceeded(f"{problem}: API {flag['flag']} ({flag['reason']})", problem=problem,
                                     cap=self.cap, reason=flag["flag"])
            spent, held = self._totals(conn, problem)
            if spent + held + amount > self.cap:
                raise BudgetExceeded(f"{problem}: committed {_usd(spent + held)} + bound {_usd(amount)} "
                                     f"exceeds the {_usd(self.cap)} cap", problem=problem,
                                     committed=spent + held, bound=amount, cap=self.cap)
            conn.execute(
                "INSERT INTO attempts(attempt_id, step_attempt, sub_index, problem, run_root, step_dir, status, "
                "reserved_usd, input_token_bound, output_token_bound, model, provider, api_endpoint, request_sha256, "
                "owner_pid, created_at) VALUES(?,?,?,?,?,?,'reserved',?,?,?,?,?,?,?,?,?)",
                (attempt_id, step, index, problem, str(run_root), None if step_dir is None else str(step_dir),
                 _usd(amount), bound.input_token_bound, bound.output_token_bound, model, provider, api_endpoint,
                 request_sha256, os.getpid(), time.time()))

    def mark_sent(self, attempt_id: str) -> None:
        """Committed (synchronous=FULL) before the HTTP call starts."""
        with self._tx() as conn:
            row = conn.execute("SELECT status FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["status"] != "reserved":
                raise ValueError("Only a reserved, unsent attempt can be marked sent: " + attempt_id)
            conn.execute("UPDATE attempts SET status='sent', sent_at=?, owner_pid=? WHERE attempt_id=?",
                         (time.time(), os.getpid(), attempt_id))

    def settle(self, receipt: Receipt) -> None:
        if receipt.status not in FINAL:
            raise ValueError("Unknown settlement status: " + str(receipt.status))
        cost = _amount(receipt.cost_usd, "cost")
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (receipt.attempt_id,)).fetchone()
            if row is None:
                raise ValueError("Settlement for an unreserved attempt: " + receipt.attempt_id)
            if row["status"] in FINAL:
                if row["status"] == receipt.status and Decimal(row["cost_usd"]) == cost:
                    return
                raise ValueError("Attempt already settled differently: " + receipt.attempt_id)
            if receipt.status == "void" and row["status"] != "reserved":
                raise ValueError("A sent attempt can never be voided: " + receipt.attempt_id)
            if receipt.status != "void" and row["status"] != "sent":
                raise ValueError("Only a sent attempt can be billed or refused: " + receipt.attempt_id)
            if receipt.status in ("void", "unbilled") and cost != 0:
                raise ValueError("Void/unbilled settlements must be $0")
            if receipt.status == "lost_conservative" and cost < Decimal(row["reserved_usd"]):
                raise ValueError("A lost response is settled at no less than its reservation")
            conn.execute(
                "UPDATE attempts SET status=?, cost_usd=?, generation_id=?, returned_model=?, returned_provider=?, "
                "http_status=?, basis=?, settled_at=? WHERE attempt_id=?",
                (receipt.status, _usd(cost), receipt.generation_id, receipt.model, receipt.provider,
                 receipt.http_status, receipt.basis, time.time(), receipt.attempt_id))

    # ------------------------------------------------------------ crash recovery

    def recover(self, attempt_id: str, *, step_dir: Path, key: str | None = None, lookup=None,
                sleep=time.sleep, wire=None) -> Receipt:
        """Settle an open sub-attempt after a crash: void if never sent; from the saved
        response if one exists (exact via the generation API for a lost one when a
        generation id is known and ``lookup`` or ``key`` is given); else at its full reservation.

        ``lookup`` maps a generation id to a generation document (or None); with only
        ``key`` the real generation API is queried (free). ``wire`` is the provider
        module the attempt was sent through (OpenRouter by default).
        """
        from . import transport
        from lean_agent.artifacts import read
        transport = wire if wire is not None else transport
        row = self.get(attempt_id)
        if row is None:
            raise ValueError("Unknown attempt: " + attempt_id)
        if row["status"] in FINAL:
            return self._receipt(row)
        _, index = split_attempt(attempt_id)
        folder = Path(step_dir) / "http" / f"r{index}"
        if row["status"] == "reserved":
            _atomic(folder / "void.json", {"attempt_id": attempt_id, "reason": "reserved but never sent",
                                           "at": time.time()})
            receipt = Receipt(attempt_id=attempt_id, status="void", cost_usd=Decimal(0), generation_id=None,
                              model=None, provider=None, api_endpoint=row["api_endpoint"], basis="void-never-sent")
            self.settle(receipt)
            return receipt
        reserved = Bound(row["input_token_bound"], row["output_token_bound"], Decimal(row["reserved_usd"]),
                         transport.BOUND_BASIS)
        spec, bound = None, reserved
        request_path = Path(step_dir) / "request.json"
        if request_path.exists():
            body = read(request_path)
            spec = transport.spec_for_body(body)
            bound = transport.request_bound(body, spec)
            if bound.reserved_usd != reserved.reserved_usd:
                raise ValueError("Saved request bound differs from the reservation: " + attempt_id)
        if spec is None:
            spec = transport.fallback_spec(row["model"])
        provider_path = folder / "provider-response.json"
        if provider_path.exists():
            raw = read(provider_path)
        else:
            raw = {"transport_error": "NoDurableResponse", "http_status": None, "billing_hint": "unknown",
                   "recovered": True}
            _atomic(provider_path, raw)
            _atomic(folder / "recovered.json", {"attempt_id": attempt_id, "at": time.time(),
                                                "reason": "sent without a durable provider response"})
        generation = read(folder / "generation.json") if (folder / "generation.json").exists() else None
        if lookup is None and key and getattr(transport, "GENERATION_API", True):
            lookup = lambda value: lookup_generation(value, key=key, spec=spec, sleep=sleep)  # noqa: E731
        if generation is None and transport.classify(raw) == "lost" and lookup is not None:
            generation_id = transport.generation_id_of(raw)
            if generation_id:
                generation = lookup(generation_id)
                if generation is not None:
                    _atomic(folder / "generation.json", generation)
        record = {"id": attempt_id, **transport.sub_attempt_cost(raw, spec, bound, generation)}
        receipt_path = folder / "receipt.json"
        if receipt_path.exists() and read(receipt_path) != record:
            raise ValueError("Saved receipt differs from its provider evidence: " + attempt_id)
        _atomic(receipt_path, record)
        receipt = receipt_from_record(record, row["api_endpoint"])
        self.settle(receipt)
        return receipt

    # ------------------------------------------------------------ queries

    def get(self, attempt_id: str) -> dict | None:
        with self._tx(immediate=False) as conn:
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            return dict(row) if row else None

    def sub_attempts(self, step_attempt: str) -> list[dict]:
        with self._tx(immediate=False) as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM attempts WHERE step_attempt=? ORDER BY sub_index", (step_attempt,))]

    def next_index(self, step_attempt: str) -> int:
        rows = self.sub_attempts(step_attempt)
        return max((row["sub_index"] for row in rows), default=-1) + 1

    def open_attempts(self, *, run_root: str | None = None) -> list[dict]:
        with self._tx(immediate=False) as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM attempts WHERE status IN ('reserved','sent') ORDER BY created_at, attempt_id")]
        wanted = None if run_root is None else root_key(run_root)
        return [row for row in rows if wanted is None or root_key(row["run_root"]) == wanted]

    def attempts(self, problem: str | None = None) -> list[dict]:
        with self._tx(immediate=False) as conn:
            if problem is None:
                cursor = conn.execute("SELECT * FROM attempts ORDER BY created_at, attempt_id")
            else:
                cursor = conn.execute("SELECT * FROM attempts WHERE problem=? ORDER BY created_at, attempt_id",
                                      (problem,))
            return [dict(row) for row in cursor]

    def spent_by_root(self, problem: str) -> dict[str, Decimal]:
        totals = {}
        for row in self.attempts(problem):
            if row["status"] in CHARGED:
                totals[row["run_root"]] = totals.get(row["run_root"], Decimal(0)) + Decimal(row["cost_usd"])
        return totals

    @staticmethod
    def _receipt(row) -> Receipt:
        return Receipt(attempt_id=row["attempt_id"], status=row["status"], cost_usd=Decimal(row["cost_usd"] or 0),
                       generation_id=row["generation_id"], model=row["returned_model"],
                       provider=row["returned_provider"], api_endpoint=row["api_endpoint"], basis=row["basis"] or "",
                       http_status=row["http_status"])

    def summary(self) -> dict:
        rows = self.attempts()
        with self._tx(immediate=False) as conn:
            priors = {row["problem"]: Decimal(row["usd"]) for row in conn.execute("SELECT * FROM prior")}
            flags = {}
            for row in conn.execute("SELECT * FROM flags ORDER BY problem, flag"):
                flags.setdefault(row["problem"], {})[row["flag"]] = row["reason"]
        problems = {}
        for problem in sorted({row["problem"] for row in rows} | set(priors)):
            mine = [row for row in rows if row["problem"] == problem]
            charged = [Decimal(row["cost_usd"]) for row in mine if row["status"] in CHARGED]
            spent = priors.get(problem, Decimal(0)) + sum(charged, Decimal(0))
            problems[problem] = {
                "http_calls": sum(row["status"] not in ("reserved", "void") for row in mine),
                "charged_calls": len(charged), "unbilled_calls": sum(row["status"] == "unbilled" for row in mine),
                "lost_calls": sum(row["status"] == "lost_conservative" for row in mine),
                "open_reservations": sum(row["status"] in OPEN for row in mine),
                "prior_usd": _usd(priors.get(problem, Decimal(0))), "spent_usd": _usd(spent),
                "max_call_usd": _usd(max(charged, default=Decimal(0))), "headroom_usd": _usd(self.cap - spent),
                "flags": flags.get(problem, {})}
        totals = [Decimal(value["spent_usd"]) for value in problems.values()]
        return {"schema": SCHEMA, "cap_usd": _usd(self.cap), "problems": problems,
                "total_usd": _usd(sum(totals, Decimal(0))),
                "mean_usd": _usd(sum(totals, Decimal(0)) / len(totals)) if totals else "0",
                "max_problem_usd": _usd(max(totals, default=Decimal(0))),
                "within_cap": all(value <= self.cap for value in totals),
                "open_reservations": sum(value["open_reservations"] for value in problems.values())}

    def export_json(self, path: Path) -> None:
        _atomic(Path(path), {"schema": SCHEMA, "exported_at": time.time(), "cap_usd": _usd(self.cap),
                             "summary": self.summary(), "attempts": self.attempts()})

    def reconcile(self, run_root, ledger_json: dict) -> list[str]:
        """Disagreements between this mirror and one root's ledger.json (empty = consistent)."""
        root = root_key(run_root)
        by_step = {}
        for row in self.attempts():
            if root_key(row["run_root"]) == root:
                by_step.setdefault(row["step_attempt"], []).append(row)
        errors, items = [], ledger_json.get("attempts", {})
        for step, item in items.items():
            rows = sorted((row for row in by_step.get(step, []) if row["status"] != "void"),
                          key=lambda row: row["sub_index"])
            if item.get("status") != "settled":
                errors.append(f"{step}: ledger.json attempt is {item.get('status')}")
                continue
            if not rows:
                errors.append(f"{step}: settled in ledger.json but absent from the SQLite mirror")
                continue
            if any(row["status"] in OPEN for row in rows):
                errors.append(f"{step}: SQLite sub-attempt still open")
            total = sum((Decimal(row["cost_usd"]) for row in rows if row["status"] in CHARGED), Decimal(0))
            try:
                if Decimal(str(item.get("cost_usd"))) != total:
                    errors.append(f"{step}: ledger.json cost {item.get('cost_usd')} != SQLite {_usd(total)}")
            except InvalidOperation:
                errors.append(f"{step}: ledger.json cost is not a decimal")
            listed = [sub.get("id") for sub in item.get("sub_attempts") or []]
            known = {row["attempt_id"]: row for row in rows}
            # Every charged sub-attempt must be listed; an unlisted $0 refusal is allowed only
            # because a released step's archived evidence is no longer part of the step.
            if (any(identity not in known for identity in listed)
                    or any(row["attempt_id"] not in listed for row in rows if row["status"] != "unbilled")):
                errors.append(f"{step}: ledger.json sub_attempts differ from the SQLite mirror")
        for step, rows in by_step.items():
            if step in items:
                continue
            if any(row["status"] in OPEN for row in rows):
                errors.append(f"{step}: open SQLite reservation without a ledger.json attempt")
            charged = sum((Decimal(row["cost_usd"]) for row in rows if row["status"] in CHARGED), Decimal(0))
            if charged:
                errors.append(f"{step}: SQLite spend {_usd(charged)} missing from ledger.json")
        return errors


def root_key(value) -> str:
    """Comparable form of a run-root path (absolute, symlinks resolved)."""
    try:
        return str(Path(value).resolve())
    except (OSError, RuntimeError):
        return str(value)


def receipt_from_record(record: dict, api_endpoint: str) -> Receipt:
    return Receipt(attempt_id=record["id"], status=record["status"], cost_usd=Decimal(record["cost_usd"]),
                   generation_id=record.get("generation_id"), model=record.get("returned_model"),
                   provider=record.get("returned_provider"), api_endpoint=api_endpoint, basis=record["basis"],
                   http_status=record.get("http_status"))


def lookup_generation(generation_id: str, *, key: str, spec=None, attempts: int = 3, backoff_s=(2, 5),
                      sleep=time.sleep) -> dict | None:
    """Generation document with a usable total_cost, or None (stats may lag a few seconds)."""
    from . import transport
    for number in range(attempts):
        try:
            doc = transport.generation_lookup(generation_id, key=key)
        except ValueError:
            return None
        if transport.cost_from_generation(doc, spec) is not None:
            return doc
        if number + 1 < attempts:
            sleep(backoff_s[min(number, len(backoff_s) - 1)])
    return None


def _atomic(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
