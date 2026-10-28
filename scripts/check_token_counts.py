"""Calibrate the local token metric against an existing benchmark JSONL file."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refactor_eval.lean import sha256
from refactor_eval.session import write_json
from refactor_eval.tokens import TOKENIZER_ID, proof_tokens


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.benchmark.read_bytes()
    comparisons = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        count = proof_tokens(row["src"], row["statement"])
        comparisons.append({"name": row["name"], "reference": row["proof_length"],
                            "computed": count, "matches": count == row["proof_length"]})
    report = {"input_name": args.benchmark.name, "input_sha256": sha256(raw), "tokenizer": TOKENIZER_ID,
              "total": len(comparisons), "matched": sum(row["matches"] for row in comparisons),
              "comparisons": comparisons}
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if comparisons and all(row["matches"] for row in comparisons) else 1


if __name__ == "__main__":
    raise SystemExit(main())
