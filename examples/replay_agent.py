"""Offline protocol demo: emit a broken proof, then repair it, then stop.

Replace this command with an API/agent adapter. Diagnostics go to stderr;
stdout must contain exactly one JSON object or null.
"""
import json
from pathlib import Path
import sys

feedback = json.load(sys.stdin)
paths = ["broken.lean", "short.lean"]
index = feedback["candidate_count"]
if index >= len(paths):
    print("null")
else:
    root = Path(__file__).parent / "basic"
    print(json.dumps({"code": (root / paths[index]).read_text(),
                      "parent_id": feedback["latest_candidate_id"],
                      "note": "Offline replay; no model/API call"}))
