#!/usr/bin/env python3
"""Render the completed budget experiment as one portable, offline HTML file."""
import argparse
import base64
import html
import json
from pathlib import Path
import re
from statistics import mean, median


def read(path):
    return json.loads(path.read_text())


def money(value):
    return "$" + str(value)


def render(root):
    data, report, checks = (read(root / name) for name in ("trajectory.json", "report.json", "validation.json"))
    rows = data["trajectory"]
    token_stats = {
        name: {"total": sum(values), "mean": mean(values), "median": median(values)}
        for name, key in [("input", "prompt_tokens"), ("output", "completion_tokens")]
        for values in [[row["usage"][key] for row in rows]]
    }
    assert len(rows) == data["evaluated_calls"] == data["settled_calls"] == data["paid_calls"]
    assert report["status"] == "completed" and checks["last_call_only_crossed_threshold"]
    baseline, final = data["baseline"], data["final_metrics"]
    scores = data["best"]["local_score"]
    image = base64.b64encode((root / "cost-quality.png").read_bytes()).decode()
    proof = html.escape((root / "harness/selected.lean").read_text())
    significant = {1, len(rows), *range(10, len(rows)+1, 10), *[r["step"] for r in rows if r["best_source_changed"]]}
    table = []
    for row in rows:
        valid, duplicate, changed = row["valid"], row["duplicate_source"], row["best_source_changed"]
        table.append(f'''<tr data-step="{row['step']}" data-valid="{int(valid)}" data-duplicate="{int(duplicate)}" data-change="{int(changed)}" data-key="{int(row['step'] in significant)}">
          <td class="round">{row['step']:03}</td><td class="num">{row['cumulative_usd']}</td>
          <td><span class="badge {'pass' if valid else 'fail'}">{'통과' if valid else '실패'}</span></td>
          <td>{'재등장' if duplicate else '새 소스'}</td><td>{'<span class="new-best">갱신</span>' if changed else '—'}</td>
          <td class="num">{row['best_tokens']:,}</td><td class="num">{row['best_raw_heartbeats']:,}</td><td class="num">{row['local_score']:.6f}</td></tr>''')
    metric_cards = []
    for label, key, formatter in [("증명 소스 토큰", "tokens", lambda n: f"{n:,}"), ("Raw heartbeat", "raw_heartbeats", lambda n: f"{n:,}")]:
        reduction = (1-final[key]/baseline[key])*100
        metric_cards.append(f'<div class="metric"><span>{label}</span><div class="before">{formatter(baseline[key])}<i>→</i></div><strong>{formatter(final[key])}</strong><small>{reduction:.1f}% 감소</small></div>')
    metric_cards.append(f'<div class="metric"><span>로컬 목적함수</span><div class="before">1.000000<i>→</i></div><strong>{scores:.6f}</strong><small>낮을수록 좋음 · 공식 대회 점수 아님</small></div>')
    proof_checks = [
        ("최종 증명 검증", report["final_valid"]),
        ("원본 전체 모듈 컴파일", report["full_original_module_passed"]),
        ("main 기록 재생", checks["main_replay_passed"]),
        ("마지막 호출에서만 비용 기준 도달", checks["last_call_only_crossed_threshold"]),
        ("기준 도달 후 추가 호출 없음", checks["no_step_159"]),
        ("모델 응답 ID 고유성", checks["generation_ids_unique"]),
        ("전송 본문과 main 기록 일치", checks["request_wire_matches_native_records"]),
        ("인증값 산출물 미기록", not checks["secret_in_evidence"]),
    ]
    checks_html = "".join(f'<li><span class="check-icon">{"✓" if passed else "!"}</span>{label}<b>{"통과" if passed else "확인 필요"}</b></li>' for label, passed in proof_checks)
    packet = {
        "experiment": "P02 / GPT-6.1 Sol / high", "threshold_usd": data["threshold_usd"],
        "cost_usd": data["known_cost_usd"], "overshoot_usd": data["overshoot_usd"],
        "baseline": baseline, "final_metrics": final,
        "token_usage": {"source": "OpenRouter response usage", "calls": len(rows), **token_stats},
        "rows": [{k: r[k] for k in ["step", "cumulative_usd", "cost_usd", "valid", "duplicate_source", "best_source_changed", "best_tokens", "best_raw_heartbeats", "local_score"]} for r in rows],
        "validation": checks,
    }
    download = base64.b64encode(json.dumps(packet, ensure_ascii=False, indent=2).encode()).decode()
    values = {
        "calls": str(len(rows)), "cost": money(data["known_cost_usd"]), "overshoot": money(data["overshoot_usd"]),
        "threshold": money(data["threshold_usd"]), "before_last": money(rows[-2]["cumulative_usd"]),
        "minutes": f'{data["native_run_wall_seconds"]/60:.1f}', "api_minutes": f'{data["api_request_wall_seconds"]/60:.1f}',
        "eighty_step": str(data["eighty_percent_of_observed_improvement_step"]), "eighty_cost": money(data["eighty_percent_of_observed_improvement_cost_usd"]),
        "last_step": str(data["latest_best_change_step"]), "last_cost": money(data["latest_best_change_cost_usd"]),
        "tail_calls": str(len(rows)-data["latest_best_change_step"]), "tail_cost": money(data["cost_after_last_best_change_usd"]),
        "duplicates": str(data["duplicate_candidate_sources"]), "duplicate_percent": f'{100*data["duplicate_candidate_sources"]/len(rows):.1f}',
        "valid": str(data["candidate_valid"]), "unique": str(data["unique_candidate_sources"]), "valid_unique": str(data["unique_valid_sources"]),
        "input": f'{data["total_input_tokens"]:,}', "cache_read": f'{data["total_cached_input_tokens"]:,}',
        "cache_write": f'{data["total_cache_write_tokens"]:,}', "cache_percent": f'{100*data["total_cached_input_tokens"]/data["total_input_tokens"]:.1f}',
        "output": f'{data["total_output_tokens"]:,}', "reasoning": f'{data["total_reasoning_output_tokens"]:,}',
        "input_mean": f'{token_stats["input"]["mean"]:,.1f}', "output_mean": f'{token_stats["output"]["mean"]:,.1f}',
        "input_median": f'{token_stats["input"]["median"]:,.1f}', "output_median": f'{token_stats["output"]["median"]:,.1f}',
        "unit_tests": str(checks["unit_tests_passed"]), "main_commit": html.escape(report["main_commit"][:7]),
        "metrics": "".join(metric_cards), "chart": image, "table": "\n".join(table), "checks": checks_html,
        "proof": proof, "proof_tokens": str(final["tokens"]), "download": download,
    }
    template = Path(__file__).with_name("report-template.html").read_text()
    result = re.sub(r"\{\{([a-z_]+)\}\}", lambda match: values[match[1]], template)
    if re.search(r"\{\{[a-z_]+\}\}", result):
        raise ValueError("Unresolved report placeholder")
    target = root / "report.html"
    with target.open("x") as stream:
        stream.write(result)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Completed experiment directory")
    args = parser.parse_args()
    print(render(args.output.resolve()))


if __name__ == "__main__":
    main()
