"""Native goal collection and guarded byte edits, adapted from repair PRs #41/#42.

Source: 9fe17e5 experiments/verification-repair-policy/{native.py,Support.lean}.
Instrumentation is trusted diagnostic code; final acceptance uses the evaluator.
"""
import json
from pathlib import Path
import re
import textwrap
import uuid

from .artifacts import canonical, sha, write

from .evaluator.tokens import validate_declaration

SEQUENCES = {'Lean.Parser.Tactic.tacticSeq', 'Lean.Parser.Tactic.tacticSeq1Indented',
             'Lean.Parser.Tactic.tacticSeqBracketed'}
SCOPES = {'Lean.Parser.Term.byTactic', 'Lean.cdot'}


def source_bytes(code, start, end):
    return code.encode('utf-8')[start:end].decode('utf-8')


def splice(code, start, end, replacement):
    data = code.encode('utf-8')
    if not 0 <= start <= end <= len(data):
        raise ValueError('Source range outside declaration')
    # Decode both boundaries: do not silently split a multibyte identifier.
    return data[:start].decode() + replacement + data[end:].decode()


def select_site(report, code, region=None):
    """Use native message positions and tactic states, never printed goal parsing."""
    errors = [e for e in report.get('errors', [])
              if region is None or region[0] <= e['position'] < region[1]]
    if not errors:
        return None
    error = errors[0]
    pos = error['position']
    states = [s for s in report.get('tactics', []) if 'start' in s and 'end' in s
              and 0 <= s['start'] < s['end'] <= len(code.encode())]
    # Raw syntax retains nested `have ... := by` blocks even when elaboration
    # expands them into `case`/`by` tactics instead of a Term.byTactic Info node.
    scopes = [s for s in [*report.get('blocks', []),
                         *(s for s in states if s['syntax_kind'] in SCOPES)]
              if 'start' in s and 'end' in s and 0 <= s['start'] <= pos < s['end'] <= len(code.encode())]
    if not scopes:
        return None
    scope = min(scopes, key=lambda s: s['end'] - s['start'])
    owned = [s for s in states if scope['start'] <= s['start'] and s['end'] <= scope['end']]
    if error['message'].startswith('unsolved goals'):
        sequences = [s for s in owned if s['syntax_kind'] in SEQUENCES
                     and s['end'] == scope['end']]
        if not sequences:
            # A one-tactic `have` may emit only the terminal tactic's InfoTree
            # node (no body tacticSeq). It still must end at this raw block end.
            sequences = [s for s in owned if s['syntax_kind'].startswith('Lean.Parser.Tactic.')
                         and s['syntax_kind'] not in SCOPES and s['end'] == scope['end']]
        if not sequences:
            return None
        # Use the complete sequence's outermost observation, including an empty
        # after-state. Macro-generated intermediate goals are not residual goals.
        start = min(s['start'] for s in sequences)
        sequences = [s for s in sequences if s['start'] == start]
        depth = min(s['depth'] for s in sequences)
        sequences = [s for s in sequences if s['depth'] == depth]
        if len({canonical(s['after']) for s in sequences}) != 1:
            return None
        seq = sequences[0]
        goals, start, end, append = seq['after'], seq['end'], seq['end'], True
        indent_at = seq['start']
    else:
        candidates = [s for s in owned if s['before'] and s['start'] <= pos < s['end']
                      and s['syntax_kind'] not in SEQUENCES | SCOPES | {'by', 'Lean.cdotTk'}]
        if not candidates:
            return None
        tactic = min(candidates, key=lambda s: (s['end']-s['start'], -s['depth']))
        sequences = [s for s in owned if s['syntax_kind'] in SEQUENCES
                     and s['start'] <= tactic['start'] and tactic['end'] <= s['end']]
        if not sequences:
            # The same one-tactic `have` expansion can omit its body sequence
            # on a concrete error. Replace only the terminal tactic, never an
            # outer sequence that crosses this syntax block's boundary.
            if tactic['end'] != scope['end']:
                return None
            end = tactic['end']
        else:
            end = min(sequences, key=lambda s: s['end']-s['start'])['end']
        goals, start, append = tactic['before'], tactic['start'], False
        indent_at = tactic['start']
    if not goals or not all(isinstance(g.get('local_context'), list) and g.get('target') for g in goals):
        return None
    prefix = code.encode()[:indent_at].decode()
    indent = len(prefix.rsplit('\n', 1)[-1])
    site = {'start': start, 'end': end, 'append': append, 'indent': indent,
            'goal': goals[0], 'pending_goals': goals, 'error': error,
            'source_sha256': sha(code)}
    if region is not None and not (region[0] <= start <= end <= region[1]):
        return None
    return site


def patch_site(code, site, proof):
    """Wrap one proof in `exact (by ...)`, so other goals keep their own scope."""
    if sha(code) != site['source_sha256']:
        raise ValueError('Stale source range')
    if not re.match(r'^by\b', proof.strip()):
        raise ValueError('Subproof must be a by term')
    # Validate a synthetic declaration through the same repository guard.
    statement = 'theorem recursive_repair_fragment : True'
    validate_declaration(statement + ' := ' + proof, statement)
    body = textwrap.dedent(proof.strip()[2:]).strip()
    if not body:
        raise ValueError('Empty subproof')
    indent = site['indent']
    lead = '\n' + ' ' * indent if site['append'] else ''
    replacement = lead + 'exact (by\n' + textwrap.indent(body, ' ' * (indent + 2)) + '\n' + ' ' * indent + ')'
    start, end = site['start'], site['end']
    result = splice(code, start, end, replacement)
    inner_start = start + len((lead + 'exact (').encode())
    # Include the inserted term only; sibling errors are not child obligations.
    region = (inner_start, start + len(replacement.encode()))
    return result, region


def local_closed(report, region):
    if report.get('kind') != 'proof':
        return False
    if any(region[0] <= e['position'] < region[1] for e in report['errors']):
        return False
    return any(s.get('start') == region[0] and s['syntax_kind'] == 'Lean.Parser.Term.byTactic'
               and s['before'] and not s['after'] for s in report['tactics'])


def observe(code, statement, output, build_source, run_source, *, timeout, memory):
    """Collect native states through the caller's pinned compiler/executor.

    build_source(support, declaration) preserves the original context;
    run_source(path, timeout, memory) preserves setup, sandbox and libraries.
    Missing instrumentation is a capability failure, never a verified proof.
    """
    validate_declaration(code, statement)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    support = (Path(__file__).parent / 'support/AutoSolver.lean').read_text().removeprefix('import Lean\n')
    nonce = uuid.uuid4().hex
    wrapper = f'set_option Elab.async false in\n#recursive_repair_context "{nonce}"\n'
    source = build_source(support, wrapper + code)
    offset = len(source[:source.index(wrapper) + len(wrapper)].encode())
    path = output / 'instrumented.lean'
    path.write_text(source)
    result = run_source(path, timeout, memory)
    log = result.pop('output')
    (output / 'compiler.log').write_text(log)
    write(output / 'execution.json', result)
    matches = re.findall(r'RECURSIVE_REPAIR ' + nonce + r' (\{[^\n]*\})', log)
    report = {'kind': 'extraction_unavailable', 'errors': [], 'tactics': [], 'blocks': [],
              'seconds': result['seconds'], 'returncode': result['returncode'],
              'source_sha256': sha(code)}
    if result['timed_out']:
        report['kind'] = 'timeout'
    elif len(matches) == 1:
        observed = json.loads(matches[0])
        for record in [*observed['tactics'], *observed['blocks']]:
            for key in ('start', 'end'):
                if key in record:
                    record[key] -= offset
        for error in observed['errors']:
            error['position'] -= offset
        report.update(observed, kind='proof')
    else:
        report['detail'] = log[-3000:]
    write(output / 'result.json', report)
    return report
