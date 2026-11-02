"""Offline structural audit of user-supplied final benchmark; never execute Lean."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics

from lean_agent.evaluator import tokens

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DATA = HERE / "benchmark_data_final.jsonl"
WARMUP = HERE.parent / "56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c/benchmark_data_warmup.jsonl"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    provenance = json.loads((HERE / "snapshot.json").read_text())
    if sha(DATA) != provenance["sha256"]:
        raise ValueError("Frozen dataset changed")
    rows = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]
    old = [json.loads(line) for line in WARMUP.read_text().splitlines() if line.strip()]
    old_by_name = {row["name"]: row for row in old}
    names = Counter(row["name"] for row in rows)
    pins = defaultdict(set)
    records, issues, overlap = [], [], []
    banned = re.compile(next(s for s in tokens.validate_declaration.__code__.co_consts
                             if isinstance(s, str) and "sorryAx" in s))
    for index, row in enumerate(rows, 1):
        item = {"row": index, "name": row["name"], "source": row["source"],
                "proof_length": row["proof_length"], "src_characters": len(row["src"]),
                "num_lines": row["num_lines"], "version_info": row["version_info"],
                "statement_sha256": hashlib.sha256(row["statement"].encode()).hexdigest(),
                "src_sha256": hashlib.sha256(row["src"].encode()).hexdigest()}
        if row["name"] in old_by_name:
            previous = old_by_name[row["name"]]
            overlap.append({"final_row": index, "warmup_row": next(i for i, r in enumerate(old, 1) if r["name"] == row["name"]),
                            "name": row["name"], "changed_fields": sorted(k for k in set(previous) | set(row)
                                                                         if previous.get(k) != row.get(k))})
        try:
            item["local_proof_tokens"] = tokens.proof_tokens(row["src"], row["statement"])
            item["statement_boundary_valid"] = True
            if item["local_proof_tokens"] != row["proof_length"]:
                issues.append({"kind": "local_token_metric_difference", "row": index, "name": row["name"],
                               "dataset": row["proof_length"], "local": item["local_proof_tokens"],
                               "note": "Local metric difference; not a claim that the dataset or current official metric is wrong."})
        except ValueError as error:
            item["statement_boundary_valid"] = False
            issues.append({"kind": "statement_or_proof_boundary", "row": index, "error": str(error)})
        try:
            tokens.validate_declaration(row["src"], row["statement"])
            item["current_harness_gate_passed"] = True
        except ValueError as error:
            item["current_harness_gate_passed"] = False
            body = tokens.without_comments(tokens.proof_body(row["src"], row["statement"]))
            matches = [{"token": m.group(), "context": body[max(0, m.start() - 50):m.end() + 80]}
                       for m in banned.finditer(body)]
            issues.append({"kind": "current_harness_gate_rejection", "row": index, "name": row["name"],
                           "error": str(error), "matches": matches,
                           "note": "Conservative text gate only; Lean compilation has not been attempted."})
        if row["num_lines"] != len(row["src"].splitlines()):
            issues.append({"kind": "num_lines_mismatch", "row": index})
        if "start_line" in row and row["end_line"] - row["start_line"] + 1 != row["num_lines"]:
            issues.append({"kind": "source_range_length_mismatch", "row": index})
        if len(row["src"]) > 12000:
            issues.append({"kind": "reference_exceeds_prior_p02_candidate_character_limit", "row": index,
                           "name": row["name"], "characters": len(row["src"]), "prior_limit": 12000})
        for pin in row["version_info"]:
            if not isinstance(pin, dict) or len(pin) != 1:
                raise ValueError("Unexpected version schema")
            for version, revision in pin.items():
                if not re.fullmatch(r"[0-9a-f]{40}", revision):
                    raise ValueError("Invalid source revision")
                pins[(row["source"], version)].add(revision)
        records.append(item)
    source_stats = {}
    for source in sorted({row["source"] for row in rows}):
        lengths = [row["proof_length"] for row in rows if row["source"] == source]
        source_stats[source] = {"count": len(lengths), "min_tokens": min(lengths),
                                "median_tokens": statistics.median(lengths), "max_tokens": max(lengths)}
    report = {"schema_version": 1, "inspection_date_kst": "2026-11-01", "dataset_sha256": sha(DATA),
              "audit_code_sha256": sha(Path(__file__)), "warmup_sha256": sha(WARMUP),
              "local_tokenizer": tokens.TOKENIZER_ID, "local_tokenizer_sha256": sha(Path(tokens.__file__)),
              "record_count": len(rows), "unique_names": len(names),
              "duplicate_names": {n: c for n, c in names.items() if c > 1}, "sources": source_stats,
              "source_version_pairs": len(pins), "problem_version_combinations": sum(len(r["version_info"]) for r in rows),
              "pins": [{"source": source, "version": version, "revisions": sorted(revisions)}
                       for (source, version), revisions in sorted(pins.items())],
              "pin_conflicts": [list(pair) for pair, revisions in pins.items() if len(revisions) != 1],
              "warmup_overlap": overlap, "new_problem_count": len(rows) - len(overlap),
              "missing_warmup": [{"warmup_row": i, "name": row["name"]} for i, row in enumerate(old, 1) if row["name"] not in names],
              "issue_counts": dict(Counter(issue["kind"] for issue in issues)), "issues": issues, "records": records,
              "scope": {"static_only": True, "lean_compilations": 0, "paid_api_calls": 0,
                        "remote_provenance_verified": False, "heartbeat_baselines_in_this_file": False},
              "notes": ["Putnam rows use header + src and Mathlib revisions; empty file_path/url and absent line ranges are expected.",
                        "Project rows require full repository context at each declared revision.",
                        "Warmup IDs and heartbeat baselines must not be reused by final row position."]}
    (HERE / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("record_count", "unique_names", "new_problem_count", "source_version_pairs",
                                          "problem_version_combinations", "issue_counts", "scope")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
