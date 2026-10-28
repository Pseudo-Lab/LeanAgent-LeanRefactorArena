#!/usr/bin/env python3
"""Read live experiment progress; save a final cost/quality trajectory offline."""
import argparse
from collections import Counter
from decimal import Decimal
from datetime import datetime
import json
from pathlib import Path
from statistics import mean, median

import compare as c
from lean_agent import harness as h


def inspect(root):
    ledger = c.read(root / "budget.json")
    attempts = ledger["attempts"]
    charges = [a for a in attempts.values() if a["cost_usd"] is not None]
    total = sum((c.money(a["cost_usd"]) for a in charges), Decimal(0))
    native = root / "harness"
    baseline_path = native / "initial-state.json"
    initial = c.read(baseline_path) if baseline_path.exists() else None
    rows, seen, valid_seen = [], Counter(), Counter()
    previous = initial["best"]["sha256"] if initial else None
    for folder in sorted((native / "steps").glob("*"), key=lambda p: int(p.name)):
        if not (folder / "event.json").exists():
            continue
        try:
            state = c.read(folder / "event.json")["state_after"]
            response = c.read(folder / "response.json")
        except (ValueError, KeyError):
            continue  # A live writer may still be flushing this last event.
        path = folder / "candidate.lean"
        proof_hash = c.sha(path.read_bytes()) if path.exists() else None
        valid = state["latest"]["feedback"].get("valid", False)
        if proof_hash:
            seen[proof_hash] += 1
            if valid:
                valid_seen[proof_hash] += 1
        best = state["best"]
        base = state["baseline"]
        score = best["rank_numerator"] / (2 * base["tokens"] * base["raw_heartbeats"])
        rows.append({"step": int(folder.name), "cumulative_usd": state["cost_usd"],
            "cost_usd": c.models.receipt(response)["cost_usd"], "valid": valid,
            "candidate_sha256": proof_hash, "duplicate_source": bool(proof_hash and seen[proof_hash] > 1),
            "best_sha256": best["sha256"], "best_source_changed": best["sha256"] != previous,
            "best_tokens": best["tokens"], "best_raw_heartbeats": best["raw_heartbeats"], "local_score": score,
            "usage": response.get("usage"), "feedback_status": state["latest"]["feedback"].get("status")})
        previous = best["sha256"]
    changes = [r for r in rows if r["best_source_changed"]]
    last_change = changes[-1] if changes else None
    eighty = None
    if rows and rows[-1]["local_score"] < 1:
        score_target = 1 - 0.8 * (1 - rows[-1]["local_score"])
        eighty = next(r for r in rows if r["local_score"] <= score_target)
    native_result = c.read(native / "result.json") if (native / "result.json").exists() else None
    return {"paid_calls": len(attempts), "settled_calls": sum(a["status"] == "settled" for a in attempts.values()),
            "evaluated_calls": len(rows), "known_cost_usd": str(total), "native_result": native_result,
            "candidate_valid": sum(r["valid"] for r in rows), "unique_candidate_sources": len(seen),
            "unique_valid_sources": len(valid_seen), "duplicate_candidate_sources": sum(r["duplicate_source"] for r in rows),
            "best_source_changes": len(changes), "latest_best_change_step": last_change["step"] if last_change else 0,
            "eighty_percent_of_observed_improvement_step": eighty["step"] if eighty else None,
            "eighty_percent_of_observed_improvement_cost_usd": eighty["cumulative_usd"] if eighty else None,
            "latest_best_change_cost_usd": last_change["cumulative_usd"] if last_change else "0",
            "cost_after_last_best_change_usd": str(total - c.money(last_change["cumulative_usd"]) if last_change else total),
            "best": {k: rows[-1][k] for k in ["best_tokens", "best_raw_heartbeats", "local_score"]} if rows else None,
            "trajectory": rows}


def final(root, result):
    native = root / "harness"
    replay = h.replay(native)
    report = c.read(root / "report.json")
    rows = result["trajectory"]
    cumulative_before_last = Decimal(rows[-2]["cumulative_usd"]) if len(rows) > 1 else Decimal(0)
    threshold = Decimal(report["budget_usd"])
    assert report["stop_reason"] == "cost_limit" and report["mode"] == "threshold"
    assert cumulative_before_last < threshold <= Decimal(report["cost_usd"])
    assert result["paid_calls"] == result["settled_calls"] == result["evaluated_calls"] == report["calls"]
    assert report["budget_ok"] and not report["secret_in_evidence"]
    usage_in = sum(r["usage"]["prompt_tokens"] for r in rows)
    usage_out = sum(r["usage"]["completion_tokens"] for r in rows)
    cached_in = sum((r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0) for r in rows)
    written_in = sum((r["usage"].get("prompt_tokens_details") or {}).get("cache_write_tokens", 0) for r in rows)
    reasoning_out = sum((r["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0) for r in rows)
    journal = [json.loads(line) for line in (native / "events.jsonl").read_text().splitlines()]
    elapsed = (datetime.fromisoformat(journal[-1]["time"]) - datetime.fromisoformat(journal[0]["time"])).total_seconds()
    api_elapsed = sum(c.read(p)["seconds"] for p in (root / "transport").glob("*/timing.json"))
    result.update(replay=replay, threshold_usd=str(threshold), overshoot_usd=report["overshoot_usd"],
                  total_input_tokens=usage_in, total_output_tokens=usage_out,
                  total_cached_input_tokens=cached_in, total_cache_write_tokens=written_in,
                  total_reasoning_output_tokens=reasoning_out,
                  native_run_wall_seconds=elapsed, api_request_wall_seconds=api_elapsed,
                  baseline=report["baseline"], final_metrics=report["selected_metrics"],
                  full_original_module_passed=report["full_original_module_passed"],
                  threshold_crossed_only_on_last_call=True)
    c.write(root / "trajectory.json", result)
    import csv
    with (root / "trajectory.csv").open("x", newline="") as stream:
        fields = ["step", "cumulative_usd", "cost_usd", "valid", "duplicate_source", "best_source_changed", "best_tokens", "best_raw_heartbeats", "local_score"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# P02: $2.50 도달 시 종료하는 main 루프", "",
        "GPT-6.1 Sol·high, 원본에서 새로 시작, 횟수 제한 없음. 성공·정체·중복 후보로 조기 종료하지 않았다.", "",
        f'종료: **{report["calls"]}회**, 비용 **${report["cost_usd"]}**, 마지막 호출 초과분 **${report["overshoot_usd"]}**.',
        f'직전 누적 비용은 ${cumulative_before_last}였으며 마지막 응답에서만 기준 ${threshold}를 넘겼다.', "",
        f'원본 {report["baseline"]["tokens"]} proof-token / raw HB {report["baseline"]["raw_heartbeats"]:,} → 최종 재측정 {report["selected_metrics"]["tokens"]} proof-token / raw HB {report["selected_metrics"]["raw_heartbeats"]:,}. 선택 시점 local score는 {rows[-1]["local_score"]:.6f}다.', "",
        f'후보 통과 {result["candidate_valid"]}/{result["evaluated_calls"]}, 서로 다른 후보 소스 {result["unique_candidate_sources"]}개, 서로 다른 유효 소스 {result["unique_valid_sources"]}개.',
        f'동일 소스 재등장 {result["duplicate_candidate_sources"]}회. 최선 소스 변경 {result["best_source_changes"]}회.',
        f'마지막 최선 소스 변경은 {result["latest_best_change_step"]}회차, ${result["latest_best_change_cost_usd"]} 시점이다. 이후 지출은 ${result["cost_after_last_best_change_usd"]}다.', "",
        f'이번 실행에서 관측한 최종 개선의 80%는 {result["eighty_percent_of_observed_improvement_step"]}회차, ${result["eighty_percent_of_observed_improvement_cost_usd"]}에 도달했다. 이는 실행 후 계산한 기술 통계다.', "",
        "## API 입출력 토큰 사용량", "",
        f'아래 수치는 추정값이 아니라 OpenRouter 응답의 `usage.prompt_tokens`와 `usage.completion_tokens`를 집계한 값이다. 실패·중복 후보를 포함한 전체 {len(rows)}회가 대상이며, 회당 평균·중앙값은 소수 첫째 자리까지 표시했다.', "",
        "| 집계 | 입력 토큰 | 출력 토큰 |",
        "|---|---:|---:|",
        f'| 전체 합계 | {usage_in:,} | {usage_out:,} |',
        f'| 회당 평균 | {mean(r["usage"]["prompt_tokens"] for r in rows):,.1f} | {mean(r["usage"]["completion_tokens"] for r in rows):,.1f} |',
        f'| 회당 중앙값 | {median(r["usage"]["prompt_tokens"] for r in rows):,.1f} | {median(r["usage"]["completion_tokens"] for r in rows):,.1f} |', "",
        f'입력 {usage_in:,}토큰 중 캐시 읽기 {cached_in:,}, 캐시 쓰기 {written_in:,}토큰이다. 출력 {usage_out:,}토큰에는 reasoning {reasoning_out:,}토큰이 포함되며 다시 더하지 않는다.', "",
        f'캐시 읽기는 전체 입력의 {100*cached_in/usage_in:.1f}%다. 캐시 읽기·쓰기는 입력 합계에, reasoning은 출력 합계에 이미 포함되어 있으며 중복 합산하지 않았다. 비용은 응답의 `usage.cost`를 합산했다.', "",
        f'main 실행 구간은 약 {elapsed/60:.1f}분이고, HTTP 모델 요청 대기 합계는 약 {api_elapsed/60:.1f}분이다. 나머지에는 Lean 컴파일·계측·파일 검사·기록 등이 포함된다.', "",
        "| 회차 | 누적 비용 $ | 유효 | 새 최선 소스 | 최선 proof-token | 최선 raw HB | local score |",
        "|---:|---:|---|---|---:|---:|---:|"]
    notable = {1, len(rows), *[r["step"] for r in rows if r["best_source_changed"]], *range(10, len(rows)+1, 10)}
    for r in rows:
        if r["step"] in notable:
            lines.append(f'| {r["step"]} | {r["cumulative_usd"]} | {r["valid"]} | {r["best_source_changed"]} | {r["best_tokens"]} | {r["best_raw_heartbeats"]:,} | {r["local_score"]:.6f} |')
    lines += ["", "local score는 원본=1인 로컬 목적함수이며 낮을수록 좋다. 공식 Arena 점수가 아니다.",
              "동일 proof의 heartbeat 재측정에서 작은 차이가 날 수 있어 소스 변경과 점수 변화를 따로 기록했다.",
              "이 루프는 전체 대화 이력 대신 고정 문맥·현재 최선·직전 후보와 피드백을 전달한다. 같은 소스가 다시 나오는 것을 막는 기능은 추가하지 않았다.",
              "최종 검증·전체 모듈 컴파일 결과는 report.json, 전체 회차는 trajectory.csv, 원문은 harness/steps/에 있다.", ""]
    with (root / "report.md").open("x") as stream:
        stream.write("\n".join(lines))
    c.atomic(root / "artifacts.json", c.inventory(root))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    result = inspect(root)
    if args.save:
        final(root, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("trajectory", "native_result")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
