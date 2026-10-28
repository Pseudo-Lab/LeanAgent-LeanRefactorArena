#!/usr/bin/env python3
"""Static research plot of verified cost/quality records. No model or Lean calls."""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(os.environ["PROJECT_CACHE_DIR"]) / "matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    data = json.loads((root / "trajectory.json").read_text())
    rows = data["trajectory"]
    x = [0, *[float(r["cumulative_usd"]) for r in rows]]
    scores = [1, *[r["local_score"] for r in rows]]
    seen, valid_seen, unique, valid_unique = set(), set(), [0], [0]
    for row in rows:
        value = row["candidate_sha256"]
        if value:
            seen.add(value)
            if row["valid"]:
                valid_seen.add(value)
        unique.append(len(seen))
        valid_unique.append(len(valid_seen))
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(2, 1, figsize=(9, 6.6), sharex=True, gridspec_kw={"height_ratios": [1.3, 1]})
        fig.suptitle("P02 · GPT-6.1 Sol / high · native main loop", fontsize=14, x=0.12, ha="left", y=0.98)
        axes[0].step(x, scores, where="post", color="#2463a7", linewidth=2)
        changes = [r for r in rows if r["best_source_changed"]]
        axes[0].scatter([float(r["cumulative_usd"]) for r in changes], [r["local_score"] for r in changes],
                        color="#2463a7", edgecolors="white", s=35, zorder=3, label="Best source changed")
        axes[0].set_ylabel("Best local score\n(lower is better)")
        axes[0].set_ylim(min(0, min(scores)-0.05), 1.04)
        axes[0].legend(loc="upper right", frameon=False)
        axes[1].step(x, list(range(len(rows)+1)), where="post", color="#a2a8ae", label="All proposals")
        axes[1].step(x, unique, where="post", color="#2463a7", label="Distinct sources")
        axes[1].step(x, valid_unique, where="post", color="#24846a", label="Distinct valid sources")
        axes[1].set_ylabel("Cumulative candidates")
        axes[1].set_xlabel("Cumulative reported API cost (USD)")
        axes[1].legend(loc="upper left", frameon=False)
        threshold = float(data["threshold_usd"])
        for ax in axes:
            ax.axvline(threshold, color="#c47b2a", linestyle="--", linewidth=1.1)
            ax.grid(axis="y", alpha=0.18)
            ax.set_axisbelow(True)
        fig.text(0.12, 0.016,
            f'{len(rows)} calls · {data["native_run_wall_seconds"]/60:.1f} min · cost USD {data["known_cost_usd"]} · threshold USD {data["threshold_usd"]}',
            fontsize=8, color="#555b63")
        fig.subplots_adjust(left=0.12, right=0.97, bottom=0.10, top=0.91, hspace=0.20)
        for extension in ("png", "svg"):
            target = root / ("cost-quality." + extension)
            if target.exists():
                raise FileExistsError(target)
            fig.savefig(target, dpi=180, facecolor="white")
        plt.close(fig)
    print(root / "cost-quality.png")


if __name__ == "__main__":
    main()
