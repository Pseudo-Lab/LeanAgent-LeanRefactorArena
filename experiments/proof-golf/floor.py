"""Lexical length-floor estimate for every benchmark problem (no Lean, no API).

A proof that only names its distinct global premises once, inside one closer
(`by closer [p1, ..., pk]`), has 2k + 3 tokens. This "premise-list floor" is a
heuristic, not a proof bound: simp/grind-tagged premises could be dropped
(lower), and one closer may be unable to finish the proof (higher).
Globals are separated from local names lexically, so the lists need review.
"""
import argparse
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
from lean_agent.evaluator.tokens import OPERATORS, proof_body, without_comments

SYNTAX = set('''by at only using with fun from show have let set in if then else match do return
this it generalizing case next all_goals any_goals first try repeat repeat' focus on_goal pick_goal
intro intros rintro exact exacts apply refine refine' rw rwa rewrite erw nth_rw nth_rewrite simp simp_all
simpa dsimp simp_rw simp_arith norm_num norm_num1 obtain rcases cases cases' induction induction'
fun_induction constructor exists use ext funext congr gcongr linarith nlinarith omega ring ring_nf
field_simp positivity aesop grind decide trivial rfl assumption contradiction exfalso by_contra by_contra!
by_cases split split_ifs unfold delta specialize calc subst symm trans exact_mod_cast push_cast norm_cast
convert filter_upwards interval_cases fin_cases change clear rename_i left right apply_rules apply_fun
conv lhs rhs arg enter push_neg tauto continuity measurability fun_prop bound polyrith abel module
noncomm_ring zify qify lift rel mono choose wlog absurd? infer_instance inferInstance exact? apply?
injection injections nofun nomatch rintro' obtain' generalize clear_value revert iterate refl
simp? simp_all? field_simp? and_intros native_decide sorry admit unfold_let dsimp only
haveI letI suffices conv_lhs conv_rhs ring1 disch config enableSimp safe unsafe forward destruct
constructors case' false true add norm erase simp_arith rotate_left'''.split())
# Hypothesis-style names (h, hk, ih, Hup, h_foo) are local even when no binder was parsed.
LOCAL_NAME = re.compile(r"^(ih|h)[a-z0-9'₀-₉]*$|^h_|^H[A-Z]|^H[a-z0-9']+$")
BINDERS = {'intro', 'intros', 'rintro', 'fun', 'obtain', 'rename_i', 'next', 'case', 'have', 'let',
           'set', 'generalizing', 'choose', 'by_cases', 'by_contra', 'funext', 'ext', 'with', '|',
           '∀', '∃', 'λ', 'induction', 'cases', 'rcases', 'generalize'}
STOP = {':=', ':', '=>', ',', '↦'}


def lex(line):
    """Tokens exactly as evaluator/tokens.py counts them (one line)."""
    tokens, word = [], ''
    for c in line:
        if c.isalnum() or c in "._'":
            word += c
        else:
            if word:
                tokens.append(word); word = ''
            if not c.isspace():
                tokens.append(c)
    if word:
        tokens.append(word)
    spaced = ' '.join(tokens)
    for op in OPERATORS:
        spaced = spaced.replace(' '.join(op), op)
    return spaced.split()


def is_word(t):
    return t[0].isalnum() or t[0] in "_'"


def bound_names(lines):
    """Names introduced by binder syntax; everything after a binder keyword up to a stop token."""
    names = set()
    for toks in lines:
        active = False
        for t in toks:
            if t in BINDERS:
                active = True
            elif t in STOP:
                active = False
            elif active and is_word(t) and t not in SYNTAX:
                names.add(t)
    return names


def statement_binders(statement):
    names = set()
    for m in re.finditer(r'[({\[⦃]([^(){}\[\]⦃⦄:]+):', statement):
        names.update(w for w in re.findall(r"[^\s()]+", m[1]))
    for m in re.finditer(r'[∀∃λ]\s*([^,]+),', statement):
        names.update(w.strip('(){}') for w in re.findall(r"[^\s:]+", m[1].split(':')[0]))
    return names


def analyse(name, proof, statement):
    start = proof.find(statement)
    if start < 0:
        raise ValueError('Statement not found: ' + name)
    body = without_comments(proof_body(proof[start:], statement))
    lines = [lex(l) for l in body.splitlines() if l.strip()]
    local = bound_names(lines) | statement_binders(statement)
    stats = {'keyword': 0, 'global': 0, 'local': 0, 'punct': 0, 'number': 0}
    globals_ = {}
    for t in (t for toks in lines for t in toks):
        if not is_word(t):
            stats['punct'] += 1
        elif t in SYNTAX:
            stats['keyword'] += 1
        elif t[0].isdigit():
            stats['number'] += 1
        elif (t.split('.')[0] in local or t == '_' or (len(t) <= 2 and '.' not in t)
              or LOCAL_NAME.match(t.split('.')[0])):
            stats['local'] += 1
        else:
            stats['global'] += 1
            globals_[t] = globals_.get(t, 0) + 1
    tokens = sum(stats.values())
    return {'tokens': tokens, 'breakdown': stats, 'globals': globals_,
            'floor_list': 2 * len(globals_) + 3}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--submission', type=Path, required=True, help='JSONL with name and proof')
    ap.add_argument('--benchmark', type=Path, required=True, help='Benchmark JSONL with statement')
    ap.add_argument('--metrics', type=Path, required=True, help='measured-metrics.json (T0, H0, T, H)')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    bench = {}
    for line in a.benchmark.open():
        d = json.loads(line); bench[d['name']] = d
    metrics = json.loads(a.metrics.read_text())['problems']
    rows = []
    for i, line in enumerate(a.submission.open()):
        d = json.loads(line)
        m = metrics[i]
        r = analyse(d['name'], d['proof'], bench[d['name']]['statement'])
        t0, h0, h = m['reference_tokens'], m['reference_heartbeats'], m['heartbeats']
        rate = h0 / t0
        pts = 100 / (3 * t0)
        head = max(0, r['tokens'] - r['floor_list'])
        rows.append({'id': m['id'], 'name': d['name'], 'T0': t0, 'H0_k': h0, 'T': r['tokens'],
                     'T_metrics': m['tokens'], 'H_k': h, 'rate_k_per_token': round(rate, 2),
                     'H_over_r': round(h / rate, 1), 'phase': 'length' if h / rate < r['tokens'] else 'heartbeat',
                     'distinct_globals': len(r['globals']), 'global_mentions': sum(r['globals'].values()),
                     'floor_list': r['floor_list'], 'headroom_tokens': head,
                     'problem_pts_per_token': round(pts, 4), 'headroom_problem_pts': round(head * pts, 2),
                     'headroom_overall_pts': round(head * pts / len(metrics), 3),
                     'breakdown': r['breakdown'], 'globals': r['globals']})
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / 'floor.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    for x in rows:
        print(json.dumps({k: v for k, v in x.items() if k not in ('globals', 'name')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
