"""OpenRouter adapter for final-batch-next (the final60 money path).

It exposes the names driver.py and report.py use from ``openai_transport``
(ENDPOINT, PRICING, MODEL_ID, payload, request_cost, model_metadata, query,
normalize, compute_cost, load_key) plus ``audit_step``, and step-level helpers for
the driver hooks of the final60 design (section 11.2, amendments A1/A4/A5):

* ``dispatch(root, row, step, body, model, step_dir, *, driver)``        hook 2
* ``recover_pending(root, row, step, step_dir, *, driver)``              hook 7
* ``audit_root(root)``                                                   hook 6 (with report.py)
* ``seal_fields(...)`` / ``summary_fields(model)``                       hooks 1 and summary

Every call goes through ``lean_agent.final60.money.dispatch_guarded`` and the
shared SQLite ``CostLedger``; the root's ``ledger.json`` keeps exactly one settled
item per driver step whose ``cost_usd`` is the sum of its HTTP sub-attempts.
Nothing here reads credentials except ``load_key``/``current_key``, and no value of
a key is ever printed or stored.
"""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from lean_agent import artifacts as a
from lean_agent.final60 import catalog, ledger as cost_ledger, money, transport as t
from lean_agent.final60.contracts import CAP_USD

MODEL_ID = catalog.spec(catalog.DEFAULT_KEY).model_id
ENDPOINT = t.ENDPOINT
PROVIDER = "OpenRouter"
PRICING = catalog.pricing_json()
COST_BASIS = t.COST_BASIS
KEY_ENV = "OPENROUTER_API_KEY"
LEDGER_ENV = "FINAL60_COST_LEDGER"
DEFAULT_LEDGER_NAME = "cost-ledger.sqlite"
BudgetExceeded = cost_ledger.BudgetExceeded
ApiDisabled = money.ApiDisabled
MockOpenRouter = t.MockOpenRouter

_STATE = {"transport": None, "policy": None, "sleep": None}
_LEDGERS = {}


# ---------------------------------------------------------------- openai_transport-compatible names

def load_key(path):
    """OPENROUTER_API_KEY / OPENROUTER from an explicit dotenv file (sk-or- keys only)."""
    return t.load_key(path)


def payload(messages, model):
    return t.payload(messages, catalog.spec_for_model(model))


def request_cost(body):
    """Same shape as openai_transport.request_cost: the worst-case reservation of one request."""
    spec = catalog.spec_for_body(body)
    return t.bound_json(t.request_bound(body, spec), body, spec)


def model_metadata(model=None):
    """Static endpoint evidence (no network); live checks are ``endpoint_check``."""
    spec = catalog.spec_for_model(model) if model is not None else catalog.spec(catalog.DEFAULT_KEY)
    return t.endpoint_evidence(spec)


def current_key():
    """The key from OPENROUTER_API_KEY, or None when a fixture transport is bound."""
    if _STATE["transport"] is not None:
        return None
    value = os.environ.get(KEY_ENV)
    return t.require_key(value)


def query(body, model, step):
    """One POST, no retry (driver signature). Use ``dispatch`` for guarded, ledgered calls."""
    spec = catalog.spec_for_model(model)
    if _STATE["transport"] is not None:
        return _STATE["transport"].query(body, spec, key=None)
    return t.query(body, spec, key=current_key())


def _spec_for_raw(raw):
    model = raw.get("model") if isinstance(raw, dict) else None
    return catalog.spec_for_returned_model(model) or catalog.spec(catalog.DEFAULT_KEY)


def compute_cost(raw):
    return t.compute_cost(raw, _spec_for_raw(raw))


def normalize(raw, bound=None):
    """Single-response normalization. Without a bound an unusable bill stays unknown (None)."""
    spec = _spec_for_raw(raw)
    if bound is not None:
        return t.normalize(raw, spec, bound)
    normalized = json.loads(a.canonical(raw)) if isinstance(raw, dict) else {
        "invalid_provider_response_type": type(raw).__name__}
    try:
        receipt = t.compute_cost(raw, spec)
    except (ValueError, TypeError, KeyError) as exc:
        receipt = {"cost_usd": None, "basis": "unknown", "invoice_verified": False, "error": str(exc)[:300],
                   "provider_response_sha256": a.sha(a.canonical(raw))}
    if not isinstance(normalized.get("usage"), dict):
        normalized["usage"] = {}
    normalized["usage"]["cost"] = receipt["cost_usd"]
    normalized["_cost_receipt"] = receipt
    return normalized


def audit_step(step_dir, ledger_item):
    return t.audit_step(Path(step_dir), ledger_item)


def endpoint_check(model=None):
    """Public endpoint list check for the pinned tag (no key, no charge)."""
    spec = catalog.spec_for_model(model) if model is not None else catalog.spec(catalog.DEFAULT_KEY)
    return t.endpoint_check(spec)


def key_status(key_file):
    """Key validity and remaining credit (free GETs); numbers only, never the key or its label."""
    return t.key_status(key=load_key(key_file))


# ---------------------------------------------------------------- configuration helpers

def use_transport(transport=None, *, policy=None, sleep=None):
    """Bind a fixture transport (``MockOpenRouter``) for dry runs/tests; ``None`` restores HTTP."""
    _STATE.update(transport=transport, policy=policy, sleep=sleep)


def seal_fields(*, cost_ledger_path: str, target_usd: Decimal = CAP_USD) -> dict:
    """Authorization fields for an OpenRouter root (hook 1); ``cost_ledger_path`` may be relative to the root."""
    target = Decimal(str(target_usd))
    if not target.is_finite() or target <= 0 or target > CAP_USD:
        raise ValueError(f"Per-problem target must be in (0, {CAP_USD}]")
    return {"provider": PROVIDER, "api_endpoint": ENDPOINT, "per_problem_target_usd": t.usd(target),
            "last_call_may_overshoot": False, "max_api_parallel": 2, "cost_ledger": str(cost_ledger_path),
            "budget_cost_basis": COST_BASIS, "no_automatic_retries": False,
            "retry_policy": "unbilled 4xx retried at $0 with backoff; lost responses charged their bound"}


def summary_fields(model) -> dict:
    spec = catalog.spec_for_model(model)
    return {"cost_basis": COST_BASIS, "invoice_verified": False, "provider": PROVIDER, "model": spec.model_id,
            "provider_pin": spec.provider, "api_endpoint": ENDPOINT}


def is_openrouter(authorization: dict) -> bool:
    endpoint = authorization.get("api_endpoint")
    return (authorization.get("provider") == PROVIDER and isinstance(endpoint, str)
            and urlparse(endpoint).hostname == t.HOST)


def _authorization(root):
    authorization = a.read(Path(root) / "authorization.json")
    if not is_openrouter(authorization):
        raise ValueError("Run root is not authorized for OpenRouter")
    return authorization


def ledger_path(root, authorization=None) -> Path:
    root = Path(root).resolve()
    if os.environ.get(LEDGER_ENV):
        return Path(os.environ[LEDGER_ENV]).resolve()
    authorization = authorization if authorization is not None else a.read(root / "authorization.json")
    configured = authorization.get("cost_ledger")
    if configured:
        path = Path(configured)
        return (path if path.is_absolute() else root / path).resolve()
    return root / DEFAULT_LEDGER_NAME


def ledger_for_root(root, authorization=None) -> cost_ledger.CostLedger:
    authorization = authorization if authorization is not None else _authorization(root)
    path = ledger_path(root, authorization)
    cap = min(CAP_USD, Decimal(str(authorization.get("per_problem_target_usd", CAP_USD))))
    cached = _LEDGERS.get((path, cap))
    if cached is None:
        cached = _LEDGERS[(path, cap)] = cost_ledger.CostLedger(path, cap_usd=cap)
    return cached


def _problem(row):
    return f"F{row:03}"


def _attempt(row, step):
    return f"F{row:03}-{step:04}"


def _call_options():
    options = {"transport": _STATE["transport"]}
    if _STATE["policy"] is not None:
        options["policy"] = _STATE["policy"]
    if _STATE["sleep"] is not None:
        options["sleep"] = _STATE["sleep"]
    return options


def _void_pending(root, attempt, step_dir, driver, reason):
    """Drop a pending ledger.json item whose step spent nothing (all sub-attempts $0)."""
    with driver.locked(Path(root) / "ledger.lock"):
        ledger = a.read(Path(root) / "ledger.json")
        item = ledger["attempts"].get(attempt)
        if item is None or item.get("status") != "pending":
            return
        del ledger["attempts"][attempt]
        record = {"attempt": attempt, "reason": reason[:500], "at": driver.now(), "cost_usd": "0",
                  "request_sha256": item.get("request_sha256")}
        driver.atomic(Path(step_dir) / "voided.json", record)
        driver.atomic(Path(root) / "ledger.json", ledger)
    with (Path(root) / "voided-attempts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _settle_item(root, attempt, result, driver):
    with driver.locked(Path(root) / "ledger.lock"):
        ledger = a.read(Path(root) / "ledger.json")
        item = ledger["attempts"][attempt]
        if item.get("status") != "pending":
            raise ValueError("Ledger item changed while dispatching: " + attempt)
        item.update(result.ledger_fields(), finished_at=driver.now())
        driver.atomic(Path(root) / "ledger.json", ledger)
    return item


# ---------------------------------------------------------------- driver hooks

def dispatch(root, row, step, body, model, step_dir, *, driver):
    """OpenRouter replacement for ``driver.dispatch`` (hook 2). Returns the normalized response.

    Raises BudgetExceeded or ApiDisabled when the step could not spend anything
    (its pending ledger.json item is then removed), so the run loop breaks to selection.
    """
    root, step_dir = Path(root).resolve(), Path(step_dir)
    driver.verify_frozen(root)
    authorization = _authorization(root)
    spec = catalog.spec_for_model(model)
    bound = t.request_bound(body, spec)
    cost = t.bound_json(bound, body, spec)
    target = min(CAP_USD, Decimal(str(authorization["per_problem_target_usd"])))
    attempt = _attempt(row, step)
    led = ledger_for_root(root, authorization)
    key = current_key()
    money.check_api_enabled(root, ledger=led, problem=_problem(row))
    with driver.api_slot(root), driver.locked(root / "dispatch-locks" / (attempt + ".lock"), blocking=False):
        with driver.locked(root / "ledger.lock"):
            ledger = a.read(root / "ledger.json")
            driver.check_dispatchable(root, ledger)
            config_path = driver.folder(root, row) / "input/config.json"
            cap = a.read(config_path)["limits"].get("cost_cap_usd") if config_path.exists() else None
            if cap is not None and not driver.request_fits_budget(ledger, row, cost, cap):
                raise BudgetExceeded("Request would exceed the strict per-problem budget", reason="cap")
            if driver.problem_spend(ledger, row) + bound.reserved_usd > target:
                raise BudgetExceeded("Request would exceed the sealed per-problem target", reason="cap")
            if attempt in ledger["attempts"]:
                raise ValueError("Attempt already dispatched; refusing duplicate API call")
            ledger["attempts"][attempt] = {
                "row": row, "step": step, "status": "pending", "cost_usd": None, "owner_pid": os.getpid(),
                "request_sha256": a.sha(a.canonical(body)), "started_at": driver.now(),
                "maximum_request_cost_usd": cost["reserved_usd"], "api_endpoint": ENDPOINT,
                "catalog_key": spec.key, "model": spec.model_id, "provider_pin": spec.provider}
            driver.atomic(root / "ledger.json", ledger)
        try:
            result = money.dispatch_guarded(body, spec, ledger=led, problem=_problem(row), attempt_id=attempt,
                                            run_root=root, step_dir=step_dir, key=key, **_call_options())
        except (BudgetExceeded, ApiDisabled) as exc:
            _void_pending(root, attempt, step_dir, driver, f"{type(exc).__name__}: {exc}")
            raise
        _settle_item(root, attempt, result, driver)
    print(json.dumps({"row": row, "step": step, "call_cost_usd": t.usd(result.step_cost_usd),
                      "http_calls": result.http_calls, "settlement_basis": result.settlement_basis,
                      **({"stopped": result.stopped} if result.stopped else {})}), flush=True)
    return result.normalized


def recover_pending(root, row, step, step_dir, *, driver):
    """OpenRouter replacement for ``driver.recover_pending`` (hook 7).

    A pending step left by a crash is finished from its evidence: unsent
    reservations are voided, sent ones settled (at the bound when nothing was
    saved), a saved completion is reused, and otherwise the same body is sent again
    as the next sub-attempt only if the cap admits it. Returns the normalized
    response when the step closed, else None (nothing pending, or voided).
    """
    root, step_dir = Path(root).resolve(), Path(step_dir)
    attempt = _attempt(row, step)
    authorization = _authorization(root)
    led = ledger_for_root(root, authorization)
    with driver.locked(root / "ledger.lock"):
        item = a.read(root / "ledger.json")["attempts"].get(attempt)
    if item is None:
        if money.settle_orphans(led, attempt, step_dir, transport=_STATE["transport"]):
            raise ValueError("SQLite spend without a ledger.json attempt: " + attempt)
        return None
    if item["status"] == "settled":
        errors = audit_step(step_dir, item)
        if errors:
            raise ValueError(f"{attempt}: settled step evidence is inconsistent: " + "; ".join(errors[:3]))
        return None
    if item["status"] != "pending":
        raise ValueError(f"{attempt}: unexpected ledger status {item['status']}")
    with driver.api_slot(root), driver.locked(root / "dispatch-locks" / (attempt + ".lock"), blocking=False):
        if not (step_dir / "request.json").exists():
            if money.settle_orphans(led, attempt, step_dir, transport=_STATE["transport"]):
                raise ValueError("Charged sub-attempt without saved request evidence: " + attempt)
            _void_pending(root, attempt, step_dir, driver, "crashed before the first reservation was sent")
            return None
        body = a.read(step_dir / "request.json")
        if a.sha(a.canonical(body)) != item["request_sha256"]:
            raise ValueError("Saved request differs from the ledger reservation: " + attempt)
        spec = catalog.spec_for_body(body)
        try:
            key = current_key()
        except ValueError:
            key = None    # settle-only: dispatch_guarded refuses to send without a key
        try:
            if key is None and _STATE["transport"] is None:
                spent = money.settle_orphans(led, attempt, step_dir)
                raise ValueError(f"{attempt}: pending step needs {KEY_ENV} to finish (spent so far {t.usd(spent)})")
            result = money.dispatch_guarded(body, spec, ledger=led, problem=_problem(row), attempt_id=attempt,
                                            run_root=root, step_dir=step_dir, key=key, **_call_options())
        except (BudgetExceeded, ApiDisabled) as exc:
            _void_pending(root, attempt, step_dir, driver, f"recovery: {type(exc).__name__}: {exc}")
            return None
        _settle_item(root, attempt, result, driver)
    return result.normalized


def audit_root(root) -> list[str]:
    """Every OpenRouter step of a root re-audited from evidence, plus the SQLite mirror check."""
    root = Path(root).resolve()
    authorization = _authorization(root)
    ledger = a.read(root / "ledger.json")
    errors = []
    for attempt, item in ledger["attempts"].items():
        step_dir = root / "problems" / f"F{item['row']:03}" / "steps" / f"{item['step']:04}"
        errors.extend(f"{attempt}: {message}" for message in audit_step(step_dir, item))
    path = ledger_path(root, authorization)
    if path.exists():
        errors.extend(ledger_for_root(root, authorization).reconcile(root, ledger))
    else:
        errors.append("SQLite cost ledger missing: " + str(path))
    return errors
