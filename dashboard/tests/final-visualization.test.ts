import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { baselineSnapshot } from '../src/lib/final-snapshot.ts';
import { parseFinalBaselines } from '../src/lib/final-baselines.ts';
import { parseSnapshot, valueOf } from '../src/lib/model.ts';
import { scoreColors, scoreTone } from '../src/lib/heatmap.ts';

test('all 60 originals remain baselines, with no fabricated improvement or compatibility', () => {
  const data = parseFinalBaselines(JSON.parse(readFileSync(new URL('../public/data/final-baselines.json', import.meta.url), 'utf8')));
  const snapshot = parseSnapshot(baselineSnapshot(data));
  assert.equal(snapshot.problems.length, 60);
  for (const p of snapshot.problems) {
    const original = data.problems[p.id - 1];
    assert.equal(p.baseline?.tokens, original.local?.tokens);
    assert.equal(p.baseline?.heartbeats, original.local?.rawHeartbeats);
    assert.equal(p.candidate, null);
    for (const metric of ['improvement', 'tokens', 'heartbeats', 'compatibility', 'combined'] as const) {
      assert.equal(valueOf(p, metric), null);
      assert.equal(scoreTone(valueOf(p, metric)), 'tone-unknown');
    }
  }
  assert.throws(() => parseSnapshot({ ...snapshot, problems: snapshot.problems.slice(0, 50) }), /60/);
});

test('shared colors keep missing scores gray, 60 and below red, above 60 progressively green', () => {
  assert.equal(scoreTone(null), 'tone-unknown');
  for (const score of [-10, 0, 59.9, 60]) assert.equal(scoreTone(score), 'tone-warning');
  assert.equal(scoreColors(null), undefined);
  assert.equal(scoreColors(60), undefined);
  assert.equal(scoreTone(60.1), '');
  assert.notDeepEqual(scoreColors(60.1), scoreColors(100));
  assert.deepEqual(scoreColors(100), scoreColors(120));
});
