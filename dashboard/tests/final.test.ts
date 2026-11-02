import test from 'node:test';
import assert from 'node:assert/strict';
import { aggregate, parseSnapshot, problemLabel } from '../src/lib/model.ts';
import type { Snapshot } from '../src/lib/model.ts';

function fixture(): Snapshot {
  return { schemaVersion: 1, id: 'synthetic-final', label: 'Synthetic Final', dataset: 'final',
    datasetSha256: 'd53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682',
    measuredAt: '2000-01-01T00:00:00Z', releaseDate: null, provenance: 'synthetic tests only',
    problems: Array.from({ length: 60 }, (_, i) => ({ id: i + 1, name: `test.${i}`, source: 'test',
      status: 'pending', baseline: { tokens: 10, heartbeats: 123 }, candidate: null,
      baselineCompatibility: 100, versions: [{ version: 'v4.34.1', revision: 'a'.repeat(40), status: 'pending' }],
      environment: 'test-v4.34.1', candidateHash: '', evidence: [], note: 'candidate pending',
      original: { benchmarkId: `F${String(i + 1).padStart(3, '0')}`, sha256: 'b'.repeat(64),
        providedTokens: 11, localTokens: 10, primaryEnvironment: 'test-v4.34.1',
        versions: [{ version: 'v4.34.1', revision: 'a'.repeat(40), status: 'pass', environment: 'test-v4.34.1',
          rawHeartbeats: 123456, heartbeats: 123, rawSamples: [123456] }] },
    })) };
}

test('Final accepts 60 slots and preserves separate original and candidate checks', () => {
  const data = parseSnapshot(fixture());
  assert.equal(data.problems.length, 60);
  assert.equal(problemLabel(data, 1), 'F001');
  assert.equal(problemLabel(data, 60), 'F060');
  assert.equal(data.problems[0].original?.versions[0].status, 'pass');
  assert.equal(data.problems[0].versions[0].status, 'pending');
  assert.equal(aggregate(data.problems, 'improvement').count, 0);
  assert.equal(aggregate(data.problems, 'combined').value, null);
  assert.deepEqual(parseSnapshot(JSON.parse(JSON.stringify(data))), data);
});

test('Final rejects 50 slots, repeated IDs, wrong dataset hash and warmup-like IDs', () => {
  const data = fixture();
  assert.throws(() => parseSnapshot({ ...data, problems: data.problems.slice(0, 50) }), /60/);
  data.problems[1].id = 1;
  assert.throws(() => parseSnapshot(data), /중복/);
  assert.throws(() => parseSnapshot({ ...fixture(), datasetSha256: '0'.repeat(64) }), /SHA256/);
  const wrongId = fixture(); wrongId.problems[0].original!.benchmarkId = 'P01';
  assert.throws(() => parseSnapshot(wrongId), /식별자/);
});

test('Final retains missing original HB as null rather than a measurement or score', () => {
  const data = fixture(), p = data.problems[0];
  p.baseline = null; p.baselineCompatibility = null;
  Object.assign(p.original!.versions[0], { status: 'pending', rawSamples: [], rawHeartbeats: null, heartbeats: null });
  const result = parseSnapshot(data);
  assert.equal(result.problems[0].original!.localTokens, 10);
  assert.equal(result.problems[0].baseline, null);
  assert.equal(aggregate(result.problems, 'combined').value, null);
});

test('Final rejects fabricated HB medians, wrong unit, mismatched pins and invented compatibility', () => {
  for (const key of ['rawHeartbeats', 'heartbeats'] as const) {
    const data = fixture(); data.problems[0].original!.versions[0][key] = 123457;
    assert.throws(() => parseSnapshot(data), /HB/);
  }
  const pin = fixture(); pin.problems[0].original!.versions[0].revision = 'c'.repeat(40);
  assert.throws(() => parseSnapshot(pin), /버전/);
  const compatibility = fixture(); compatibility.problems[0].baselineCompatibility = 50;
  assert.throws(() => parseSnapshot(compatibility), /호환성/);
});

test('Final import strips unknown metadata from every original version', () => {
  const data = fixture();
  Object.assign(data.problems[0].original!, { unknown: 'discard' });
  Object.assign(data.problems[0].original!.versions[0], { unknown: 'discard' });
  const result = parseSnapshot(data);
  assert.equal('unknown' in result.problems[0].original!, false);
  assert.equal('unknown' in result.problems[0].original!.versions[0], false);
});
