"""Deterministic, bounded reminders derived from the durable action archive.

No model summaries, external cache, or cross-problem state. The full history is
already checkpointed by the harness; these views survive the recent-action window
and restart, and portfolio callers supply only their scoped history.
"""
import re

from .artifacts import canonical

READ_ACTIONS = {"search", "inspect", "read_candidate", "analyze"}
GENERIC = {"theorem", "lemma", "def", "by", "eq", "the", "and", "of", "in"}
MAX_PACKET_CHARACTERS = 10000


def enabled(config):
    return config.get("agent", {}).get("persistent_memory", False)


def key(action):
    value = dict(action)
    if value["action"] == "search":
        value["query"] = " ".join(value["query"].casefold().split())
    if value["action"] in {"inspect", "read_candidate"}:
        value.setdefault("offset", 0)
    return canonical(value)


def lookups(history):
    entries = {}
    for row in history:
        action = row.get("action")
        if not action or action["action"] not in READ_ACTIONS:
            continue
        fingerprint = key(action)
        previous = entries.get(fingerprint)
        entries[fingerprint] = {"action": action, "first_step": previous["first_step"] if previous else row["step"],
            "last_step": row["step"], "count": (previous["count"] if previous else 0) + 1,
            "observation": row.get("observation"), "rejection": row.get("rejection")}
    return entries


def recall(history, action):
    previous = lookups(history).get(key(action))
    if previous and previous["observation"] is not None and previous["rejection"] is None:
        # The action is still a paid model turn. This reuses only a deterministic
        # tool observation; it never changes accounting or proof verification.
        return {**previous["observation"], "memory_reuse": {
            "first_step": previous["first_step"], "previous_count": previous["count"],
            "guidance": "This exact lookup was already answered. Use its evidence or make a different targeted query."}}
    return None


def brief(observation):
    if not observation:
        return None
    if "matches" in observation:
        return {"total_matches": observation["total_matches"], "matches": [
            {"name": row["name"], **({"excerpt": row["excerpt"][:180]} if index == 0 else {})}
            for index, row in enumerate(observation["matches"])],
            **({"guidance": observation["guidance"]} if "guidance" in observation else {})}
    return {k: (v[:400] if isinstance(v, str) else v) for k, v in observation.items()
            if k in {"name", "candidate_id", "offset", "next_offset", "text_sha256", "text",
                     "lines", "characters", "keywords", "analysis", "tokens", "raw_heartbeats"}}


def view(memory):
    entries = lookups(memory["history"])
    result = {"lookup_count": sum(x["count"] for x in entries.values()),
        "unique_lookup_count": len(entries), "lookups": [], "failed_strategies": [],
        "notes": "Persistent evidence from this problem/context, not verified lemma availability. "
                 "Reuse remembered results; change the query/page only for missing evidence. "
                 "Failures describe specific candidates, not a ban on a strategy or declaration. "
                 "Full observations remain in the archive; this prompt view is bounded."}
    # Frequent repeats stay visible even after leaving the recent-action window.
    ordered = sorted(entries.values(), key=lambda x: (-x["count"], -x["last_step"]))[:16]
    for item in ordered:
        result["lookups"].append({**{k: v for k, v in item.items() if k != "observation"},
                                  "result": brief(item["observation"])})
    failures = {}
    for cid, candidate in memory["candidates"].items():
        if candidate["valid"]:
            continue
        feedback = candidate.get("feedback") or {}
        strategy = candidate.get("strategy", "")
        parent = candidate.get("parent_id")
        fingerprint = (parent, strategy.casefold().strip())
        old = failures.get(fingerprint)
        failures[fingerprint] = {"candidate_id": cid, "parent_id": parent, "strategy": strategy[:300],
            "attempts": (old["attempts"] if old else 0) + 1,
            "last_step": candidate.get("step", 0),
            "status": feedback.get("status"), "diagnosis": str(feedback.get("diagnosis", ""))[:200],
            "issues": [{k: (v[:180] if isinstance(v, str) else v) for k, v in issue.items()
                        if k in {"kind", "message", "candidate_line"}} for issue in feedback.get("issues", [])[:2]],
            "details": feedback.get("details", "")[:250]}
    result["failed_strategy_count"] = len(failures)
    result["failed_strategies"] = sorted(failures.values(), key=lambda row: row["last_step"])[-8:]
    consecutive = 0
    for row in reversed(memory["history"]):
        if (row.get("action") or {}).get("action") not in READ_ACTIONS:
            break
        consecutive += 1
    result["consecutive_lookups"] = consecutive
    if consecutive >= 3:
        result["next_action_guidance"] = (
            "You have made at least three consecutive lookups. Prefer a concrete propose/repair using remembered evidence. "
            "Another lookup is allowed when a specific missing fact prevents a candidate; narrow its query.")
    while len(canonical(result)) > MAX_PACKET_CHARACTERS - 150:
        if len(result["lookups"]) > 4:
            result["lookups"].pop()
        elif result["failed_strategies"]:
            result["failed_strategies"].pop(0)
        else:
            result["lookups"].pop()
    result["omitted_lookups"] = len(entries) - len(result["lookups"])
    result["omitted_failed_strategies"] = len(failures) - len(result["failed_strategies"])
    return result


def search(query, corpus, sha):
    """Prefer exact names, then specific identifier components, then text."""
    terms = set(re.findall(r"[\w'.]+", query.casefold())) - GENERIC
    if not terms:
        return {"matches": [], "total_matches": 0, "scope": "frozen source corpus; availability unverified",
                "guidance": "Use a specific declaration name or identifier; generic theorem/eq queries are too broad."}
    components = {part for term in terms for part in re.split(r"[._]+", term)
                  if len(part) > 1 and part not in GENERIC}
    matches = []
    for entry in corpus["entries"]:
        name, text = entry["name"].casefold(), entry["text"].casefold()
        exact = name in terms
        full = sorted(term for term in terms if term in name or term in text)
        parts = sorted(term for term in components if term in name or term in text)
        if not full and not parts:
            continue
        name_score = sum(term in name for term in terms)
        name_parts = sum(term in re.split(r"[._]+", name) for term in components)
        score = (exact, name_score, name_parts, len(full), len(parts))
        positions = [text.find(term) for term in (full or parts) if term in text]
        start = max(0, min(positions, default=0) - 100)
        matches.append((score, {"name": entry["name"], "source": entry["source"],
            "excerpt": entry["text"][start:start + 500], "text_sha256": sha(entry["text"]),
            "match_kind": "exact-name" if exact else "full-term" if full else "identifier-components",
            "matched_terms": full or parts}))
    matches.sort(key=lambda item: (tuple(-int(x) for x in item[0]), item[1]["name"]))
    return {"matches": [item[1] for item in matches[:5]], "total_matches": len(matches),
            "scope": "frozen source corpus; availability unverified"}
