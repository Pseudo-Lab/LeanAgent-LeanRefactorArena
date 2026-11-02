#!/usr/bin/env python3
"""Measure frozen Final references serially using already sealed environments.

No model calls, dependency updates, or builds. One problem completes before the
next starts. Missing environments stop the queue without recording fake results.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "experiments/final-batch-next")]
from evaluator import FinalEvaluator
from lean_agent.evaluator.tokens import proof_tokens

DATASET_SHA = "d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def implementations():
    names = ["scripts/measure_final_baselines.py", "experiments/final-batch-next/evaluator.py",
             "experiments/final-batch-next/policy.py", "experiments/final-batch-next/resources.py",
             "src/lean_agent/prepared.py", "src/lean_agent/evaluator/lean.py",
             "src/lean_agent/evaluator/tokens.py"]
    return {name: sha((REPO / name).read_bytes()) for name in names}


def report(root, markdown):
    records = [json.loads(p.read_text()) for p in sorted(root.glob("F*/record.json"))]
    progress = json.loads((root / "progress.json").read_text())
    text = ["# Final 60문제 원본 Length·HB 측정", "",
            f"갱신: {now()}", "",
            f"원본 dataset SHA256: `{DATASET_SHA}`. 모델 API 호출 0회.", "",
            "문제를 F001부터 순서대로 처리한다. 각 지정 버전에서 원문 컴파일·공리 확인 후 "
            "새 Lean 프로세스 3회로 HB를 측정한다. 버전별 중앙값을 따로 보존하고, "
            "대표 HB는 dataset의 첫 번째 지정 버전 값을 사용한다. 공식 worker 점수는 아니다.", "",
            "Length는 제공 기준값과 로컬 tokenizer 결과를 구분한다. "
            "raw HB와 환산 HB(raw // 1000)도 분리하며 미측정 값을 0으로 채우지 않는다.", "",
            f"완료: {sum(r['status'] == 'measured' for r in records)}/60. "
            f"현재 상태: `{progress['status']}`.", ""]
    if progress.get("reason"):
        text += ["현재 사유: " + progress["reason"], ""]
    text += ["| 문제 | 정리 | 제공 Length | 로컬 Length | 버전 | raw HB 중앙값 | 환산 HB | 새 표본 수 |",
             "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |"]
    for record in records:
        for env, value in record.get("environments", {}).items():
            text.append(f"| {record['id']} | `{record['name']}` | {record['provided_length']} | "
                        f"{record['local_length']} | {env} | {value['median_raw_heartbeats']:,} | "
                        f"{value['median_heartbeats']:,} | {len(value['raw_samples'])} |")
    text += ["", "원시 소스·컴파일 로그·측정 표본·결과 해시는 다음 로컬 실행 폴더에 보관한다.", "",
             f"`{root}`", "", "환경 빌드 산출물은 재사용하되 이 실행의 HB 표본은 캐시에서 가져오지 않는다.", ""]
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text("\n".join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler-lock", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, default=REPO / "docs/measurements/final60-baselines.md")
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.limit <= 60:
        parser.error("--limit must be within 1..60")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    data = REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"
    assert sha(data.read_bytes()) == DATASET_SHA, "Dataset changed"
    rows = [json.loads(line) for line in data.read_text().splitlines() if line.strip()]
    assert len(rows) == 60
    registry = json.loads((REPO / "configs/final-environments.local.json").read_text())
    protocol = {"schema_version": 1, "dataset_sha256": DATASET_SHA,
                "repetitions": 3, "all_versions": True, "fresh": True,
                "ordering": "F001..F060, one problem at a time",
                "implementation_sha256": implementations(), "model_api_calls": 0}
    protocol_path = root / "protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != protocol:
        raise ValueError("Frozen measurement protocol changed; use a new output root")
    write(protocol_path, protocol)
    lengths = [{"id": f"F{i:03d}", "name": row["name"], "source": row["source"],
                "provided_length": row["proof_length"],
                "local_length": proof_tokens(row["src"], row["statement"]),
                "reference_sha256": sha(row["src"].encode())}
               for i, row in enumerate(rows, 1)]
    write(root / "lengths.json", lengths)
    evaluator = FinalEvaluator(repo_root=REPO, global_lock_path=args.compiler_lock)
    progress = {"status": "running", "updated_at": now(), "next_problem": "F001"}
    write(root / "progress.json", progress)
    for index, row in enumerate(rows[:args.limit], 1):
        item = lengths[index - 1]
        problem = evaluator.load_problem(index)
        missing = []
        for env in problem["environments"]:
            state_file = REPO / "sources/final/environments" / env / "environment.json"
            state = json.loads(state_file.read_text()) if state_file.exists() else {}
            if (env not in registry["environments"] or state.get("status") != "ready"
                    or not any(loc["row"] == index for loc in state.get("locations", []))):
                missing.append(env)
        if missing:
            reason = f"{item['id']}의 고정 문맥 준비 필요: " + ", ".join(missing)
            write(root / "progress.json", {"status": "blocked_environment", "updated_at": now(),
                                           "next_problem": item["id"], "reason": reason})
            report(root, args.markdown)
            print(reason, flush=True)
            return 2
        fingerprints = {env: sha((REPO / "sources/final/environments" / env /
                                  "environment.json").read_bytes()) for env in problem["environments"]}
        record_path = root / item["id"] / "record.json"
        if record_path.exists():
            record = json.loads(record_path.read_text())
            if (record["reference_sha256"] != item["reference_sha256"] or
                    record["environment_state_sha256"] != fingerprints or record["status"] != "measured"):
                raise ValueError("Stored measurement does not match frozen source/environment")
            result_file = record_path.parent / "evaluation/result.json"
            if sha(result_file.read_bytes()) != record["result_sha256"]:
                raise ValueError("Stored measurement evidence changed")
            print("RETAIN", item["id"], flush=True)
            continue
        print("MEASURE", item["id"], row["name"], flush=True)
        started = time.monotonic()
        initial = evaluator.verify_environments(problem, full=True)
        result = evaluator.evaluate(row["src"], problem, record_path.parent / "evaluation",
                                    repetitions=3, all_versions=True, trusted_reference=True, fresh=True)
        final = evaluator.verify_environments(problem, full=True)
        assert initial == final, "Prepared environment changed during measurement"
        if not result["valid"]:
            write(root / "progress.json", {"status": "failed_measurement", "updated_at": now(),
                                           "next_problem": item["id"], "reason": str(result["error"])})
            report(root, args.markdown)
            print("FAILED", item["id"], result["error"], flush=True)
            return 1
        environments = {}
        for env, value in result["environments"].items():
            samples = [r["measurement"]["raw"] for r in value["runs"] if "measurement" in r]
            assert len(samples) == 3 and statistics.median(samples) == value["median_raw_heartbeats"]
            environments[env] = {"valid": True, "raw_samples": samples,
                                 "median_raw_heartbeats": value["median_raw_heartbeats"],
                                 "median_heartbeats": value["median_heartbeats"]}
        record = {**item, "status": "measured", "measured_at": now(),
                  "seconds": round(time.monotonic() - started, 3),
                  "primary_environment": problem["environments"][0], "environments": environments,
                  "environment_state_sha256": fingerprints, "environment_fingerprints": final,
                  "result_sha256": sha((record_path.parent / "evaluation/result.json").read_bytes())}
        write(record_path, record)
        write(root / "progress.json", {"status": "running", "updated_at": now(),
                                       "next_problem": f"F{index+1:03d}" if index < 60 else None})
        report(root, args.markdown)
        print("DONE", item["id"], json.dumps(environments), flush=True)
    write(root / "progress.json", {"status": "complete" if args.limit == 60 else "checkpoint",
                                   "updated_at": now(), "next_problem": f"F{args.limit+1:03d}" if args.limit < 60 else None})
    report(root, args.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
