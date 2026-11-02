"""Refresh the human-readable snapshot without changing any frozen evaluator."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent.parent / 'runs/portfolio-94'
NAMES = ['p05-432', 'p06-432', 'p07-agent3-431', 'p07-432', 'p07-433',
         'p08-agent3-433', 'p10-exclusive4-431', 'p11-exclusive4-431']


def refresh():
    rows = []
    for name in NAMES:
        root = RUNS / name
        state = json.loads((root / 'state.json').read_text())
        baseline, best = state['baseline'], state['best']
        confirmations = []
        for path in (root / 'evaluations').glob('*/result.json'):
            result = json.loads(path.read_text())
            if result.get('valid') and result.get('code_sha256') == best['code_sha256']:
                confirmations.append(result)
        chosen = max(confirmations, key=lambda r: len(r['raw_samples']))
        score = 100 - 100 / 3 * (chosen['tokens'] / baseline['tokens'] +
                                 chosen['raw'] / baseline['raw'])
        rows.append(dict(run=name, baseline_tokens=baseline['tokens'],
                         baseline_raw=baseline['raw'], tokens=chosen['tokens'],
                         raw=chosen['raw'], local_all_compat_assumed_score=score,
                         samples=len(chosen['raw_samples']), label=chosen['label'],
                         candidate_sha256=chosen['code_sha256'],
                         candidate_path=str(Path(chosen['folder']) / 'candidate.lean')))
    now = datetime.now(timezone.utc).isoformat()
    snapshot = dict(updated_utc=now, scope='Single-pin local comparisons, not official LB; '
                    'check compatibility against validated manifests', rows=rows)
    (HERE / 'primary-snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    path = HERE / 'PROGRESS.ko.md'
    content = path.read_text()
    start, end = content.index('| 실행 |'), content.index('\n## 재사용할 접근')
    table = ['| 실행 | Tokens | raw HB | 단독 비교 점수 | best 측정 횟수 |',
             '|---|---:|---:|---:|---:|']
    for row in rows:
        table.append(f'| {row["run"]} | {row["tokens"]} | {row["raw"]:,} | '
                     f'{row["local_all_compat_assumed_score"]:.4f} | {row["samples"]} |')
    content = content[:start] + '\n'.join(table) + '\n' + content[end:]
    content = re.sub(r'갱신 UTC: .*', '갱신 UTC: ' + now, content)
    path.write_text(content)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    refresh()
