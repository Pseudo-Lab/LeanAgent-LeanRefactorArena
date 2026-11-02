#!/usr/bin/env python3
"""Run baseline/actions through real Lean with scripted responses. No model API."""
import argparse
import json
from pathlib import Path
import time

from lean_agent import artifacts, harness

HERE = Path(__file__).resolve().parent


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for condition, filename in (("whole", "baseline.json"), ("actions-memory", "smoke.json")):
        started = time.monotonic()
        result = harness.run(HERE / filename, output / condition)
        replay = harness.replay(output / condition)
        memory = result["state"].get("exploration")
        candidates = memory["candidates"] if memory else {}
        rows.append({"condition": condition, "model_backend": "fixture", "model_calls": result["state"]["calls"],
            "reported_cost_usd": result["state"]["cost_usd"], "stop_reason": result["stop_reason"],
            "baseline": result["state"]["baseline"], "final": result["final"],
            "final_valid": result["final_valid"], "selected_sha256": result["state"]["best"]["sha256"],
            "candidate_evaluations": sum((step / "evaluation/result.json").exists()
                                         for step in (output / condition / "steps").iterdir()),
            "archive_count": len(candidates) if memory else None,
            "ancestry": [{"id": cid, "parent_id": row["parent_id"], "valid": row["valid"]}
                         for cid, row in candidates.items()],
            "record_replay_passed": replay["record_replay_passed"],
            "wall_seconds": round(time.monotonic() - started, 3)})
    report = {"schema_version": 1, "experiment": "action-candidate-memory", "official_evaluation": False,
        "purpose": "Scripted control-flow verification with real Lean; not evidence of model quality or cost savings.",
        "same_proposals": True, "conditions": rows,
        "same_selected_source": rows[0]["selected_sha256"] == rows[1]["selected_sha256"]}
    artifacts.write(output / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not all(row["final_valid"] and row["record_replay_passed"] for row in rows):
        raise ValueError("Smoke verification failed")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    run(parser.parse_args().output)
