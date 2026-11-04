#!/usr/bin/env python3
"""Static pre-submission check against the official rules text (no Lean, no model call).

Checks every row of a submission JSONL: benchmark name, unchanged statement, the official
forbidden patterns, `unsafe` outside `aesop (add unsafe ...)`, extra top-level commands,
the 256 KiB proof limit, and that every benchmark problem is present (a missing one scores 0).
Compilation, heartbeats and version compatibility are not checked here.

usage (repository root):
  python scripts/check_submission_rules.py --jsonl benchmark_data_final.jsonl --submission submission.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FORBIDDEN = [
    (r"#eval\b", "#eval"), (r"#reduce\b", "#reduce"), (r"(?<![\w.])IO\.", "IO"),
    (r"\bextern\b", "extern"), (r"\binitialize\b", "initialize"), (r"implemented_by", "implemented_by"),
    (r"\bsorry\b", "sorry"), (r"\badmit\b", "admit"), (r"\baxiom\b", "axiom"),
    (r"native_decide", "native_decide"), (r"decide\s*\+\s*native", "decide +native"), (r"ofReduceBool", "ofReduceBool"),
    (r"#count_heartbeats", "#count_heartbeats"), (r"getNumHeartbeats|withHeartbeats", "heartbeat API"),
    (r"\brun_tac\b", "run_tac"), (r"\bby_elab\b", "by_elab"), (r"\brun_meta\b", "run_meta"),
    (r"\bd?simproc\b", "simproc"), (r"eval%", "eval%"),
]
TOP_LEVEL = re.compile(r"(?m)^(def|instance|attribute|macro|notation|syntax|theorem|lemma|abbrev|axiom|opaque|"
                       r"structure|inductive|class|open|namespace|section|end|set_option|@\[)\b")
MAX_BYTES = 256 * 1024


def strip_comments(text: str) -> str:
    return re.sub(r"--[^\n]*|/-.*?-/", " ", text, flags=re.S)


def check_row(statement: str, proof: str) -> list[str]:
    issues = []
    if not proof.startswith(statement):
        issues.append("statement differs from the benchmark statement")
    body = strip_comments(proof[len(statement):] if proof.startswith(statement) else proof)
    issues += [f"forbidden: {label}" for pattern, label in FORBIDDEN if re.search(pattern, body)]
    for match in re.finditer(r"\bunsafe\b", body):
        if not re.search(r"add\s*$", body[max(0, match.start() - 12):match.start()]):
            issues.append("unsafe outside `aesop (add unsafe ...)`")
    if (m := TOP_LEVEL.search(body)):
        issues.append(f"extra top-level command: {m.group(0)}")
    if len(proof.encode("utf-8")) > MAX_BYTES:
        issues.append("proof exceeds 256 KiB")
    return issues


def check(benchmark: list[dict], submission: list[dict]) -> dict:
    rows = {r["name"]: r for r in benchmark}
    seen, problems = set(), {}
    for entry in submission:
        name = entry.get("name")
        if name not in rows:
            problems.setdefault(str(name), []).append("name is not a benchmark id (row ignored)")
            continue
        if name in seen:
            problems.setdefault(name, []).append("duplicate row")
        seen.add(name)
        if issues := check_row(rows[name]["statement"], entry.get("proof", "")):
            problems.setdefault(name, []).extend(issues)
    return {"rows": len(submission), "problems": problems, "missing": [n for n in rows if n not in seen]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", type=Path, required=True, help="benchmark JSONL (name, statement)")
    ap.add_argument("--submission", type=Path, required=True, help="submission JSONL (name, proof)")
    a = ap.parse_args()
    load = lambda p: [json.loads(line) for line in p.open(encoding="utf-8") if line.strip()]
    result = check(load(a.jsonl), load(a.submission))
    for name, issues in result["problems"].items():
        for issue in issues:
            print(f"{name}: {issue}")
    for name in result["missing"]:
        print(f"{name}: missing (scores 0)")
    bad = len(result["problems"]) + len(result["missing"])
    print(f"{result['rows']} rows, {bad} problem(s) with issues")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
