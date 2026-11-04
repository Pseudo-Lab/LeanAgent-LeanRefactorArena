"""Native InfoTree extraction and byte-range transformations in original context."""
import json
from pathlib import Path
import re
import textwrap
import uuid

from common import HERE, canonical, sha
from lean_agent.evaluator.lean import LeanEvaluator, execute, validate_template
from lean_agent.evaluator.tokens import validate_declaration

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


class NativeLean:
    # One compilation check followed by three heartbeat/axiom measurements.
    evaluation_processes = 4

    def __init__(self, environment, problem, folder, invoke=execute):
        self.environment, self.problem, self.folder = environment, problem, Path(folder)
        self.invoke = invoke
        self.folder.mkdir(parents=True, exist_ok=True)
        validate_template(environment['template'])

    def availability(self, tactics, timeout, memory):
        env = self.environment
        support = (HERE/'Support.lean').read_text().removeprefix('import Lean\n')
        nonce = uuid.uuid4().hex
        commands = '\n'.join(f'#recursive_repair_tactic "{nonce}" {json.dumps(t)}' for t in tactics)
        values = {'{{HARNESS_IMPORT}}': 'public import Lean' if re.search(r'(?m)^module\s*$', env['template']) else 'import Lean',
                  '{{HARNESS_COMMANDS}}': support, '{{DECLARATION}}': commands}
        source = re.sub('|'.join(map(re.escape, values)), lambda m: values[m[0]], env['template'])
        path = self.folder/'availability.lean'
        path.write_text(source)
        command = [a for a in env['command'] if not a.startswith('-M')]
        result = self.invoke([*command, f'-M{memory}', str(path.resolve())], Path(env['project']), timeout)
        (self.folder/'availability.log').write_text(result['output'])
        records = [json.loads(m) for m in re.findall(r'REPAIR_TACTIC ' + nonce + r' (\{[^\n]*\})', result['output'])]
        if result['returncode'] or result['timed_out'] or [r['tactic'] for r in records] != list(tactics):
            raise ValueError('Cannot establish native tactic availability')
        return records

    def inspect(self, code, label, timeout, memory):
        env = self.environment
        validate_declaration(code, self.problem['statement'])
        support = (HERE/'Support.lean').read_text().removeprefix('import Lean\n')
        nonce = uuid.uuid4().hex
        wrapper = f'set_option Elab.async false in\n#recursive_repair_context "{nonce}"\n'
        values = {'{{HARNESS_IMPORT}}': 'public import Lean' if re.search(r'(?m)^module\s*$', env['template']) else 'import Lean',
                  '{{HARNESS_COMMANDS}}': support, '{{DECLARATION}}': wrapper + code}
        source = re.sub('|'.join(map(re.escape, values)), lambda m: values[m[0]], env['template'])
        offset = len(source[:source.index(wrapper) + len(wrapper)].encode())
        path = self.folder / (label + '.lean')
        path.write_text(source)
        command = [a for a in env['command'] if not a.startswith('-M')]
        command += [f'-M{memory}', '--root=' + str(self.folder.resolve()), str(path.resolve())]
        result = self.invoke(command, Path(env['project']), timeout)
        (self.folder/(label+'.log')).write_text(result['output'])
        matches = re.findall(r'RECURSIVE_REPAIR ' + nonce + r' (\{[^\n]*\})', result['output'])
        if result['timed_out']:
            return {'kind': 'timeout', 'errors': [], 'tactics': [], 'blocks': [], 'seconds': result['seconds']}
        if len(matches) != 1:
            return {'kind': 'extraction_unavailable', 'errors': [], 'tactics': [], 'blocks': [],
                    'seconds': result['seconds'], 'returncode': result['returncode'], 'detail': result['output'][-3000:]}
        report = json.loads(matches[0])
        for record in [*report['tactics'], *report['blocks']]:
            for key in ('start', 'end'):
                if key in record:
                    record[key] -= offset
        for error in report['errors']:
            error['position'] -= offset
        report.update(kind='proof', seconds=result['seconds'], returncode=result['returncode'])
        return report

    def evaluate(self, code, label, timeout, memory):
        env = {**self.environment, 'timeout_seconds': timeout}
        env['command'] = [a for a in env['command'] if not a.startswith('-M')] + [f'-M{memory}']
        result = LeanEvaluator(executor=self.invoke).evaluate(
            code, self.problem, [env], self.folder/label, runs=self.evaluation_processes-1)
        # Results contain no output-directory-dependent strings; raw logs stay in native/.
        return result
