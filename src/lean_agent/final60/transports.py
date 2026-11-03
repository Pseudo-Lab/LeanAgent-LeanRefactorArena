"""Transport registry for final60: ``openrouter`` (the entry), ``openai`` (development
only) and ``mock`` (OpenRouter wire with a fixture, never submitted).

The name is a sealed run setting (``authorization.json`` ``transport``) and a CLI flag
(``--transport``, default ``openrouter``). ``profile_for_authorization`` recovers it
from a sealed root and refuses anything else, ``is_submittable`` is the single rule
assembly and the provenance checks apply, and ``seal_fields`` writes the sealed
provider / endpoint / transport fields for a root.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from importlib import import_module
from urllib.parse import urlparse

from .contracts import CAP_USD, OPENROUTER_ENDPOINT

DEFAULT = "openrouter"
NAMES = ("openrouter", "openai", "mock")
FIELD = "transport"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"


@dataclass(frozen=True)
class Profile:
    name: str
    provider: str
    api_endpoint: str
    host: str
    module: str          # wire module (lean_agent.final60.transport | .openai_direct)
    submittable: bool
    dry_run: bool
    key_env: str
    description: str

    @property
    def wire(self):
        return import_module(self.module)

    def spec_for_model(self, model: dict):
        return self.wire.spec_for_model(model)

    def spec_for_body(self, body: dict):
        return self.wire.spec_for_body(body)

    def driver_model(self, **options) -> dict:
        """The frozen ``config["model"]`` dict rows of this transport use."""
        if self.name == "openai":
            return self.wire.driver_model(**options)
        from . import catalog
        return catalog.driver_model(**options)

    def pricing_json(self) -> dict:
        if self.name == "openai":
            return self.wire.pricing_json()
        from . import catalog
        return catalog.pricing_json()

    def seal_fields(self, *, cost_ledger_path: str, target_usd=CAP_USD, prior_usd=Decimal(0)) -> dict:
        """Sealed authorization fields: provider, endpoint, transport name, submittability."""
        target, prior = Decimal(str(target_usd)), Decimal(str(prior_usd))
        if not target.is_finite() or target <= 0 or target > CAP_USD:
            raise ValueError(f"Per-problem target must be in (0, {CAP_USD}]")
        if not prior.is_finite() or prior < 0 or prior >= target:
            raise ValueError("Prior spend must be nonnegative and below the target")
        wire = self.wire
        fields = {"provider": self.provider, "api_endpoint": self.api_endpoint, FIELD: self.name,
                  "submittable": self.submittable, "dry_run": self.dry_run,
                  "per_problem_target_usd": wire.usd(target), "last_call_may_overshoot": False,
                  "max_api_parallel": 2, "cost_ledger": str(cost_ledger_path), "budget_cost_basis": wire.COST_BASIS,
                  "no_automatic_retries": False,
                  "retry_policy": "unbilled 4xx retried at $0 with backoff; lost responses charged their bound"}
        if prior:
            fields["prior_cost_usd"] = wire.usd(prior)
        if not self.submittable:
            fields["development_only"] = ("proofs, candidates and prompts of this root are never submitted and never "
                                          "seed, carry into or appear in an OpenRouter run")
        return fields


PROFILES = {
    "openrouter": Profile("openrouter", "OpenRouter", OPENROUTER_ENDPOINT, "openrouter.ai",
                          "lean_agent.final60.transport", True, False, "OPENROUTER_API_KEY",
                          "the competition entry: pinned OpenRouter provider, SQLite cost ledger, $2.99 cap"),
    "openai": Profile("openai", "OpenAI direct", OPENAI_ENDPOINT, "api.openai.com",
                      "lean_agent.final60.openai_direct", False, False, "OPENAI_API_KEY",
                      "development only: direct gpt-6.1-sol with the same cap and ledger; refused at submission"),
    "mock": Profile("mock", "OpenRouter", OPENROUTER_ENDPOINT, "openrouter.ai",
                    "lean_agent.final60.transport", False, True, "OPENROUTER_API_KEY",
                    "dry run: OpenRouter wire bound to MockOpenRouter; no network, no spend, never submitted"),
}


def profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError("Unknown final60 transport: " + str(name) + " (expected one of " + ", ".join(NAMES) + ")") from None


def _host(endpoint) -> str | None:
    return urlparse(endpoint).hostname if isinstance(endpoint, str) else None


def profile_for_authorization(authorization: dict) -> Profile:
    """The sealed transport of a root. Legacy OpenAI-direct roots (no ``transport``
    field) and roots whose provider/endpoint disagree with the name are refused."""
    if not isinstance(authorization, dict):
        raise ValueError("Missing sealed authorization")
    name = authorization.get(FIELD)
    if name is None:
        if authorization.get("provider") == "OpenRouter" and _host(authorization.get("api_endpoint")) == "openrouter.ai":
            name = "mock" if authorization.get("dry_run") else "openrouter"
        else:
            raise ValueError("Run root is not authorized for a final60 transport "
                             "(legacy OpenAI-direct roots carry no sealed transport)")
    found = profile(name)
    if (authorization.get("provider") != found.provider or _host(authorization.get("api_endpoint")) != found.host
            or (found.name == "mock" and not authorization.get("dry_run"))
            or (found.name == "openrouter" and authorization.get("dry_run"))):
        raise ValueError("Sealed provider/endpoint disagree with transport " + found.name)
    return found


def profile_for_model(model: dict) -> Profile:
    """Transport implied by a frozen model dict (the OpenRouter wire for mock runs too)."""
    backend = model.get("backend") if isinstance(model, dict) else None
    if backend == "openrouter":
        return PROFILES["openrouter"]
    if backend == "openai":
        return PROFILES["openai"]
    raise ValueError("Model backend selects no final60 transport: " + str(backend))


def is_submittable(authorization: dict) -> tuple[bool, str | None]:
    """(True, None) only for a real OpenRouter root; otherwise the reason it is refused."""
    try:
        found = profile_for_authorization(authorization)
    except ValueError as exc:
        return False, str(exc)
    if found.submittable and not authorization.get("dry_run") and authorization.get("submittable", True):
        return True, None
    return False, f"{found.provider} transport '{found.name}' is development data, never submitted"


def add_argument(parser, *, default: str = DEFAULT, dest: str = FIELD):
    """``--transport openrouter|openai|mock`` on an argparse parser (default openrouter)."""
    return parser.add_argument("--" + FIELD, dest=dest, choices=NAMES, default=default,
                               help="model transport: openrouter (entry, default), openai (OpenAI direct, "
                                    "development only, never submitted) or mock (dry run)")
