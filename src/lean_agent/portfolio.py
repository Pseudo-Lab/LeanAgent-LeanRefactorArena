"""Scoped scout contexts and an evaluation barrier before merger generation.

Adapted from competitive-search40-20261031: three isolated scouts, evaluation
quotas, then a pooled merger. The common runner dispatches these contexts
serially through its existing model/Lean/budget path. No external I/O here.
"""
from copy import deepcopy

BRANCHES = ("scout-a", "scout-b", "scout-c", "merge")
ROUTES = {
    "scout-a": "Derive a route from the goal, definitions and available theorem types.",
    "scout-b": "Contract dependencies, repeated steps and obligations in the original proof.",
    "scout-c": "Seek a stronger compositional property or representation, and verify its bridge to the goal.",
    "merge": "Compare the sealed scout results. Synthesize their useful ideas into a complete proof; verify every combined candidate.",
}


def enabled(config):
    return "portfolio" in config.get("agent", {})


def validate(settings):
    if (not isinstance(settings, dict) or set(settings) - {
            "scout_evaluations", "merger_evaluations", "hide_original_first_scout", "progress_guard",
            "rounds", "merger_until_budget"}):
        raise ValueError("Expected portfolio evaluation quotas")
    for key, default in (("scout_evaluations", 6), ("merger_evaluations", 22)):
        value = settings.get(key, default)
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError("Expected portfolio " + key + " between 1 and 100")
    if "progress_guard" in settings and settings["progress_guard"] != "bounded-v1":
        raise ValueError("Expected progress_guard bounded-v1")
    if type(settings.get("hide_original_first_scout", True)) is not bool:
        raise ValueError("Expected boolean hide_original_first_scout")
    if type(settings.get("rounds", 1)) is not int or not 1 <= settings.get("rounds", 1) <= 10:
        raise ValueError("Expected portfolio rounds between 1 and 10")
    if type(settings.get("merger_until_budget", False)) is not bool:
        raise ValueError("Expected boolean merger_until_budget")


def extended(config):
    """Rounds or budget-ended merging requested; otherwise state and summaries keep their shape."""
    settings = config["agent"]["portfolio"]
    return settings.get("rounds", 1) > 1 or settings.get("merger_until_budget", False)


def budget_phase(scope, config):
    """The last round's merger runs until the shared per-problem budget instead of a count."""
    settings = config["agent"]["portfolio"]
    return (settings.get("merger_until_budget", False) and scope["active"] == "merge"
            and scope.get("round", 1) == settings.get("rounds", 1))


def quotas(config):
    settings = config["agent"]["portfolio"]
    return {branch: settings.get("merger_evaluations", 22) if branch == "merge"
            else settings.get("scout_evaluations", 6) for branch in BRANCHES}


def initialize(state, config):
    if enabled(config):
        state["portfolio"] = {
            "active": BRANCHES[0], "evaluations": dict.fromkeys(BRANCHES, 0),
            "calls": dict.fromkeys(BRANCHES, 0), "owners": {"c000": "baseline"},
            "best_ids": dict.fromkeys(BRANCHES, "c000"),
            "latest": dict.fromkeys(BRANCHES, None),
        }

        if guarded(config):
            state["portfolio"].update(stalled_calls=dict.fromkeys(BRANCHES, 0), exits={})
        if extended(config):
            state["portfolio"].update(round=1, completed_rounds=[])


def guarded(config):
    return config.get("agent", {}).get("portfolio", {}).get("progress_guard") == "bounded-v1"


def progress(state, config):
    """Bound research even when errors/duplicates never produce an evaluation."""
    if not guarded(config):
        return None
    scope = state["portfolio"]
    branch = scope["active"]
    recent = []
    for row in reversed(state["exploration"]["history"]):
        if row.get("branch") != branch:
            continue
        if row.get("candidate_id"):
            break
        if row.get("action"):
            recent.append(row["action"])
    repeated = [action for i, action in enumerate(recent)
                if action in recent[i + 1:] and action not in recent[:i]]
    stalled = scope["stalled_calls"][branch]
    return {"mode": "bounded-v1", "consecutive_unevaluated_calls": stalled,
            "force_candidate": stalled >= 4 or bool(repeated),
            "max_consecutive_unevaluated_calls": 8,
            "max_branch_calls": None if budget_phase(scope, config) else 3 * quotas(config)[branch] + 8,
            "repeated_actions": repeated[:3],
            "instruction": "After four calls without an evaluation or a repeated read, submit a complete propose/repair using collected evidence. Reads cannot advance the evaluation quota. Never repeat the listed actions. A stalled branch is closed without claiming its quota was completed."}


def record_progress(state, config, evaluated):
    """Shared deterministic routing for execution and receipt-based auditing."""
    scope = state["portfolio"]
    branch = scope["active"]
    scope["calls"][branch] += 1
    if evaluated:
        scope["evaluations"][branch] += 1
    open_ended = budget_phase(scope, config)
    reason = "quota" if not open_ended and scope["evaluations"][branch] == quotas(config)[branch] else None
    if guarded(config):
        scope["stalled_calls"][branch] = 0 if evaluated else scope["stalled_calls"][branch] + 1
        if reason is None and scope["stalled_calls"][branch] >= 8:
            reason = "stalled"
        if reason is None and not open_ended and scope["calls"][branch] >= 3 * quotas(config)[branch] + 8:
            reason = "call_limit"
        if reason:
            scope["exits"][branch] = reason
    if reason:
        index = BRANCHES.index(branch) + 1
        if index < len(BRANCHES):
            scope["active"] = BRANCHES[index]
        elif scope.get("round", 1) < config["agent"]["portfolio"].get("rounds", 1):
            start_round(state, config)
        else:
            scope["active"] = "complete"


def start_round(state, config):
    """Archive this round's counts and restart the scouts from the incumbent (seed)."""
    scope = state["portfolio"]
    scope["completed_rounds"].append({"evaluations": dict(scope["evaluations"]), "calls": dict(scope["calls"]),
                                      **({"exits": dict(scope["exits"])} if guarded(config) else {})})
    scope["round"] += 1
    scope["evaluations"] = dict.fromkeys(BRANCHES, 0)
    scope["calls"] = dict.fromkeys(BRANCHES, 0)
    if guarded(config):
        scope["stalled_calls"] = dict.fromkeys(BRANCHES, 0)
        scope["exits"] = {}
    scope["active"] = BRANCHES[0]
    seed = state.get("exploration", {}).get("best_candidate_id")
    if seed is not None:  # the receipt-only audit has no candidates; routing does not depend on the seed
        scope["seed_id"] = seed
        for scout in BRANCHES[:-1]:
            scope["best_ids"][scout] = seed


def completed(state, config):
    scope, limits = state["portfolio"], quotas(config)
    earlier = all(row["evaluations"][b] == n for row in scope.get("completed_rounds", []) for b, n in limits.items())
    if budget_phase(scope, config):
        # Every scout quota was met; the open-ended merger ends only at the budget.
        return earlier and all(scope["evaluations"][b] == limits[b] for b in BRANCHES[:-1])
    return finished(state) and earlier and all(scope["evaluations"][b] == n for b, n in limits.items())


def stop_reason(state, config):
    return "portfolio_complete" if completed(state, config) else "portfolio_stalled"


def finished(state):
    return state.get("portfolio", {}).get("active") == "complete"


def hidden_original(state, config):
    return (enabled(config) and state["portfolio"]["active"] == "scout-a"
            and config["agent"]["portfolio"].get("hide_original_first_scout", True))


def validate_shared_inputs(config, reference, prompt, corpus):
    if enabled(config) and config["agent"]["portfolio"].get("hide_original_first_scout", True):
        shared = [prompt, *(value for entry in corpus["entries"] for value in entry.values())]
        if any(reference.strip() in text for text in shared):
            raise ValueError("Hidden original proof occurs in shared prompt/corpus; remove it or disable original hiding")


def scoped_state(state, config):
    if not enabled(config):
        return state
    scope = state["portfolio"]
    branch = scope["active"]
    if branch == "complete":
        raise ValueError("Portfolio evaluation quotas are complete")
    view = deepcopy(state)
    memory = view["exploration"]
    if branch != "merge":
        allowed = {cid for cid, owner in scope["owners"].items() if owner in ("baseline", branch)}
        if scope.get("seed_id"):
            allowed.add(scope["seed_id"])
        memory["candidates"] = {cid: row for cid, row in memory["candidates"].items() if cid in allowed}
        memory["history"] = [row for row in memory["history"] if row.get("branch") == branch]
        cid = scope["best_ids"][branch]
        memory["best_candidate_id"] = cid
        view["best"] = {key: value for key, value in memory["candidates"][cid].items()
                        if key not in {"parent_id", "strategy", "step", "valid", "feedback"}}
    view["latest"] = deepcopy(scope["latest"][branch])
    return view


def packet(state, config):
    scope, limits = state["portfolio"], quotas(config)
    branch = scope["active"]
    if branch == "complete":
        raise ValueError("Portfolio evaluation quotas are complete")
    open_ended = budget_phase(scope, config)
    value = {"branch": branch, "route": ROUTES[branch], "quota": None if open_ended else limits[branch],
             "evaluated": scope["evaluations"][branch],
             "remaining_evaluations": None if open_ended else limits[branch] - scope["evaluations"][branch],
             "branch_calls": scope["calls"][branch],
             "original_proof_hidden": hidden_original(state, config),
             "execution": "serial dispatch with separate scout-visible contexts; one shared budget",
             "credit_policy": "Valid and invalid evaluated proofs consume credits; queries, format errors and duplicates still consume model calls/cost."}
    if guarded(config):
        value["progress_guard"] = progress(state, config)
        value["branch_exits"] = dict(scope["exits"])
    if extended(config):
        value["round"] = scope["round"]
        value["rounds"] = config["agent"]["portfolio"].get("rounds", 1)
        if open_ended:
            value["stops_at"] = "shared per-problem budget"
        if scope.get("seed_id") and branch != "merge":
            value["seed_candidate_id"] = scope["seed_id"]
    if branch == "merge":
        value["scout_results"] = [{"branch": scout, "evaluated": scope["evaluations"][scout],
                                    "best_candidate_id": scope["best_ids"][scout],
                                    "candidate_ids": [cid for cid, owner in scope["owners"].items() if owner == scout],
                                    "failed_candidate_ids": [cid for cid, owner in scope["owners"].items()
                                        if owner == scout and not state["exploration"]["candidates"][cid]["valid"]]}
                                   for scout in BRANCHES[:-1]]
    return value


def advance(state, config, code, result, ranking):
    if not enabled(config):
        return
    scope = state["portfolio"]
    branch = scope["active"]
    scope["latest"][branch] = deepcopy(state["latest"])
    state["exploration"]["history"][-1]["branch"] = branch
    if code is not None:
        cid = f"c{state['step']:03}"
        scope["owners"][cid] = branch
        row = state["exploration"]["candidates"][cid]
        previous = state["exploration"]["candidates"][scope["best_ids"][branch]]
        if row["valid"] and ranking(row) < ranking(previous):
            scope["best_ids"][branch] = cid
    record_progress(state, config, code is not None and result is not None)


def summary(state, config):
    if not enabled(config):
        return None
    scope = state["portfolio"]
    return {"complete": completed(state, config), "active": scope["active"],
            "quotas": quotas(config), "evaluations": scope["evaluations"],
            "calls": scope["calls"], "execution": "serial-scoped-scouts-then-merger",
            **({"exits": scope["exits"], "stalled_calls": scope["stalled_calls"]} if guarded(config) else {}),
            **({"round": scope["round"], "rounds": config["agent"]["portfolio"].get("rounds", 1),
                "completed_rounds": scope["completed_rounds"],
                "merger_until_budget": config["agent"]["portfolio"].get("merger_until_budget", False)}
               if extended(config) else {})}
