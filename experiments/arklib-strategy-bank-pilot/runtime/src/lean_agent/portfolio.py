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
            "scout_evaluations", "merger_evaluations", "hide_original_first_scout"}):
        raise ValueError("Expected portfolio evaluation quotas")
    for key, default in (("scout_evaluations", 6), ("merger_evaluations", 22)):
        value = settings.get(key, default)
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError("Expected portfolio " + key + " between 1 and 100")
    if type(settings.get("hide_original_first_scout", True)) is not bool:
        raise ValueError("Expected boolean hide_original_first_scout")


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
    value = {"branch": branch, "route": ROUTES[branch], "quota": limits[branch],
             "evaluated": scope["evaluations"][branch],
             "remaining_evaluations": limits[branch] - scope["evaluations"][branch],
             "branch_calls": scope["calls"][branch],
             "original_proof_hidden": hidden_original(state, config),
             "execution": "serial dispatch with separate scout-visible contexts; one shared budget",
             "credit_policy": "Valid and invalid evaluated proofs consume credits; queries, format errors and duplicates still consume model calls/cost."}
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
    scope["calls"][branch] += 1
    scope["latest"][branch] = deepcopy(state["latest"])
    state["exploration"]["history"][-1]["branch"] = branch
    if code is not None:
        cid = f"c{state['step']:03}"
        scope["owners"][cid] = branch
        row = state["exploration"]["candidates"][cid]
        previous = state["exploration"]["candidates"][scope["best_ids"][branch]]
        if row["valid"] and ranking(row) < ranking(previous):
            scope["best_ids"][branch] = cid
    if code is not None and result is not None:
        scope["evaluations"][branch] += 1
    if scope["evaluations"][branch] == quotas(config)[branch]:
        index = BRANCHES.index(branch) + 1
        scope["active"] = BRANCHES[index] if index < len(BRANCHES) else "complete"


def summary(state, config):
    if not enabled(config):
        return None
    scope = state["portfolio"]
    return {"complete": finished(state), "active": scope["active"],
            "quotas": quotas(config), "evaluations": scope["evaluations"],
            "calls": scope["calls"], "execution": "serial-scoped-scouts-then-merger"}
