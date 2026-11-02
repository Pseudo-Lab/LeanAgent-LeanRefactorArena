"""Prepare pinned Arena work and screen development overlap; no Lean/model calls."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from lean_agent.evaluator.tokens import without_comments


def digest(value):
    return hashlib.sha256(value).hexdigest()


def statement_key(statement):
    # A conservative lexical screen, not Lean equivalence or alpha-equivalence.
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|«[^»]*»|[\w.\']+|[^\s]',
                        without_comments(statement))
    if len(tokens) > 1 and tokens[0] in {"theorem", "lemma"}:
        tokens[0] = "declaration"
        tokens[1] = "_declaration_name_"
    return tuple(tokens)


def read_rows(path, *, benchmark):
    raw = Path(path).read_bytes()
    rows, names = [], set()
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("expected a JSON object")
            for field in ("name", "source", "statement"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f"missing nonempty {field}")
            if row["name"] in names:
                raise ValueError("duplicate problem name: " + row["name"])
            if benchmark:
                if not isinstance(row.get("src"), str) or not row["src"].strip():
                    raise ValueError("missing nonempty src")
                if type(row.get("proof_length")) is not int or row["proof_length"] <= 0:
                    raise ValueError("proof_length must be a positive integer")
                pins, versions = row.get("version_info"), set()
                if not isinstance(pins, list) or not pins:
                    raise ValueError("version_info must be a nonempty list")
                for pin in pins:
                    if not isinstance(pin, dict) or len(pin) != 1:
                        raise ValueError("each version entry must contain exactly one pin")
                    version, commit = next(iter(pin.items()))
                    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\d+)?", version):
                        raise ValueError("unsupported Lean version label")
                    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                        raise ValueError("source commit must be a full lowercase SHA")
                    if version in versions:
                        raise ValueError("duplicate Lean version for one problem")
                    versions.add(version)
            statement_key(row["statement"])
            names.add(row["name"])
            rows.append((line_number, row))
        except (ValueError, TypeError) as error:
            raise ValueError(f"{path}: line {line_number}: {error}") from error
    if not rows:
        raise ValueError(f"{path}: empty dataset")
    return rows, digest(raw)


def build_plan(benchmark, sources=(), development=None):
    rows, benchmark_sha = read_rows(benchmark, benchmark=True)
    separation = {"status": "not_checked"}
    if development is not None:
        dev_rows, dev_sha = read_rows(development, benchmark=False)
        identities = {(row["source"], row["name"]) for _, row in rows}
        statements = {statement_key(row["statement"]) for _, row in rows}
        for line_number, row in dev_rows:
            if ((row["source"], row["name"]) in identities
                    or statement_key(row["statement"]) in statements):
                raise ValueError(f"development overlap at line {line_number}: {row['name']}")
        separation = {"status": "no_lexical_overlap_found", "development_sha256": dev_sha,
                      "semantic_or_family_overlap": "not_checked"}
    requested = set(sources)
    missing = requested - {row["source"] for _, row in rows}
    if missing:
        raise ValueError("unknown source filter: " + ", ".join(sorted(missing)))
    selected = [(line, row) for line, row in rows if not requested or row["source"] in requested]
    problems, environments, checks = [], {}, []
    for line_number, row in selected:
        problems.append({"name": row["name"], "source": row["source"], "input_line": line_number,
                         "statement_sha256": digest(row["statement"].encode()),
                         "reference_sha256": digest(row["src"].encode()),
                         "reference_tokens": row["proof_length"], "budget_key": row["name"]})
        for pin in row["version_info"]:
            version, commit = next(iter(pin.items()))
            identity = (row["source"], version, commit)
            environment_id = digest(json.dumps(identity).encode())
            environments[environment_id] = {"id": environment_id, "source": row["source"],
                                             "lean_version": version, "source_commit": commit}
            checks.append({"problem": row["name"], "environment": environment_id, "status": "not_run"})
    return {"schema_version": 1, "kind": "execution_plan", "benchmark_sha256": benchmark_sha,
            "input_problems": len(rows), "development_check": separation,
            "counts": {"problems": len(problems), "environments": len(environments),
                       "checks": len(checks), "by_source": dict(sorted(Counter(
                           row["source"] for row in problems).items()))},
            "problems": problems, "environments": sorted(environments.values(), key=lambda e: e["id"]),
            "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--source", action="append", default=[], help="Repeat to select sources")
    parser.add_argument("--development", type=Path, help="Optional development JSONL: name, source, statement")
    parser.add_argument("--output", type=Path, help="New JSON file; default: stdout")
    args = parser.parse_args()
    try:
        plan = build_plan(args.benchmark, args.source, args.development)
        payload = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(payload)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(payload)
            print(json.dumps({"output": str(args.output), **plan["counts"]}, ensure_ascii=False))
    except (ValueError, OSError, UnicodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
