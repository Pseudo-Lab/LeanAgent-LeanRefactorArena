"""Deterministic local proof golf: source rewrites + Lean screening, no model calls.

Greedy search on J = T + H/r with r = H0/T0 (token units). Screening compiles each
variant once with the measurement wrapper; the final candidate is re-measured by
the common LeanEvaluator (check + three runs). Tokens follow evaluator/tokens.py.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
from lean_agent.evaluator.lean import ALLOWED_AXIOMS, LeanEvaluator, execute, render
from lean_agent.evaluator import lean as lean_module

# Contexts that define their own `Name` (Cslib CCS) misresolve the wrapper's
# unqualified `Name.toString`; qualify it for this experiment only.
lean_module.WRAPPER = lean_module.WRAPPER.replace('(axioms.toList.map Name.toString)',
                                                  '(axioms.toList.map Lean.Name.toString)')
from lean_agent.evaluator.tokens import proof_tokens, validate_declaration

OPEN, CLOSE = '([⟨{', ')]⟩}'
CLOSERS = ['simp_all', 'simp', 'grind', 'assumption', 'rfl']
BULLET = re.compile(r'^[·.]\s+')


def depth(text):
    return sum((c in OPEN) - (c in CLOSE) for c in text)


def parse(code, statement):
    """Split a tactic proof into logical tactics (indent, one-line text)."""
    rest = code[len(statement):]
    m = re.match(r'\s*:=\s*by\b', rest)
    if not code.startswith(statement) or not m:
        raise ValueError('Expected the fixed statement followed by := by')
    tactics = []
    lines = rest[m.end():].split('\n')
    if lines[0].strip():
        lines[0] = '  ' + lines[0].strip()
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if tactics:
            ind, text = tactics[-1]
            col = ind + 2 if BULLET.match(text) else ind
            if depth(text) > 0 or indent > col:
                tactics[-1] = (ind, text + ' ' + line.strip())
                continue
        tactics.append((indent, line.strip()))
    return tactics


def assemble(statement, tactics):
    return statement + ' := by\n' + '\n'.join(' ' * i + t for i, t in tactics) + '\n'


def groups(text, opener='('):
    """Top-level bracket spans (start, end-exclusive) of the given opener."""
    spans, level, start = [], 0, None
    for k, c in enumerate(text):
        if c in OPEN:
            if level == 0 and c == opener:
                start = k
            level += 1
        elif c in CLOSE:
            level -= 1
            if level == 0 and start is not None:
                spans.append((start, k + 1))
                start = None
    return spans


def split_top(text):
    parts, level, cur = [], 0, ''
    for c in text:
        level += (c in OPEN) - (c in CLOSE)
        if c == ',' and level == 0:
            parts.append(cur.strip()); cur = ''
        else:
            cur += c
    return parts + [cur.strip()]


def words(text):
    """Word spans as the lexical counter sees them (alnum plus ._')."""
    spans, k = [], 0
    while k < len(text):
        if text[k].isalnum() or text[k] in "._'":
            j = k
            while j < len(text) and (text[j].isalnum() or text[j] in "._'"):
                j += 1
            spans.append((k, j)); k = j
        else:
            k += 1
    return spans


def block_end(tactics, i):
    ind = tactics[i][0]
    j = i + 1
    while j < len(tactics) and tactics[j][0] > ind:
        j += 1
    return j


def variants(tactics, dollar):
    """Yield (tag, tactics). Tags name the edited source, so they survive other edits."""
    n = len(tactics)
    for i, (ind, text) in enumerate(tactics):
        t = lambda new: tactics[:i] + new + tactics[i + 1:]
        end = block_end(tactics, i) if BULLET.match(text) else i + 1
        yield ('del', text), tactics[:i] + tactics[end:]
        if BULLET.match(text):
            body = [(ind, BULLET.sub('', text))] + [(k - 2, s) for k, s in tactics[i + 1:end]]
            yield ('unbullet', text), tactics[:i] + body + tactics[end:]
        for a, b in groups(text, '['):
            elts = split_top(text[a + 1:b - 1])
            for e in range(len(elts)):
                rest = elts[:e] + elts[e + 1:]
                new = text[:a] + ('[' + ', '.join(rest) + ']' if rest else '') + text[b:]
                yield ('elt', text, elts[e]), t([(ind, re.sub(r'\s+', ' ', new).strip())])
        m = re.fullmatch(r'rw \[(.*)\]', text)
        if m and '←' not in text:
            yield ('cases', text), t([(ind, 'cases ' + e) for e in split_top(m[1])])
            if i + 1 < n and tactics[i + 1][0] == ind and re.fullmatch(r'rw \[(.*)\]', tactics[i + 1][1]):
                merged = 'rw [' + m[1] + ', ' + tactics[i + 1][1][4:-1] + ']'
                yield ('merge', text), tactics[:i] + [(ind, merged)] + tactics[i + 2:]
        m = re.match(r'(exact|apply) ', text)
        spans = groups(text)
        if m and spans and spans[-1][1] == len(text) and spans[-1][0] > len(m[0]):
            a = spans[-1][0]
            yield ('chain', text), t([(ind, 'apply ' + text[len(m[0]):a].strip()), (ind, 'exact ' + text[a + 1:-1])])
        m = re.fullmatch(r"have ([\w'.]+) := (.+)", text)
        if m:
            name, expr = m[1], m[2]
            use = expr if len(words(expr)) == 1 and not re.search(r'[\s()]', expr) else '(' + expr + ')'
            pat = re.compile(r"(?<![\w.'])" + re.escape(name) + r"(?![\w.'])")
            later = [(k, pat.sub(lambda _: use, s)) for k, s in tactics[i + 1:]]
            yield ('inline', text), tactics[:i] + later
        for a, b in groups(text):
            yield ('unwrap', text, text[a:b]), t([(ind, text[:a] + text[a + 1:b - 1] + text[b:])])
            yield ('dropgrp', text, text[a:b]), t([(ind, re.sub(r'\s+', ' ', text[:a] + text[b:]).strip())])
            if dollar and b == len(text) and a > 0 and text[a - 1] == ' ':
                yield ('dollar', text, text[a:b]), t([(ind, text[:a] + '$ ' + text[a + 1:b - 1])])
        for a, b in words(text)[1:]:
            if a and text[a - 1] == '?':
                continue
            new = re.sub(r'\s+', ' ', text[:a] + text[b:]).strip()
            yield ('word', text, text[a:b], a), t([(ind, new)])
        for c in CLOSERS:
            yield ('trunc', text, c), tactics[:i] + [(ind, c)]
            if not BULLET.match(text) and len(words(text)) > 1:
                yield ('replace', text, c), t([(ind, c)])


class Golf:
    def __init__(self, problem_dir, output, workers, version=None):
        # run.py problem folders hold input.json; committed packets hold agent-input.json.
        packet = problem_dir / 'input.json'
        if not packet.exists():
            packet = problem_dir / 'agent-input.json'
        inp = json.loads(packet.read_text())['problem']
        env = json.loads((problem_dir / 'environment.json').read_text())
        if env.get('lead'):
            raise ValueError('Lead text is not supported by this experiment')
        # Screening uses one pinned version; check the others with verify.py afterwards.
        envs = [e for e in env['environments'] if version in (None, e['id'])][:1]
        if not envs:
            raise ValueError('No environment with id ' + str(version))
        self.problem, self.envs = inp, envs
        self.statement, self.name = inp['statement'], inp['name']
        self.out, self.workers = output, workers
        self.cache = {}

    def tokens(self, code):
        validate_declaration(code, self.statement)
        return proof_tokens(code, self.statement)

    def screen(self, code):
        if code in self.cache:
            return self.cache[code]
        env, nonce = self.envs[0], uuid.uuid4().hex
        folder = self.out / 'screen' / nonce[:12]
        folder.mkdir(parents=True)
        path = folder / 'measure.lean'
        path.write_text(render(env['template'], code, self.name, nonce))
        (folder / 'candidate.lean').write_text(code)
        r = execute([*env['command'], '--root=' + str(folder.resolve()), str(path.resolve())],
                    Path(env['project']), env['timeout_seconds'])
        (folder / 'measure.log').write_text(r['output'])
        res = {'valid': False, 'hb': None, 'error': None, 'seconds': r['seconds'], 'dir': folder.name}
        found = re.findall(r'REFACTOR_EVAL ' + nonce + r' (\{[^\n]*\})', r['output'])
        if r['timed_out']:
            res['error'] = 'timeout'
        elif r['returncode'] or len(found) != 1:
            m = re.search(r'error: ([^\n]*)', r['output'])
            res['error'] = m[1][:160] if m else r['output'][-160:]
        else:
            report = json.loads(found[0])
            if set(report['axioms']) <= ALLOWED_AXIOMS:
                res.update(valid=True, hb=report['raw'])
            else:
                res['error'] = 'axioms ' + str(report['axioms'])
        (folder / 'result.json').write_text(json.dumps(res))
        self.cache[code] = res
        return res

    def load(self):
        """Reuse screenings from an interrupted search in the same output folder."""
        for result in (self.out / 'screen').glob('*/result.json'):
            self.cache[(result.parent / 'candidate.lean').read_text()] = json.loads(result.read_text())

    def run(self, seed_code, rate, max_rounds, dollar, margin, log):
        cur = seed_code
        base = self.screen(cur)
        if not base['valid']:
            raise ValueError('Seed failed screening: ' + str(base['error']))
        cur_t = self.tokens(cur); cur_j = cur_t + base['hb'] / rate
        print(json.dumps({'event': 'seed', 'T': cur_t, 'hb_k': base['hb'] // 1000, 'J': round(cur_j, 3)}), flush=True)
        tried, good = set(), set()
        path = [{'round': 0, 'T': cur_t, 'hb': base['hb'], 'J': cur_j, 'tag': None}]
        for rnd in range(1, max_rounds + 1):
            seen, cands = set(), []
            for tag, tac in variants(parse(cur, self.statement), dollar):
                code = assemble(self.statement, tac)
                if code in seen or code == cur:
                    continue
                seen.add(code)
                try:
                    t = self.tokens(code)
                except ValueError:
                    continue
                if t < cur_t:
                    cands.append((tag, code, t))
            tiers = [[c for c in cands if c[0] in good],
                     [c for c in cands if c[0] not in good and c[0] not in tried],
                     [c for c in cands if c[0] not in good and c[0] in tried]]
            best = None
            for tier_no, tier in enumerate(tiers):
                if not tier:
                    continue
                with ThreadPoolExecutor(self.workers) as pool:
                    results = list(pool.map(lambda c: self.screen(c[1]), tier))
                for (tag, code, t), res in zip(tier, results):
                    tried.add(tag)
                    j = t + res['hb'] / rate if res['valid'] else None
                    log.write(json.dumps({'round': rnd, 'tier': tier_no, 'tag': list(map(str, tag)), 'T': t,
                                          'hb': res['hb'], 'J': j, 'valid': res['valid'],
                                          'error': res['error'], 'dir': res['dir']}, ensure_ascii=False) + '\n')
                    if j is not None and j < cur_j - margin:
                        good.add(tag)
                        if best is None or j < best[0]:
                            best = (j, tag, code, t, res['hb'])
                    else:
                        good.discard(tag)
                log.flush()
                if best:
                    break
            print(json.dumps({'event': 'round', 'round': rnd, 'candidates': len(cands),
                              'accepted': None if not best else {'tag': list(map(str, best[1])), 'T': best[3],
                                                                 'hb_k': best[4] // 1000, 'J': round(best[0], 3)}},
                             ensure_ascii=False), flush=True)
            if not best:
                break
            cur_j, tag, cur, cur_t, hb = best
            path.append({'round': rnd, 'T': cur_t, 'hb': hb, 'J': cur_j, 'tag': list(map(str, tag))})
        return cur, path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--problem-dir', type=Path, required=True,
                    help='Folder with input.json or agent-input.json, and environment.json')
    ap.add_argument('--version', help='Environment id used for screening (default: first)')
    ap.add_argument('--seed', type=Path, required=True, help='Valid candidate declaration (.lean)')
    ap.add_argument('--output', type=Path, required=True, help='New output folder')
    ap.add_argument('--h0', type=int, required=True, help='Original raw heartbeats')
    ap.add_argument('--t0', type=int, required=True, help='Original proof tokens')
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--max-rounds', type=int, default=40)
    ap.add_argument('--margin', type=float, default=0.3, help='Minimum J gain in token units')
    ap.add_argument('--no-dollar', action='store_true')
    ap.add_argument('--closers', nargs='*', help='Closer tactics tried by trunc/replace (default: built-in list)')
    ap.add_argument('--resume', action='store_true', help='Reuse screenings saved in --output')
    a = ap.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=a.resume)
    if a.closers is not None:
        CLOSERS[:] = a.closers
    golf = Golf(a.problem_dir.resolve(), out, a.workers, a.version)
    golf.load()
    seed = a.seed.read_text()
    (out / 'seed.lean').write_text(seed)
    rate = a.h0 / a.t0
    started = time.monotonic()
    with (out / 'screen-log.jsonl').open('a') as log:
        best, path = golf.run(seed, rate, a.max_rounds, not a.no_dollar, a.margin, log)
    (out / 'best.lean').write_text(best)
    final = LeanEvaluator().evaluate(best, {**golf.problem, 'statement': golf.statement}, golf.envs, out / 'final', 3)
    med = [r['median_heartbeats'] for r in final['environments'].values()]
    summary = {'seed': str(a.seed), 'T0': a.t0, 'H0': a.h0, 'rate_hb_per_token': rate, 'path': path,
               'final': {'valid': final['valid'], 'tokens': final['tokens'], 'hb_k': med[0] if med else None,
                         'objective': final['tokens'] / a.t0 + med[0] * 1000 / a.h0 if final['valid'] else None},
               'screened': len(golf.cache), 'seconds': round(time.monotonic() - started)}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps({'event': 'final', **summary['final'], 'screened': summary['screened']}), flush=True)


if __name__ == '__main__':
    main()
