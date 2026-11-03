"""final60 orchestrator: run layout, options, coverage, routes, plan and status.

Nothing here calls a model or Lean. The row worker (rowworker.py) drives one
OpenRouter run root per row through experiments/final-batch-next/driver.py; the
supervisor (supervisor.py) schedules row workers; assemble.py builds the
60-row submission. Machine paths come only from flags or FINAL60_* variables.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from .contracts import CAP_USD, SCHEMA, Route, RowState

REPO = Path(__file__).resolve().parents[3]
DRIVER_DIR = REPO / "experiments" / "final-batch-next"
DATASET_SHA = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"
DEFAULT_DATASET = REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"
DEFAULT_DEADLINE = "2026-11-04T20:59:59+09:00"
TERMINAL = ("done", "fallback", "published")
DEFAULT_MODEL = {"backend": "openrouter", "id": "openai/gpt-6.1-sol", "provider": "openai",
                 "reasoning_effort": "high", "max_tokens": 8192, "timeout_seconds": 900, "seed": 42,
                 "max_price": {"prompt": 2, "completion": 10}, "catalog_key": "gen_primary"}
DEFAULT_GOLF = {"original_compiles": 4, "top_k": 2, "max_compiles_best": 8, "max_compiles_other": 4, "minutes": 20}
DEFAULT_PORTFOLIO = {"scout_evaluations": 6, "merger_evaluations": 22, "progress_guard": "bounded-v1",
                     "merger_until_budget": True}
# Repository folders that hold proofs produced outside OpenRouter (A3). More come from --non-openrouter.
REPO_NON_OPENROUTER = ("dashboard/public/data", "solutions", "submissions", "experiments/assigned-route-results")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_text(text):
    return sha_bytes(text.encode("utf-8"))


def normalized_sha(text):
    """PR #70 proof identity: trailing spaces and outer blank lines ignored."""
    return sha_text("\n".join(line.rstrip() for line in text.strip("\n").splitlines()))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_json(path, value):
    atomic_bytes(path, json_bytes(value))


def parse_deadline(text):
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError("Deadline needs an explicit UTC offset, e.g. 2026-11-04T20:59:59+09:00")
    return value


def parse_rows(text):
    """'1-60', '11-30,41', '5' -> sorted unique rows in 1..60."""
    rows = set()
    for part in str(text).replace(" ", "").split(","):
        if not part:
            continue
        low, _, high = part.partition("-")
        start, stop = int(low), int(high or low)
        if not 1 <= start <= stop <= 60:
            raise ValueError("Rows must lie in 1..60: " + part)
        rows.update(range(start, stop + 1))
    if not rows:
        raise ValueError("No rows selected")
    return sorted(rows)


@dataclass
class RunOptions:
    run_dir: Path
    key_file: Path | None = None
    rows: list = field(default_factory=lambda: list(range(1, 61)))
    max_rows: int = 8
    compiler_slots: int = 6
    deadline: datetime = field(default_factory=lambda: parse_deadline(DEFAULT_DEADLINE))
    soft_stop_min: int = 100
    diversity: bool = False
    dry_run: bool = False
    dataset: Path | None = None
    prepared_repo: Path | None = None
    non_openrouter: list = field(default_factory=list)
    cap_usd: Decimal = CAP_USD
    prior_costs: dict = field(default_factory=dict)      # row -> Decimal spend outside the row root (A11)
    exploration_minutes: int = 75
    mem_start_gib: float = 10.0
    mem_reserve_gib: float = 6.0
    gib_per_compile: float = 3.5
    poll_seconds: float = 15.0
    coverage_seconds: float = 120.0
    python: str = sys.executable

    def deadline_epoch(self):
        return self.deadline.timestamp()


class Layout:
    """<run-dir>/rows/F0NN is a normal final-batch-next root holding exactly one row."""

    def __init__(self, run_dir):
        self.run_dir = Path(run_dir).resolve()

    def row_root(self, row):
        return self.run_dir / "rows" / f"F{row:03}"

    def row_folder(self, row):
        return self.row_root(row) / "problems" / f"F{row:03}"

    @property
    def supervisor(self):
        return self.run_dir / "supervisor"

    def state_path(self, row):
        return self.supervisor / "rows" / f"F{row:03}.json"

    def control_path(self, row):
        return self.supervisor / "rows" / f"F{row:03}.supervisor.json"

    def worker_path(self, row):
        return self.row_root(row) / "worker-state.json"

    def log_path(self, row):
        return self.supervisor / "logs" / f"F{row:03}.log"

    @property
    def sqlite(self):
        return self.run_dir / "final60.sqlite"

    @property
    def plan(self):
        return self.run_dir / "plan.json"

    @property
    def non_openrouter(self):
        return self.run_dir / "non-openrouter.jsonl"

    @property
    def options(self):
        return self.run_dir / "run-options.json"


def load_rowstate(layout, row):
    path = layout.state_path(row)
    if path.exists():
        value = read_json(path)
        names = {item.name for item in dataclasses.fields(RowState)}
        return RowState(**{key: value[key] for key in value if key in names})
    return RowState(row=row, status="waiting_env", updated_at=now_iso())


def save_rowstate(layout, state, event=None):
    state.updated_at = now_iso()
    if event:
        state.history.append({"at": state.updated_at, **event})
        del state.history[:-50]
    atomic_json(layout.state_path(state.row), dataclasses.asdict(state))
    return state


def driver_modules():
    """Import the frozen team driver by name, so report.py shares its module object."""
    if str(DRIVER_DIR) not in sys.path:
        sys.path.insert(0, str(DRIVER_DIR))
    import driver
    import report
    return driver, report


def load_dataset(path=None):
    path = Path(path or DEFAULT_DATASET)
    raw = path.read_bytes()
    if sha_bytes(raw) != DATASET_SHA:
        raise ValueError("Final benchmark JSONL hash mismatch: " + str(path))
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != 60 or len({row["name"] for row in rows}) != 60:
        raise ValueError("Expected 60 unique final theorems")
    return rows


def problem_packet(row, repo=None):
    return read_json(Path(repo or REPO) / "sources/final/problems" / f"F{row:03}.json")


def registry(prepared_repo=None):
    path = Path(prepared_repo or REPO) / "configs/final-environments.local.json"
    if not path.exists():
        return {"environments": {}}
    return read_json(path)


def coverage(rows, dataset_rows, prepared_repo=None):
    """route60.inspect_row per row: metadata readiness only (Lean checks happen in preflight)."""
    driver_modules()
    from route60 import inspect_row
    repo = Path(prepared_repo or REPO).resolve()
    environments = registry(repo).get("environments", {})
    result = {}
    for row in rows:
        try:
            result[row] = inspect_row(repo, row, dataset_rows[row - 1], environments)
        except (OSError, ValueError, KeyError) as exc:
            result[row] = {"row": row, "missing": ["inspection failed: " + str(exc)[:300]]}
    return result


def baseline_for(row):
    """Team-measured original metrics (docs/measurements/final60-baselines.json) when present."""
    path = REPO / "docs/measurements/final60-baselines.json"
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return None
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("row") == row and ("tokens" in json.dumps(item)[:4000] or "heartbeat" in json.dumps(item)[:4000]):
                return item
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return None


def routing_module():
    try:
        from . import routing
        return routing
    except ImportError:
        return None


def fallback_route(problem):
    """Stub when the routing component is absent: full loop, no hints, merger until budget."""
    return Route(row=problem["row"], name=problem["name"], source=problem["source"], problem_type="default",
                 skip_llm=False, portfolio=dict(DEFAULT_PORTFOLIO), role_models={}, hints=(), hint_sources=(),
                 golf=dict(DEFAULT_GOLF), priority=float(len(problem["reference"])), wallclock_budget_s=4500)


def route_for(problem, *, non_openrouter_proofs=(), diversity=False):
    routing = routing_module()
    if routing is not None:
        try:
            return routing.route(problem, baseline_for(problem["row"]),
                                 non_openrouter_proofs=list(non_openrouter_proofs), diversity=diversity)
        except Exception as exc:  # routing is hot-fixable; a routing bug must not stop the row
            print(json.dumps({"row": problem["row"], "routing_error": f"{type(exc).__name__}: {exc}"[:500]}),
                  file=sys.stderr, flush=True)
            if hasattr(routing, "default_route"):
                try:
                    return routing.default_route(problem)
                except Exception:
                    pass
    return fallback_route(problem)


def route_dict(route):
    routing = routing_module()
    if routing is not None and hasattr(routing, "route_json"):
        try:
            return routing.route_json(route)
        except Exception:
            pass
    return json.loads(json.dumps(dataclasses.asdict(route), sort_keys=True, default=str))


def prompt_addendum(route):
    routing = routing_module()
    if routing is not None and hasattr(routing, "prompt_addendum"):
        try:
            text = routing.prompt_addendum(route)
        except Exception:
            return ""
        if isinstance(text, str) and len(text) <= 2000 and "original_context>" not in text:
            return text
    return ""


def schedule(routes, ready):
    """Priority order (routing.schedule when present; else priority desc, then row)."""
    routing = routing_module()
    if routing is not None and hasattr(routing, "schedule"):
        try:
            order = list(routing.schedule(list(routes.values()), set(ready)))
            if set(order) <= set(ready):
                return order + sorted(set(ready) - set(order))
        except Exception:
            pass
    return sorted(ready, key=lambda row: (-routes[row].priority if row in routes else 0, row))


def number(value):
    value = Decimal(str(value))
    return int(value) if value == value.to_integral_value() else float(value)


def model_settings(key="gen_primary"):
    """Driver config['model'] for a catalog role (transport catalog when present)."""
    try:
        from . import catalog
        spec = catalog.spec(key)
    except (ImportError, AttributeError, KeyError):
        if key != "gen_primary":
            raise
        return dict(DEFAULT_MODEL)
    model = {"backend": "openrouter", "id": spec.model_id, "provider": spec.provider,
             "max_tokens": spec.max_tokens, "timeout_seconds": spec.timeout_s,
             "max_price": {"prompt": number(spec.prompt_usd_per_mtok), "completion": number(spec.completion_usd_per_mtok)},
             "catalog_key": spec.key}
    if spec.reasoning_effort is not None:
        model["reasoning_effort"] = spec.reasoning_effort
    if spec.seed is not None:
        model["seed"] = spec.seed
    return model


def row_settings(layout, row, route, *, cap, prior, compiler_slots, dry_run, route_sha256, addendum):
    """input/final60.json: everything the frozen driver needs from the orchestrator."""
    cap, prior = Decimal(str(cap)), Decimal(str(prior))
    root = layout.row_root(row)
    return {"schema": SCHEMA, "row": row, "name": route.name, "cap_usd": str(cap), "prior_cost_usd": str(prior),
            "effective_cap_usd": str(cap - prior), "model": model_settings("gen_primary"),
            "skip_llm": bool(route.skip_llm), "portfolio": None if route.skip_llm else dict(route.portfolio),
            "prompt_addendum": addendum, "route_sha256": route_sha256,
            "cost_ledger": os.path.relpath(layout.sqlite, root), "run_dir": os.path.relpath(layout.run_dir, root),
            "compiler_slots": int(compiler_slots), "dry_run": bool(dry_run),
            # Critic A7: exploration screens compile once (instrumented); final validation is unchanged.
            "screening": "single-pass",
            # Per-role models need a per-step model audit (critic A9); every role uses gen_primary.
            "role_models": {}, "role_models_requested": dict(route.role_models)}


def proofs_in(value, label=""):
    """(name, proof) pairs nested anywhere in a JSON value (dashboard problems[]/alternatives[])."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key in ("proof", "code"):
                text = item.get(key)
                if isinstance(text, str) and looks_like_declaration(text):
                    yield str(item.get("name") or item.get("id") or label), text
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


DECLARATION = re.compile(r"\b(theorem|lemma)\s")
SKIP_DIRS = {".git", ".lake", "evaluation-cache", "node_modules", "toolchains", "checkouts", "__pycache__",
             "downloads", "cache", "code"}
WRAPPER_FILE = re.compile(r"^(check|measure-\d+|native.*|axiom-audit.*|probe.*|source)\.lean$")


def looks_like_declaration(text):
    return len(text) <= 256 * 1024 and ":=" in text and DECLARATION.search(text[:600]) is not None


def walk_files(base):
    """Files under base in sorted order, pruning caches, toolchains and copied code."""
    for directory, names, files in os.walk(base):
        names[:] = sorted(name for name in names if name not in SKIP_DIRS)
        for name in sorted(files):
            yield Path(directory) / name


def collect_non_openrouter(paths):
    """Flatten every known non-OpenRouter proof into {name, proof, source} rows (critic A3)."""
    found = {}
    def add(name, proof, source):
        found.setdefault(normalized_sha(proof), {"name": name, "proof": proof, "source": source})
    for base in paths:
        base = Path(base)
        if not base.exists():
            continue
        files = [base] if base.is_file() else walk_files(base)
        for path in files:
            try:
                if path.suffix == ".lean":
                    if WRAPPER_FILE.match(path.name) or path.stat().st_size > 256 * 1024:
                        continue
                    text = path.read_text(encoding="utf-8")
                    if looks_like_declaration(text):
                        add(path.stem, text, str(path))
                elif path.suffix in (".json", ".jsonl") and path.stat().st_size <= 64 * 2**20:
                    text = path.read_text(encoding="utf-8")
                    values = ([json.loads(line) for line in text.splitlines() if line.strip()]
                              if path.suffix == ".jsonl" else [json.loads(text)])
                    for value in values:
                        for name, proof in proofs_in(value, path.stem):
                            add(name, proof, str(path))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
    return [found[key] for key in sorted(found)]


def write_non_openrouter(layout, extra_paths=()):
    rows = collect_non_openrouter([REPO / path for path in REPO_NON_OPENROUTER] + [Path(p) for p in extra_paths])
    atomic_bytes(layout.non_openrouter, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode())
    return rows


def load_non_openrouter(layout):
    if not layout.non_openrouter.exists():
        return []
    return [json.loads(line) for line in layout.non_openrouter.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_options(layout, opts):
    value = {key: (str(item) if isinstance(item, (Path, Decimal, datetime)) else item)
             for key, item in dataclasses.asdict(opts).items() if key != "key_file"}
    value["prior_costs"] = {str(row): str(cost) for row, cost in opts.prior_costs.items()}
    value["non_openrouter"] = [str(path) for path in opts.non_openrouter]
    value["key_file_configured"] = opts.key_file is not None
    atomic_json(layout.options, value)


def plan(run_dir, *, dataset=None, prepared_repo=None, rows=None, diversity=False, non_openrouter=(),
         refresh_non_openrouter=True, assemble_submission=True):
    """Coverage, routes and an all-original submission with checks; no API call and no Lean."""
    layout = Layout(run_dir)
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    data = load_dataset(dataset)
    rows = list(rows or range(1, 61))
    if refresh_non_openrouter or not layout.non_openrouter.exists():
        outside = write_non_openrouter(layout, non_openrouter)
    else:
        outside = load_non_openrouter(layout)
    covered = coverage(rows, data, prepared_repo)
    proofs = [row["proof"] for row in outside]
    entries, routes = [], {}
    for row in rows:
        problem = problem_packet(row)
        route = route_for(problem, non_openrouter_proofs=proofs, diversity=diversity)
        routes[row] = route
        missing = covered[row].get("missing", [])
        entries.append({"row": row, "name": problem["name"], "source": problem["source"],
                        "ready": not missing, "missing": missing, "problem_type": route.problem_type,
                        "skip_llm": route.skip_llm, "priority": route.priority,
                        "wallclock_budget_s": route.wallclock_budget_s})
    ready = [entry["row"] for entry in entries if entry["ready"]]
    sources = {str(Path(prepared_repo or REPO).resolve() / "sources"): str((Path(prepared_repo or REPO) / "sources").resolve()),
               str(REPO / "sources"): str((REPO / "sources").resolve())}
    value = {"schema": SCHEMA, "at": now_iso(), "dataset_sha256": DATASET_SHA,
             "dataset": str(Path(dataset or DEFAULT_DATASET).resolve()),
             "prepared_repo": str(Path(prepared_repo or REPO).resolve()), "repo": str(REPO),
             "sources_resolved": sources, "same_sources": len(set(sources.values())) == 1,
             "rows": entries, "ready": ready, "order": schedule(routes, ready),
             "non_openrouter_proofs": len(outside), "api_calls": 0, "lean_runs": 0}
    atomic_json(layout.plan, value)
    if assemble_submission:
        from .assemble import assemble
        value["assemble"] = assemble(layout.run_dir, final=False, dataset=dataset)
    return value


def row_spend(layout, row):
    path = layout.row_root(row) / "ledger.json"
    if not path.exists():
        return Decimal(0)
    ledger = read_json(path)
    return sum((Decimal(str(item["cost_usd"])) for item in ledger.get("attempts", {}).values()
                if item.get("cost_usd") is not None), Decimal(0))


def status(run_dir):
    """JSON status: frozen-code check first (critic A6), then per-row state and spend."""
    layout = Layout(run_dir)
    rows, frozen_errors = [], []
    driver, _ = driver_modules()
    for row in range(1, 61):
        state = load_rowstate(layout, row)
        root = layout.row_root(row)
        entry = {"row": row, "status": state.status, "attempts": state.attempts,
                 "spent_usd": str(row_spend(layout, row)), "score_estimate": state.score_estimate,
                 "last_error": state.last_error, "updated_at": state.updated_at}
        if (root / "frozen.json").exists():
            try:
                driver.verify_frozen(root)
            except (OSError, ValueError) as exc:
                frozen_errors.append(f"F{row:03}: {exc}"[:300])
        if (root / "published.json").exists():
            published = read_json(root / "published.json")
            entry.update(origin=published.get("origin"), published_at=published.get("at"))
        control = layout.control_path(row)
        if control.exists():
            entry["supervisor"] = read_json(control)
        rows.append(entry)
    spend = [Decimal(entry["spent_usd"]) for entry in rows]
    value = {"at": now_iso(), "run_dir": str(layout.run_dir), "frozen_code_ok": not frozen_errors,
             "frozen_errors": frozen_errors, "rows": rows,
             "counts": {name: sum(entry["status"] == name for entry in rows)
                        for name in sorted({entry["status"] for entry in rows})},
             "total_usd": str(sum(spend, Decimal(0))), "max_usd": str(max(spend)),
             "api_disabled": (layout.run_dir / "api-disabled.json").exists(),
             "soft_stop": (layout.run_dir / "stop-exploration.json").exists()}
    if (layout.supervisor / "status.json").exists():
        value["supervisor"] = read_json(layout.supervisor / "status.json")
    return value
