#!/usr/bin/env python3
"""Compare block-kind profiles of the main benchmark with the warm-up (train) set.

The strategy texts in make_prompts.py were written on the warm-up set. Before applying them
unchanged to the main benchmark (test), check whether the main problems look like the warm-up
problems: source mix, main block kind, how dominant it is, how many problems mix two kinds,
and proof length. No model call, no Lean.

usage (repository root):
  python experiments/analyze-prompts/profile.py --train benchmark_data_warmup.jsonl \
      --test benchmark_data.jsonl --out runs/profile-main
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "proof-analyze"))
sys.path.insert(0, str(HERE))
from analyze import analyze  # noqa: E402
from make_prompts import MIN_SHARE, STRATEGY  # noqa: E402

BANDS = [(90, "90% 이상"), (70, "70–90%"), (50, "50–70%"), (0, "50% 미만")]


def profile(row: dict) -> dict:
    ks = analyze(row["src"], row["statement"], row.get("source", ""))["kind_share"]
    order = sorted(ks.items(), key=lambda kv: -kv[1])
    top = next(((k, v) for k, v in order if k in STRATEGY), (order[0] if order else ("other", 0.0)))
    chosen = [k for k, v in order if k in STRATEGY and v >= MIN_SHARE]
    return {"name": row["name"], "source": row.get("source", ""), "tokens": row.get("proof_length"),
            "shares": dict(order), "top": top[0], "top_share": top[1], "soft_kinds": chosen,
            "hard_differs_from_soft": chosen != [top[0]]}


def band(v: float) -> str:
    return next(label for lo, label in BANDS if v >= lo)


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    lengths = [r["tokens"] for r in rows if r["tokens"] is not None]
    q = statistics.quantiles(lengths, n=4) if len(lengths) >= 2 else [None] * 3
    return {"n": n, "source": Counter(r["source"] for r in rows), "top": Counter(r["top"] for r in rows),
            "band": Counter(band(r["top_share"]) for r in rows),
            "differs": sum(r["hard_differs_from_soft"] for r in rows),
            "length": {"min": min(lengths, default=None), "q1": q[0], "median": q[1], "q3": q[2],
                       "max": max(lengths, default=None)}}


def pct(c: int, n: int) -> str:
    return f"{c} ({100 * c / n:.0f}%)" if n else "0"


def table(title: str, keys: list[str], a: dict, b: dict, na: int, nb: int) -> list[str]:
    out = [f"### {title}", "", "| | 웜업 | 본 대회 |", "| --- | ---: | ---: |"]
    out += [f"| {k} | {pct(a.get(k, 0), na)} | {pct(b.get(k, 0), nb)} |" for k in keys]
    return out + [""]


def report(train: list[dict], test: list[dict]) -> str:
    s, t = summary(train), summary(test)
    na, nb = s["n"], t["n"]
    L = ["# 본 대회 블록 종류 분포 점검", "",
         f"웜업 {na}문제로 전략 문장을 정했고, 본 대회 {nb}문제에는 문장을 고치지 않고 적용한다. "
         "아래는 두 집합이 비슷한지 보는 점검이다. 모델 호출과 컴파일은 없다.", ""]
    L += table("출처", sorted(set(s["source"]) | set(t["source"])), s["source"], t["source"], na, nb)
    L += table("가장 큰 블록 종류", ["case", "calc", "have", "other"], s["top"], t["top"], na, nb)
    L += table("가장 큰 종류의 비중", [label for _, label in BANDS], s["band"], t["band"], na, nb)
    L += [f"### hard와 soft가 다른 문제", "",
          f"{MIN_SHARE:.0f}% 이상인 종류가 둘 이상이거나, 가장 큰 종류도 {MIN_SHARE:.0f}% 미만인 문제.", "",
          "| | 웜업 | 본 대회 |", "| --- | ---: | ---: |",
          f"| 문제 수 | {pct(s['differs'], na)} | {pct(t['differs'], nb)} |", ""]
    L += ["### 원본 증명 길이 (토큰)", "", "| | 최소 | 1사분위 | 중앙값 | 3사분위 | 최대 |",
          "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for label, x in (("웜업", s), ("본 대회", t)):
        g = x["length"]
        L.append(f"| {label} | " + " | ".join("-" if v is None else f"{v:.0f}" for v in
                                             (g["min"], g["q1"], g["median"], g["q3"], g["max"])) + " |")
    L += ["", "## 본 대회 문제별", "", "| # | 출처 | 토큰 | 비중 | hard | soft |", "| ---: | --- | ---: | --- | --- | --- |"]
    for k, r in enumerate(test, 1):
        shares = ", ".join(f"{a} {v}" for a, v in r["shares"].items() if v >= 1)
        L.append(f"| {k} | {r['source']} | {r['tokens']} | {shares} | {r['top']} | {', '.join(r['soft_kinds']) or '-'} |")
    return "\n".join(L) + "\n"


def load(path: Path) -> list[dict]:
    return [profile(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=Path, required=True, help="warm-up benchmark jsonl")
    ap.add_argument("--test", type=Path, required=True, help="main benchmark jsonl")
    ap.add_argument("--out", type=Path, required=True, help="new folder: profile.md, profile.json")
    a = ap.parse_args()
    train, test = load(a.train), load(a.test)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "profile.json").write_text(json.dumps({"train": train, "test": test}, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    md = report(train, test)
    (a.out / "profile.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
