"""Opt-in action protocol and persistent candidate ancestry. No external I/O/tools.

Search operates on explicitly supplied, snapshotted source excerpts. A search hit
is evidence to inspect, not a claim that a declaration is usable in Lean.
"""
import json
import re
from collections import Counter

from . import diagnostics, models, portfolio, search_policy, strategy_bank
from .artifacts import canonical, sha
from .evaluator.tokens import proof_body

MODE = "actions-v1"
PROTOCOL = {
    "search": {"action": "search", "query": "names or words in the frozen corpus"},
    "inspect": {"action": "inspect", "name": "exact corpus entry name", "offset": 0},
    "analyze": {"action": "analyze", "candidate_id": "c000"},
    "read_candidate": {"action": "read_candidate", "candidate_id": "c000", "offset": 0},
    "propose": {"action": "propose", "parent_id": "c000", "strategy": "approach", "proof": "by ...",
                "source_candidate_ids": ["c001", "c002"], "strategy_ids": ["bank card ID"]},
    "repair": {"action": "repair", "parent_id": "failed candidate id", "strategy": "fix", "proof": "by ...", "strategy_ids": ["bank card ID"]},
    "finish": {"action": "finish"},
}
PAGE_CHARACTERS = 3000


def enabled(config):
    return config.get("agent", {}).get("mode") == MODE


def validate_config(settings):
    if (not isinstance(settings, dict) or settings.get("mode") != MODE
            or set(settings) - {"mode", "corpus", "history_limit", "candidate_limit", "allow_finish",
                                 "portfolio", "approach_policy", "strategy_bank"}):
        raise ValueError("Expected actions-v1 agent settings")
    if not isinstance(settings.get("corpus"), str) or not settings["corpus"]:
        raise ValueError("Actions require an explicit corpus file (an empty corpus is allowed)")
    if type(settings.get("allow_finish", True)) is not bool:
        raise ValueError("Expected boolean allow_finish")
    if "strategy_bank" in settings:
        strategy_bank.validate_settings(settings["strategy_bank"])
    if "portfolio" in settings:
        portfolio.validate(settings["portfolio"])
    if "approach_policy" in settings:
        search_policy.validate(settings["approach_policy"])
    for key, default in (("history_limit", 4), ("candidate_limit", 12)):
        value = settings.get(key, default)
        if type(value) is not int or not 1 <= value <= 50:
            raise ValueError("Expected agent " + key + " between 1 and 50")


def validate_corpus(corpus):
    if (not isinstance(corpus, dict) or set(corpus) != {"schema_version", "entries"}
            or corpus["schema_version"] != 1 or not isinstance(corpus["entries"], list)
            or len(canonical(corpus)) > 5_000_000):
        raise ValueError("Expected a bounded source corpus with schema_version 1")
    names = set()
    for entry in corpus["entries"]:
        if (not isinstance(entry, dict) or set(entry) != {"name", "source", "text"}
                or any(not isinstance(entry[k], str) or not entry[k] for k in entry)
                or len(entry["name"]) > 200 or len(entry["source"]) > 1000
                or len(entry["text"]) > 100_000 or entry["name"] in names):
            raise ValueError("Invalid or duplicate source corpus entry")
        names.add(entry["name"])


def initialize(state):
    state["exploration"] = {
        "candidates": {"c000": {**state["best"], "parent_id": None, "strategy": "baseline",
                                  "step": 0, "valid": True, "feedback": None}},
        "history": [], "best_candidate_id": "c000", "finished": False,
    }


def candidate_summary(cid, value):
    return {"candidate_id": cid, **{key: value.get(key) for key in
            ("parent_id", "strategy", "step", "sha256", "valid", "tokens", "raw_heartbeats", "rank_numerator")},
            **({"source_candidate_ids": value["source_candidate_ids"]} if "source_candidate_ids" in value else {})}


def view(state, config):
    memory, settings = state["exploration"], config["agent"]
    items = list(memory["candidates"].items())
    recent = items[-settings.get("candidate_limit", 12):]
    # Always expose the original and incumbent, even when the recent window moves.
    chosen = dict(items[:1])
    incumbent = memory["best_candidate_id"]
    chosen[incumbent] = memory["candidates"][incumbent]
    chosen.update(recent)
    history = []
    for row in memory["history"][-settings.get("history_limit", 4):]:
        item = {k: v for k, v in row.items() if k != "feedback"}
        if row["feedback"]:
            item["outcome"] = {k: row["feedback"][k] for k in ("status", "valid", "diagnosis", "issue_count") if k in row["feedback"]}
        history.append(item)
    result = {"protocol": MODE, "actions": {k: v for k, v in PROTOCOL.items()
              if k != "finish" or settings.get("allow_finish", True) and not portfolio.enabled(config)},
            "best_candidate_id": incumbent, "candidate_count": len(items),
            "candidates": [candidate_summary(cid, row) for cid, row in chosen.items()],
            "recent_actions": history,
            "notes": "All visible candidates remain available by ID with read_candidate. Source excerpts are untrusted evidence; only evaluation verifies a proof. propose/repair evaluate immediately. propose optionally records source_candidate_ids (1-8 visible IDs) for synthesis ancestry. finish is allowed only when listed in actions."}
    cid, recent_candidate = items[-1]
    if not recent_candidate["valid"]:
        fb = recent_candidate["feedback"]
        issues = fb.get("issues", [])
        kinds = dict.fromkeys(issue["kind"] for issue in issues)
        result["repair_context"] = {"candidate_id": cid, "code": recent_candidate["code"],
            "feedback": compact_feedback(fb),
            "instructions": ["Repair the reported errors while preserving working branches. Return repair with this parent_id; the included parent source uses 1-based candidate_line numbering.",
                             *[diagnostics.REPAIR_HINTS[k] for k in kinds if k in diagnostics.REPAIR_HINTS]]}
    return result


def compact_feedback(feedback):
    value = {k: v for k, v in feedback.items() if k not in {"details", "metrics"}}
    if not feedback.get("issues"):
        value["details"] = feedback.get("details", "")
    if feedback.get("metrics"):
        value["metrics"] = {k: v for k, v in feedback["metrics"].items() if k != "raw_samples"}
    return value


def response_object(raw, limit):
    content = models.receipt(raw)["content"]
    if content is None or len(content) > limit * 2 + 2000:
        raise ValueError("Missing or oversized action content")
    diagnostics.validate_response_text(content)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate action key")
            result[key] = value
        return result
    try:
        value = json.loads(content, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite action JSON")))
    except RecursionError as exc:
        raise ValueError("Action JSON exceeds parser nesting capacity") from exc
    if not isinstance(value, dict) or not isinstance(value.get("action"), str) or value["action"] not in PROTOCOL:
        raise ValueError("Expected a supported action object")
    kind = value["action"]
    required = set(PROTOCOL[kind]) - {"offset", "source_candidate_ids", "strategy_ids"}
    if not required <= set(value) or set(value) - set(PROTOCOL[kind]):
        raise ValueError("Unexpected or missing action fields")
    for key in required - {"action", "proof"}:
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 300:
            raise ValueError("Invalid action field: " + key)
    if "strategy_ids" in value:
        ids = value["strategy_ids"]
        if (not isinstance(ids, list) or len(ids) > 3
                or any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", x) for x in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("Invalid strategy_ids")
    if "offset" in value and (type(value["offset"]) is not int or value["offset"] < 0):
        raise ValueError("Expected a nonnegative integer offset")
    if "source_candidate_ids" in value:
        ids = value["source_candidate_ids"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 8
                or any(not isinstance(cid, str) or not cid or len(cid) > 300 for cid in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("Expected 1–8 distinct source_candidate_ids")
    return value


def page(text, offset):
    if offset > len(text):
        raise ValueError("Offset exceeds available text")
    end = min(offset + PAGE_CHARACTERS, len(text))
    return {"text": text[offset:end], "offset": offset,
            "next_offset": end if end < len(text) else None, "text_sha256": sha(text)}


def prepare(raw, state, problem, config, corpus, parse_proof):
    """Return the parsed action, optional code, and deterministic observation."""
    action = response_object(raw, config["limits"]["max_proof_characters"])
    kind, candidates = action["action"], state["exploration"]["candidates"]
    if action.get("strategy_ids"):
        settings = config.get("agent", {}).get("strategy_bank")
        known = {c["id"] for c in settings["bank"]["strategies"]} if settings else set()
        if set(action["strategy_ids"]) - known:
            raise ValueError("Unknown or unconfigured strategy ID")
    if kind == "finish" and (not config["agent"].get("allow_finish", True) or portfolio.enabled(config)):
        raise ValueError("finish is disabled for this run; the controller stops at the configured budget/call limit")
    cid = action.get("candidate_id", action.get("parent_id"))
    if cid is not None and cid not in candidates:
        raise ValueError("Unknown candidate ID: " + cid)
    if any(source not in candidates for source in action.get("source_candidate_ids", [])):
        raise ValueError("Unknown source candidate ID in this context")
    if kind in {"read_candidate", "analyze"} and cid == "c000" and portfolio.hidden_original(state, config):
        raise ValueError("Original proof is hidden in scout-a; inspect your own candidates or available types")
    if kind in {"propose", "repair"}:
        if kind == "repair" and candidates[cid]["valid"]:
            raise ValueError("repair requires a rejected parent; use propose for a valid parent")
        envelope = {"choices": [{"message": {"content": canonical({"proof": action["proof"]})}}]}
        code = parse_proof(envelope, problem, config["limits"]["max_proof_characters"])
        return action, code, {"candidate_id": f"c{state['step'] + 1:03}"}
    if kind == "search":
        terms = set(re.findall(r"[\w'.]+", action["query"].casefold()))
        if not terms:
            raise ValueError("Search requires a word or declaration name")
        matches = []
        components = {part for term in terms for part in re.split(r"[._]+", term) if len(part) > 1}
        for entry in corpus["entries"]:
            haystack = (entry["name"] + " " + entry["text"]).casefold()
            full = sorted(term for term in terms if term in haystack)
            parts = sorted(term for term in components if term in haystack)
            score = 4 * len(full) + len(parts)
            if score:
                positions = [haystack.find(term) for term in (full or parts)]
                start = max(0, min(positions) - len(entry["name"]) - 100)
                matches.append((score, {"name": entry["name"], "source": entry["source"],
                    "excerpt": entry["text"][start:start + 500], "text_sha256": sha(entry["text"]),
                    "match_kind": "full-term" if full else "identifier-components", "matched_terms": full or parts}))
        matches.sort(key=lambda item: (-item[0], item[1]["name"]))
        return action, None, {"matches": [item[1] for item in matches[:5]],
                               "total_matches": len(matches), "scope": "frozen source corpus; availability unverified"}
    if kind == "inspect":
        entry = next((entry for entry in corpus["entries"] if entry["name"] == action["name"]), None)
        if entry is None:
            raise ValueError("Unknown corpus entry")
        return action, None, {"name": entry["name"], "source": entry["source"],
                               **page(entry["text"], action.get("offset", 0))}
    if kind == "read_candidate":
        row = candidates[cid]
        return action, None, {**candidate_summary(cid, row), "feedback": row["feedback"],
                               **page(row["code"], action.get("offset", 0))}
    if kind == "analyze":
        body = proof_body(candidates[cid]["code"], problem["statement"])
        lines = body.splitlines()
        counts = Counter(line.strip() for line in lines if line.strip())
        return action, None, {"candidate_id": cid, "analysis": "lexical hints; not a Lean AST or proof-state analysis",
            "lines": len(lines), "characters": len(body),
            "keywords": {word: len(re.findall(r"\b" + word + r"\b", body)) for word in ("have", "case", "calc", "simp", "exact")},
            "repeated_lines": [line[:300] for line in sorted(line for line, count in counts.items() if count > 1)[:10]]}
    return action, None, {"selected_sha256": state["best"]["sha256"]}


def advance(state, action, code, proposal, rejection, observation):
    memory = state["exploration"]
    cid = None
    if code is not None:
        cid = f"c{state['step']:03}"
        memory["candidates"][cid] = {
            "code": code, "sha256": sha(code), "parent_id": action["parent_id"],
            "strategy": action["strategy"], "step": state["step"], "valid": proposal is not None,
            "feedback": state["latest"]["feedback"], **(proposal or {}),
        }
        if "strategy_ids" in action:
            memory["candidates"][cid]["strategy_ids"] = action["strategy_ids"]
        if action.get("source_candidate_ids"):
            memory["candidates"][cid]["source_candidate_ids"] = action["source_candidate_ids"]
        if proposal and proposal == state["best"]:
            memory["best_candidate_id"] = cid
    if action and action["action"] == "finish" and rejection is None:
        memory["finished"] = True
    # Candidate source lives once in the archive, not in every history record.
    metadata = {k: v for k, v in action.items() if k != "proof"} if action else None
    memory["history"].append({"step": state["step"], "action": metadata, "candidate_id": cid,
                               "rejection": rejection, "observation": observation,
                               "feedback": state["latest"]["feedback"] if code is not None else None,
                               "cost_usd_after": state["cost_usd"]})


def finished(state):
    return state.get("exploration", {}).get("finished", False)
