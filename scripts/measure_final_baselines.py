#!/usr/bin/env python3
"""Measure frozen Final references serially using already sealed environments.

No model calls, dependency updates, or builds. One problem completes before the
next starts. Missing environments stop the queue without recording fake results.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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
             "experiments/final-batch-next/fast_prepared.py", "experiments/final-batch-next/policy.py", "experiments/final-batch-next/resources.py",
             "src/lean_agent/prepared.py", "src/lean_agent/evaluator/lean.py",
             "src/lean_agent/evaluator/tokens.py"]
    return {name: sha((REPO / name).read_bytes()) for name in names}


@contextmanager
def verification_session(evaluator, root, markdown, boundary):
    """Keep full-byte checks at run boundaries and stat checks between jobs."""
    write(root / "environment-verification.json", {"status": "pending", "policy": boundary})
    try:
        yield
    finally:
        try:
            verified = {}
            with evaluator._compiler_lock():
                for name, prepared in evaluator._prepared.items():
                    state = evaluator._states[name]
                    current = json.loads((evaluator.root / "environments" / name / "environment.json").read_text())
                    if current != state:
                        raise ValueError("Environment metadata changed: " + name)
                    manifest = evaluator.repo / state["prepared_environment"]
                    if sha(manifest.read_bytes()) != state["prepared_manifest_sha256"]:
                        raise ValueError("Prepared manifest changed: " + name)
                    verified[name] = prepared.verify(full=boundary == "run")
            write(root / "environment-verification.json", {
                "status": "passed", "policy": boundary, "finished_at": now(), "environments": verified})
        except Exception as error:
            write(root / "environment-verification.json", {
                "status": "failed", "policy": boundary, "error": str(error)})
            write(root / "progress.json", {"status": "failed_environment_boundary", "updated_at": now(),
                                           "reason": str(error)})
            report(root, markdown)
            raise
        report(root, markdown)


def report(root, markdown):
    protocol = json.loads((root / "protocol.json").read_text())
    indexed = {}
    for boundary in protocol.get('history_boundaries', []):
        if sha(Path(boundary['path']).read_bytes()) != boundary['sha256']:
            raise ValueError('Historical environment verification changed')
    for history in protocol.get("history_records", []):
        path = Path(history["path"])
        if sha(path.read_bytes()) != history["sha256"]:
            raise ValueError("Historical record changed")
        record = json.loads(path.read_text())
        evidence = Path(record.get("evidence_root", str(path.parent))) / "evaluation/result.json"
        if sha(evidence.read_bytes()) != record["result_sha256"]:
            raise ValueError("Historical result changed")
        record["evidence_root"] = str(evidence.parent.parent)
        indexed[record["id"]] = record
    indexed.update({p.parent.name: json.loads(p.read_text()) for p in sorted(root.glob("F*/record.json"))})
    validation_path = root / "environment-verification.json"
    validation = json.loads(validation_path.read_text()) if validation_path.exists() else {"status": "per-problem"}
    if validation["status"] == "failed":
        # Do not publish current-run values after an environment-boundary failure.
        indexed = {k: v for k, v in indexed.items() if not (root / k / "record.json").exists()}
    records = [indexed[key] for key in sorted(indexed)]
    progress = json.loads((root / "progress.json").read_text())
    repetitions = protocol["repetitions"]
    text = ["# Final 60문제 원본 Length·HB 측정", "",
            f"갱신: {now()}", "",
            f"원본 dataset SHA256: `{DATASET_SHA}`. 모델 API 호출 0회.", "",
            "문제를 F001부터 순서대로 처리한다. 각 지정 버전의 새 Lean 프로세스에서 "
            f"원문 컴파일·공리 확인과 HB {repetitions}회 계측을 수행한다. 원본 단일 컴파일 모드는 "
            "protocol에 기록하며 이전의 별도 사전 컴파일 증거도 보존한다. 이미 완료한 복수 표본은 "
            "실제 횟수와 중앙값을 그대로 보존한다. 버전별 결과를 따로 보존하고, "
            "대표 HB는 dataset의 첫 번째 지정 버전 값을 사용한다. 공식 worker 점수는 아니다.", "",
            "Length는 제공 기준값과 로컬 tokenizer 결과를 구분한다. "
            "raw HB와 환산 HB(raw // 1000)도 분리하며 미측정 값을 0으로 채우지 않는다.", "",
            f"완료: {sum(r['status'] == 'measured' for r in records)}/60. "
            f"현재 상태: `{progress['status']}`. 환경 종료 검사: `{validation['status']}`.", "",
            "실행 중인 결과는 종료 시 전체 해시 검사가 끝날 때까지 잠정값이다. "
            "문제 사이에는 stat-cache와 원본 소스 해시 검사를 유지한다.", ""]
    if progress.get("reason"):
        text += ["현재 사유: " + progress["reason"], ""]
    text += ["| 문제 | 정리 | 제공 Length | 로컬 Length | 버전 | raw HB | 환산 HB | 실제 표본 수 |",
             "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |"]
    for record in records:
        for env, value in record.get("environments", {}).items():
            text.append(f"| {record['id']} | `{record['name']}` | {record['provided_length']} | "
                        f"{record['local_length']} | {env} | {value['median_raw_heartbeats']:,} | "
                        f"{value['median_heartbeats']:,} | {len(value['raw_samples'])} |")
    text += ["", "원시 소스·컴파일 로그·측정 표본·결과 해시는 다음 로컬 실행 폴더에 보관한다.", "",
             f"`{root}`", "", "동일 입력·환경·평가기의 검증된 캐시가 있으면 원래 표본을 재사용한다. "
             "그 밖의 HB는 새로 측정한다. 재사용한 결과의 cache 필드는 원래 증거 경로와 새 compiler 실행 0회를 기록한다.", ""]
    for source in sorted({r["evidence_root"] for r in records if "evidence_root" in r}):
        text += [f"- 기존 증거: `{source}`", ""]
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text("\n".join(text))
    lengths = json.loads((root / "lengths.json").read_text())
    for item in lengths:
        record = indexed.get(item["id"])
        if record:
            item.update({k: record[k] for k in ["status", "primary_environment", "environments", "measured_at",
                                               "seconds", "result_sha256", "environment_state_sha256"]})
            for value in item["environments"].values():
                value["measurement_count"] = len(value["raw_samples"])
        else:
            item.update(status="pending_environment", environments={})
    write(markdown.with_suffix(".json"), {
        "schema_version": 1, "dataset_sha256": DATASET_SHA,
        "scope": "Local original-reference measurements; not official worker scores",
        "tokenizer": "lean-source-anchored-v1", "default_hb_repetitions": repetitions,
        "measurement_policy": "One fresh HB sample per environment for new measurements; retain historical counts.",
        "environment_verification": validation,
        "total_problems": 60, "measured_problems": len(records), "next_problem": progress.get("next_problem"),
        "model_api_calls": 0, "problems": lengths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler-lock", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, default=REPO / "docs/measurements/final60-baselines.md")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--verification-boundary", choices=["run", "problem"], default="run")
    parser.add_argument("--evaluation-cache", type=Path,
                        help="Reuse verified identical problem/environment evidence; measure cache misses once")
    parser.add_argument("--separate-reference-check", action="store_true",
                        help="Compile the reference separately before its instrumented compile (legacy protocol)")
    parser.add_argument('--wait-for-environments', action='store_true',
                        help='Keep one verified evaluator session while the operator seals missing environments')
    parser.add_argument('--environment-wait-seconds', type=int, default=7200)
    parser.add_argument("--carry-forward", type=Path,
                        help="Retain verified completed evidence from an older frozen run")
    parser.add_argument("--history-root", type=Path, action="append", default=[],
                        help="Display earlier problem measurements in their original frozen environments")
    args = parser.parse_args()
    if not 1 <= args.limit <= 60:
        parser.error("--limit must be within 1..60")
    if not 1 <= args.start <= args.limit:
        parser.error("--start must be within 1..limit")
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if args.environment_wait_seconds < 1:
        parser.error('Environment wait must be positive')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    data = REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"
    assert sha(data.read_bytes()) == DATASET_SHA, "Dataset changed"
    rows = [json.loads(line) for line in data.read_text().splitlines() if line.strip()]
    assert len(rows) == 60
    registry = json.loads((REPO / "configs/final-environments.local.json").read_text())
    protocol = {"schema_version": 1, "dataset_sha256": DATASET_SHA,
                "repetitions": args.repetitions, "all_versions": True, "fresh": args.evaluation_cache is None,
                "evaluation_cache": str(args.evaluation_cache.resolve()) if args.evaluation_cache else None,
                "reference_single_pass": not args.separate_reference_check,
                "wait_for_environments": args.wait_for_environments,
                "environment_wait_seconds": args.environment_wait_seconds,
                "first_problem": args.start,
                "verification_boundary": args.verification_boundary,
                "ordering": "F001..F060, one problem at a time",
                "implementation_sha256": implementations(), "model_api_calls": 0}
    history = []
    history_boundaries = []
    for history_root in args.history_root:
        historical_protocol = json.loads((history_root / "protocol.json").read_text())
        if historical_protocol["dataset_sha256"] != DATASET_SHA or not historical_protocol["all_versions"]:
            raise ValueError("Historical dataset/scope differs")
        boundary = history_root / 'environment-verification.json'
        if boundary.exists():
            if json.loads(boundary.read_text()).get('status') != 'passed':
                raise ValueError('Historical run has not passed final environment verification')
            history_boundaries.append({'path': str(boundary.resolve()), 'sha256': sha(boundary.read_bytes())})
        elif historical_protocol.get('verification_boundary') == 'run':
            raise ValueError('Historical run is missing its final environment verification')
        for path in sorted(history_root.glob("F*/record.json")):
            value = json.loads(path.read_text())
            index = int(value["id"][1:])
            if index >= args.start:
                raise ValueError("Historical record overlaps the requested fresh measurement range")
            row = rows[index - 1]
            expected_envs = {row["source"] + "-" + version for pin in row["version_info"] for version in pin}
            if (value["reference_sha256"] != sha(row["src"].encode()) or value["status"] != "measured"
                    or set(value["environments"]) != expected_envs):
                raise ValueError("Historical reference/environment coverage differs")
            history.append({"path": str(path.resolve()), "sha256": sha(path.read_bytes())})
    if history:
        protocol["history_records"] = history
        protocol['history_boundaries'] = history_boundaries
    if args.carry_forward:
        previous_root = args.carry_forward.resolve()
        if previous_root == root:
            raise ValueError("Carry-forward requires a separate, immutable previous run")
        previous_protocol = json.loads((previous_root / "protocol.json").read_text())
        if (previous_protocol["dataset_sha256"] != DATASET_SHA
                or not previous_protocol["all_versions"]
                or previous_protocol["repetitions"] < args.repetitions):
            raise ValueError("Previous evidence does not meet the requested measurement scope")
        for name, digest in protocol["implementation_sha256"].items():
            if name != "scripts/measure_final_baselines.py" and previous_protocol["implementation_sha256"].get(name) != digest:
                raise ValueError("Previous evaluator implementation differs: " + name)
        protocol["carry_forward"] = {"root": str(previous_root),
                                     "protocol_sha256": sha((previous_root / "protocol.json").read_bytes())}
    protocol_path = root / "protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != protocol:
        raise ValueError("Frozen measurement protocol changed; use a new output root")
    write(protocol_path, protocol)
    for name, expected in protocol["implementation_sha256"].items():
        data_bytes = (REPO / name).read_bytes()
        if sha(data_bytes) != expected:
            raise ValueError("Implementation changed while freezing: " + name)
        snapshot = root / "implementation" / name
        if snapshot.exists() and snapshot.read_bytes() != data_bytes:
            raise ValueError("Saved implementation changed: " + name)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(data_bytes)
    lengths = [{"id": f"F{i:03d}", "name": row["name"], "source": row["source"],
                "provided_length": row["proof_length"],
                "local_length": proof_tokens(row["src"], row["statement"]),
                "reference_sha256": sha(row["src"].encode())}
               for i, row in enumerate(rows, 1)]
    write(root / "lengths.json", lengths)
    evaluator = FinalEvaluator(repo_root=REPO, global_lock_path=args.compiler_lock,
                               cache_root=args.evaluation_cache)
    progress = {"status": "running", "updated_at": now(), "next_problem": f"F{args.start:03d}"}
    write(root / "progress.json", progress)
    with verification_session(evaluator, root, args.markdown, args.verification_boundary):
        for index, row in enumerate(rows[args.start - 1:args.limit], args.start):
            item = lengths[index - 1]
            problem = evaluator.load_problem(index)
            wait_started, notified = time.monotonic(), None
            while True:
                registry = json.loads((REPO / 'configs/final-environments.local.json').read_text())
                missing = []
                for env in problem['environments']:
                    state_file = REPO / 'sources/final/environments' / env / 'environment.json'
                    state = json.loads(state_file.read_text()) if state_file.exists() else {}
                    if (env not in registry['environments'] or state.get('status') != 'ready'
                            or not state.get('prepared_environment') or not state.get('prepared_manifest_sha256')
                            or not any(loc['row'] == index for loc in state.get('locations', []))):
                        missing.append(env)
                if not missing:
                    break
                reason = f"{item['id']}의 고정 문맥 준비 필요: " + ", ".join(missing)
                waiting = args.wait_for_environments and time.monotonic() - wait_started < args.environment_wait_seconds
                marker = (tuple(missing), waiting)
                if marker != notified:
                    write(root / "progress.json", {"status": "waiting_environment" if waiting else "blocked_environment", "updated_at": now(),
                                               "next_problem": item["id"], "reason": reason})
                    report(root, args.markdown)
                    print(reason, flush=True)
                    notified = marker
                if not waiting:
                    return 2
                time.sleep(5)
            fingerprints = {env: sha((REPO / "sources/final/environments" / env /
                                      "environment.json").read_bytes()) for env in problem["environments"]}
            record_path = root / item["id"] / "record.json"
            if not record_path.exists() and args.carry_forward:
                previous = previous_root / item["id"] / "record.json"
                if previous.exists():
                    carried = json.loads(previous.read_text())
                    carried["evidence_root"] = carried.get("evidence_root", str(previous.parent))
                    # Validate before publishing a copied record or treating it as completed.
                    if (carried["reference_sha256"] != item["reference_sha256"]
                            or carried["environment_state_sha256"] != fingerprints
                            or carried["status"] != "measured"):
                        raise ValueError("Previous source/environment differs")
                    evidence = Path(carried["evidence_root"]) / "evaluation/result.json"
                    if sha(evidence.read_bytes()) != carried["result_sha256"]:
                        raise ValueError("Previous measurement evidence changed")
                    if set(carried["environments"]) != set(problem["environments"]):
                        raise ValueError("Previous environment coverage differs")
                    if any(len(v["raw_samples"]) < args.repetitions for v in carried["environments"].values()):
                        raise ValueError("Previous sample count is insufficient")
                    write(record_path, carried)
            if record_path.exists():
                record = json.loads(record_path.read_text())
                if (record["reference_sha256"] != item["reference_sha256"] or
                        record["environment_state_sha256"] != fingerprints or record["status"] != "measured"):
                    raise ValueError("Stored measurement does not match frozen source/environment")
                result_file = Path(record.get("evidence_root", str(record_path.parent))) / "evaluation/result.json"
                if sha(result_file.read_bytes()) != record["result_sha256"]:
                    raise ValueError("Stored measurement evidence changed")
                current = evaluator.verify_environments(problem, full=False)
                if current != record["environment_fingerprints"]:
                    raise ValueError("Stored environment fingerprint changed")
                print("RETAIN", item["id"], flush=True)
                continue
            print("MEASURE", item["id"], row["name"], flush=True)
            started = time.monotonic()
            initial = evaluator.verify_environments(problem, full=args.verification_boundary == "problem")
            result = evaluator.evaluate(row["src"], problem, record_path.parent / "evaluation",
                                        repetitions=args.repetitions, all_versions=True, trusted_reference=True,
                                        fresh=args.evaluation_cache is None,
                                        reference_single_pass=not args.separate_reference_check)
            final = evaluator.verify_environments(problem, full=args.verification_boundary == "problem")
            assert initial == final, "Prepared environment changed during measurement"
            if not result["valid"]:
                write(root / "progress.json", {"status": "failed_measurement", "updated_at": now(),
                                               "next_problem": item["id"], "reason": str(result["error"])})
                report(root, args.markdown)
                print("FAILED", item["id"], result["error"], flush=True)
                return 1
            environments = {}
            for env, value in result["environments"].items():
                if evaluator.cache is not None:
                    evaluator.cache.audit_reuse(value, problem=problem, code=row["src"], environment=env)
                samples = [r["measurement"]["raw"] for r in value["runs"] if "measurement" in r]
                assert len(samples) == args.repetitions and statistics.median(samples) == value["median_raw_heartbeats"]
                environments[env] = {"valid": True, "raw_samples": samples,
                                     "median_raw_heartbeats": value["median_raw_heartbeats"],
                                     "median_heartbeats": value["median_heartbeats"]}
                if value.get("cache"):
                    environments[env]["cache"] = value["cache"]
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
