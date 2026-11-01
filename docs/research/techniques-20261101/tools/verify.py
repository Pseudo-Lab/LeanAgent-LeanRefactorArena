"""Verify this documentation capsule offline; no Lean, model or network calls."""
import ast
from collections import Counter
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess

BUNDLE = Path(__file__).resolve().parents[1]
ROOT = BUNDLE.parents[2]


def load(name):
    return json.loads((BUNDLE / 'evidence' / name).read_text())


def main():
    audit = load('git-audit.json')
    revision = audit['main_sha']
    assert revision == '7f9508a85d44c5369f9461222f9904d6a9c01486'
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args])
    entries = git('ls-tree', '-rz', revision).split(b'\0')
    tree = {}
    for entry in entries:
        if entry:
            info, path = entry.split(b'\t', 1)
            if info.split()[1] == b'blob':
                tree[path.decode()] = info.split()[2].decode()
    assert dict(Counter(row['main_status'] for row in audit['files'])) == audit['counts']
    for row in audit['files']:
        assert tree.get(row['path']) == row['main_blob']
        expected = ('identical_to_main' if row['git_blob'] == row['main_blob'] else
                    'different_from_main' if row['main_blob'] else 'absent_from_main')
        assert row['main_status'] == expected
    prepared = next(x for x in audit['files'] if x['path'] == 'src/lean_agent/prepared.py')
    assert prepared['main_status'] == 'identical_to_main'
    assert audit['specific_main_checks']['harness_exposes_stat_cache']
    assert not audit['specific_main_checks']['common_wrapper_uses_qualified_Lean_Name']
    examples = load('proofs.json')
    for row in examples:
        source = BUNDLE / 'evidence' / row['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256']
        metrics = row['metrics']
        assert metrics['valid'] and len(metrics['raw_samples']) == 3
        median = int(statistics.median(metrics['raw_samples']))
        if 'raw_hb' in metrics:
            assert metrics['raw_hb'] == median
        if 'scaled_heartbeats' in metrics:
            assert metrics['scaled_heartbeats'] == median // 1000
        original = git('show', revision + ':submissions/warmup/best/' + row['problem'] + '.lean')
        assert row['identical_bytes_to_main_submission'] == (original == source.read_bytes())
    facts = load('facts.json')
    assert facts['main_submissions']['P06']['tokens'] == 450
    assert facts['main_submissions']['P11']['tokens'] == 1656
    for version in ('v4.29.0', 'v4.30.0'):
        report = facts['manual_P11_' + version]
        assert report['all_valid'] and report['environment_unchanged']
        assert report['rows'][1]['proof_sha256'] == facts['manual_P11']['candidate']['sha256']
    assert facts['v5_paid_study_status']['status'] == 'deferred_after_user_scope_correction'
    assert Decimal(str(facts['v5_paid_study_status']['api_cost_usd'])) == 0
    assert facts['v5_common_40']['candidate_evaluations'] == 120
    structural = facts['structural_completion']
    assert structural['all_complete'] and structural['candidate_evaluations'] == 160
    assert structural['valid'] == 120 and structural['invalid'] == 40
    assert structural['fresh_baselines'] == structural['independent_finals'] == 4
    assert len(structural['audits']) == 4 and all(row['audit_passed'] for row in structural['audits'])
    assert sum(row['candidate_evaluations'] for row in structural['cases']) == 160
    assert sum(row['valid'] for row in structural['cases']) == 120
    gains = {'incumbents': Fraction(0), '88': Fraction(0)}
    for row in structural['cases']:
        norm = row['normalizers']
        def cost(result):
            return Fraction(result['tokens'], norm['tokens']) + Fraction(result['raw_hb'] // 1000, norm['hb_scaled'])
        final = row['final']
        assert final['raw_hb'] == statistics.median(final['raw_samples'])
        assert cost(final) == Fraction(final['official_cost']['fraction'])
        for label, key in [('incumbents', 'incumbent'), ('88', 'reference_88')]:
            gain = Fraction(100, 3) * (cost(row[key]) - cost(final))
            gains[label] += gain / 15
        example = next(p for p in examples if p['file'] == 'proofs/' + row['problem'].lower() + '-structural.lean')
        assert example['sha256'] == row['final_sha256']
    assert gains['incumbents'] == Fraction(structural['delta_15_task_mean_vs_incumbents']['fraction'])
    assert gains['88'] == Fraction(structural['delta_15_task_mean_vs_88']['fraction'])
    events = facts['structural_learning_events']
    p13 = {row['attempt']: row['metrics'] for row in events['P13']}
    assert p13[36]['tokens'] - p13[28]['tokens'] == 2
    assert p13[28]['raw_hb'] - p13[36]['raw_hb'] == 277280
    p15 = {row['attempt']: row['metrics'] for row in events['P15']}
    case15 = next(row for row in structural['cases'] if row['problem'] == 'P15')
    norm15 = case15['normalizers']
    def cost15(result):
        return Fraction(result['tokens'], norm15['tokens']) + Fraction(result['raw_hb'] // 1000, norm15['hb_scaled'])
    assert cost15(p15[3]) > cost15(case15['incumbent'])
    assert p15[34]['tokens'] - p15[39]['tokens'] == 5
    assert p15[39]['raw_hb'] - p15[34]['raw_hb'] == 7048
    assert cost15(p15[39]) < cost15(p15[34])
    links = 0
    for path in BUNDLE.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            if target.startswith(('https://', 'http://', '#')):
                continue
            target = target.split('#', 1)[0]
            assert (path.parent / target).resolve().exists(), (path, target)
            links += 1
    for path in (BUNDLE / 'tools').glob('*.py'):
        ast.parse(path.read_text())
    print(json.dumps({'main_sha': revision, 'audited_files': len(audit['files']),
                      'proof_hashes_and_medians_verified': len(examples),
                      'local_links_verified': links, 'source_records': len(load('source-records.json')),
                      'structural_candidates': 160, 'structural_valid': 120, 'independent_structural_finals': 4,
                      'lean_called': False, 'model_called': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
