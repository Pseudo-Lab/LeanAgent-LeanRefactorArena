"""Bounded rounds over the pinned final benchmark, with explicit coverage."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from assigned_routes import assigned_mean, compare
from driver import DATASET_SHA, REPO, atomic
from evaluator import FinalEvaluator, lean_memory_mib

# Files whose bytes decide which proof text this run can produce (plus the evaluator and the
# declaration policy that accept it). protocol.json records their hashes, like route20's.
HARNESS_FILES = ("route60.py", "assigned_routes.py", "assigned_route_hints.json", "reuse_scout.py",
                 "evaluator.py", "policy.py")


def preflight(repo):
    """Find and probe the Linux compiler sandbox before any work (macOS uses sandbox-exec).

    The evaluator looks bwrap up on PATH; fall back to the prepared bundled build. The probe
    runs bwrap with the evaluator's own flags, so a build that cannot create namespaces (for
    example under AppArmor-restricted user namespaces) fails here instead of on every compile.
    """
    if sys.platform != "linux":
        return
    sandbox = shutil.which("bwrap")
    if not sandbox:
        bundled = repo / "sources/final/bin/bwrap"
        if not (bundled.is_file() and os.access(bundled, os.X_OK)):
            raise SystemExit("bwrap (bubblewrap) is not on PATH and sources/final/bin/bwrap is absent; "
                             "the Linux evaluator sandbox requires it")
        os.environ["PATH"] = str(bundled.parent) + os.pathsep + os.environ.get("PATH", "")
        print(f"Using the prepared bubblewrap {bundled}", flush=True)
        sandbox = str(bundled)
    probe = [sandbox, "--die-with-parent", "--unshare-all", "--ro-bind", "/", "/",
             "--dev", "/dev", "--proc", "/proc", "--", "true"]
    try:
        done = subprocess.run(probe, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"The bwrap sandbox probe could not run ({sandbox}): {exc}")
    if done.returncode:
        raise SystemExit(f"The bwrap sandbox probe failed ({sandbox}, exit {done.returncode}): "
                         + ((done.stderr or done.stdout or "").strip()[-500:] or "no output"))


def failure_details(folder):
    """Per-environment error kind and message of the row's latest failed evaluation.

    A failed reference otherwise reaches report.json only as a generic message; the cause
    (for example Lean's -M memory_exception) sits in that evaluation's result.json.
    """
    evaluations = sorted(folder.glob("[0-9]*-*/result.json"),
                         key=lambda path: int(path.parent.name.split("-", 1)[0]))
    for path in reversed(evaluations):
        try:
            result = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        errors = {env: {"kind": value["error"].get("kind"), "message": str(value["error"].get("message", ""))[-1000:]}
                  for env, value in result.get("environments", {}).items() if isinstance(value.get("error"), dict)}
        if errors:
            return {"evaluation": path.parent.name, "environments": errors}
    return None


def inspect_row(repo, row, ref, registry):
    packet = repo / "sources/final/problems" / f"F{row:03}.json"
    pins = {
        ref["source"] + "-" + version: commit
        for item in ref["version_info"]
        for version, commit in item.items()
    }
    result = {
        "row": row,
        "name": ref["name"],
        "source": ref["source"],
        "required": list(pins),
        "missing": [],
    }
    if not packet.is_file():
        result["missing"].append("problem packet")
    else:
        p = json.loads(packet.read_bytes())
        if (
            p["row"],
            p["name"],
            p["source"],
            p["statement"],
            p["reference"],
            p["header"],
            p["dataset_sha256"],
            p["environments"],
        ) != (
            row,
            ref["name"],
            ref["source"],
            ref["statement"],
            ref["src"],
            ref["header"],
            DATASET_SHA,
            list(pins),
        ):
            raise ValueError(f"Packet F{row:03} differs from frozen dataset")
    for env, rev in pins.items():
        path = repo / "sources/final/environments" / env / "environment.json"
        state = json.loads(path.read_bytes()) if path.is_file() else {}
        if (
            env not in registry
            or state.get("id") != env
            or state.get("status") != "ready"
            or state.get("revision") != rev
            or not state.get("prepared_environment")
            or not (repo / state["prepared_environment"]).is_file()
            or not any(loc["row"] == row for loc in state.get("locations", []))
        ):
            result["missing"].append(env)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", "--root", type=Path, required=True, help="A new output directory")
    ap.add_argument("--dataset", type=Path, help="Exact final benchmark JSONL")
    ap.add_argument("--prepared-repo", type=Path, default=REPO)
    ap.add_argument("--rows", type=int, nargs="+", choices=range(1, 61), default=list(range(1, 61)))
    ap.add_argument("--team-seeds", type=Path, help="Optional published team solutions for development")
    ap.add_argument(
        "--carry-jsonl",
        type=Path,
        action="append",
        help="Previously selected proofs to revalidate; repeat for independent sources",
    )
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--limit", type=int, default=2, help="New deterministic proposals per row per round")
    ap.add_argument("--policy", choices=("local", "issue61", "portfolio"), default="local")
    ap.add_argument(
        "--compiler-parallelism",
        type=int,
        choices=(1, 2, 3),
        default=1,
        help="Memory-gated compiler slots shared with other processes (PR #68); 1 keeps the exclusive lock",
    )
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args(argv)
    if args.rounds < 1 or args.limit < 0 or len(set(args.rows)) != len(args.rows):
        ap.error("Expected positive rounds, a nonnegative limit and unique rows")
    repo = args.prepared_repo.resolve()
    dataset = (
        args.dataset or repo / f"benchmarks/arena/final-{DATASET_SHA[:12]}/benchmark_data_final.jsonl"
    )
    if not dataset.is_file():
        ap.error(f"Final benchmark JSONL not found: {dataset} (gitignored; copy the pinned file or pass --dataset)")
    raw = dataset.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATASET_SHA:
        raise ValueError("Dataset hash mismatch")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows) != 60 or len({r["name"] for r in rows}) != 60:
        raise ValueError("Expected 60 unique theorems")
    try:
        ev = FinalEvaluator(repo_root=repo, compiler_parallelism=args.compiler_parallelism)
    except FileNotFoundError as exc:
        ap.error(f"Prepared environment registry not found: {exc.filename} (untracked; prepare or copy it)")
    if ev.registry["dataset_sha256"] != DATASET_SHA:
        raise ValueError("Dataset registry mismatch")
    inventory = [inspect_row(repo, n, rows[n - 1], ev.registry["environments"]) for n in args.rows]
    try:
        memory_mib = lean_memory_mib()
    except ValueError as exc:
        ap.error(str(exc))
    if not args.plan_only:
        preflight(repo)  # before any output, so a failed check leaves --out reusable
    args.out.mkdir(parents=True, exist_ok=False)
    ready = [r["row"] for r in inventory if not r["missing"]]
    atomic(
        args.out / "coverage.json",
        {
            "dataset_sha256": DATASET_SHA,
            "ready": ready,
            "rows": inventory,
            "meaning": "metadata availability; full library and Lean checks occur during evaluation",
        },
    )
    print(f"Prepared metadata: {len(ready)}/{len(inventory)}. Details in coverage.json", flush=True)
    if args.plan_only:
        return
    prior = {}
    if args.carry_jsonl:
        allowed = {r["name"]: r["statement"] for r in rows}
        from policy import validate_declaration

        for index, path in enumerate(args.carry_jsonl, 1):
            seen_names = set()
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                name = entry["name"]
                if name not in allowed or name in seen_names:
                    raise ValueError("Unknown or duplicate carried theorem: " + name)
                seen_names.add(name)
                validate_declaration(entry["proof"], allowed[name])
                prior.setdefault(name, []).append((f"carry-{index:02}", entry["proof"]))
    carry_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in args.carry_jsonl or []]
    atomic(
        args.out / "protocol.json",
        {
            "rounds": args.rounds,
            "limit": args.limit,
            "policy": args.policy,
            "dataset_sha256": DATASET_SHA,
            "team_seeds": bool(args.team_seeds),
            "carry_sha256": carry_hashes[0] if carry_hashes else None,
            "carry_sha256s": carry_hashes,
            "compiler_parallelism": args.compiler_parallelism,
            "lean_memory_mib": memory_mib,
            "code_hashes": {
                name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in HARNESS_FILES
            },
        },
    )
    selected = {}
    failed = {}
    tried = {n: set() for n in ready}
    active = set(ready)
    for iteration in range(1, args.rounds + 1):
        for n in sorted(active):
            p = ev.load_problem(n)
            root = args.out / f"round-{iteration:02}" / f"F{n:03}"
            root.mkdir(parents=True)
            initial = prior.get(p["name"], []) if n not in selected else []
            parent = selected[n]["proof"] if n in selected else (initial[0][1] if initial else None)
            try:
                result = compare(
                    ev,
                    p,
                    root,
                    args.team_seeds,
                    args.limit,
                    policy=args.policy,
                    incumbent=parent,
                    extra_seeds=initial[1:],
                    explored=tried[n],
                )
                if n in selected and result["controls"]["previous-round"] is None:
                    raise ValueError(f"Previous winner failed revalidation for F{n:03}")
                ev.verify_environments(p, full=True)
            except (ValueError, RuntimeError, OSError) as exc:
                # An infrastructure or policy failure is not a low-scoring proof.
                # Do not export a stale winner for this row after a failed recheck.
                selected.pop(n, None)
                failed[n] = {"round": iteration, "error": str(exc)[:1500]}
                details = failure_details(root)
                if details:
                    failed[n].update(details)
                atomic(root / "incomplete.json", failed[n])
                active.discard(n)
                continue
            atomic(root / "selected.json", result)
            selected[n] = result
            tried[n].update(result["screened_hashes"])
            if result["attempts"] < args.limit or not args.limit:
                active.discard(n)
        if not active:
            break
    complete = set(selected) == set(range(1, 61))
    name = "submission.jsonl" if complete else "partial.jsonl"
    (args.out / name).write_text(
        "".join(
            json.dumps({"name": r["name"], "proof": r["proof"]}, ensure_ascii=False) + "\n"
            for _, r in sorted(selected.items())
        ),
        encoding="utf-8",
    )
    atomic(
        args.out / "report.json",
        {
            "official": False,
            "assisted": args.team_seeds is not None or bool(prior),
            "api_calls": 0,
            "coverage": len(selected),
            "assigned20_mean": assigned_mean({"row": n, "score": r["score"]} for n, r in selected.items()),
            "failed": failed,
            "full60_mean": sum(r["score"] for r in selected.values()) / 60 if complete else None,
            "rows": {
                n: {
                    "score": r["score"],
                    "chosen": r["selected"],
                    "carried_inputs": [
                        {"source": label, "proof_sha256": hashlib.sha256(code.encode()).hexdigest()}
                        for label, code in prior.get(r["name"], [])
                    ],
                }
                for n, r in selected.items()
            },
        },
    )
    unselected = sorted(set(args.rows) - set(selected))
    if unselected:
        # Outputs are written; a nonzero status tells wrappers the requested coverage is incomplete.
        print(f"Incomplete: {len(selected)}/{len(args.rows)} requested rows selected; "
              f"failed or unprepared rows: {unselected}. See coverage.json and report.json", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
