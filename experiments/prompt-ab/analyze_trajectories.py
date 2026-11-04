"""Offline candidate and gain analysis. No model calls or source mutations."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def analyze(root):
    rows = []
    for arm in ("control", "treatment"):
        for folder in sorted((root / arm / "problems").iterdir()):
            initial = read(folder / "initial-state.json")
            state = read(folder / "state.json")
            baseline = initial["baseline"]

            def score(value):
                return 100 - 100 / 3 * (
                    value["tokens"] / baseline["tokens"]
                    + value["raw_heartbeats"] / baseline["raw_heartbeats"])

            archive = state["exploration"]["candidates"]
            candidates = sorted((c for c in archive.values() if c.get("step", 0) > 0),
                                key=lambda c: c["step"])
            by_hash = {c["sha256"]: c for c in archive.values() if c["valid"]}
            seen = {c["sha256"] for c in initial["exploration"]["candidates"].values()}
            rank = initial["best"]["rank_numerator"]
            duplicates = non_improving = 0
            for candidate in candidates:
                duplicates += candidate["sha256"] in seen
                seen.add(candidate["sha256"])
                if candidate["valid"]:
                    non_improving += candidate["rank_numerator"] >= rank
                    rank = min(rank, candidate["rank_numerator"])
            improvements = []
            rejections = Counter()
            best_hash = initial["best"]["sha256"]
            previous_score = score(initial["best"])
            for path in sorted(folder.glob("steps/*/event.json")):
                event = read(path)
                if event.get("rejection"):
                    rejections[str(event["rejection"])] += 1
                if event["best_sha256"] != best_hash:
                    best_hash = event["best_sha256"]
                    current_score = score(by_hash[best_hash])
                    improvements.append({"step": event["step"],
                        "cost_usd": event["cost_usd_after"], "score": current_score,
                        "gain": current_score - previous_score,
                        "action": event["action"], "candidate_sha256": best_hash})
                    previous_score = current_score
            rows.append({"arm": arm, "problem": folder.name,
                "completed": (folder / "summary.json").exists(),
                "candidates": len(candidates),
                "valid_candidates": sum(c["valid"] for c in candidates),
                "valid_non_improving_incumbent": non_improving,
                "duplicate_source_candidates_including_seed": duplicates,
                "rejected_actions": dict(rejections), "improvements": improvements})
    return {"rows": rows, "note": "Exploration uses single-sample scores; final comparison uses fresh three-sample verification. Non-improvement is relative to the best rank available before that candidate. Source duplicates are exact hashes, not semantic equivalence."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.root.resolve()), ensure_ascii=False, indent=2))
