import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseFinalBaselines} from '../src/lib/final-baselines.ts';
import {parseFinalResults} from '../src/lib/final-results.ts';
import {resultSnapshot} from '../src/lib/final-snapshot.ts';
import {parseSnapshot, valueOf, aggregate} from '../src/lib/model.ts';
import {scoreTone} from '../src/lib/heatmap.ts';
const load = () => JSON.parse(readFileSync(new URL('../public/data/final-results.json', import.meta.url), 'utf8'));
const baseline = parseFinalBaselines(JSON.parse(readFileSync(new URL('../public/data/final-baselines.json', import.meta.url), 'utf8')));
test('20 verified proofs use paired measurements; other 40 stay gray and whole-set score stays pending', () => {
  const results = parseFinalResults(load(), baseline);
  const snapshot = parseSnapshot(resultSnapshot(baseline, results));
  assert.equal(snapshot.problems.filter(p => p.status === 'measured').length, 20);
  assert.equal(aggregate(snapshot.problems, 'combined').value, null);
  for (const p of snapshot.problems) {
    const result = results.problems.find(r => r.row === p.id);
    if (!result) { assert.equal(scoreTone(valueOf(p, 'combined')), 'tone-unknown'); continue; }
    assert.ok(Math.abs(valueOf(p, 'combined')! - result.score) < 1e-9);
    assert.equal(p.baseline?.heartbeats, result.baseline.raw_heartbeats);
    assert.equal(createHash('sha256').update(result.proof).digest('hex'), p.candidateHash);
    assert.equal(readFileSync(new URL(`../../${result.proofPath}`, import.meta.url), 'utf8'), result.proof);
    assert.ok(result.versions.every(v => v.status === 'pass'));
  }
  assert.deepEqual(results.problems.filter(p => p.runId !== results.runId).map(p => p.row), [2,6,7,8]);
});
test('reject missing versions, stale identity, duplicate rows, invented samples/score and overspend', () => {
  const mutations = [
    (d: any) => { d.problems[0].versions.pop(); },
    (d: any) => { d.problems[0].name = 'wrong'; },
    (d: any) => { d.problems[1] = d.problems[0]; },
    (d: any) => { d.problems[0].candidate.raw_samples = [1]; },
    (d: any) => { d.problems[0].score = 100; },
    (d: any) => { d.problems[0].currentRunCostUsd = '3.01'; },
    (d: any) => { d.costUsd = '0'; },
    (d: any) => { d.problems[0].versions[0].status = 'pending'; },
  ];
  for (const mutate of mutations) { const d = load(); mutate(d); assert.throws(() => parseFinalResults(d, baseline)); }
});
