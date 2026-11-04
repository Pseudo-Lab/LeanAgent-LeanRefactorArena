"""Read-only post-run timing breakdown; never dispatches model calls."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def analyze(root):
    rows = []
    for arm in ("control", "treatment"):
        for folder in sorted((root / arm / "problems").iterdir()):
            totals = Counter()
            actions = Counter()
            # Aggregate only top-level evaluator results with timing, excluding
            # the shared preflight and nested historical cache evidence.
            paths = list(folder.glob("steps/**/result.json"))
            paths += list(folder.glob("compatibility/*/result.json"))
            paths += list(folder.glob("final/result.json"))
            for path in paths:
                result = read(path)
                for key, value in result.get("timing", {}).items():
                    totals[key] += value
            for path in folder.glob("steps/*/timing.json"):
                totals["api_seconds"] += read(path)["seconds"]
            for path in folder.glob("steps/*/event.json"):
                event = read(path)
                action = event.get("action") or {}
                actions[action.get("action", "rejected")] += 1
            start = root / "operator" / f"{arm}-{folder.name}-start.json"
            end = root / "operator" / f"{arm}-{folder.name}-end.json"
            if start.exists() and end.exists():
                # A coordinator resume returns completed trials without another
                # paid call, but rewrites its operator markers. Preserve the
                # first start/completion from archived recovery evidence.
                starts = [start, *(root / "operator/recoveries").glob(
                    f"*/{arm}-{folder.name}-start.json")]
                ends = [end, *(root / "operator/recoveries").glob(
                    f"*/{arm}-{folder.name}-end.json")]
                totals["trial_wall_seconds"] = (
                    min(datetime.fromisoformat(read(p)["at"]) for p in ends)
                    - min(datetime.fromisoformat(read(p)["at"]) for p in starts)
                ).total_seconds()
                totals["unattributed_runner_seconds"] = (
                    totals["trial_wall_seconds"] - totals["api_seconds"]
                    - totals["wall_seconds"]
                )
                pause = 0.0
                for progress in (root / "operator/recoveries").glob(
                        f"*/{arm}-{folder.name}-progress.json"):
                    saved = read(progress)
                    if saved.get("status") != "stopped":
                        continue
                    stopped = datetime.fromisoformat(saved["at"])
                    resumptions = [datetime.fromisoformat(read(p)["at"])
                                   for p in starts
                                   if datetime.fromisoformat(read(p)["at"]) > stopped]
                    if resumptions:
                        pause += (min(resumptions) - stopped).total_seconds()
                totals["operator_pause_seconds"] = pause
                totals["trial_active_wall_seconds"] = totals["trial_wall_seconds"] - pause
                totals["unattributed_active_runner_seconds"] = (
                    totals["unattributed_runner_seconds"] - pause)
            rows.append({"arm": arm, "problem": folder.name,
                         "timings": dict(totals), "actions": dict(actions)})
    return {"rows": rows,
            "note": "Shared preflight excluded. API, compiler and lock-wait sums are worker time; overlapping trials do not add to experiment wall time. Cache hits exclude historical compiler time. First start/completion markers include archived recovery evidence; interrupted trials include the operator pause in wall and unattributed time. Active wall fields subtract the recorded stopped-to-resumed interval, including waiting for an operator restart slot."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.root.resolve()), indent=2))
