#!/usr/bin/env python3
"""Export verified Final references without treating them as candidate results."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

REPO = Path(__file__).resolve().parents[2]
DATASET_SHA = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"
TOKEN_SPEC = importlib.util.spec_from_file_location('final_dashboard_tokens', REPO / 'experiments/proof-analyze/proof_tokens.py')
TOKEN_MODULE = importlib.util.module_from_spec(TOKEN_SPEC)
TOKEN_SPEC.loader.exec_module(TOKEN_MODULE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-incomplete", action="store_true", help="Local preview only; publication requires all 60")
    args = parser.parse_args()
    dataset = REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"
    if hashlib.sha256(dataset.read_bytes()).hexdigest() != DATASET_SHA:
        raise ValueError("Final dataset bytes changed")
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    report = json.loads((REPO / "docs/measurements/final60-baselines.json").read_text())
    if report["dataset_sha256"] != DATASET_SHA or len(rows) != 60:
        raise ValueError("Final dataset/report scope differs")
    records = {p["id"]: p for p in report["problems"]}
    if len(records) != 60:
        raise ValueError("Missing or duplicate Final slots")
    if not args.allow_incomplete and (report["measured_problems"] != 60 or
            report.get("environment_verification", {}).get("status") != "passed"):
        raise ValueError("Publication requires all 60 and a passed final environment-byte verification")
    problems = []
    for index, row in enumerate(rows, 1):
        benchmark = f"F{index:03d}"
        record = records[benchmark]
        reference_sha = hashlib.sha256(row["src"].encode()).hexdigest()
        if TOKEN_MODULE.proof_length(row["src"], row["statement"]) != row["proof_length"]:
            raise ValueError("Final evaluator Length differs from dataset: " + benchmark)
        if (record["name"] != row["name"] or record["source"] != row["source"] or
                record["reference_sha256"] != reference_sha or record["provided_length"] != row["proof_length"]):
            raise ValueError("Final identity mismatch: " + benchmark)
        pins = [(version, revision) for item in row["version_info"] for version, revision in item.items()]
        expected = {row["source"] + "-" + version for version, _ in pins}
        measured = record.get("environments", {})
        if not set(measured) <= expected or (record["status"] == "measured" and set(measured) != expected):
            raise ValueError("Final environment coverage mismatch: " + benchmark)
        versions = []
        for version, revision in pins:
            environment = row["source"] + "-" + version
            value = measured.get(environment)
            samples = value["raw_samples"] if value else []
            if value:
                if (not value["valid"] or not samples or any(type(n) is not int or n < 0 for n in samples) or
                        statistics.median(samples) != value["median_raw_heartbeats"] or
                        statistics.median(n // 1000 for n in samples) != value["median_heartbeats"]):
                    raise ValueError("Invalid measured samples: " + benchmark + "/" + environment)
            versions.append({"version": version, "revision": revision, "environment": environment,
                             "status": "pass" if value else "pending", "rawSamples": samples,
                             "rawHeartbeats": value["median_raw_heartbeats"] if value else None,
                             "heartbeats": value["median_heartbeats"] if value else None})
        primary = versions[0]
        problems.append({
            "id": index, "name": row["name"], "source": row["source"], "status": "pending",
            "baseline": {"tokens": record["provided_length"], "heartbeats": primary["heartbeats"]}
                        if primary["status"] == "pass" else None,
            "candidate": None, "baselineCompatibility": 100 if len(measured) == len(pins) else None,
            "versions": [{"version": version, "revision": revision, "status": "pending"} for version, revision in pins],
            "environment": primary["environment"] + " · scaled heartbeat (raw // 1000)",
            "candidateHash": "", "evidence": ["docs/measurements/final60-baselines.md"],
            "note": "후보 미실행. 원본 측정과 후보 검증은 별도로 집계합니다.",
            "original": {"benchmarkId": benchmark, "sha256": reference_sha,
                         "providedTokens": record["provided_length"], "localTokens": record["local_length"],
                         "primaryEnvironment": primary["environment"], "versions": versions},
        })
    measured_at = max(p["measured_at"] for p in report["problems"] if p.get("measured_at"))
    snapshot = {"schemaVersion": 1, "id": "final60-baselines", "dataset": "final", "datasetSha256": DATASET_SHA,
                "label": "Final 60문제 · 원본 기준" if report["measured_problems"] == 60 else "Final 60문제 · 원본 측정 중",
                "measuredAt": measured_at, "releaseDate": "2026-11-01",
                "provenance": "고정 Final 원본의 Length·HB. 비교 Length는 Final 평가기의 arena-paper-compatible-v1과 일치하는 제공값; 별도 로컬 tokenizer 값도 보존. 신규 HB 버전별 1회, F001 기존 3회 보존. 공식 worker 결과 아님.",
                "problems": problems}
    public = REPO / "dashboard/public/data"
    filename = snapshot["id"] + ".json"
    (public / filename).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    index_path = public / "index.json"
    files = json.loads(index_path.read_text())
    index_path.write_text(json.dumps([filename] + [f for f in files if f != filename], ensure_ascii=False) + "\n")
    print("EXPORTED", len(problems), "references;", report["measured_problems"], "fully measured; candidate results 0")


if __name__ == "__main__":
    main()
