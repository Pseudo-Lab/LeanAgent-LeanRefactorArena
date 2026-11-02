"""Exchange feedback and deterministic approach selection for visible candidates.

Reuses the structural-search exchange packet, cost-hypothesis residual axes and
v4's approach instructions. Fixed ranking remains in harness.py. An exchange
rate is not a noise estimate; no r/4 measurement-noise rule is carried over.
"""
from fractions import Fraction

MODE = "exchange-v1"
GUIDANCE = (
    "Follow approach_policy's selected approach and portfolio.route when supplied. "
    "They select the next exploration method, never change the fixed acceptance objective. "
    "All model/tool actions share the run budget. Candidate IDs are scoped to the current context. "
    "Return only the configured action object; only the harness verifies a complete proof."
)
INSTRUCTIONS = {
    "explore": "Compare proof routes by obligations removed and bridge cost. Inspect actual theorem types before spending attempts on an uncertain bridge.",
    "merge": "Compare scout parents, failed bridges and Pareto candidates. Combine useful ideas into a complete proof, not concatenated scripts. Revalidate the whole result.",
    "reduce_length": "Length is the larger residual axis. Prefer direct lemmas, compositional internal properties, shared obligations and omission of inferred work. Measure any HB increase.",
    "reduce_heartbeat": "Heartbeat is the larger residual axis. Localize repeated normalization, large-term comparison or automation; use evidence, narrower rules, explicit witnesses or a better representation.",
    "repair_or_reconsider": "Inspect the failed parent's exact errors and goal/types. Repair a justified bridge or abandon that hypothesis; do not repeat a failed edit without new evidence.",
    "reconsider": "Recent evaluated candidates did not improve. Revisit available lemmas, a different representation or a retained nonwinning structure rather than repeating the same tactic changes.",
    "consolidate": "Few evaluations or calls remain. Finish a route with an established bridge and compress validated work; preserve the verified best rather than opening an unsupported new route.",
}


def enabled(config):
    agent = config.get("agent", {})
    return agent.get("approach_policy") == MODE or "portfolio" in agent


def validate(value):
    if value != MODE:
        raise ValueError("Expected approach_policy exchange-v1")


def rational(value):
    return {"numerator": value.numerator, "denominator": value.denominator,
            "value": float(value)}


def packet(state, config, context=None):
    memory = state["exploration"]
    valid = [(cid, row) for cid, row in memory["candidates"].items() if row["valid"]]
    baseline, best = state["baseline"], state["best"]
    t0, h0 = baseline["tokens"], baseline["raw_heartbeats"]
    length, heartbeat = Fraction(best["tokens"], t0), Fraction(best["raw_heartbeats"], h0)
    key = lambda item: (item[1]["rank_numerator"], item[1]["tokens"], item[1]["sha256"])
    frontier = [(cid, row) for cid, row in valid if not any(
        other["tokens"] <= row["tokens"] and other["raw_heartbeats"] <= row["raw_heartbeats"]
        and (other["tokens"] < row["tokens"] or other["raw_heartbeats"] < row["raw_heartbeats"])
        for _, other in valid)]
    attempts = [{**row, "candidate_id": row.get("effective_candidate_id", row.get("candidate_id"))}
                for row in memory["history"] if row.get("candidate_id")]
    # Count evaluated candidates after the last strict objective improvement.
    incumbent = memory["candidates"]["c000"]["rank_numerator"]
    stagnant = 0
    for attempt in attempts:
        row = memory["candidates"][attempt["candidate_id"]]
        if row["valid"] and row["rank_numerator"] < incumbent:
            incumbent, stagnant = row["rank_numerator"], 0
        else:
            stagnant += 1
    remaining = context["remaining_evaluations"] if context else None
    if config["limits"]["max_calls"] is not None:
        calls = config["limits"]["max_calls"] - state["calls"]
        remaining = min(remaining, calls) if remaining is not None else calls
    latest = state.get("latest")
    failed = latest and latest["feedback"].get("valid") is False
    dominance = "length" if length >= heartbeat else "heartbeat"
    if failed:
        approach = "repair_or_reconsider"
    elif context and context["branch"].startswith("scout") and context["evaluated"] < 2:
        approach = "explore"
    elif context and context["branch"] == "merge" and context["evaluated"] == 0:
        approach = "merge"
    elif remaining is not None and remaining <= 2:
        approach = "consolidate"
    elif stagnant >= 3:
        approach = "reconsider"
    elif not context and len(attempts) < 2:
        approach = "explore"
    else:
        approach = "reduce_length" if dominance == "length" else "reduce_heartbeat"
    tradeoff = None
    if attempts:
        row = memory["candidates"][attempts[-1]["candidate_id"]]
        parent = memory["candidates"].get(row.get("parent_id"))
        if row["valid"] and parent and parent["valid"]:
            dt, dh = row["tokens"] - parent["tokens"], row["raw_heartbeats"] - parent["raw_heartbeats"]
            delta = Fraction(dt) + Fraction(dh * t0, h0)
            tradeoff = {"candidate_id": attempts[-1]["candidate_id"], "parent_id": row["parent_id"],
                        "delta_tokens": dt, "delta_raw_hb": dh, "delta_token_equivalent": rational(delta),
                        "strict_objective_improvement": delta < 0}
    return {"version": MODE, "approach": approach, "instructions": INSTRUCTIONS[approach],
            "normalizers": {"tokens": t0, "raw_hb": h0, "basis": "fixed measured baseline"},
            "raw_hb_per_token": rational(Fraction(h0, t0)),
            "residual_ratios": {"length": rational(length), "heartbeat": rational(heartbeat)},
            "larger_score_component": dominance, "stagnant_evaluations": stagnant,
            "latest_tradeoff": tradeoff,
            "remaining": remaining,
            "acceptance": "Prefer DeltaT + DeltaRawHB / (H0/T0) < 0; objective ties use tokens then declaration SHA256. Exchange is not measurement noise.",
            "pareto_candidates": [{"candidate_id": cid, "tokens": row["tokens"],
                                    "raw_heartbeats": row["raw_heartbeats"]}
                                   for cid, row in sorted(frontier, key=key)[:8]],
            "retained_structure_parents": [{"candidate_id": cid, "strategy": row.get("strategy", "unspecified")}
                                            for cid, row in valid[-4:] if cid != "c000"],
            "policy_parameters": {"stagnation_evaluations": 3, "consolidation_remaining": 2,
                                  "status": "initial configurable-by-code policy; not empirically optimal"}}
