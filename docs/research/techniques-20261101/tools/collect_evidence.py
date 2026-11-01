"""Collect compact existing evidence, without new model or Lean executions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--ref', default='origin/main')
    args = ap.parse_args()
    src, out = args.source_root.resolve(), args.output.resolve()
    (out / 'proofs').mkdir(parents=True, exist_ok=True)
    records, proofs, facts = {}, [], {}
    def read(name):
        data = (src / name).read_bytes()
        records[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        return json.loads(data) if name.endswith('.json') else data.decode()
    def copy_proof(name, label, case, metrics, scope):
        code = read(name)
        data = code.encode()
        target = out / 'proofs' / label
        if target.exists():
            assert target.read_bytes() == data
        else:
            target.write_bytes(data)
        current = subprocess.check_output(['git', '-C', str(src), 'show',
                                          args.ref + ':submissions/warmup/best/' + case + '.lean'])
        row = {'file': 'proofs/' + label, 'problem': case, 'source': name,
               'sha256': hashlib.sha256(data).hexdigest(), 'metrics': metrics, 'scope': scope,
               'identical_bytes_to_main_submission': data == current}
        proofs.append(row)
        return row
    base = 'runs/oai-techniques-p06-p11-20261101/'
    for case, session, file in [('P06', 'P06/session', 'P06/report.json'),
                                ('P11', 'P11/v4.31.0/session', 'P11/report-v4.31.0.json')]:
        r = read(base + file)
        winner = r['selection']['winner']['candidate_id']
        rows = {row['id']: row for row in r['rows']}
        facts['manual_' + case] = {k: r[k] for k in ('version', 'revision', 'repetitions')}
        facts['manual_' + case].update(baseline=rows['baseline'], candidate=rows[winner], selected_candidate_id=winner)
        if case == 'P06':
            facts['manual_P06']['previous_team_control'] = rows['candidate-0001']
        copy_proof(base + session + '/' + r['selection']['source'], case.lower() + '-manual.lean',
                   case, rows[winner], 'Full original module, allowed axioms and three fresh primary measurements.')
    for version in ('v4.29.0', 'v4.30.0'):
        r = read(base + 'P11/' + version + '/compatibility/report.json')
        assert r['all_valid'] and r['environment_unchanged']
        facts['manual_P11_' + version] = {k: r[k] for k in ('all_valid', 'environment_unchanged')}
        facts['manual_P11_' + version]['rows'] = [{k: x[k] for k in
            ('label', 'valid', 'axioms', 'tokens', 'proof_sha256')} for x in r['rows']]
    metric_keys = ('valid', 'tokens', 'raw_hb', 'raw_samples', 'verified_versions')
    completion = read('results/competitive-structure-20261101/comparison.json')
    assert completion['all_complete'] and completion['candidate_evaluations'] == 160
    assert completion['valid'] == 120 and completion['invalid'] == 40
    assert completion['independent_finals'] == 4
    assert len(completion['audits']) == 4 and all(row['audit_passed'] for row in completion['audits'])
    facts['structural_completion'] = completion
    review = read('results/competitive-structure-20261101/review.md')
    assert review.startswith('# Independent review — complete')
    (out / 'structural-review.md').write_text(review)
    groups = [('portfolio40', 'competitive-search40-20261031/portfolio', ('P01', 'P02', 'P03')),
              ('fresh40', 'competitive-search40-extra-20261101/portfolio', ('P06', 'P13', 'P14', 'P15')),
              ('structural', 'competitive-structure-20261101', ('P06', 'P13', 'P14', 'P15'))]
    for label, folder, cases in groups:
        for case in cases:
            prefix = 'runs/' + folder + '/' + case + '/'
            state = read(prefix + 'state.json')
            final = state['final']
            v = final['verification']
            assert v['valid']
            scope = ('Exact supplied local primary context only; no extra-version claim. '
                     'Putnam examples have narrowed imports, not their full benchmark header. '
                     + ('Incumbent-seeded continuation; all four offline case audits and final comparison review passed.'
                        if label == 'structural' else 'Original-start independent portfolio.'))
            row = copy_proof(prefix + 'final.lean', case.lower() + '-' + label + '.lean', case,
                             {k: v.get(k) for k in metric_keys}, scope)
            assert row['sha256'] == final['sha256']
            facts[label + '_' + case] = {'attempts': len(state['attempts']),
                'inflight': bool(state['inflight']), 'winner': final['candidate'],
                'final': row['metrics'], 'normalizers': state['normalizers']}
            if label == 'structural' and case in ('P13', 'P15'):
                chosen = (28, 36) if case == 'P13' else (3, 32, 34, 39)
                events = []
                for number in chosen:
                    attempt = state['attempts'][number - 1]
                    path = prefix + f'attempt-{number:02}.lean'
                    code = read(path)
                    assert hashlib.sha256(code.encode()).hexdigest() == attempt['sha256']
                    events.append({'attempt': number, 'metadata': attempt['metadata'],
                        'source': path, 'sha256': attempt['sha256'],
                        'metrics': {k: attempt['result'].get(k) for k in metric_keys}})
                facts.setdefault('structural_learning_events', {})[case] = events
    copy_proof('runs/retrieval-v11-p11-20261101/P11/golf-best.lean', 'p11-retrieval.lean', 'P11',
        {'valid': True, 'tokens': 368, 'raw_hb': 9067259, 'raw_samples': [9067259, 9067201, 9067288],
         'verified_versions': ['v4.31.0']},
        'Full primary context only. One-level fiber lemma was used before retrieve; discovery is not attributed to retrieval.')
    sources = {
        'posthoc_ablation': 'runs/structured-v6-analysis-20261031/ablation-results.designer-only.json',
        'posthoc_rule_order': 'runs/structured-v6-analysis-20261031/order-control-results.designer-only.json',
        'v5_common_40': 'runs/common-v5-local-agent-r2-isolated-20261030/results-at-40.designer-only.json',
        'v5_paid_study_status': 'runs/common-v5-study-20261030/study-manifest.json',
        'v10_comparison': 'runs/incremental-v10-threecase-20261031/comparison.json',
        'v10_parallel_checks': 'runs/incremental-v10-fresh-parallel-validation-20261031/summary.json',
        'retrieval_diagnostics': 'runs/theorem-retrieval-20261101/report.json',
        'retrieval_v11_comparison': 'runs/retrieval-v11-p11-20261101/comparison.json',
        'competitive_12': 'runs/competitive-search-20261031/results.json',
        'competitive_40': 'runs/competitive-search40-20261031/results.json',
        'competitive_extra': 'runs/competitive-search40-extra-20261101/results.json',
    }
    for key, name in sources.items():
        data = read(name)
        if key == 'v5_common_40':
            data = {k: data[k] for k in ('status', 'candidate_evaluations', 'valid_attempts',
                'invalid_attempts', 'macro_objective_at_6', 'macro_objective_at_40', 'limits')}
        if key == 'v5_paid_study_status':
            data = {k: data[k] for k in ('status', 'api_cost_usd', 'paired_controls_verified')}
        facts[key] = data
    for name in ('runs/structured-v6-analysis-20261031/analysis.md',
                 'runs/structured-openai-20261031/report.md',
                 'runs/fast-p10-timing-20261031/comparison.md',
                 'runs/research-v9-threecase-20261031/comparison.md',
                 'runs/postprocess-88-20261028-204910/review.md',
                 'results/competitive-structure-20261101/review.md',
                 'results/competitive-structure-20261101/analysis.md',
                 'results/competitive-structure-20261101/comparison.md',
                 'results/competitive-structure-20261101/report.json',
                 'experiments/competitive-structure-20261101/controller.py',
                 'experiments/competitive-structure-20261101/instructions.txt',
                 'runs/competitive-structure-20261101/P13/solver-report.md',
                 'runs/competitive-structure-20261101/P15/solver-report.md',
                 'experiments/retrieval-harness-20261101/README.md'):
        read(name)
    sys.path.insert(0, str(src / 'src'))
    from lean_agent.evaluator.tokens import proof_tokens
    packets = read('submissions/warmup/verification-inputs.json')['problems']
    packets['6'] = read(base + 'P06/inputs/metadata.json')
    for number in range(1, 6):
        path = f'experiments/problem-inputs/P{number:02}/agent-input.json'
        packet = json.loads(subprocess.check_output(['git', '-C', str(src), 'show', args.ref + ':' + path]))
        packets[str(number)] = packet['problem']
    facts['main_submissions'] = {}
    for key, meta in packets.items():
        case = f'P{int(key):02}'
        name = 'submissions/warmup/best/' + case + '.lean'
        code = subprocess.check_output(['git', '-C', str(src), 'show', args.ref + ':' + name], text=True)
        index = code.find(meta['statement'])
        facts['main_submissions'][case] = {'path': name, 'sha256': hashlib.sha256(code.encode()).hexdigest(),
            'tokens': proof_tokens(code[index:], meta['statement']) if index >= 0 else None}
    def portable(value):
        if isinstance(value, str):
            return value.replace(str(src) + '/', '').replace('/Users/jwkweon/00_work/00_project/', '<CENTRAL>/')
        if isinstance(value, list):
            return [portable(v) for v in value]
        if isinstance(value, dict):
            return {portable(k): portable(v) for k, v in value.items()}
        return value
    for name, data in [('facts.json', facts), ('proofs.json', proofs), ('source-records.json', records)]:
        with (out / name).open('x') as handle:
            json.dump(portable(data), handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    print(json.dumps({'sources': len(records), 'proofs': len(proofs), 'fact_groups': len(facts)}))


if __name__ == '__main__':
    main()
