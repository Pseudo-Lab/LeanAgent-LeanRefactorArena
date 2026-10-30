#!/usr/bin/env python3
"""Run profile.py and minimize.py over every warm-up problem that has a local environment.

    python3 experiments/hb-profile/run_all.py --submission submissions/warmup/submission.jsonl \
        --output runs/hb-profile/<date>

For each line i of the submission (P01..P15 in file order) the script looks for
runs/warmup-team-results/20261022-verify-01/P<i>/<version>/environment.json. Problems with
no local environment (P03, P10, P11, P12, P13–P15 here) are listed and skipped.
Steps per problem: profile baseline, profile submission, minimize submission (all local
versions must pass), then profile the minimized result. A final table is written to
<output>/summary.md. Lean only; no model calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
VERIFY = REPO / "runs/warmup-team-results/20261022-verify-01"
BENCH = REPO / "benchmarks/arena/56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c"


def run(cmd: list[str], log: Path) -> int:
    with open(log, "w", encoding="utf-8") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
    return proc.returncode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--only", nargs="*", help="e.g. P05 P06")
    ap.add_argument("--skip-minimize", action="store_true")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    inputs = args.output / "inputs"
    inputs.mkdir()
    py = sys.executable
    rows = []
    for i, line in enumerate(args.submission.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rec = json.loads(line)
        pid = f"P{i:02d}"
        if args.only and pid not in args.only:
            continue
        name = rec["name"]
        decl = inputs / f"{pid}.lean"
        decl.write_text(rec["proof"].rstrip("\n") + "\n", encoding="utf-8")
        envs = sorted((VERIFY / pid).glob("*/environment.json")) if (VERIFY / pid).is_dir() else []
        if not envs:
            rows.append((pid, name, "no local environment", None))
            print(f"{pid}: no local environment, skipped", flush=True)
            continue
        baseline = envs[0].parent / "baseline.lean"
        print(f"{pid}: {len(envs)} env(s) — profiling baseline", flush=True)
        run([py, "-B", str(HERE / "profile.py"), "--env", str(envs[0]), "--decl", str(baseline),
             "--name", name, "--benchmark", str(BENCH), "--output", str(args.output / pid / "profile-baseline")],
            args.output / f"{pid}-profile-baseline.out")
        print(f"{pid}: profiling submission", flush=True)
        run([py, "-B", str(HERE / "profile.py"), "--env", str(envs[0]), "--decl", str(decl),
             "--name", name, "--benchmark", str(BENCH), "--output", str(args.output / pid / "profile-submission")],
            args.output / f"{pid}-profile-submission.out")
        summary = None
        if not args.skip_minimize:
            print(f"{pid}: minimizing", flush=True)
            cmd = [py, "-B", str(HERE / "minimize.py"), "--decl", str(decl), "--name", name,
                   "--benchmark", str(BENCH), "--output", str(args.output / pid / "minimize")]
            for e in envs:
                cmd += ["--env", str(e)]
            run(cmd, args.output / f"{pid}-minimize.out")
            sfile = args.output / pid / "minimize" / "summary.json"
            if sfile.exists():
                summary = json.loads(sfile.read_text(encoding="utf-8"))
                if summary.get("changed"):
                    run([py, "-B", str(HERE / "profile.py"), "--env", str(envs[0]),
                         "--decl", str(args.output / pid / "minimize" / "best.lean"),
                         "--name", name, "--benchmark", str(BENCH),
                         "--output", str(args.output / pid / "profile-minimized")],
                        args.output / f"{pid}-profile-minimized.out")
        rows.append((pid, name, f"{len(envs)} env(s)", summary))

    lines = ["| P | envs | input score | best score | tokens | hb (k) | compiles | changed |", "|---|---|---:|---:|---|---|---:|---|"]
    for pid, name, status, s in rows:
        if s is None:
            lines.append(f"| {pid} | {status} | | | | | | |")
            continue
        est = s["problem_score_estimate"]
        im, bm = s["input_metrics"], s["best_metrics"]
        lines.append(f"| {pid} | {status} | {est['input']} | {est['best']} | {im['tokens']}→{bm['tokens']} | "
                     f"{im['heartbeats']}→{bm['heartbeats_median']} | {s['compiles']} | {'yes' if s['changed'] else 'no'} |")
    (args.output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
