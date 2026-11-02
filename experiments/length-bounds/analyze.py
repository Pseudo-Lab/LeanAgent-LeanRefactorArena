"""Static, conditional length floors for the frozen final 60 problems.

No proof search, API calls, Lean execution, or claim of shortest proofs.
Run from anywhere: python3 -B /absolute/path/to/analyze.py
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
from lean_agent.evaluator import tokens


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values):
    return {"count": len(values), "sum": sum(values),
            "mean": statistics.mean(values), "median": statistics.median(values),
            "min": min(values), "max": max(values)}


def main():
    snapshot = REPO / "benchmarks/arena/final-d53690b057f9"
    dataset = snapshot / "benchmark_data_final.jsonl"
    provenance = json.loads((snapshot / "snapshot.json").read_text())
    if digest(dataset) != provenance["sha256"]:
        raise ValueError("Dataset differs from its frozen snapshot")
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    if len(rows) != 60 or len({r["name"] for r in rows}) != 60:
        raise ValueError("Expected the final 60 unique problems")
    records = []
    for number, row in enumerate(rows, 1):
        measured = tokens.proof_tokens(row["src"], row["statement"])
        rejection = None
        try:
            tokens.validate_declaration(row["src"], row["statement"])
        except ValueError as exc:
            rejection = str(exc)
        records.append({
            "problem_id": f"F{number:03}", "name": row["name"], "source": row["source"],
            "required_versions": row["version_info"],
            "dataset_reference_length": row["proof_length"],
            "local_reference_length": measured,
            "reference_metric_difference": measured - row["proof_length"],
            "reference_passes_local_text_gate": rejection is None,
            "reference_text_gate_rejection": rejection,
            "conditional_tactic_syntax_lower_bound": 2,
            "exact_minimum_length": None,
            "problem_specific_lower_bound_proved": False,
            "two_token_proof_found_in_this_analysis": False,
        })
    groups = defaultdict(list)
    for row in records:
        groups[row["source"]].append(row)
    def aggregate(group):
        return {
            "dataset_reference_length": describe([r["dataset_reference_length"] for r in group]),
            "local_reference_length": describe([r["local_reference_length"] for r in group]),
            "conditional_tactic_syntax_lower_bound": describe([r["conditional_tactic_syntax_lower_bound"] for r in group]),
            "exact_minima_established": 0,
        }
    report = {
        "schema_version": 1,
        "dataset_sha256": digest(dataset),
        "analysis_sha256": digest(Path(__file__)),
        "tokenizer_id": tokens.TOKENIZER_ID,
        "tokenizer_sha256": digest(Path(tokens.__file__)),
        "units": "Lexical source tokens of the proof body, including by; not LLM/BPE tokens",
        "scope": {"static_only": True, "model_api_calls": 0, "lean_compilations": 0,
                  "proof_search_performed": False, "official_worker_metric_verified": False},
        "interpretation": {
            "floor": "Conditional on successful ordinary tactic proofs accepted by the current local by-only gate: the by keyword and at least one tactic token require at least two tokens.",
            "not_attainability": "A floor of two does not show that any of the 60 problems has a two-token proof.",
            "not_exact": "Existence of a shortest proof does not supply an algorithm or a certificate of its length. No problem-specific optimality is established here.",
            "library": "Fixed source/version contexts are assumed. New free helper declarations and changes to imported libraries are not included.",
            "lemma_calls": "by exact helper has three tokens only when helper elaborates without explicit arguments. This is the length of a proposed construction, not a universal lower bound. No such helper is assumed to exist.",
            "official_scope": "The by-only floor is a local candidate-language restriction, not a verified competition-wide restriction. Allowing term proofs can admit one-token bodies.",
            "reference": "Reference lengths are measurements of supplied proofs, not proven minima. Text-gate and token-metric differences are retained explicitly; no official-valid upper bounds are certified by this static analysis.",
        },
        "overall": aggregate(records),
        "by_source": {source: aggregate(group) for source, group in sorted(groups.items())},
        "metric_differences": [{"problem_id": r["problem_id"], "dataset": r["dataset_reference_length"], "local": r["local_reference_length"]}
                               for r in records if r["reference_metric_difference"]],
        "reference_text_gate_rejections": [r["problem_id"] for r in records if not r["reference_passes_local_text_gate"]],
        "problems": records,
    }
    destination = HERE / "final60-length-bounds.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(destination), "overall": report["overall"],
                      "metric_differences": report["metric_differences"],
                      "reference_text_gate_rejections": report["reference_text_gate_rejections"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
