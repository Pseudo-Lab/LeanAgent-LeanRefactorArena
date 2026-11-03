"""python -m lean_agent.final60 {plan,run,row,status,assemble} (see docs/final60/RUNBOOK.md)."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

from . import transports
from .contracts import CAP_USD
from .orchestrator import (DEFAULT_DEADLINE, REPO, Layout, RunOptions, parse_deadline, parse_rows, plan, read_json,
                           status)


def prior_costs(path):
    """{"F012": "0.12", "13": "0.05"} -> {12: Decimal("0.12"), 13: Decimal("0.05")} (critic A11)."""
    if path is None:
        return {}
    value = read_json(path)
    return {int(str(key).lstrip("Ff")): Decimal(str(cost)) for key, cost in value.items()}


def add_common(parser):
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, help="Final benchmark JSONL (default: the repo's pinned copy)")
    parser.add_argument("--prepared-repo", type=Path, help="Checkout whose configs/ and sources/ give environment coverage")
    parser.add_argument("--non-openrouter", type=Path, action="append", default=[],
                        help="Extra file/folder of proofs produced outside OpenRouter (repeatable)")


def add_run(parser):
    parser.add_argument("--key-file", type=Path, help="Dotenv file with OPENROUTER_API_KEY (OPENAI_API_KEY for "
                                                      "--transport openai); read only by the transport")
    parser.add_argument("--rows", default="1-60", help="Rows, e.g. 1-60 or 11-30,41")
    parser.add_argument("--max-rows", type=int, default=8)
    parser.add_argument("--compiler-slots", type=int, default=6)
    parser.add_argument("--deadline", default=DEFAULT_DEADLINE)
    parser.add_argument("--soft-stop-min", type=int, default=100)
    parser.add_argument("--exploration-minutes", type=int, default=75)
    parser.add_argument("--cap", type=Decimal, default=CAP_USD)
    parser.add_argument("--prior-costs", type=Path, help="JSON {row: USD already spent outside the row root}")
    parser.add_argument("--mem-start-gib", type=float, default=10.0)
    parser.add_argument("--mem-reserve-gib", type=float, default=6.0)
    parser.add_argument("--gib-per-compile", type=float, default=3.5)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--memory-log-seconds", type=float, default=30.0,
                        help="Period of supervisor/memory.jsonl (lean RSS and MemAvailable)")
    parser.add_argument("--diversity", action="store_true", help="Pass to routing; per-role models stay off (critic A9)")
    parser.add_argument("--dry-run", action="store_true", help="Mock transport (no network, no spend); never submitted")
    add_passthrough(parser)


def add_passthrough(parser):
    # openrouter (the entry, default), mock (dry run; implied by --dry-run) or openai (development only).
    transports.add_argument(parser, default=None)
    parser.add_argument("--lean-memory-mib", type=int, help="ARENA_LEAN_MEMORY_MIB for every row "
                                                            "(default: 16384 for Mathlib-based sources, else 4096)")


def options(args):
    saved = {}
    if getattr(args, "command", None) == "row" and Layout(args.run_dir).options.exists():
        saved = read_json(Layout(args.run_dir).options)
    def pick(name, default=None):
        value = getattr(args, name, None)
        return value if value is not None else saved.get(name, default)
    rows = parse_rows(args.rows) if getattr(args, "rows", None) else saved.get("rows", list(range(1, 61)))
    deadline = parse_deadline(pick("deadline", DEFAULT_DEADLINE))
    priors = prior_costs(args.prior_costs) if getattr(args, "prior_costs", None) else {
        int(key): Decimal(value) for key, value in saved.get("prior_costs", {}).items()}
    # The transport is a sealed run setting: --dry-run is the mock, and the mock is always a dry run.
    dry_run = bool(getattr(args, "dry_run", False) or saved.get("dry_run"))
    transport = str(pick("transport") or transports.DEFAULT)
    if dry_run and transport == transports.DEFAULT:
        transport = "mock"
    if transport == "mock":
        dry_run = True
    opts = RunOptions(run_dir=args.run_dir.resolve(), key_file=getattr(args, "key_file", None), rows=rows,
                      max_rows=int(pick("max_rows", 8)), compiler_slots=int(pick("compiler_slots", 6)),
                      deadline=deadline, soft_stop_min=int(pick("soft_stop_min", 100)),
                      diversity=bool(pick("diversity", False)), dry_run=dry_run,
                      dataset=Path(pick("dataset")) if pick("dataset") else None,
                      prepared_repo=Path(pick("prepared_repo")) if pick("prepared_repo") else None,
                      non_openrouter=[Path(path) for path in (getattr(args, "non_openrouter", None) or saved.get("non_openrouter", []))],
                      cap_usd=Decimal(str(pick("cap", None) or saved.get("cap_usd") or CAP_USD)), prior_costs=priors,
                      exploration_minutes=int(pick("exploration_minutes", 75)),
                      mem_start_gib=float(pick("mem_start_gib", 10.0)), mem_reserve_gib=float(pick("mem_reserve_gib", 6.0)),
                      gib_per_compile=float(pick("gib_per_compile", 3.5)), poll_seconds=float(pick("poll_seconds", 15.0)),
                      transport=transport,
                      lean_memory_mib=(int(pick("lean_memory_mib")) if pick("lean_memory_mib") else None),
                      memory_log_seconds=float(pick("memory_log_seconds", 30.0)))
    if not 0 < opts.cap_usd <= CAP_USD:
        raise SystemExit("--cap must be in (0, 2.99]")
    if not 2 <= opts.compiler_slots <= 8 or not 1 <= opts.max_rows <= 14:
        raise SystemExit("--compiler-slots must be 2..8 and --max-rows 1..14")
    if opts.lean_memory_mib is not None and not 1024 <= opts.lean_memory_mib <= 262144:
        raise SystemExit("--lean-memory-mib must be 1024..262144")
    return opts


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m lean_agent.final60", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan", help="Coverage, routes and an all-original submission; no API, no Lean")
    add_common(plan_parser)
    plan_parser.add_argument("--rows", default="1-60")
    plan_parser.add_argument("--diversity", action="store_true")
    run_parser = commands.add_parser("run", help="Supervise all selected rows until done or the deadline")
    add_common(run_parser)
    add_run(run_parser)
    row_parser = commands.add_parser("row", help="One row worker (normally spawned by run)")
    row_parser.add_argument("--run-dir", type=Path, required=True)
    row_parser.add_argument("--row", type=int, required=True)
    row_parser.add_argument("--key-file", type=Path)
    row_parser.add_argument("--dry-run", action="store_true")
    add_passthrough(row_parser)
    status_parser = commands.add_parser("status", help="Per-row state, spend and frozen-code check (JSON)")
    status_parser.add_argument("--run-dir", type=Path, required=True)
    assemble_parser = commands.add_parser("assemble", help="60-row submission, checkers and report")
    add_common(assemble_parser)
    assemble_parser.add_argument("--final", action="store_true")
    assemble_parser.add_argument("--refresh-non-openrouter", action="store_true")
    assemble_parser.add_argument("--allow-dry-run", action="store_true", help="Testing only: include dry-run roots")
    package_parser = commands.add_parser("package", help="Code ZIP of tracked files (no symlinks, indexes, quarantine "
                                                        "or competitor artifacts); asserts the exclusions")
    package_parser.add_argument("--out", type=Path, required=True)
    package_parser.add_argument("--repo", type=Path, help="Checkout to pack (default: this one)")
    package_parser.add_argument("--name", help="Top-level folder inside the ZIP (default: the checkout's name)")
    package_parser.add_argument("--exclude", action="append", default=[], help="Extra path regex to leave out (repeatable)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "package":
        from .package import package_code
        print(json.dumps(package_code(args.repo or REPO, args.out, name=args.name, extra_excludes=args.exclude),
                         ensure_ascii=False))
        return 0
    if args.command == "plan":
        value = plan(args.run_dir, dataset=args.dataset, prepared_repo=args.prepared_repo, rows=parse_rows(args.rows),
                     diversity=args.diversity, non_openrouter=args.non_openrouter)
        print(json.dumps({key: value[key] for key in ("ready", "order", "non_openrouter_proofs", "same_sources")}
                         | {"assemble": value.get("assemble")}, ensure_ascii=False))
        return 0
    if args.command == "status":
        print(json.dumps(status(args.run_dir), ensure_ascii=False, indent=2))
        return 0
    if args.command == "assemble":
        from .assemble import assemble
        from .orchestrator import write_non_openrouter
        if args.refresh_non_openrouter or args.non_openrouter:
            write_non_openrouter(Layout(args.run_dir), args.non_openrouter)
        print(json.dumps(assemble(args.run_dir, final=args.final, dataset=args.dataset,
                                  allow_dry_run=args.allow_dry_run), ensure_ascii=False))
        return 0
    opts = options(args)
    if args.command == "run":
        if opts.key_file is None and not opts.dry_run:
            raise SystemExit("run needs --key-file (or --dry-run / --transport mock)")
        from .supervisor import supervise
        return supervise(args.run_dir, opts)
    from .rowworker import EXIT_RETRYABLE, WorkerBusy, run_row
    if not 1 <= args.row <= 60:
        raise SystemExit("--row must be 1..60")
    try:
        state = run_row(args.run_dir, args.row, opts)
    except WorkerBusy as exc:
        print(json.dumps({"row": args.row, "busy": str(exc)}), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"row": args.row, "error": f"{type(exc).__name__}: {exc}"[:1000]}), flush=True)
        return EXIT_RETRYABLE if getattr(exc, "final60_retryable", False) else 1
    print(json.dumps({"row": args.row, "status": state.status, "score_estimate": state.score_estimate}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
