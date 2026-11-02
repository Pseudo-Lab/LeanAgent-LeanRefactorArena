"""Join fresh primary confirmation with two independently evaluated pin seeds."""
import argparse
import json
from pathlib import Path
from search import read, write, digest
from audit import audit


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path); p.add_argument('--confirmation', type=Path, required=True)
    p.add_argument('--pins', type=Path, nargs='+', required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); root = a.root.resolve(); c = read(a.confirmation)
    assert c['all_valid']
    selected = c['results'][c['confirmed_choice']]
    code = (Path(selected['folder']) / 'candidate.lean').read_text()
    assert digest(code) == selected['code_sha256']
    rows, audits = [], {}
    def metrics(label, baseline, candidate):
        return {'pin': label, 'tokens': candidate['tokens'], 'raw_samples': candidate['raw_samples'],
                'raw_median': candidate['raw'], 'baseline_raw_samples': baseline['raw_samples'],
                'baseline_raw_median': baseline['raw'], 'code_sha256': candidate['code_sha256'],
                'HB_reduction_pct': 100*(1-candidate['raw']/baseline['raw']),
                'length_reduction_pct': 100*(1-candidate['tokens']/baseline['tokens']),
                'local_score': 100-100/3*(candidate['tokens']/baseline['tokens']+candidate['raw']/baseline['raw']),
                'evidence': candidate['folder']}
    rows.append(metrics('4.31.0',c['results']['original'],selected))
    audits['4.31.0'] = audit(root)
    for pinroot in a.pins:
        state = read(pinroot / 'state.json')
        candidate = next(r for r in state['attempts'] if r['label'] == 'seed')
        assert candidate['valid'] and len(candidate['raw_samples']) == 3
        assert candidate['code_sha256'] == digest(code), 'Cross-pin source differs'
        config = read(pinroot / 'config.json'); env = read(Path(config['environment']))
        pin = env.get('lean_pin', env.get('lean_version', str(pinroot)))
        rows.append(metrics(pin,state['baseline'],candidate)); audits[pin] = audit(pinroot.resolve())
    assert len(rows) == 3
    assert {r['pin'].removeprefix('v') for r in rows} == {'4.31.0','4.30.0','4.29.0'}
    assert all(v['passed'] for v in audits.values())
    seed = c['results']['seed']; base = c['results']['original']
    oldscore = 100-100/3*(seed['tokens']/base['tokens']+seed['raw']/base['raw'])
    state = read(root / 'state.json')
    result = {'status': 'VERIFIED_ALL_3_REQUIRED_PINS', 'official_submission': False,
              'scope': 'P12 development optimization seeded by earlier all-pin best, not a blind policy A/B or held-out evaluation',
              'code_sha256': digest(code), 'pins': rows, 'audits': audits,
              'primary_previous_best': {'tokens': seed['tokens'], 'raw_samples': seed['raw_samples'], 'local_score': oldscore},
              'extra_length_reduction_vs_seed_pct': 100*(1-selected['tokens']/seed['tokens']),
              'extra_HB_reduction_vs_seed_pct': 100*(1-selected['raw']/seed['raw']),
              'primary_problem_score_gain': rows[0]['local_score']-oldscore,
              'conditional_15_problem_mean_gain': (rows[0]['local_score']-oldscore)/15,
              'primary_search_attempts_excluding_original_and_seed': len(state['attempts'])-2,
              'primary_valid_search_attempts': sum(r['valid'] for r in state['attempts'][2:]),
              'confirmation_path': str(a.confirmation.resolve()),
              'no_search_time_penalty': True, 'all_search_space_exhausted': False}
    if a.output.exists():
        raise ValueError('Use a fresh output path')
    write(a.output,result)
    a.output.with_suffix('.lean').write_text(code)
    print(json.dumps({k:v for k,v in result.items() if k!='audits'},ensure_ascii=False,indent=2))
