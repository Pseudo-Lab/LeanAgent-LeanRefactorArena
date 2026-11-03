#!/usr/bin/env python3
"""Check where every submitted proof came from (no Lean, no model call).

The closed-track rules require every model call to go through OpenRouter and the
per-problem API spend, including retries and discarded candidates, to stay within
US$3. `check_submission_rules.py` checks the proof text; this script checks its
origin. For every row of the submission JSONL it requires one of:

  * the benchmark reference proof itself (no model output, no cost), or
  * a final-batch-next run root (`--run-root`) whose `problems/FNNN/selected.lean`
    equals the proof, whose `authorization.json` endpoint is openrouter.ai and whose
    ledger for that row is settled and within the cap, or
  * an entry in `--manifest` for a proof produced by another runner (reported as
    self-declared: endpoint, cost and evidence path are taken as written).

Proof texts that came from outside OpenRouter (Codex, OpenAI direct, dashboard
results) can be listed with `--non-openrouter`. A submitted proof equal to one of
them fails, and so does a run whose saved model requests contain one of them as
a seed, warm start or carried candidate.

usage (repository root):
  python scripts/check_submission_provenance.py --jsonl benchmark_data_final.jsonl \
      --submission runs/final/submission.jsonl --run-root runs/final \
      [--run-root runs/rerun] [--manifest provenance.json] [--non-openrouter solutions/codex]

manifest (JSON list), one entry per proof produced outside final-batch-next:
  {"name": ..., "proof_sha256": ..., "api_endpoint": "https://openrouter.ai/api/v1/...",
   "cost_usd": "1.23", "evidence": "path/to/ledger"}
An entry may also carry "prior_cost_usd" to add spend from earlier runs whose
candidates fed the submitted proof (also allowed for rows found in a run root).
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

OPENROUTER_HOST = "openrouter.ai"
MIN_LEAK_CHARS = 40


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def sha(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def via_openrouter(endpoint) -> bool:
    return isinstance(endpoint, str) and urlparse(endpoint).hostname == OPENROUTER_HOST


def strings(value):
    """All strings in a JSON value, decoding JSON documents nested inside strings."""
    if isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, str):
        yield value
        if value.lstrip()[:1] in ("{", "["):
            try:
                yield from strings(json.loads(value))
            except ValueError:
                pass


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def load_proofs(path: Path) -> list[tuple[str, str]]:
    """(label, proof) pairs from .lean files and from JSONL/JSON rows with a proof field."""
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    found = []
    for file in files:
        if file.suffix == ".lean":
            found.append((str(file), file.read_text(encoding="utf-8")))
        elif file.suffix in (".jsonl", ".json"):
            text = file.read_text(encoding="utf-8")
            rows = load_jsonl(file) if file.suffix == ".jsonl" else json.loads(text)
            for index, row in enumerate(rows if isinstance(rows, list) else [rows]):
                if isinstance(row, dict) and isinstance(row.get("proof"), str):
                    found.append((f"{file}#{row.get('name', index)}", row["proof"]))
    return found


def body(proof: str, statement: str) -> str:
    return proof[len(statement):] if proof.startswith(statement) else proof


class RunRoot:
    def __init__(self, root: Path):
        self.root = root
        self.authorization = json.loads((root / "authorization.json").read_text())
        self.ledger = json.loads((root / "ledger.json").read_text())
        report = root / "report.json"
        self.report = json.loads(report.read_text()) if report.exists() else None
        self.rows = {}
        for folder in sorted((root / "problems").glob("F[0-9][0-9][0-9]")):
            selected = folder / "selected.lean"
            problem = folder / "input" / "problem.json"
            if selected.exists() and problem.exists():
                name = json.loads(problem.read_text())["name"]
                self.rows[(name, sha(selected.read_text()))] = folder

    def attempts(self, row: int):
        return [item for item in self.ledger.get("attempts", {}).values() if item.get("row") == row]

    def requests(self, folder: Path):
        for request in sorted((folder / "steps").glob("*/request.json")):
            yield request, flat(" ".join(strings(json.loads(request.read_text()))))


def check(benchmark, submission, roots, manifest, outside, cap):
    problems = {row["name"]: row for row in benchmark}
    declared = {entry["name"]: entry for entry in manifest}
    outside_by_hash = {}
    for label, proof in outside:
        outside_by_hash.setdefault(sha(proof), label)
    results, errors = [], []

    def fail(name, message):
        errors.append(f"{name}: {message}")

    for entry in submission:
        name, proof = entry.get("name"), entry.get("proof", "")
        problem = problems.get(name)
        if problem is None:
            fail(name, "not a benchmark name")
            continue
        statement = problem["statement"]
        reference = problem.get("proof", problem.get("reference"))
        digest = sha(proof)
        prior = Decimal(str(declared.get(name, {}).get("prior_cost_usd", "0")))
        result = {"name": name, "proof_sha256": digest}
        if reference is not None and digest == sha(reference):
            result.update(origin="reference", cost_usd="0")
            results.append(result)
            continue
        if digest in outside_by_hash:
            fail(name, f"submitted proof equals a non-OpenRouter proof ({outside_by_hash[digest]})")
        match = next(((run, run.rows[(name, digest)]) for run in roots if (name, digest) in run.rows), None)
        if match:
            run, folder = match
            row = int(folder.name[1:])
            endpoint = run.authorization.get("api_endpoint")
            attempts = run.attempts(row)
            spent = sum((Decimal(str(item["cost_usd"])) for item in attempts if item.get("cost_usd") is not None),
                        Decimal(0))
            result.update(origin=str(folder), api_endpoint=endpoint, calls=len(attempts),
                          cost_usd=str(spent + prior))
            if not via_openrouter(endpoint):
                fail(name, f"run {run.root} called {endpoint or 'an unrecorded endpoint'}, not OpenRouter")
            if any(item.get("status") != "settled" for item in attempts):
                fail(name, f"run {run.root} has unsettled calls for F{row:03}")
            if run.report is None or not run.report.get("audit_passed"):
                fail(name, f"run {run.root} has no passing report.json (run report.py first)")
            for label, other in outside:
                piece = flat(body(other, statement))
                if len(piece) < MIN_LEAK_CHARS or (reference is not None and sha(other) == sha(reference)):
                    continue
                for request, text in run.requests(folder):
                    if piece in text:
                        fail(name, f"model request {request.relative_to(run.root)} contains non-OpenRouter proof {label}")
                        break
        elif name in declared and declared[name].get("proof_sha256") == digest:
            item = declared[name]
            result.update(origin="manifest (self-declared)", api_endpoint=item.get("api_endpoint"),
                          cost_usd=str(Decimal(str(item.get("cost_usd", "0"))) + prior),
                          evidence=item.get("evidence"))
            if not via_openrouter(item.get("api_endpoint")):
                fail(name, f"manifest endpoint {item.get('api_endpoint')} is not OpenRouter")
            if "cost_usd" not in item or not item.get("evidence"):
                fail(name, "manifest entry needs cost_usd and an evidence path")
        else:
            result["origin"] = None
            fail(name, "no OpenRouter run evidence for this proof (not the reference, not in any run root or manifest)")
        if result.get("cost_usd") is not None and Decimal(result["cost_usd"]) > cap:
            fail(name, f"cost US${result['cost_usd']} exceeds the US${cap} cap")
        results.append(result)
    seen = {entry.get("name") for entry in submission}
    missing = [name for name in problems if name not in seen]
    return {"rows": results, "errors": errors, "missing": missing, "cap_usd": str(cap)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", type=Path, required=True, help="benchmark JSONL (name, statement, proof)")
    ap.add_argument("--submission", type=Path, required=True, help="submission JSONL (name, proof)")
    ap.add_argument("--run-root", type=Path, action="append", default=[], help="final-batch-next run root")
    ap.add_argument("--manifest", type=Path, help="JSON list of proofs produced by other runners")
    ap.add_argument("--non-openrouter", type=Path, action="append", default=[],
                    help="file or directory of proofs produced outside OpenRouter (.lean, .jsonl, .json)")
    ap.add_argument("--cap", type=Decimal, default=Decimal("3"))
    ap.add_argument("--json-out", type=Path, help="write the per-row result as JSON")
    a = ap.parse_args()
    roots = [RunRoot(path) for path in a.run_root]
    manifest = json.loads(a.manifest.read_text()) if a.manifest else []
    outside = [pair for path in a.non_openrouter for pair in load_proofs(path)]
    result = check(load_jsonl(a.jsonl), load_jsonl(a.submission), roots, manifest, outside, a.cap)
    if a.json_out:
        a.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for row in result["rows"]:
        print(f"{row['name']}\t{row.get('origin')}\tUS${row.get('cost_usd', '?')}")
    for line in result["errors"]:
        print("ERROR " + line)
    for name in result["missing"]:
        print(f"ERROR {name}: missing from the submission (scores 0)")
    costs = [Decimal(row["cost_usd"]) for row in result["rows"] if row.get("cost_usd") is not None]
    if costs:
        print(f"{len(result['rows'])} rows, total US${sum(costs)}, max US${max(costs)}")
    bad = len(result["errors"]) + len(result["missing"])
    print(f"{bad} provenance issue(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
