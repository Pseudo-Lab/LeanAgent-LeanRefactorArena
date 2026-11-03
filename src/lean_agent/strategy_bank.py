"""Optional, deterministic strategy hints. No model/Lean calls or external I/O.

Rule scoring adapts Chaewon Park's PR #50 Strategy Retriever (all/any tags,
tactic minima, stable ties). Evidence stays offline; requests contain generic
cards only. Final-derived banks describe benchmark adaptation, not generalization.
"""
import re

from .artifacts import canonical, sha
from .evaluator.tokens import without_comments
from . import strategy_signals

TACTICS = ("have", "calc", "cases", "rcases", "induction", "obtain", "simp",
           "simp_all", "grind", "aesop", "rw", "exact", "apply", "refine")


def features(code):
    # A lexical signal, never an AST, tactic cost estimate, or official tokenizer.
    clean = without_comments(code)
    clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', clean)
    counts = {w: len(re.findall(r"(?<![\w.])" + w + r"(?![\w'])", clean)) for w in TACTICS}
    return {"counts": counts, "tags": ["repeated_automation"] if
            sum(counts[w] for w in ("simp", "simp_all", "grind", "aesop")) >= 3 else []}


def validate(bank):
    if (not isinstance(bank, dict) or set(bank) != {"schema_version", "version", "scope", "strategies"}
            or type(bank["schema_version"]) is not int or bank["schema_version"] not in (1, 2) or not isinstance(bank["version"], str)
            or not 1 <= len(bank["version"]) <= 100 or bank["scope"] not in ("warmup", "final-adaptation")
            or not isinstance(bank["strategies"], list) or not 1 <= len(bank["strategies"]) <= 30
            or len(canonical(bank)) > 100000):
        raise ValueError("Invalid strategy bank")
    ids = set()
    for card in bank["strategies"]:
        if (not isinstance(card, dict) or set(card) - {"metadata"} != ({"id", "title", "match", "guide", "risks", "evidence"} |
                   ({"title_ko", "mechanism", "status", "constraints", "recipes"} if bank["schema_version"] == 2 else set()))
                or not isinstance(card["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", card["id"])
                or card["id"] in ids):
            raise ValueError("Invalid or duplicate strategy card")
        ids.add(card["id"])
        if "metadata" in card:
            m = card["metadata"]
            if (not isinstance(m, dict) or set(m) != {"description", "when_to_apply", "objectives", "review_status", "attribution"}
                    or any(not isinstance(m[k], str) or not 1 <= len(m[k]) <= 2000 for k in ("description", "when_to_apply"))
                    or m["review_status"] not in ("review_required", "approved", "rejected")
                    or m["attribution"] not in ("joint", "isolated", "unmeasured")
                    or not isinstance(m["objectives"], list) or any(x not in ("hb", "tokens", "compatibility") for x in m["objectives"])):
                raise ValueError("Invalid strategy metadata")
        if any(not isinstance(card[k], str) or not 1 <= len(card[k]) <= 1500 for k in ("title", "guide", "risks")):
            raise ValueError("Invalid strategy text")
        match = card["match"]
        if bank["schema_version"] == 2:
            if (not isinstance(match, dict) or set(match) != {"requires", "optional"}
                    or not isinstance(match["requires"], list) or not match["requires"]
                    or not isinstance(match["optional"], list)):
                raise ValueError("Expected v2 signal gates")
            known = set(strategy_signals.RULES) | {"repeated_derivation", "single_use_fact"}
            if any(not isinstance(group, list) or not group or any(not isinstance(t,str) or t not in known for t in group)
                   for group in match["requires"]) or any(not isinstance(t,str) or t not in known for t in match["optional"]):
                raise ValueError("Unknown v2 signal")
            if (card["status"] not in ("observed-multiple-problems", "observed-single-problem")
                    or any(not isinstance(card[k],str) or not 1 <= len(card[k]) <= 1800
                           for k in ("title_ko", "mechanism", "constraints"))
                    or not isinstance(card["recipes"],list) or not card["recipes"]
                    or any(not isinstance(v,str) or not 1 <= len(v) <= 1500 for v in card["recipes"])):
                raise ValueError("Invalid v2 strategy semantics")
        elif not isinstance(match, dict) or set(match) - {"all_tags", "any_tags", "tactic_min"}:
            raise ValueError("Invalid strategy match")
        for key in ("all_tags", "any_tags"):
            if key in match and (not isinstance(match[key], list) or
                                any(t != "repeated_automation" for t in match[key])):
                raise ValueError("Unknown strategy tag")
        minima = match.get("tactic_min", {})
        if (not isinstance(minima, dict) or any(k not in TACTICS or type(v) is not int or not 1 <= v <= 100
                                                for k, v in minima.items())):
            raise ValueError("Invalid tactic minimum")
        if (not isinstance(card["evidence"], list) or not card["evidence"] or
                any(not isinstance(e, dict) or set(e) != {"problem", "candidate_sha256"}
                    or not isinstance(e["problem"], str) or not 1 <= len(e["problem"]) <= 1000
                    or not isinstance(e["candidate_sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", e["candidate_sha256"]) for e in card["evidence"])):
            raise ValueError("Invalid strategy evidence identity")


def validate_settings(settings):
    if (not isinstance(settings, dict) or not {"bank", "top_k"} <= set(settings) or set(settings) - {"bank", "top_k", "contextual", "search_policy"}
            or type(settings["top_k"]) is not int or not 1 <= settings["top_k"] <= 3):
        raise ValueError("Strategy bank requires bank and top_k (1..3)")
    if "contextual" in settings and type(settings["contextual"]) is not bool:
        raise ValueError("contextual must be boolean")
    if settings.get("search_policy", "guided") not in ("guided", "alternating-v1"):
        raise ValueError("Unknown strategy search_policy")
    validate(settings["bank"])


def score(match, feat):
    if "requires" in match:
        signals = set(feat["signals"])
        if any(not signals.intersection(group) for group in match["requires"]):
            return None
        optional = match["optional"]
        # All hard gates are mandatory. Optional coverage is normalized so cards
        # with longer condition lists do not get more points merely for length.
        generic = {"repeated_derivation", "single_use_fact", "proof_wrapper", "branch_duplication",
                   "broad_search", "rational_algebra", "cast_roundtrip"}
        required_hits = {t for group in match["requires"] for t in group if t in signals}
        specificity = 2 if required_hits - generic else 1
        return specificity + 0.5 * (sum(t in signals for t in optional) / len(optional) if optional else 0)
    tags, counts = set(feat["tags"]), feat["counts"]
    if not set(match.get("all_tags", [])) <= tags:
        return None
    hits = [t for t in match.get("any_tags", []) if t in tags]
    hits += [w for w, n in match.get("tactic_min", {}).items() if counts.get(w, 0) >= n]
    if (match.get("any_tags") or match.get("tactic_min")) and not hits:
        return None
    return len(match.get("all_tags", [])) + len(hits)


def packet(problem, settings, *, hidden=False, current_proof=None, objective=None, excluded_ids=()):
    validate_settings(settings)
    bank = settings["bank"]
    identity = {"bank_version": bank["version"], "bank_sha256": sha(canonical(bank)),
                "scope": bank["scope"], "policy": ("signal-gated-other-problem-evidence-v2" if bank["schema_version"] == 2
                           else "generic-cards-other-problem-evidence-v1")}
    # No reference-derived signals, excluded IDs or retrieved cards in hidden scout.
    if hidden:
        return {**identity, "status": "withheld_hidden_original", "strategies": []}
    if objective not in (None, "hb", "tokens", "compatibility"):
        raise ValueError("Unknown strategy objective")
    code = problem["reference"] if current_proof is None else current_proof
    feat = features(code)
    if bank["schema_version"] == 2:
        feat["signals"] = strategy_signals.extract(problem.get("statement", ""), code)
    ranked = []
    for index, card in enumerate(bank["strategies"]):
        if card["id"] in excluded_ids or card.get("metadata", {}).get("review_status") == "rejected":
            continue
        # Remove this problem's evidence even when a card also has other examples.
        other = {e["problem"] for e in card["evidence"] if e["problem"] != problem["name"]}
        value = score(card["match"], feat)
        if other and value is not None:
            if objective in card.get("metadata", {}).get("objectives", []):
                value += 0.25
            ranked.append((-value, index, card, len(other)))
    cards = [{"id": c["id"], "title": c["title"], "guide": c["guide"], "risks": c["risks"],
              "match_score": -s, "other_evidence_problems": n}
             for s, _, c, n in sorted(ranked, key=lambda x: (x[0], x[1]))[:settings["top_k"]]]
    if bank["schema_version"] == 2:
        for result in cards:
            card = next(c for c in bank["strategies"] if c["id"] == result["id"])
            relevant = {s for group in card["match"]["requires"] for s in group} | set(card["match"]["optional"])
            result.update(title_ko=card["title_ko"], constraints=card["constraints"],
                          matched_signals={s: feat["signals"][s] for s in sorted(relevant & set(feat["signals"]))})
    return {**identity, "status": "retrieved" if cards else "no_match", "strategies": cards,
            "note": "Optional hypotheses, not verified edits. Do not treat match scores as proof quality. "
                    "Evidence describes complete candidate changes; individual tactic effects are not isolated."}


def hints(value):
    """Proposal-compatible generic hints; no source answers or evidence excerpts."""
    return [{"strategy_id": c["id"], "title": c["title"],
             "application_guide": [c["guide"]], "risk_notes": [c["risks"]],
             "match_score": c["match_score"], "why": c.get("matched_signals", {})}
            for c in value["strategies"]]


def search_mode(settings, request, *, hidden=False):
    """Alternate by completed candidates, not tool calls or truncated history."""
    if hidden:
        return "withheld"
    if settings.get("search_policy", "guided") == "alternating-v1":
        # The controller's local evaluation count resets for each branch/round.
        # Counting visible candidates would include other scouts in the merger
        # and an extra seed in subsequent rounds.
        if "portfolio" in request:
            evaluated = request["portfolio"].get("evaluated")
            if type(evaluated) is not int or evaluated < 0:
                raise ValueError("alternating-v1 requires portfolio evaluated count")
            return "free" if evaluated % 2 == 0 else "guided"
        count = request.get("exploration", {}).get("candidate_count")
        if type(count) is not int or count < 1:
            raise ValueError("alternating-v1 requires actions candidate_count")
        return "free" if (count - 1) % 2 == 0 else "guided"
    return "guided"


def without_strategy_history(value):
    """Remove explicit historical Bank labels from a free request copy.

    Proof code and diagnostics remain visible; this is not an independent reset.
    """
    if isinstance(value, dict):
        # Action examples describe required protocol fields, not past strategy
        # choices. Keep the required `strategy` field usable in free requests.
        result = {k: ({kind: {field: sample for field, sample in fields.items() if field != "strategy_ids"}
                     for kind, fields in v.items()} if k == "actions" else without_strategy_history(v))
                for k, v in value.items()
                if k not in {"strategy", "strategy_ids", "strategy_hints", "recommended_ids"}}
        if value.get("status") == "tool_result" and "details" in result:
            # details is a serialized, possibly truncated copy of the tool
            # observation. Its embedded labels evade structural redaction.
            # The same observation is already available as a redacted dict.
            result.pop("details")
            result["details_ref"] = "exploration.recent_actions[-1].observation"
        return result
    if isinstance(value, list):
        return [without_strategy_history(v) for v in value]
    return value


def for_request(problem, settings, request, *, hidden=False):
    """Use only visible snapshotted request data; reproducible by the auditor."""
    validate_settings(settings)
    mode = search_mode(settings, request, hidden=hidden)
    if mode == "free":
        bank = settings["bank"]
        return {"bank_version": bank["version"], "bank_sha256": sha(canonical(bank)),
                "scope": bank["scope"], "policy": "alternating-v1",
                "search_mode": "free", "status": "withheld_free_exploration",
                "strategies": [], "strategy_hints": [],
                "note": "Develop your own proof modification without Bank hints. "
                        "Existing proofs and verification feedback remain available."}
    if settings.get("search_policy") == "alternating-v1" and not hidden:
        guided = dict(settings, search_policy="guided")
        result = for_request(problem, guided, request)
        result.update(search_mode="guided", search_policy="alternating-v1")
        return result
    if not settings.get("contextual", False) or hidden:
        return packet(problem, settings, hidden=hidden)
    best = request["best"]
    code = best.get("code", problem["reference"])
    baseline = request["baseline"]
    objective = max(("tokens", "hb"), key=lambda key:
        best.get("tokens" if key == "tokens" else "raw_heartbeats", 0) /
        max(1, baseline.get("tokens" if key == "tokens" else "raw_heartbeats", 0)))
    failed = set()
    for row in request.get("exploration", {}).get("recent_actions", []):
        action = row.get("action") or {}
        feedback = row.get("outcome") or {}
        if feedback.get("valid") is False and feedback.get("status") == "proof_rejected":
            failed.update(action.get("strategy_ids", []))
    result = packet(problem, settings, current_proof=code, objective=objective, excluded_ids=failed)
    result["context"] = {"proof_sha256": sha(code), "objective": objective,
                         "excluded_ids": sorted(failed), "history_scope": "visible recent actions"}
    result["strategy_hints"] = hints(result)
    result["tracking"] = "On propose/repair, report selected Bank IDs in optional strategy_ids (0..3). This declares selection only; actual edits require review. Unmatched strategies may be chosen explicitly."
    return result
