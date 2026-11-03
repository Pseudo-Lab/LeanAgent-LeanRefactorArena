"""Guarded OpenRouter dispatch: bound -> reserve -> evidence -> send -> settle.

Every HTTP call is reserved in the shared ``CostLedger`` before it is sent, so the
per-problem cap holds with retries and discarded responses included. One driver
step (``F017-0005``) can need several HTTP sub-attempts (``F017-0005#r0``, ``#r1``):

* unbilled refusals (HTTP 400/401/402/403/404/429) settle at $0 and are retried
  with backoff (15/30/60/120/240 s, then a 10-minute stall; after 3 stalls the
  problem's API is disabled). 401/402 disable the API globally at once.
* a lost response (timeout, connection reset, 5xx, unreadable body) is settled
  exactly through the generation API when a generation id is known, else at its
  full bound, and the same body is sent again only if the cap still admits it
  (at most 3 lost sub-attempts per step, then the step closes as lost).

A step is resumable after a crash at any point: an unsent reservation is voided, a
sent one is settled from its saved evidence (at its bound if nothing was saved),
and a saved successful response is reused without a second HTTP call.

Evidence layout under the step directory::

    request.json  cost-bound.json  endpoint.json      written after the first reservation
    http/rN/{sent,provider-response,generation,receipt,void,recovered}.json
    provider-response.json  response.json  cost-receipt.json   written when the step closes

``response.json`` carries ``usage.cost`` = the step total (all sub-attempts), so the
harness state, the root ledger.json item (one settled item per step, amendment A4)
and report.py all agree.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
import fcntl
import os
from pathlib import Path
import time

from lean_agent.artifacts import canonical, read, sha

from . import transport as t
from .contracts import Bound, ModelSpec, Receipt
from .ledger import BudgetExceeded, CostLedger, _atomic, lookup_generation, receipt_from_record, root_key

GLOBAL_MARKER = "api-disabled.json"        # <run-dir>/api-disabled.json: no new LLM work anywhere
ROW_MARKER = "api-disabled-row.json"       # <row root>/api-disabled-row.json: no new LLM work for that row
FROZEN_MARKER = "api-frozen.json"          # <row root>/api-frozen.json: a bound violation froze the row's API
GLOBAL_MARKER_ENV = "FINAL60_API_DISABLED_PATH"


class ApiDisabled(RuntimeError):
    """No further OpenRouter calls: scope 'global' (401/402) or 'row' (subclasses below)."""

    def __init__(self, scope: str, reason: str, *, marker: Path | None = None):
        super().__init__(f"OpenRouter API disabled ({scope}): {reason}")
        self.scope, self.reason, self.marker = scope, reason, marker


class RowApiDisabled(ApiDisabled):
    """This problem only: repeated unbilled refusals (3 stalls) or its api_disabled flag."""

    def __init__(self, reason: str, *, marker: Path | None = None):
        super().__init__("row", reason, marker=marker)


class RowApiFrozen(ApiDisabled):
    """This problem only: a response broke its cost or token bound (frozen flag)."""

    def __init__(self, reason: str, *, marker: Path | None = None):
        super().__init__("row", reason, marker=marker)


def _disabled_error(scope: str, reason: str, marker: Path | None = None) -> ApiDisabled:
    if scope == "global":
        return ApiDisabled("global", reason, marker=marker)
    if (marker is not None and Path(marker).name == FROZEN_MARKER) or "frozen" in reason:
        return RowApiFrozen(reason, marker=marker)
    return RowApiDisabled(reason, marker=marker)


@dataclass(frozen=True)
class RetryPolicy:
    max_unbilled_retries: int = 5
    backoff_s: tuple = (15, 30, 60, 120, 240)
    stall_s: int = 600
    max_stalls: int = 3
    max_lost: int = 3
    lost_backoff_s: tuple = (60, 180)
    generation_lookups: int = 3
    generation_backoff_s: tuple = (2, 5)
    max_retry_after_s: int = 600


@dataclass
class DispatchResult:
    raw: dict
    normalized: dict
    receipt: Receipt
    bound: Bound
    http_calls: int
    sub_attempts: list = field(default_factory=list)
    step_cost_usd: Decimal = Decimal(0)
    settlement_basis: str = ""
    bound_violated: bool = False
    stopped: str | None = None   # None | budget | api_disabled_global | api_disabled_row | lost_limit
    lost: bool = False           # True when no usable completion was obtained

    def ledger_fields(self) -> dict:
        """Fields for the root ledger.json item of this step (status always settled).

        Endpoint, provider and cost basis come from the step's own receipt, so an
        OpenAI-direct development step records api.openai.com / "OpenAI direct".
        """
        receipt = self.normalized["_cost_receipt"]
        return {"status": "settled", "cost_usd": t.usd(self.step_cost_usd), "response_id": self.normalized["id"],
                "sub_attempts": list(self.sub_attempts), "settlement_basis": self.settlement_basis,
                "bound_violated": self.bound_violated, "api_endpoint": receipt["api_endpoint"],
                "provider": receipt["provider"],
                "catalog_key": receipt["catalog_key"], "model": receipt["model"],
                "returned_model": receipt["returned_model"], "returned_provider": receipt["returned_provider"],
                "cost_basis": receipt["cost_basis"], "invoice_verified": False, "http_calls": self.http_calls,
                "provider_response_sha256": receipt["provider_response_sha256"], "lost": self.lost,
                "stopped": self.stopped}


@dataclass
class _Sub:
    record: dict
    raw: dict
    generation: dict | None


def default_global_marker(ledger: CostLedger, run_root: Path) -> Path:
    if os.environ.get(GLOBAL_MARKER_ENV):
        return Path(os.environ[GLOBAL_MARKER_ENV])
    if ledger.path is not None:
        return ledger.path.parent / GLOBAL_MARKER
    return Path(run_root) / GLOBAL_MARKER


def disabled(run_root: Path, *, global_marker: Path) -> tuple[str, Path] | None:
    if Path(global_marker).exists():
        return "global", Path(global_marker)
    for name in (ROW_MARKER, FROZEN_MARKER):
        if (Path(run_root) / name).exists():
            return "row", Path(run_root) / name
    return None


def check_api_enabled(run_root: Path, *, ledger: CostLedger, problem: str | None = None,
                      global_marker: Path | None = None) -> None:
    """Raise ApiDisabled when a global/row marker or a ledger flag forbids new calls."""
    marker = Path(global_marker) if global_marker is not None else default_global_marker(ledger, Path(run_root))
    found = disabled(Path(run_root), global_marker=marker)
    if found:
        raise _disabled_error(found[0], "marker " + found[1].name, found[1])
    if problem is not None:
        flags = ledger.flags(problem)
        if flags:
            name = sorted(flags)[0]
            raise _disabled_error("row", f"ledger flag {name}: {flags[name]}")


@contextmanager
def _attempt_lock(run_root: Path, attempt_id: str):
    path = Path(run_root) / "dispatch-locks" / (attempt_id + ".money.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Step is being dispatched by another live process: " + attempt_id) from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _wire(wire):
    """The provider module a step is sent through: OpenRouter unless a wire is given
    (``lean_agent.final60.openai_direct`` for development runs)."""
    return t if wire is None else wire


def _query_function(transport, wire=None):
    if transport is None:
        return _wire(wire).query
    return transport.query if hasattr(transport, "query") else transport


def _lookup_function(transport, key, policy, spec, sleep, wire=None):
    """generation_id -> generation document with a usable total, or None. A fixture
    transport is never allowed to reach the network: it supplies its own lookup or none.
    A wire without a generation API (OpenAI direct) settles lost responses at the bound."""
    if transport is not None:
        own = getattr(transport, "generation_lookup", None)
        if own is None:
            return None
        return lambda generation_id: own(generation_id, key=key)
    if not key or not getattr(_wire(wire), "GENERATION_API", True):
        return None
    return lambda generation_id: lookup_generation(generation_id, key=key, spec=spec,
                                                   attempts=policy.generation_lookups,
                                                   backoff_s=policy.generation_backoff_s, sleep=sleep)


def _write_request_evidence(step_dir: Path, body: dict, bound: Bound, spec: ModelSpec, wire=None) -> None:
    wire = _wire(wire)
    expected = {"request.json": body, "cost-bound.json": wire.bound_json(bound, body, spec),
                "endpoint.json": wire.endpoint_evidence(spec)}
    for name, value in expected.items():
        path = step_dir / name
        if path.exists():
            if read(path) != value:
                raise ValueError(f"Saved {name} differs from this dispatch; refusing to mix requests")
        else:
            _atomic(path, value)


def _load_subs(ledger, attempt_id, step_dir, request_sha, lookup, sleep, run_root=None, wire=None):
    """Existing sub-attempts of this step (this root only), recovering any left open by a crash.

    $0 sub-attempts whose evidence a caller archived (an unsent/unbilled step that was
    released and is now dispatched again) are skipped: they cost nothing and are no
    longer part of this step's evidence.
    """
    subs = []
    for row in ledger.sub_attempts(attempt_id):
        if run_root is not None and root_key(row["run_root"]) != root_key(run_root):
            continue
        folder = step_dir / "http" / f"r{row['sub_index']}"
        if row["status"] in ("void", "unbilled") and not (folder / "provider-response.json").exists():
            continue
        if row["request_sha256"] != request_sha:
            raise ValueError("Saved sub-attempt belongs to a different request: " + row["attempt_id"])
        if row["status"] in ("reserved", "sent"):
            ledger.recover(row["attempt_id"], step_dir=step_dir, lookup=lookup, sleep=sleep, wire=_wire(wire))
            row = ledger.get(row["attempt_id"])
        if row["status"] == "void":
            continue
        raw = read(folder / "provider-response.json")
        generation = read(folder / "generation.json") if (folder / "generation.json").exists() else None
        subs.append(_Sub(read(folder / "receipt.json"), raw, generation))
    return subs


def _trailing(subs, outcome):
    count = 0
    for sub in reversed(subs):
        if sub.record["outcome"] != outcome:
            break
        count += 1
    return count


def _spend(subs) -> Decimal:
    return sum((Decimal(sub.record["cost_usd"]) for sub in subs), Decimal(0))


def _finish(subs, *, spec, bound, attempt_id, step_dir, http_calls, stopped=None, wire=None) -> DispatchResult:
    wire = _wire(wire)
    final = subs[-1]
    normalized = wire.normalize(final.raw, spec, bound, sub_attempts=[sub.record for sub in subs[:-1]],
                                attempt_id=attempt_id, final_id=final.record["id"], generation=final.generation)
    receipt_doc = normalized["_cost_receipt"]
    _atomic(step_dir / "provider-response.json", final.raw)
    _atomic(step_dir / "response.json", normalized)
    _atomic(step_dir / "cost-receipt.json", receipt_doc)
    ok = final.record["outcome"] == "ok"
    total = Decimal(receipt_doc["step_cost_usd"])
    receipt = Receipt(attempt_id=attempt_id, status="settled" if ok else "lost_conservative", cost_usd=total,
                      generation_id=final.record["generation_id"] if ok else None,
                      model=final.record["returned_model"], provider=final.record["returned_provider"],
                      api_endpoint=wire.ENDPOINT, basis=receipt_doc["settlement_basis"],
                      http_status=final.record["http_status"])
    return DispatchResult(raw=final.raw, normalized=normalized, receipt=receipt, bound=bound, http_calls=http_calls,
                          sub_attempts=receipt_doc["sub_attempts"], step_cost_usd=total,
                          settlement_basis=receipt_doc["settlement_basis"],
                          bound_violated=receipt_doc["bound_violated"], stopped=stopped, lost=not ok)


def dispatch_guarded(body: dict, spec: ModelSpec, *, ledger: CostLedger, problem: str, attempt_id: str,
                     run_root: Path, step_dir: Path, key: str | None, transport=None,
                     max_unbilled_retries: int = 5, policy: RetryPolicy | None = None, sleep=time.sleep,
                     global_marker: Path | None = None, wire=None) -> DispatchResult:
    """Send one driver step through the cap; see the module docstring for the order.

    Raises BudgetExceeded / ApiDisabled only when this step has spent nothing (the
    caller then voids its pending ledger.json item). Once a step has spend, it
    always returns a DispatchResult (``lost``/``stopped`` say why it has no content).

    ``wire`` is the provider module (OpenRouter by default; ``openai_direct`` for a
    development run). Every reservation, evidence file and receipt records that
    wire's endpoint and provider, and the same cap applies.
    """
    wire = _wire(wire)
    policy = policy or RetryPolicy(max_unbilled_retries=max_unbilled_retries)
    run_root, step_dir = Path(run_root).resolve(), Path(step_dir)
    bound = wire.request_bound(body, spec)       # 1. bound (ValueError before anything else)
    request_sha = sha(canonical(body))
    if transport is None:
        wire.require_key(key)                     # never mark a call sent without a usable key
    marker = Path(global_marker) if global_marker is not None else default_global_marker(ledger, run_root)
    query = _query_function(transport, wire)
    lookup = _lookup_function(transport, key, policy, spec, sleep, wire)
    window = policy.max_unbilled_retries + 1
    with _attempt_lock(run_root, attempt_id):
        subs = _load_subs(ledger, attempt_id, step_dir, request_sha, lookup, sleep, run_root=run_root, wire=wire)
        http_calls = 0

        def close(stopped=None):
            return _finish(subs, spec=spec, bound=bound, attempt_id=attempt_id, step_dir=step_dir,
                           http_calls=http_calls, stopped=stopped, wire=wire)

        if subs and subs[-1].record["outcome"] == "ok":
            return close()                         # resumed after a crash: reuse, never resend
        unbilled, lost = _trailing(subs, "unbilled"), _trailing(subs, "lost")
        if lost >= policy.max_lost:
            return close("lost_limit")             # resumed after the last allowed lost sub-attempt
        while True:
            found = disabled(run_root, global_marker=marker)
            if found:
                if _spend(subs):
                    return close("api_disabled_" + found[0])
                raise _disabled_error(found[0], "marker " + found[1].name, found[1])
            index = ledger.next_index(attempt_id)
            sub_id = f"{attempt_id}#r{index}"
            try:                                    # 2. reserve (nothing written or sent on refusal)
                ledger.reserve(problem=problem, attempt_id=sub_id, bound=bound, run_root=str(run_root),
                               model=spec.model_id, provider=spec.provider, api_endpoint=wire.ENDPOINT,
                               request_sha256=request_sha, step_dir=str(step_dir))
            except BudgetExceeded as exc:
                stopped = "budget" if exc.reason == "cap" else "api_disabled_row"
                if _spend(subs):
                    return close(stopped)
                if exc.reason != "cap":
                    raise _disabled_error("row", f"ledger flag {exc.reason}: {exc}") from exc
                raise
            _write_request_evidence(step_dir, body, bound, spec, wire)   # 3. request evidence
            folder = step_dir / "http" / f"r{index}"
            ledger.mark_sent(sub_id)                                  # 4. durable before the call
            _atomic(folder / "sent.json", {"attempt_id": sub_id, "sent_at": time.time(), "pid": os.getpid(),
                                           "api_endpoint": wire.ENDPOINT, "provider": wire.PROVIDER})
            raw = wire.scrub(query(body, spec, key=key), key, strict=False)   # 5. one HTTP call
            if wire.classify(raw) != "ok":
                raw = wire.scrub(raw, key)
            http_calls += 1
            _atomic(folder / "provider-response.json", raw)           # 6. raw evidence
            generation = None
            if wire.classify(raw) == "lost" and lookup is not None and wire.generation_id_of(raw):
                generation = lookup(wire.generation_id_of(raw))
                if generation is not None:
                    _atomic(folder / "generation.json", generation)
            record = {"id": sub_id, **wire.sub_attempt_cost(raw, spec, bound, generation)}
            _atomic(folder / "receipt.json", record)
            ledger.settle(receipt_from_record(record, wire.ENDPOINT))  # 7. settle the sub-attempt
            subs.append(_Sub(record, raw, generation))
            if record["bound_violated"]:
                ledger.flag(problem, "frozen", "cost or token bound violated by " + sub_id)
                _atomic(run_root / FROZEN_MARKER, {"attempt_id": sub_id, "at": time.time(),
                                                   "reason": "cost or token bound violated"})
            outcome = record["outcome"]
            if outcome == "ok":
                return close()                                         # 8. normalize, write, return
            if outcome == "unbilled":
                lost = 0
                status = record["http_status"]
                if status in wire.DISABLE_HTTP:
                    _atomic(marker, {"at": time.time(), "attempt_id": sub_id, "http_status": status,
                                     "provider": wire.PROVIDER,
                                     "reason": wire.PROVIDER + " refused the key or credits; no further LLM calls"})
                    if _spend(subs):
                        return close("api_disabled_global")
                    raise ApiDisabled("global", f"HTTP {status}", marker=marker)
                unbilled += 1
                if unbilled >= window * policy.max_stalls:
                    reason = f"{unbilled} consecutive unbilled HTTP refusals (last {status})"
                    ledger.flag(problem, "api_disabled", reason)
                    _atomic(run_root / ROW_MARKER, {"at": time.time(), "attempt_id": sub_id, "reason": reason})
                    if _spend(subs):
                        return close("api_disabled_row")
                    raise RowApiDisabled(reason, marker=run_root / ROW_MARKER)
                if unbilled % window == 0:
                    delay = policy.stall_s
                else:
                    delay = policy.backoff_s[min(unbilled % window, len(policy.backoff_s)) - 1]
                if raw.get("retry_after_s"):
                    delay = max(delay, min(int(raw["retry_after_s"]), policy.max_retry_after_s))
                sleep(delay)
                continue
            unbilled = 0                                               # lost: charged; retry if it fits
            lost += 1
            if lost >= policy.max_lost:
                return close("lost_limit")
            sleep(policy.lost_backoff_s[min(lost, len(policy.lost_backoff_s)) - 1])


def close_unfinished(body: dict, spec: ModelSpec, *, ledger: CostLedger, problem: str, attempt_id: str,
                     run_root: Path, step_dir: Path, key: str | None = None, transport=None,
                     sleep=time.sleep, wire=None) -> DispatchResult | None:
    """No-resend recovery: settle the step's open sub-attempts from evidence and close it.

    Returns the closed step (a saved completion is reused; otherwise a lost step with
    its exact or bound charge), written in the same audited shape as dispatch_guarded,
    or None when nothing billable was ever sent (the caller releases the pending item).
    """
    wire = _wire(wire)
    run_root, step_dir = Path(run_root).resolve(), Path(step_dir)
    bound = wire.request_bound(body, spec)
    lookup = _lookup_function(transport, key, RetryPolicy(), spec, sleep, wire)
    with _attempt_lock(run_root, attempt_id):
        subs = _load_subs(ledger, attempt_id, step_dir, sha(canonical(body)), lookup, sleep, run_root=run_root,
                          wire=wire)
        if not subs or all(sub.record["outcome"] == "unbilled" for sub in subs):
            return None
        return _finish(subs, spec=spec, bound=bound, attempt_id=attempt_id, step_dir=step_dir, http_calls=0,
                       stopped=None if subs[-1].record["outcome"] == "ok" else "recovered_no_resend", wire=wire)


def settle_orphans(ledger: CostLedger, attempt_id: str, step_dir: Path, *, key: str | None = None,
                   transport=None, sleep=time.sleep, wire=None) -> Decimal:
    """Settle every open sub-attempt of a step without sending anything; returns the step's spend."""
    spent = Decimal(0)
    wire = _wire(wire)
    lookup = _lookup_function(transport, key, RetryPolicy(), None, sleep, wire)
    for row in ledger.sub_attempts(attempt_id):
        if row["status"] in ("reserved", "sent"):
            ledger.recover(row["attempt_id"], step_dir=Path(step_dir), lookup=lookup, sleep=sleep, wire=wire)
            row = ledger.get(row["attempt_id"])
        if row["status"] in ("settled", "lost_conservative"):
            spent += Decimal(row["cost_usd"])
    return spent
