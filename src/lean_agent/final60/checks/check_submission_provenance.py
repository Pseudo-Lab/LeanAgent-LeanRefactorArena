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
  * a route60 or unpaid route20 output directory (`--harness-root`, PR #63) whose final
    selection for the row (route60: the last round's FNNN/selected.json of a row that
    report.json still lists; route20: FNNN/selected.json) equals it. These runs make no
    model call, so the proof is a deterministic harness transform. Only an unassisted
    run counts: no team seeds, no carried proofs and no paid proposal. The run must
    also have recorded the hashes of its proof-generating files (protocol.json
    code_hashes) and they must equal this checkout's (`--harness-code`), so output
    of harness code that is not being submitted is refused. The certificate records
    those hashes and the winning label (e.g. reference/delta-predicate). This origin
    is an integration addition; PR #70 itself defines only the other three. Or
  * an entry in `--manifest` for a proof produced by another runner (reported as
    self-declared: endpoint, cost and evidence path are taken as written).

The benchmark reference is the official `src` field (`proof`/`reference` are accepted
for other row layouts).

Spend: every origin's cost_usd adds the settled spend that all given `--run-root`
ledgers record for the theorem (including discarded candidates and other runs) and
the manifest's prior_cost_usd, and an unsettled call in any of them fails the row.
Pass every run root that called a model for the submission's theorems.

Proof texts that came from outside OpenRouter (Codex, OpenAI direct, dashboard
results) can be listed with `--non-openrouter`. A submitted proof equal to one of
them fails, and so does a run whose saved model requests contain one of them as
a seed, warm start or carried candidate. Unchanged benchmark originals in such a
set are not leaks: a prompt may hold an earlier row's original from the same file.

usage (repository root):
  python scripts/check_submission_provenance.py --jsonl benchmark_data_final.jsonl \
      --submission runs/final/submission.jsonl --run-root runs/final \
      [--run-root runs/rerun] [--harness-root runs/route60] [--manifest provenance.json] \
      [--non-openrouter solutions/codex] [--harness-code experiments/final-batch-next]

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
def _harness_code() -> Path:
    """experiments/final-batch-next of the checkout holding this file (also from a vendored copy)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "experiments" / "final-batch-next" / "route60.py").is_file():
            return parent / "experiments" / "final-batch-next"
    return Path(__file__).resolve().parents[1] / "experiments" / "final-batch-next"


HARNESS_CODE = _harness_code()
# Files whose bytes decide which proof text a route20/route60 run can produce.
GENERATOR_FILES = ("assigned_routes.py", "assigned_route_hints.json", "reuse_scout.py")
ROUTE60_GENERATOR_FILES = GENERATOR_FILES + ("route60.py",)


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


def reference_proof(problem: dict):
    """The original proof: the official benchmark rows keep it under `src`."""
    for key in ("src", "proof", "reference"):
        if isinstance(problem.get(key), str):
            return problem[key]
    return None


class RunRoot:
    def __init__(self, root: Path):
        self.root = root
        missing = [name for name in ("authorization.json", "ledger.json") if not (root / name).is_file()]
        if missing:
            raise ValueError(f"{root} is not a final-batch-next run root (missing {', '.join(missing)}); "
                             "pass route60/route20 output directories with --harness-root")
        self.authorization = json.loads((root / "authorization.json").read_text())
        self.ledger = json.loads((root / "ledger.json").read_text())
        report = root / "report.json"
        self.report = json.loads(report.read_text()) if report.exists() else None
        self.rows = {}
        self.numbers = {}  # theorem name -> row number used by this root's ledger
        for folder in sorted((root / "problems").glob("F[0-9][0-9][0-9]")):
            selected = folder / "selected.lean"
            problem = folder / "input" / "problem.json"
            if problem.exists():
                name = json.loads(problem.read_text())["name"]
                self.numbers[name] = int(folder.name[1:])
                if selected.exists():
                    self.rows[(name, sha(selected.read_text()))] = folder

    def attempts(self, row: int):
        return [item for item in self.ledger.get("attempts", {}).values() if item.get("row") == row]

    def requests(self, folder: Path):
        for request in sorted((folder / "steps").glob("*/request.json")):
            yield request, flat(" ".join(strings(json.loads(request.read_text()))))


class HarnessRoot:
    """A finished route60 or route20 output directory (PR #63): deterministic proposals only.

    route60 never calls a model (report.json api_calls 0); route20 does only in paid mode,
    whose spend lives in a SQLite ledger this checker does not read, so paid route20 runs
    are refused here (declare them in --manifest). Seeds and carried proofs may come from
    outside OpenRouter, so an assisted run certifies nothing. Neither does a run whose
    recorded proof-generating code differs from `code_dir` (the harness being submitted).
    Only final selections count: route60 rows that report.json no longer lists (a later
    round failed, see incomplete.json) and earlier rounds' winners are not certified.
    """

    def __init__(self, root: Path, code_dir: Path = HARNESS_CODE):
        self.root = root
        try:
            protocol = json.loads((root / "protocol.json").read_text())
            report = json.loads((root / "report.json").read_text())
        except FileNotFoundError as exc:
            raise ValueError(f"{root} is not a finished route60/route20 directory "
                             f"(missing {Path(exc.filename).name})") from exc
        self.problems = []
        route60 = "api_calls" in report
        if route60:
            if report["api_calls"] != 0:
                self.problems.append(f"report.json records {report['api_calls']} API calls")
        elif report.get("paid_enabled") is not False or protocol.get("paid") is not False:  # route20
            self.problems.append("route20 paid mode (its spend is only in the SQLite ledger)")
        if report.get("assisted") is not False:
            self.problems.append("assisted run (team seeds or carried proofs)")
        if protocol.get("team_seeds"):
            self.problems.append("team seeds were used")
        if protocol.get("carry_sha256s") or protocol.get("carry_sha256"):
            self.problems.append("carried proofs were used")
        self.code_hashes = protocol.get("code_hashes")
        if not isinstance(self.code_hashes, dict):
            self.problems.append("protocol.json records no code hashes, so the generating harness code is unknown")
        else:
            for name in ROUTE60_GENERATOR_FILES if route60 else GENERATOR_FILES:
                path = Path(code_dir) / name
                current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                if self.code_hashes.get(name) is None:
                    self.problems.append(f"protocol.json records no hash for {name}")
                elif self.code_hashes[name] != current:
                    self.problems.append(f"{name} differs from the harness in {code_dir} (made by other code)")
        self.rows = {}
        if route60:
            failed = {str(key) for key in report.get("failed", {})}
            for key in report.get("rows", {}):
                if str(key) in failed or not str(key).isdigit():
                    continue
                rounds = sorted(root.glob(f"round-[0-9][0-9]/F{int(key):03}/selected.json"))
                if rounds:
                    self._add(rounds[-1])
        else:
            for selected in sorted(root.glob("F[0-9][0-9][0-9]/selected.json")):
                self._add(selected)

    def _add(self, selected: Path):
        data = json.loads(selected.read_text())
        if isinstance(data.get("name"), str) and isinstance(data.get("proof"), str):
            self.rows.setdefault((data["name"], sha(data["proof"])), (selected, data.get("call"), data.get("selected")))


def spend(attempts):
    return sum((Decimal(str(item["cost_usd"])) for item in attempts if item.get("cost_usd") is not None),
               Decimal(0))


def check(benchmark, submission, roots, manifest, outside, cap, harness_roots=()):
    problems = {row["name"]: row for row in benchmark}
    # Unchanged originals of any benchmark row are public inputs, not leaked outside proofs:
    # rows from one source file see earlier rows' originals in their prompt context.
    originals = {sha(text) for text in map(reference_proof, benchmark) if text is not None}
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
        reference = reference_proof(problem)
        digest = sha(proof)
        prior = Decimal(str(declared.get(name, {}).get("prior_cost_usd", "0")))
        # The cap counts every call for the theorem: all given run roots, not only the matched one.
        spent = Decimal(0)
        for run in roots:
            if name in run.numbers:
                attempts = run.attempts(run.numbers[name])
                spent += spend(attempts)
                if any(item.get("status") != "settled" for item in attempts):
                    fail(name, f"run {run.root} has unsettled calls for F{run.numbers[name]:03}")
        result = {"name": name, "proof_sha256": digest}
        if roots:
            result["run_roots_cost_usd"] = str(spent)
        if reference is not None and digest == sha(reference):
            result.update(origin="reference", cost_usd=str(spent + prior))
            if spent + prior > cap:
                fail(name, f"cost US${result['cost_usd']} exceeds the US${cap} cap")
            results.append(result)
            continue
        if digest in outside_by_hash:
            fail(name, f"submitted proof equals a non-OpenRouter proof ({outside_by_hash[digest]})")
        match = next(((run, run.rows[(name, digest)]) for run in roots if (name, digest) in run.rows), None)
        harness = next(((run, run.rows[(name, digest)]) for run in harness_roots if (name, digest) in run.rows),
                       None)
        if not match and harness:
            run, (selected, call, label) = harness
            result.update(origin="deterministic-harness", api_endpoint=None, calls=0, cost_usd=str(spent + prior),
                          evidence=str(selected), harness_label=label, code_hashes=run.code_hashes)
            for problem_text in run.problems:
                fail(name, f"harness run {run.root} cannot certify this proof: {problem_text}")
            if call is not None:
                fail(name, f"{selected} records a model call; only unpaid deterministic proposals qualify")
        elif match:
            run, folder = match
            row = int(folder.name[1:])
            endpoint = run.authorization.get("api_endpoint")
            attempts = run.attempts(row)
            result.update(origin=str(folder), api_endpoint=endpoint, calls=len(attempts),
                          cost_usd=str(spent + prior))
            # Every call is stamped with its own endpoint (final60 ledger schema); a step sent
            # through the OpenAI-direct development transport fails even under an OpenRouter seal.
            foreign = sorted({str(item.get("api_endpoint")) for item in attempts
                              if "api_endpoint" in item and not via_openrouter(item.get("api_endpoint"))})
            if foreign:
                fail(name, f"run {run.root} recorded F{row:03} calls against {', '.join(foreign)}, not OpenRouter")
            if not via_openrouter(endpoint):
                fail(name, f"run {run.root} called {endpoint or 'an unrecorded endpoint'}, not OpenRouter")
            if run.report is None or not run.report.get("audit_passed"):
                fail(name, f"run {run.root} has no passing report.json (run report.py first)")
            for label, other in outside:
                piece = flat(body(other, statement))
                if len(piece) < MIN_LEAK_CHARS or sha(other) in originals:
                    continue
                for request, text in run.requests(folder):
                    if piece in text:
                        fail(name, f"model request {request.relative_to(run.root)} contains non-OpenRouter proof {label}")
                        break
        elif name in declared and declared[name].get("proof_sha256") == digest:
            item = declared[name]
            result.update(origin="manifest (self-declared)", api_endpoint=item.get("api_endpoint"),
                          cost_usd=str(Decimal(str(item.get("cost_usd", "0"))) + spent + prior),
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
    ap.add_argument("--jsonl", type=Path, required=True, help="benchmark JSONL (name, statement, src)")
    ap.add_argument("--submission", type=Path, required=True, help="submission JSONL (name, proof)")
    ap.add_argument("--run-root", type=Path, action="append", default=[], help="final-batch-next run root")
    ap.add_argument("--harness-root", type=Path, action="append", default=[],
                    help="route60 or unpaid route20 output directory (deterministic proposals, no model call); "
                         "counts only when the run used no team seeds, carried proofs or paid calls and "
                         "recorded the same proof-generating code as --harness-code")
    ap.add_argument("--harness-code", type=Path, default=HARNESS_CODE,
                    help="directory with the submitted harness's route files; --harness-root runs must have "
                         "recorded the same hashes (default: this checkout's experiments/final-batch-next)")
    ap.add_argument("--manifest", type=Path, help="JSON list of proofs produced by other runners")
    ap.add_argument("--non-openrouter", type=Path, action="append", default=[],
                    help="file or directory of proofs produced outside OpenRouter (.lean, .jsonl, .json)")
    ap.add_argument("--cap", type=Decimal, default=Decimal("3"))
    ap.add_argument("--json-out", type=Path, help="write the per-row result as JSON")
    a = ap.parse_args()
    try:
        roots = [RunRoot(path) for path in a.run_root]
        harness_roots = [HarnessRoot(path, a.harness_code) for path in a.harness_root]
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    manifest = json.loads(a.manifest.read_text()) if a.manifest else []
    outside = [pair for path in a.non_openrouter for pair in load_proofs(path)]
    result = check(load_jsonl(a.jsonl), load_jsonl(a.submission), roots, manifest, outside, a.cap, harness_roots)
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
