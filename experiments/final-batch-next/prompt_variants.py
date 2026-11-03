"""Predeclared prompt-only comparison; model, tools and scoring stay fixed."""
BASELINE = (
    "Optimization guidance: first look for existing lemmas, assumptions, or witnesses that remove proof steps. "
    "Then reduce repeated whole-context simplification or broad search using recorded evidence. "
    "Judge complete proof-token and heartbeat ratios together; a shorter proof can be worse. "
    "propose: state a short concrete approach in strategy and supply the complete replacement proof. "
    "repair: fix the reported errors in the named rejected parent, preserving working branches. "
    "search/inspect: retrieve a specific missing definition or theorem rather than repeatedly browsing. "
    "Start from best_candidate_id (including seed-best when present), the best verified incumbent. "
    "Use exploration.persistent_memory before searching or repeating a failed strategy. "
    "A failed strategy applies to its recorded parent/candidate; repair it with concrete new evidence. "
    "After repeated failure of the same approach, branch from another candidate or change the proof structure. "
)
STRUCTURE_REPAIR = (
    "Optimization loop: start from the verified best_candidate_id, including seed-best. "
    "Before cosmetic shortening, target a concrete source of proof work: duplicate case analysis, "
    "repeated normalization, repeated typing inversions, or repeated construction of the same witness. "
    "Try one structural hypothesis at a time: reuse an applicable lemma, eliminate an equivalence witness "
    "directly, transport a relational derivation, or share obligations across branches. These are options, "
    "not requirements when the goal does not fit. In strategy briefly name the work removed and the bridge "
    "needed to preserve the exact goal; use the existing JSON schema and provide the full proof. "
    "Consult persistent_memory first. Search/inspect only for a specific missing declaration or type "
    "blocking that hypothesis, and check the actual type before application. If three lookups occur "
    "without a candidate, prefer proposing from available evidence; further targeted lookup remains allowed. "
    "When a structural candidate fails, preserve its working branches and repair the reported goal/type "
    "mismatch, equality orientation, binder names, or missing implicit arguments. A local error does not "
    "disprove the structural idea. Do not replace the entire route merely because it failed once. "
    "If the same obstruction repeats without new evidence, change the bridge or branch from a retained "
    "candidate instead of repeating the edit. After a route verifies, remove the remaining shared work "
    "and redundant syntax. Judge length and raw-HB ratios together; never accept shorter as synonymous "
    "with better. Preserve the verified incumbent while exploring a risky branch. "
)
VARIANTS = {"baseline": BASELINE, "structure-repair-v1": STRUCTURE_REPAIR}


def policy(variant="baseline", strict_cap=False):
    if variant not in VARIANTS or type(strict_cap) is not bool:
        raise ValueError("Unknown prompt variant or nonboolean strict budget policy")
    return {"variant": variant, "strict_cap": strict_cap}
