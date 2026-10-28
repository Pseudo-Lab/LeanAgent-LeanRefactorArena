"""Durable stage records and read-only status queries; never resume an execution."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from .artifacts import sha


@dataclass
class Progress:
    journal: Journal
    stage: str = "setup"
    calls: int = 0
    failure_report: str | None = None
    active: dict | None = None

    def enter(self, stage, **details):
        if self.active:
            raise ValueError("Previous stage has no finish record: " + self.stage)
        self.stage, self.failure_report = stage, None
        self.active = self.journal.start(stage, details)

    def finish(self, outcome="passed", paths=(), candidate=None):
        if self.active:
            self.journal.finish(self.active, outcome, paths, candidate)
            self.active = None


class Journal:
    """Single-writer append-only journal. A partial trailing line is not an event."""
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "events.jsonl"
        self.path.touch(exist_ok=False)
        self.sequence = 0

    def append(self, event, **data):
        self.sequence += 1
        value = {"schema_version": 1, "sequence": self.sequence,
                 "time": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        encoded = (json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n").encode()
        with self.path.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return value

    def evidence(self, paths):
        refs = []
        for path in paths:
            path = Path(path)
            if not path.is_absolute():
                path = self.root / path
            if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
                raise ValueError("Stage evidence escapes run directory")
            refs.append({"path": str(path.relative_to(self.root)), "sha256": sha(path.read_bytes())})
        return refs

    def start(self, stage, details):
        return self.append("started", operation=self.sequence + 1, stage=stage, details=details)

    def finish(self, started, outcome, paths=(), candidate=None):
        return self.append("finished", operation=started["operation"], stage=started["stage"],
                           status=outcome, evidence=self.evidence(paths), candidate=candidate)

    def seal(self, outcome):
        self.append("run_finished", status=outcome, evidence=self.evidence(["result.json"]))


def read_json(path):
    return json.loads(path.read_bytes())


def validate_evidence(root, refs):
    for ref in refs:
        path = root / ref["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(root) or sha(path.read_bytes()) != ref["sha256"]:
            raise ValueError("Stage evidence is missing or changed: " + ref["path"])


def inspect(root):
    """Observe a snapshot without touching files or checking process liveness."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Run directory does not exist")
    value = {"schema_version": 1, "status": "unknown", "process_state": "unknown",
             "last_completed_stage": None, "last_finished_stage": None,
             "incomplete_stages": [], "latest_failure": None,
             "latest_verified_candidate": None, "final_verification": None,
             "final_result": None, "diagnostics": [], "record_error": None,
             "partial_trailing_record": False, "sealed": False}
    path = root / "events.jsonl"
    if not path.exists():
        value["record_error"] = "No stage journal; legacy run or recording has not started."
        return value
    data = path.read_bytes()
    active, ends, terminal = {}, [], None
    try:
        for number, line in enumerate(data.splitlines(keepends=True), 1):
            if not line.endswith(b"\n"):
                value["partial_trailing_record"] = True
                break
            row = json.loads(line)
            if row.get("schema_version") != 1 or row.get("sequence") != number or terminal:
                raise ValueError("Invalid stage journal sequence")
            if row["event"] == "started":
                if (row["operation"] != number or active or not isinstance(row.get("stage"), str)
                        or not isinstance(row.get("details"), dict)):
                    raise ValueError("Overlapping or invalid stage start")
                active[row["operation"]] = row
            elif row["event"] == "finished":
                start = active.pop(row["operation"], None)
                if start is None or start["stage"] != row["stage"] or row["status"] not in ("passed", "failed", "interrupted"):
                    raise ValueError("Stage finish does not match its start")
                candidate = row.get("candidate")
                if candidate is not None and (not isinstance(candidate, dict)
                        or not isinstance(candidate.get("sha256"), str)
                        or not isinstance(candidate.get("source"), str)):
                    raise ValueError("Invalid verified-candidate record")
                validate_evidence(root, row["evidence"])
                ends.append({**start, **row, "started_at": start["time"], "finished_at": row["time"]})
            elif row["event"] == "run_finished":
                if active:
                    raise ValueError("Run finished with an open stage")
                terminal = row
            else:
                raise ValueError("Unknown stage event")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        value["record_error"] = str(exc)

    value["incomplete_stages"] = [{**row, "status": "incomplete"} for row in active.values()]
    for row in ends:
        value["last_finished_stage"] = row
        if row["status"] == "passed":
            value["last_completed_stage"] = row
            if row.get("candidate") and row["stage"] in ("baseline", "candidate"):
                value["latest_verified_candidate"] = row["candidate"]
        else:
            value["latest_failure"] = row
        if row["stage"] == "final":
            value["final_verification"] = row
    value["status"] = "incomplete" if data else "unknown"

    # Only call a result final once result+journal were sealed in the inventory.
    # During a live read, an absent/partial seal is simply unconfirmed completion.
    if terminal and not value["record_error"] and not value["partial_trailing_record"]:
        try:
            inventory = read_json(root / "artifacts.json")
            result_bytes = (root / "result.json").read_bytes()
            result = json.loads(result_bytes)
            if (inventory["events.jsonl"] != sha(data) or inventory["result.json"] != sha(result_bytes)
                    or terminal["evidence"] != [{"path": "result.json", "sha256": sha(result_bytes)}]
                    or result["status"] != terminal["status"]):
                raise ValueError("Result or journal differs from the sealed records")
            value.update(status=result["status"], sealed=True)
            final = value["final_verification"]
            if (result["status"] == "completed" and result.get("replay", {}).get("record_replay_passed")
                    and final and final["status"] == "passed" and final.get("candidate")
                    and final["candidate"]["sha256"] == result.get("selected_sha256")):
                value["final_result"] = final["candidate"]
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            value["record_error"] = str(exc)
    if value["record_error"]:
        value.update(status="unknown", final_result=None, sealed=False)

    # Diagnoses are separate from process state and may appear while a run is active.
    for path in sorted((root / "diagnostics").glob("*.json")):
        try:
            report = read_json(path)
            if report.get("kind"):
                value["diagnostics"].append({"path": str(path.relative_to(root)),
                    **{key: report[key] for key in ("stage", "kind", "reason")}})
        except (ValueError, KeyError, TypeError, AttributeError):
            continue  # A concurrent writer may not have finished this file yet.
    return value


def describe(value):
    def stage(row):
        if not row:
            return "none"
        attempt = row.get("details", {}).get("attempt")
        return row["stage"] + (f" (attempt {attempt})" if attempt is not None else "")
    lines = ["Recorded status: " + value["status"],
             "Last completed stage: " + stage(value["last_completed_stage"]),
             "Completion unconfirmed: " + (", ".join(stage(row) for row in value["incomplete_stages"]) or "none"),
             "Process state: unknown (not inferred from missing records)",
             "Latest verified candidate: " + (value["latest_verified_candidate"] or {}).get("sha256", "none"),
             "Final result: " + (value["final_result"] or {}).get("sha256", "not confirmed")]
    if value["latest_failure"]:
        lines.append("Last failed/interrupted stage: " + stage(value["latest_failure"]))
    lines.extend(f"Diagnosis: {row['kind']} / {row['path']}" for row in value["diagnostics"])
    if value["record_error"]:
        lines.append("Record issue: " + value["record_error"])
    if value["partial_trailing_record"]:
        lines.append("Trailing journal write is incomplete; ignored for this snapshot.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = inspect(args.run_directory)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, indent=2) if args.json else describe(value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
