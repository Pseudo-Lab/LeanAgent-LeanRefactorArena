"""Verify the published P12 proof under separate Somi v2, never the common PR3 score."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import traceback
import urllib.request

import verify_warmup_pins as common
import p12_fullsource_verifier as somi

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / 'benchmarks/arena/56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c/benchmark_data_warmup.jsonl'
BENCHMARK_SHA = '6209680cf00cde0765b77b24834cd72c64dd585b2f7e3f2a58209980ab59a804'
BENCHMARK_URL = 'https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/resolve/56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c/benchmark_data_warmup.jsonl'
PROTOCOL = 'Somi-full-source-2026-10-05; finite-cardinality-gate-v2'
PROOF_SHA = 'be1118ac252a8eecb4a94b4788dd981dba9c21bc8214ad8478e5a0d1e7a0acc8'
STATEMENT_SHA = 'a5fa44f5255cfd05d237fcee036ff87fa7f71b4a2a875ff514d48290bc3047fe'
TOKENIZER_SHA = '733f6ebb4274de88fe448d04879ba3ee58e07e725c62a7e5e4ef122cabf2394d'
ALLOWED_AXIOMS = {'propext', 'Classical.choice', 'Quot.sound'}
REPETITIONS = 3


def benchmark_bytes():
    expected = json.loads(BENCHMARK.with_name('snapshot.json').read_text())['files'][BENCHMARK.name]
    if expected != {'url': BENCHMARK_URL, 'sha256': BENCHMARK_SHA, 'bytes': 113826}:
        raise ValueError('Frozen benchmark manifest changed')
    cached = BENCHMARK.is_file()
    if cached:
        data = BENCHMARK.read_bytes()
    else:
        with urllib.request.urlopen(expected['url'], timeout=60) as response:
            data = response.read(expected['bytes'] + 1)
    if len(data) != expected['bytes'] or common.sha(data) != expected['sha256']:
        raise ValueError('Frozen benchmark size/hash mismatch')
    if not cached:
        BENCHMARK.write_bytes(data)
    return data


def load_inputs():
    rows = [json.loads(line) for line in benchmark_bytes().decode('utf-8').splitlines() if line.strip()]
    meta = rows[11]
    public = json.loads((ROOT / 'dashboard/public/research/warmup15/p12-v2.json').read_text())
    relative = public['publishedProof'].removeprefix('/')
    path = (ROOT / 'dashboard/public' / relative).resolve()
    if not path.is_relative_to((ROOT / 'dashboard/public').resolve()):
        raise ValueError('Published proof path leaves public assets')
    code = path.read_bytes().decode('utf-8')
    if common.sha(code.encode()) != PROOF_SHA or public['candidate']['candidateSha256'] != PROOF_SHA:
        raise ValueError('Published P12 proof changed')
    if common.sha(meta['statement'].encode()) != STATEMENT_SHA or public['statementSha256'] != STATEMENT_SHA:
        raise ValueError('Fixed P12 statement changed')
    original = meta['src']
    if common.sha(original.encode()) != public['original']['candidateSha256']:
        raise ValueError('Original proof differs from the published v2 control')
    if public['protocol'] != PROTOCOL or public['frozenPR3Compatible'] or public['countsInCommonScore']:
        raise ValueError('P12 separate protocol identity changed')
    return rows, meta, public, original, code


def frozen_tokens(work):
    source = subprocess.check_output(['git', '-C', str(ROOT), 'show',
        f'{common.EVALUATOR_REVISION}:refactor_eval/tokens.py'])
    if common.sha(source) != TOKENIZER_SHA:
        raise ValueError('Frozen tokenizer identity changed')
    path = work / 'frozen_tokens.py'
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location('p12_frozen_tokens', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate(code, statement, tokens):
    # Relax only #(...), without changing a byte of the source sent to Lean.
    if re.search(r'#(?!\s*\()', tokens.without_comments(code)):
        raise ValueError('Only existing finite-cardinality #(...) syntax is permitted')
    tokens.validate_declaration(re.sub(r'#(?=\s*\()', '', code), statement)
    count = tokens.proof_tokens(code, statement)
    if count != somi.proof_tokens.proof_length(code, statement):
        raise ValueError('Somi and frozen source token counts disagree')
    return count


def audit_run(report, name, returncode):
    lines = [line for line in report['check']['axioms'] if f"'{name}'" in line]
    groups = re.findall(r'\[([^\]]*)\]', ' '.join(lines))
    actual = set(re.findall(r'[\w.]+', groups[-1])) if groups else set()
    axiom_free = any('does not depend on any axioms' in line for line in lines)
    allowed = len(lines) == 1 and (bool(groups) or axiom_free) and actual <= ALLOWED_AXIOMS
    heartbeat = report.get('heartbeat', {})
    valid = (returncode == 0 and report['statement_unchanged'] and not report['forbidden_patterns']
        and report['compiled'] and allowed and heartbeat.get('returncode') == 0
        and type(heartbeat.get('heartbeats')) is int and heartbeat['heartbeats'] >= 0
        and not heartbeat.get('timed_out') and not heartbeat.get('measurement_ambiguous'))
    if valid:
        kind = None
    elif report['check'].get('timed_out') or heartbeat.get('timed_out'):
        kind = 'environment_timeout'
    elif not report['statement_unchanged'] or report['forbidden_patterns']:
        kind = 'validation'
    elif not report['compiled']:
        text = ' '.join(report['check'].get('first_errors', [])).lower()
        kind = 'environment' if any(x in text for x in ('object file', 'unknown package',
            'memory', 'cannot find', 'no such file', 'toolchain', 'invalid header')) else 'compile'
    elif not allowed:
        kind = 'axioms'
    else:
        kind = 'measurement'
    report.update(driverReturncode=returncode, actualAxioms=sorted(actual),
                  allowedAxiomsOnly=allowed, valid=valid, failureKind=kind)
    return valid


def context_hashes(folder, tag, code):
    result = {}
    for kind in ('check', 'hb'):
        path = folder / f'{tag}.{kind}.lean'
        text = path.read_text()
        body = code.rstrip('\n')
        if text.count(body) != 1:
            raise ValueError('Generated source does not contain exactly the unchanged declaration')
        prefix, suffix = text.split(body)
        result[kind] = {'prefixSha256': common.sha(prefix.encode()), 'suffixSha256': common.sha(suffix.encode())}
    return result


def main(args):
    work, output = args.work.resolve(), args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=False)
    report = {'source': 'p12-separate', 'problemId': 12, 'version': args.version,
        'protocol': PROTOCOL, 'frozenPR3Compatible': False, 'countsInCommonScore': False,
        'repetitions': REPETITIONS, 'status': 'preparing', 'host': platform.platform(),
        'startedAt': datetime.now(timezone.utc).isoformat(), 'commit': os.environ.get('GITHUB_SHA'),
        'runId': os.environ.get('GITHUB_RUN_ID'), 'candidates': {}}
    common.write(output / 'summary.json', report)
    counter = 0

    def run(command, cwd=work, capture=False):
        nonlocal counter
        counter += 1
        print('+', ' '.join(map(str, command)), flush=True)
        logfile = output / f'prepare-{counter:02}.log'
        with logfile.open('w') as log:
            completed = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                text=True, env=dict(os.environ, LEAN_NUM_THREADS='1'))
        text = logfile.read_text()
        print(text[-4000:], flush=True)
        if completed.returncode:
            raise RuntimeError(f'Environment preparation failed ({completed.returncode}); see {logfile.name}')
        return text.strip() if capture else None

    try:
        _, meta, public, original, selected = load_inputs()
        trials = [('original', original), ('selected', selected)]
        if args.candidate_file:
            extras = common.load_experiment(args.candidate_file).get('12', [])
            if not extras:
                raise ValueError('Experiment input has no P12 candidates')
            trials.extend((c['id'], c['proof']) for c in extras)
            report['experimentInputSha256'] = common.sha(args.candidate_file.read_bytes())
        tokens = frozen_tokens(work)
        if gate(original, meta['statement'], tokens) != 1353 or gate(selected, meta['statement'], tokens) != 886:
            raise ValueError('Fixed P12 token counts changed')
        revision = next(pin[args.version] for pin in meta['version_info'] if args.version in pin)
        if not any(v['version'] == args.version and v['revision'] == revision for v in public['versions']):
            raise ValueError('Published and frozen P12 library pins disagree')
        report.update(revision=revision, proofSha256=PROOF_SHA, statementSha256=STATEMENT_SHA,
            tokenizer='lean-source-anchored-v1', tokenizerSourceSha256=TOKENIZER_SHA,
            verifierSha256=common.sha(Path(somi.__file__).read_bytes()),
            wrapperSha256=common.sha(Path(__file__).read_bytes()))
        project = work / 'project'
        run(['git', 'init', str(project)])
        run(['git', 'remote', 'add', 'origin', common.REPOSITORIES['arklib']], project)
        run(['git', 'fetch', '--depth=1', 'origin', revision], project)
        run(['git', 'checkout', '--detach', 'FETCH_HEAD'], project)
        if run(['git', 'rev-parse', 'HEAD'], project, True) != revision:
            raise ValueError('Source revision mismatch')
        toolchain = (project / 'lean-toolchain').read_text().strip()
        if toolchain != f'leanprover/lean4:{args.version}':
            raise ValueError('Toolchain pin mismatch')
        manifest = (project / 'lake-manifest.json').read_bytes()
        run(['elan', 'toolchain', 'install', toolchain], project)
        run(['lake', 'exe', 'cache', 'get'], project)
        if (project / 'lake-manifest.json').read_bytes() != manifest:
            raise ValueError('Preparation changed the pinned manifest')
        dependencies = []
        for package in json.loads(manifest)['packages']:
            if package['type'] != 'git':
                raise ValueError('Unexpected non-git dependency')
            path = project / '.lake/packages' / package['name'].strip('«»')
            head = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
            if head != package['rev'] or subprocess.check_output(['git', '-C', str(path), 'diff', 'HEAD', '--', '.']):
                raise ValueError(f'Dependency pin/source mismatch: {package["name"]}')
            dependencies.append({'name': package['name'], 'revision': head})
        report.update(dependencies=dependencies, manifestSha256=common.sha(manifest), toolchain=toolchain)
        common.write(output / 'summary.json', report)
        run(['lake', 'build', '+ArkLib.Data.CodingTheory.ProximityGap.DG25.Basic:olean'], project)
        if (project / 'lake-manifest.json').read_bytes() != manifest:
            raise ValueError('Build changed the pinned manifest')
        compiler_probe = run(['lake', 'env', 'lean', '--version'], project, True)
        compiler_lines = [line for line in compiler_probe.splitlines() if line.startswith('Lean (version ')]
        paths = run(['lake', 'env', 'which', 'lean'], project, True).splitlines()
        resolved_paths = [line for line in paths if Path(line).is_absolute()]
        if len(compiler_lines) != 1 or len(resolved_paths) != 1:
            raise ValueError('Cannot identify the actual compiler in the Lake environment')
        compiler, resolved = compiler_lines[0], resolved_paths[0]
        if not compiler.startswith(f'Lean (version {args.version.removeprefix("v")},'):
            raise ValueError('Actual compiler version differs from the pin')
        source = (project / meta['file_path']).read_text()
        if source.count(meta['src']) != 1:
            raise ValueError('Exact original source declaration was not found uniquely')
        start = source.index(meta['src'])
        first = source[:start].count('\n') + 1
        last = first + len(meta['src'].splitlines()) - 1
        report.update(sourceSha256=common.sha(source.encode()), compilerVersion=compiler, resolvedCompiler=resolved,
            replacedLines=[first, last], status='verifying')
        statement = output / 'statement.lean'
        statement.write_text(meta['statement'])
        expected_context = None
        for label, code in trials:
            candidate = output / f'{label}.lean'
            candidate.write_bytes(code.encode())
            folder = output / label
            folder.mkdir()
            item = {'sha256': common.sha(code.encode()), 'tokens': gate(code, meta['statement'], tokens),
                'valid': False, 'runs': []}
            report['candidates'][label] = item
            for index in range(1, REPETITIONS + 1):
                tag = f'repeat-{index}'
                command = [sys.executable, str(Path(somi.__file__)), '--repo', str(project),
                    '--file', meta['file_path'], '--start', str(first), '--end', str(last), '--name', meta['name'],
                    '--statement', str(statement), '--candidate', str(candidate), '--workdir', str(folder), '--tag', tag,
                    '--extra-import', 'Mathlib.Util.CountHeartbeats', '--lean-arg=-j1',
                    f'--lean-arg=-M{args.memory_mb}', '--timeout', '180']
                completed = subprocess.run(command, capture_output=True, text=True,
                    env=dict(os.environ, LEAN_NUM_THREADS='1'))
                (folder / f'{tag}.driver.log').write_text(completed.stdout + completed.stderr)
                result_path = folder / f'{tag}.result.json'
                if not result_path.is_file():
                    raise RuntimeError(f'Checker produced no fresh report: {label}/{tag}')
                measured = json.loads(result_path.read_text())
                valid = audit_run(measured, meta['name'], completed.returncode)
                context = context_hashes(folder, tag, code)
                if expected_context is None:
                    expected_context = context
                elif context != expected_context:
                    raise ValueError('Original/candidate whole-file context differs')
                measured['contextHashes'] = context
                for kind in ('check', 'hb'):
                    measured[f'{kind}SourceSha256'] = common.sha((folder / f'{tag}.{kind}.lean').read_bytes())
                    measured[f'{kind}LogSha256'] = common.sha((folder / f'{tag}.{kind}.log').read_bytes())
                item['runs'].append(measured)
                common.write(folder / 'result.json', item)
                if not valid:
                    break
            item['valid'] = len(item['runs']) == REPETITIONS and all(r['valid'] for r in item['runs'])
            if item['valid']:
                item['medianHeartbeats'] = statistics.median(r['heartbeat']['heartbeats'] for r in item['runs'])
            common.write(folder / 'result.json', item)
            common.write(output / 'summary.json', report)
            if not item['valid'] and label == 'original':
                break
        if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=project, text=True).strip() != revision
                or (project / 'lake-manifest.json').read_bytes() != manifest
                or subprocess.check_output(['git', 'diff', 'HEAD', '--', '.'], cwd=project)):
            raise ValueError('Pinned source/manifest changed during verification')
        for package in dependencies:
            path = project / '.lake/packages' / package['name'].strip('«»')
            if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip() != package['revision'] or subprocess.check_output(['git', 'diff', 'HEAD', '--', '.'], cwd=path):
                raise ValueError('Pinned dependency changed during verification')
        paired = set(report['candidates']) == {label for label, _ in trials} and all(x['valid'] for x in report['candidates'].values())
        report['controlsValid'] = all(report['candidates'].get(label, {}).get('valid', False) for label in ('original', 'selected'))
        report['contextAudit'] = {'wholeFileEqual': paired, 'hashes': expected_context,
            'allAllowedAxioms': paired and all(r['allowedAxiomsOnly'] for x in report['candidates'].values() for r in x['runs'])}
        report['valid'] = paired
        report['status'] = 'completed' if report['valid'] else 'verification_failed'
        return 0 if report['valid'] else 1
    except Exception as error:
        report.update(status='environment_or_protocol_failed', valid=False, error=str(error))
        (output / 'error.log').write_text(traceback.format_exc())
        return 1
    finally:
        report['finishedAt'] = datetime.now(timezone.utc).isoformat()
        common.write(output / 'summary.json', report)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                summary.write(f'### P12 separate v2 {args.version}\n\nCommon PR3 score: excluded. Status: {report["status"]}.\n\n')
                for label, item in report['candidates'].items():
                    summary.write(f'- {label}: valid={item["valid"]}, repeats={len(item["runs"])}/{REPETITIONS}\n')


def self_check():
    from io import BytesIO
    from unittest.mock import patch

    rows, meta, _, original, selected = load_inputs()
    with tempfile.TemporaryDirectory() as directory:
        copied = Path(directory) / BENCHMARK.name
        copied.with_name('snapshot.json').write_bytes(BENCHMARK.with_name('snapshot.json').read_bytes())
        verified = BENCHMARK.read_bytes()
        with patch.dict(globals(), BENCHMARK=copied), patch('urllib.request.urlopen', return_value=BytesIO(verified)) as download:
            assert benchmark_bytes() == verified and copied.read_bytes() == verified
            assert benchmark_bytes() == verified
            download.assert_called_once_with(BENCHMARK_URL, timeout=60)
            copied.write_bytes(b'corrupt existing snapshot')
            try:
                benchmark_bytes()
            except ValueError:
                assert copied.read_bytes() == b'corrupt existing snapshot'
            else:
                raise AssertionError('Corrupt benchmark accepted')
        tokens = frozen_tokens(Path(directory))
        assert all(somi.proof_tokens.proof_length(row['src'], row['statement']) == row['proof_length'] for row in rows)
        assert gate(original, meta['statement'], tokens) == 1353
        assert gate(selected, meta['statement'], tokens) == 886
        for bad in ('#eval 1', 'sorry', 'axiom forged : False'):
            try:
                gate(meta['statement'] + ' := by\n  ' + bad, meta['statement'], tokens)
            except ValueError:
                pass
            else:
                raise AssertionError('Forbidden input accepted')
    print('Static checks passed: clean-checkout restore, corrupt-cache rejection, frozen15 token controls, fixed proof/hash, finite-cardinality gate. No Lean compatibility result produced.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--version', choices=['v4.29.0', 'v4.30.0', 'v4.31.0'])
    parser.add_argument('--work', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--memory-mb', type=int, choices=[6144, 8192], default=6144)
    parser.add_argument('--candidate-file', type=Path)
    args = parser.parse_args()
    if args.self_check:
        self_check()
    else:
        if not all((args.version, args.work, args.output)):
            parser.error('--version, --work and --output are required')
        sys.exit(main(args))
