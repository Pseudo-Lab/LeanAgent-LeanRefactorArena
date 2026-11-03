"""Versioned structural/domain cues for v2 retrieval; no theorem-name routing.

Signals are lexical evidence, not semantic truth or an AST. Keep concrete match
locations so a user can inspect why a strategy was proposed. Match only inputs,
never candidate answers or per-case evidence stored in the offline review.
"""
import re
from .evaluator.tokens import without_comments

# Each tuple is an AND of regexes; alternatives inside a regex are OR.
RULES = {
    'state_relation_recursion': (r'UpdateStates|InitStates', r'\binduction\b'),
    'typing_recursion': (r'HasType|Typing|Denotes|typeCheck', r'\binduction\b|\bmatch\b|_inv\b'),
    'trace_recursion': (r'CanReach|MTr|Execution|ParallelReduction|parallel', r'\binduction\b|Nat\.find|\.extract|\.length'),
    'branch_duplication': (r'\bcase\b|\bcases\b|\binduction\b|\bsplit\b', r'\bsimp\b|\bgrind\b|\bconstructor\b'),
    'broad_search': (r'\b(?:grind|aesop)\b(?!\s+only)',),
    'proof_wrapper': (r':=\s*by\s+exact\b|\bby\s+exact\b',),
    'finite_decision': (r'\bdecide\b', r'\brevert\b|\bcases\b|\bFin\b|→|∀'),
    'homomorphic_representation': (r'GaussianInt|RingHom|AlgHom|toComplex', r'map_add|map_mul|map_neg|ofGaussianInt'),
    'linear_basis': (r'LinearMap|Multilinear|Basis|span_induction|ofCrAnList|Matrix\.det|\.det\b', r'\bsum\b|∑|\bspan\b|span_induction|\bmap_\w+|ofCrAnList'),
    'positive_matrix': (r'HermitianMat|Matrix', r'PosDef|PosSemidef'),
    'set_cardinality': (r'\.card\b|Fintype\.card|hammingDist|distFromCode', r'biUnion|\.image|union|fiber|[Ff]iber|Injective|card_le|card_bij'),
    'probability_implication': (r'Pr_|Pr\s|prob|Probability', r'≤|<|implies|R_star'),
    'rational_algebra': (r'\bfield_simp\b|\bnlinarith\b|\bring_nf\b|\bring\b|\blinear_combination\b', r'/|\^|Polynomial|ℚ|ℝ|ℤ'),
    'cast_roundtrip': (r'WithBot|WithTop|ENat|ℕ∞|exact_mod_cast|norm_cast', r'≤|<|degree|natDegree|\.card'),
    'derivative_expression': (r'HasDerivAt|HasFDerivAt|\bderiv\b|\bfderiv\b|∂ₜ|∂\[',),
    'finite_sum_counts': (r'∑|Finset\.sum', r'\.card|filter|if\b|sum_comm|sum_bij|sum_filter|det_apply'),
    'symmetry_context': (r'inter_comm|sqDist_comm|integral_comp_neg|extremalTest_even|compl_compl|braidWord',),
    'test_function_zero': (r'IsTestFunction', r'Continuous|ContDiff', r'∫|integral'),
    'continuity_control': (r'Continuous|UniformContinuous|ContinuousAt', r'IsCompact|[Cc]ompact|infDist|[Ll]ipschitz|ramp|\bmin\b|\bmax\b|intervalIntegrable'),
    'finite_state_sequence': (r'ℕ\s*→\s*ℤ|ℕ\s*→\s*ℝ', r'Finite|finite|[Bb]ounded|Set\.Icc', r'\+\s*1|\+\s*2'),
    'stateful_support': (r'simulateQ', r'support|probFailure', r'StateT'),
    'polynomial_degree': (r'Polynomial|[A-Z]\[X\]|\.natDegree', r'natDegree|degree|degreeX|degreeY'),
    'modular_integer_cases': (r'Int\.ModEq|Int\.emod|%\s*9|ZMod', r'ℤ|intCast'),
}


def clean(text):
    text = without_comments(text)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


def extract(statement, declaration):
    stmt = clean(statement)
    # Exclude the current theorem/lemma name from routing signals.
    stmt = re.sub(r'^\s*(?:theorem|lemma)\s+\S+', '', stmt)
    body_raw = declaration[len(statement):] if statement and declaration.startswith(statement) else declaration
    body = re.sub(r'^\s*(?:theorem|lemma)\s+\S+', '', clean(body_raw))
    text = stmt + '\n' + body
    matches = {}
    for name, patterns in RULES.items():
        hits = [re.search(pattern, text) for pattern in patterns]
        if all(hits):
            matches[name] = {'components': [h.group(0) for h in hits],
                             'locations': [{'section': 'statement' if h.start() < len(stmt) else 'body',
                                            'line': (stmt[:h.start()].count('\n') + 1 if h.start() < len(stmt)
                                                     else body[:max(0,h.start()-len(stmt)-1)].count('\n')+1)} for h in hits]}
    lines = [s.strip() for s in body.splitlines() if len(s.strip()) >= 18]
    repeated = sorted({s for s in lines if lines.count(s) >= 2})
    # Repeated nontrivial lemma invocations, excluding the theorem declaration.
    names = re.findall(r'(?:\b(?:apply|exact|using)\s+|:=\s*)([\w.\']{10,})', body)
    shared = sorted({s for s in names if names.count(s) >= 2})
    if repeated or shared:
        matches['repeated_derivation'] = {'components': ['repeated nontrivial lines' if repeated else 'repeated lemma invocations'],
                                          'locations': [], 'line_groups': len(repeated), 'lemma_groups': len(shared)}
    # A named have with exactly one occurrence after its declaration is an inlining
    # candidate, not proven unused: later automation can use local hypotheses.
    locals_ = []
    for m in re.finditer(r'\bhave\s+([A-Za-z_][\w\']*)\s*(?::|:=)', body):
        name = m.group(1)
        if len(re.findall(r'(?<![\w\'])'+re.escape(name)+r'(?![\w\'])',body[m.end():])) <= 1:
            locals_.append(body[:m.start()].count('\n')+1)
    if locals_:
        matches['single_use_fact'] = {'components': ['named local fact with at most one explicit later use'],
                                      'locations': [{'section':'body','line':n} for n in locals_[:3]]}
    return matches
