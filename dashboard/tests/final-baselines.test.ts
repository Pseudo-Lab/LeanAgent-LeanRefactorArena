import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseFinalBaselines } from '../src/lib/final-baselines.ts';

const fixture = () => JSON.parse(readFileSync(new URL('../public/data/final-baselines.json', import.meta.url), 'utf8'));
test('final baseline snapshot preserves missing HB independently of provided length', () => {
  const data = parseFinalBaselines(fixture());
  assert.equal(data.problems.length, 60);
  assert.ok(data.problems.filter(p => p.local).length >= 37);
  assert.equal(data.problems[0].local?.rawHeartbeats, 4182543);
  assert.equal(data.problems[0].local?.scaledHeartbeats, 4182);
  assert.ok(data.problems[17].providedLength > 0);
  const pending = fixture();
  pending.problems[17].local = null;
  assert.equal(parseFinalBaselines(pending).problems[17].local, null);
  // Interrupted candidate searches still have valid, independent baseline evidence.
  assert.ok(data.problems[45].local);
  assert.ok(data.problems[47].local);
});
test('reject wrong dataset, duplicate IDs, missing rows and fabricated HB medians', () => {
  for (const mutate of [
    (d: ReturnType<typeof fixture>) => { d.datasetSha256 = '0'.repeat(64); },
    (d: ReturnType<typeof fixture>) => { d.problems[1] = d.problems[0]; },
    (d: ReturnType<typeof fixture>) => { d.problems.pop(); },
    (d: ReturnType<typeof fixture>) => { d.problems[0].local.rawHeartbeats = 0; },
    (d: ReturnType<typeof fixture>) => { d.problems[0].local.rawSamples.pop(); },
    (d: ReturnType<typeof fixture>) => { d.problems[0].local.scaledHeartbeats = 4182543; },
    (d: ReturnType<typeof fixture>) => { d.problems[0].local.evidence[0].path = '/Users/private'; },
  ]) { const input = fixture(); mutate(input); assert.throws(() => parseFinalBaselines(input)); }
});
test('one-sample data stays explicitly provisional and cannot claim a three-sample median', () => {
  const input = fixture();
  const local = input.problems[0].local;
  local.sampleCount = 1;
  local.rawSamples = [local.rawHeartbeats];
  local.evidence = local.evidence.slice(0, 6);
  assert.equal(parseFinalBaselines(input).problems[0].local?.sampleCount, 1);
  local.sampleCount = 3;
  assert.throws(() => parseFinalBaselines(input));
});
