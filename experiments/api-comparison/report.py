#!/usr/bin/env python3
"""Offline comparison table and aggregates, built from replay-checked evidence."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import statistics

import compare


def summarize(result):
    groups = {}
    for backend in ("subagent", "openrouter"):
        rows = [r for r in result["trials"] if r["backend"] == backend]
        first = [r for r in rows if int(r["trial"].split("-")[-1]) <= 3]
        def median_usage(*keys):
            values = [next((r["usage"][k] for k in keys if k in (r.get("usage") or {})), None) for r in first]
            return statistics.median(values) if values and all(x is not None for x in values) else None
        groups[backend] = {"completed_trials": len(rows), "comparison_trials": len(first),
            "candidate_valid": sum(r["candidate_valid"] for r in first),
            "improved": sum(r["improved"] for r in first),
            "final_valid": sum(r["final_valid"] for r in first),
            "comparison_reported_cost_usd": str(sum((Decimal(r["cost_usd"]) for r in first), Decimal(0))) if first and all(r["cost_usd"] is not None for r in first) else None,
            "comparison_estimated_token_cost_usd": str(sum((Decimal(r["estimated_token_cost_usd"]) for r in first), Decimal(0))) if first and all(r["estimated_token_cost_usd"] is not None for r in first) else None,
            "median_generation_seconds": statistics.median(r["generation_seconds"] for r in first) if first and all(r["generation_seconds"] is not None for r in first) else None,
            "tool_using_trials": sum(bool(r.get("runtime_tool_items")) for r in first),
            "median_input_tokens": median_usage("input_tokens", "prompt_tokens"),
            "median_output_tokens": median_usage("output_tokens", "completion_tokens")}
    return groups


def markdown(result, groups, root):
    lines = ["# Warm-up P02 — GPT-6.1 Sol / high", "",
        "subagent 첫 3회와 OpenRouter 첫 3회를 비교하고 OpenRouter 4–5회는 추가 반복으로 보관한다.",
        "원본과 같은 문맥의 Lean 4.26.0 검증 결과다. 모든 실행은 후보 하나를 새로 생성한다.", "",
        "| 실행 | 후보 검증 | 개선 채택 | 후보 proof-token | 후보 raw HB | 입력 / 캐시 / 출력 API-token | 보고 비용 $ | API 환산 추정 $ |",
        "|---|---|---|---:|---:|---|---:|---:|"]
    for row in result["trials"]:
        usage = row["usage"] or {}
        inp = usage.get("input_tokens", usage.get("prompt_tokens"))
        out = usage.get("output_tokens", usage.get("completion_tokens"))
        cache = usage.get("cached_input_tokens", (usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
        metrics = row["candidate_metrics"] or {}
        cost = row["cost_usd"] if row["cost_usd"] is not None else "미측정"
        est = row["estimated_token_cost_usd"] or "미측정"
        lines.append(f'| {row["trial"]} | {"통과" if row["candidate_valid"] else "실패"} | {"채택" if row["improved"] else "원본 유지"} | {metrics.get("tokens", "—")} | {metrics.get("raw_heartbeats", "—")} | {inp} / {cache} / {out} | {cost} | {est} |')
    lines += ["", f'OpenRouter 전체 보고 비용: **${result["reported_openrouter_total_usd"]}**.', "",
              "| 첫 3회 비교 | 후보 통과 | 개선 채택 | 최종 검증 | API 환산 추정 합계 $ |",
              "|---|---:|---:|---:|---:|"]
    for backend, group in groups.items():
        lines.append(f'| {backend} | {group["candidate_valid"]}/{group["comparison_trials"]} | {group["improved"]}/{group["comparison_trials"]} | {group["final_valid"]}/{group["comparison_trials"]} | {group["comparison_estimated_token_cost_usd"]} |')
    lines += ["", "## 실패 후보의 첫 진단", "", "| 실행 | Lean 진단 |", "|---|---|"]
    for row in result["trials"]:
        if row["candidate_valid"]:
            continue
        logs = sorted((root / row["trial"] / "evaluation").rglob("check.log"))
        errors = [line.split("error: ", 1)[-1] for log in logs for line in log.read_text().splitlines() if "error:" in line]
        diagnostic = errors[0] if errors else row.get("rejection") or "계측/검증 로그 참고"
        lines.append(f'| {row["trial"]} | {diagnostic.replace("|", "/")} |')
    lines += ["", "subagent 비용 추정은 구독 청구액이 아니다. reasoning은 출력 usage에 이미 포함되며 두 번 더하지 않는다.",
              "CLI의 시스템·도구 문맥과 API 입력의 차이는 남아 있다. requested model/effort를 맞췄지만 숨은 런타임 설정·snapshot 동일성을 증명하지 않는다.",
              "한 문제·작은 반복 수의 관찰이며 일반 성능 순위나 공식 Arena 점수가 아니다.",
              "기록 재생은 모델·Lean을 재호출하지 않고 파일 무결성과 선택·비용 정산을 확인했다.", "",
              "## 증거", "", f"실행 폴더: `{root}`", "",
              "`protocol.json`, `messages.json`, `wire-request.json`, `endpoint.json`, `price-snapshot.json`, `budget.json`과 각 실행의 `summary.json`을 참고한다.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="Existing suite directory")
    args = parser.parse_args()
    root = args.output.resolve()
    result = compare.replay(root)
    groups = summarize(result)
    compare.write(root / "comparison.json", {**result, "groups": groups})
    with (root / "comparison.md").open("x") as stream:
        stream.write(markdown(result, groups, root))
    print(json.dumps({"report": str(root / "comparison.md"), "groups": groups,
                      "openrouter_total_usd": result["reported_openrouter_total_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
