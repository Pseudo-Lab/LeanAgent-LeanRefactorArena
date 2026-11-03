"""final60 shared contracts. Copy byte-identically into every component branch."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

SCHEMA = "final60-v1"
CAP_USD = Decimal("2.99")                      # per-problem hard cap, every call counted
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
RowStatus = Literal["waiting_env", "ready", "prepared", "preflighted", "exploring", "salvage",
                    "golfing", "validating", "done", "fallback"]

@dataclass(frozen=True)
class ModelSpec:
    key: str                     # catalog key: gen_primary | gen_alt | gen_alt2 | cheap
    model_id: str                # exact OpenRouter id
    provider: str                # OpenRouter provider tag, pinned (only=[tag], allow_fallbacks=False)
    prompt_usd_per_mtok: Decimal
    completion_usd_per_mtok: Decimal
    cache_read_usd_per_mtok: Decimal
    cache_write_usd_per_mtok: Decimal
    max_tokens: int              # completion cap incl. reasoning
    reasoning_effort: str | None
    timeout_s: int = 900
    seed: int | None = 42

@dataclass(frozen=True)
class Bound:
    input_token_bound: int
    output_token_bound: int
    reserved_usd: Decimal
    basis: str

@dataclass(frozen=True)
class Receipt:
    attempt_id: str
    status: Literal["settled", "unbilled", "lost_conservative", "void"]
    cost_usd: Decimal
    generation_id: str | None
    model: str | None            # returned model
    provider: str | None         # returned provider name
    api_endpoint: str            # always OPENROUTER_ENDPOINT for paid calls
    basis: str
    http_status: int | None = None

@dataclass(frozen=True)
class Route:
    row: int
    name: str
    source: str
    problem_type: str            # kernel-decide-tiny | short-tactic | structural-induction | algebra-analysis-long | competition
    skip_llm: bool
    portfolio: dict              # driver portfolio settings (portfolio.validate must accept)
    role_models: dict            # {"scout-c": "gen_alt"}; {} = gen_primary for all roles
    hints: tuple[str, ...]
    hint_sources: tuple[str, ...]
    golf: dict                   # {"original_compiles": 8, "top_k": 4, "max_compiles_best": 18, "max_compiles_other": 6, "minutes": 20}
    priority: float              # larger = schedule earlier
    wallclock_budget_s: int
    expected_score: float | None = None   # estimate, reports only

@dataclass(frozen=True)
class EvalResult:
    valid: bool                  # all requested envs compiled, policy + axioms ok
    tokens: int | None
    raw_heartbeats: int | None   # primary env median raw HB (None if not measured)
    envs: dict                   # env_id -> bool
    error_kind: str | None       # validation | compile | timeout | axioms | environment
    message: str                 # Lean error tail, <= 4000 chars
    evidence_dir: str

@dataclass(frozen=True)
class Candidate:
    code: str
    sha256: str                  # sha256 of code (utf-8, exact)
    origin: Literal["original", "model", "golf"]
    parent_sha256: str | None
    label: str                   # e.g. "c017", "golf:G1:c017", "c000"
    screen: EvalResult | None = None

@dataclass(frozen=True)
class Selection:
    candidate: Candidate
    validated: EvalResult        # all versions + fresh 3x primary
    score: float                 # official formula, local estimate
    beat_original: bool
    considered: tuple[str, ...]  # labels validated, in order

@dataclass
class RowState:                  # supervisor/rows/F0NN.json
    row: int
    status: RowStatus
    attempts: int = 0            # worker (re)starts
    last_error: str | None = None
    selected_sha256: str | None = None
    score_estimate: float | None = None
    spent_usd: str = "0"
    updated_at: str = ""
    history: list = field(default_factory=list)
