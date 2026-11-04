#!/usr/bin/env python3
"""Reproduce 80 dashboard candidate diffs and a small evidence-backed hint bank.

Offline analysis only. Lexical changes flag possible transformations; paired
metrics describe the WHOLE candidate, never the causal effect of one edit.
The separately distributed official input is required and SHA-checked.
"""
import argparse
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lean_agent import strategy_bank as sb
from lean_agent.evaluator.tokens import without_comments

DATASET = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"

# Curated reusable instructions. Evidence assignment below is explicitly lexical.
# Scoring/condition semantics follow PR #50, without importing experiment loaders.
CARDS = [
    {"id": "D01", "title": "Inline or remove redundant intermediate facts",
     "match": {"tactic_min": {"have": 3}},
     "guide": "Inspect intermediate have facts and their uses. Try inlining a single-use fact or removing one unused fact; check the complete declaration after each candidate.",
     "risks": "Apparently unused facts can support inference or automation. Removing them can break elaboration or increase heartbeats."},
    {"id": "D02", "title": "Focus broad automation",
     "match": {"tactic_min": {"grind": 1, "aesop": 1, "simp_all": 1}},
     "guide": "Inspect one broad automation call. Try a direct lemma, explicit arithmetic certificate, or focused sufficient facts instead of searching the whole context.",
     "risks": "Lexical frequency is not a heartbeat profile. Preserve required unfolding and side conditions; a direct replacement may be longer or version-sensitive."},
    {"id": "D03", "title": "Consolidate calculation and rewrite chains",
     "match": {"tactic_min": {"calc": 1, "rw": 3}},
     "guide": "Inspect a long calculation or rewrite chain. Search the current context for an identity or bound that replaces intermediate equalities; preserve casts and nonzero assumptions.",
     "risks": "An identity may not match the required type or orientation. Fewer source steps do not establish a lower verification cost."},
    {"id": "D04", "title": "Reduce repeated case analysis",
     "match": {"tactic_min": {"cases": 2, "rcases": 3, "induction": 1}},
     "guide": "Look for a predicate lemma, shared branch argument, or appropriate induction principle that removes repeated decomposition. Retain branches whose local assumptions differ.",
     "risks": "Do not merge incompatible branches or change the induction invariant. Required constructors and available principles depend on the pinned environment."},
    {"id": "D05", "title": "Replace manual witnesses with a sufficient library result",
     "match": {"tactic_min": {"refine": 2, "have": 4}},
     "guide": "For an explicit witness construction, search available lemmas for the exact existence, cardinality, support or derivative property needed. Prefer a sufficient result over proving a stronger characterization.",
     "risks": "New lemma names in a diff are only a clue, not proof of transfer. Check assumptions, namespace, arity and every required version."},
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def changes(original, candidate):
    a, b = sb.features(original)["counts"], sb.features(candidate)["counts"]
    ids = []
    if b["have"] < a["have"]: ids.append("D01")
    if sum(b[t] for t in ("grind", "aesop", "simp_all")) < sum(a[t] for t in ("grind", "aesop", "simp_all")):
        ids.append("D02")
    if b["calc"] < a["calc"] or a["rw"] - b["rw"] >= 2: ids.append("D03")
    if sum(b[t] for t in ("cases", "rcases", "induction")) < sum(a[t] for t in ("cases", "rcases", "induction")):
        ids.append("D04")
    import re
    def lemmas(code):
        return set(re.findall(r"\b(?:exact|apply|refine|rw|simp)\s+(?:only\s+)?\[?([\w.']+)", without_comments(code)))
    old_identifiers = set(re.findall(r"[\w.']+", without_comments(original)))
    if (a["refine"] > b["refine"] or a["have"] - b["have"] >= 2) and lemmas(candidate) - old_identifiers:
        ids.append("D05")
    return ids


def candidates(root):
    data = root / "dashboard/public/data"
    for filename, key, author, level in (
        ("final-results.json", "problems", "권주원", "run-manifest"),
        ("physlib-cslib-results.json", "results", "정소미", "published-summary"),
        ("team-shared-results.json", "problems", None, "shared-report"),
    ):
        source = data / filename
        document = json.loads(source.read_text())
        dataset = document.get("datasetSha256", document.get("dataset_sha256"))
        if dataset != DATASET: raise ValueError("Dashboard dataset identity differs")
        for row in document[key]:
            if key == "results":
                baseline = {"tokens": row["original_tokens"], "raw_heartbeats": row["original_raw_heartbeats"]}
                candidate = {"tokens": row["candidate_tokens"], "raw_heartbeats": row["candidate_raw_heartbeats"]}
                expected = row["proof_sha256"]
            else:
                baseline, candidate = row["baseline"], row["candidate"]
                expected = row["candidateHash"]
            proof = row["proof"]
            if digest(proof.encode()) != expected: raise ValueError("Candidate hash differs: " + row["name"])
            yield row, proof, baseline, candidate, author or row["author"], level, str(source.relative_to(root))


def build(benchmark, root=ROOT):
    raw = Path(benchmark).read_bytes()
    if digest(raw) != DATASET: raise ValueError("Expected exact pinned final benchmark bytes")
    originals = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    by_name = {p["name"]: p for p in originals}
    if len(originals) != 60 or len(by_name) != 60: raise ValueError("Expected 60 unique originals")
    rows, files, seen = [], {}, set()
    for i, (p, proof, base, cand, author, level, source_file) in enumerate(candidates(root), 1):
        original = by_name[p["name"]]
        if (p["name"], author) in seen: raise ValueError("Duplicate dashboard candidate")
        seen.add((p["name"], author))
        if p["row"] != originals.index(original) + 1: raise ValueError("Row/name mismatch")
        for metrics in (base, cand):
            if any(type(metrics[k]) is not int or metrics[k] <= 0 for k in ("tokens", "raw_heartbeats")):
                raise ValueError("Expected positive paired metrics")
        ratio = cand["tokens"] / base["tokens"] + cand["raw_heartbeats"] / base["raw_heartbeats"]
        tags = changes(original["src"], proof) if ratio < 2 else []
        path = f"diffs/{i:03}-F{p['row']:03}.diff"
        diff = "\n".join(difflib.unified_diff(original["src"].splitlines(), proof.splitlines(),
                                         fromfile="original", tofile="candidate", lineterm=""))
        files[path] = diff.encode()
        rows.append({"problem": p["name"], "row": p["row"], "author": author, "source": original["source"],
                     "original_sha256": digest(original["src"].encode()), "candidate_sha256": digest(proof.encode()),
                     "candidate_path": p["proofPath"], "source_document": source_file,
                     "baseline": {k: base[k] for k in ("tokens", "raw_heartbeats")},
                     "candidate": {k: cand[k] for k in ("tokens", "raw_heartbeats")},
                     "paired_ratio_sum": ratio, "evidence_level": level, "diff": path,
                     "diff_sha256": digest(files[path]), "strategy_candidates": tags,
                     "classification": "lexical-hypothesis-not-isolated-effect",
                     "versions": p.get("versions"), "checks": p.get("checks"), "official_evaluation": False})
    if len(rows) != 80: raise ValueError("Expected all 80 dashboard candidates")
    bank_cards = []
    for card in CARDS:
        evidence = [{"problem": r["problem"], "candidate_sha256": r["candidate_sha256"]}
                    for r in rows if card["id"] in r["strategy_candidates"]]
        if evidence: bank_cards.append({**card, "evidence": evidence})
    bank = {"schema_version": 1, "version": "dashboard-diff-v1", "scope": "final-adaptation", "strategies": bank_cards}
    sb.validate(bank)
    files["bank.json"] = encoded(bank)
    files["evidence.json"] = encoded({"schema_version": 1, "dataset_sha256": DATASET,
                                     "method": "whole-candidate paired observations; lexical classification; no causal/generalization claims",
                                     "candidates": rows})
    summary = {c["id"]: {"candidate_observations": sum(c["id"] in r["strategy_candidates"] for r in rows),
                          "distinct_problems": len({r["problem"] for r in rows if c["id"] in r["strategy_candidates"]})}
               for c in bank_cards}
    files["summary.json"] = encoded({"candidates": len(rows), "problems": len(by_name),
                                     "authors": dict(Counter(r["author"] for r in rows)), "strategies": summary})
    files["manifest.json"] = encoded({"schema_version": 1, "dataset_sha256": DATASET,
                                      "files": {name: digest(value) for name, value in sorted(files.items())}})
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=ROOT / "strategy-bank/dashboard-v1")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--attach-config", type=Path, help="Read a common CLI config and emit a NEW config with embedded bank")
    ap.add_argument("--config-output", type=Path)
    args = ap.parse_args()
    files = build(args.benchmark)
    for name, value in files.items():
        path = args.output / name
        if args.check:
            if not path.is_file() or path.read_bytes() != value: raise ValueError("Generated evidence differs: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
    if args.attach_config:
        if not args.config_output or args.config_output.exists(): raise ValueError("Provide a new --config-output")
        config = json.loads(args.attach_config.read_text())
        if config.get("agent", {}).get("mode") != "actions-v1": raise ValueError("Expected actions-v1 config")
        # Config-relative paths must keep their meaning at the new location.
        for key in ("problem", "template", "project", "prompt"):
            config[key] = str((args.attach_config.parent / config[key]).resolve())
        config["agent"]["corpus"] = str((args.attach_config.parent / config["agent"]["corpus"]).resolve())
        for owner, key in ((config["model"], "responses"), (config["lean"], "prepared_environment"),
                           (config.get("usage_cost", {}), "prices")):
            if key in owner: owner[key] = str((args.attach_config.parent / owner[key]).resolve())
        config["agent"]["strategy_bank"] = {"bank": json.loads(files["bank.json"]), "top_k": 3}
        args.config_output.parent.mkdir(parents=True, exist_ok=True)
        args.config_output.write_bytes(encoded(config))
    print(files["summary.json"].decode())


if __name__ == "__main__":
    main()
