"""Bounded rounds over the pinned final benchmark, with explicit coverage."""

import argparse
import hashlib
import json
from pathlib import Path

from assigned_routes import assigned_mean, compare
from driver import DATASET_SHA, REPO, atomic
from evaluator import FinalEvaluator


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
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args(argv)
    if args.rounds < 1 or args.limit < 0 or len(set(args.rows)) != len(args.rows):
        ap.error("Expected positive rounds, a nonnegative limit and unique rows")
    repo = args.prepared_repo.resolve()
    dataset = (
        args.dataset or repo / f"benchmarks/arena/final-{DATASET_SHA[:12]}/benchmark_data_final.jsonl"
    )
    raw = dataset.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATASET_SHA:
        raise ValueError("Dataset hash mismatch")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows) != 60 or len({r["name"] for r in rows}) != 60:
        raise ValueError("Expected 60 unique theorems")
    ev = FinalEvaluator(repo_root=repo)
    if ev.registry["dataset_sha256"] != DATASET_SHA:
        raise ValueError("Dataset registry mismatch")
    inventory = [inspect_row(repo, n, rows[n - 1], ev.registry["environments"]) for n in args.rows]
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


if __name__ == "__main__":
    main()
