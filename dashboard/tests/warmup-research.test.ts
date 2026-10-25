import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const median = (values: number[]) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

test('promoted improvements match independent-process counters and exact proof hashes', () => {
  const snapshot = read('../public/data/warmup-team-results.json');
  const evidence = read('../public/research/warmup15/verification.json');
  const find = (id: number) => snapshot.problems.find((p: { id: number }) => p.id === id);
  for (const id of [1, 2, 5]) {
    const record = evidence[`P${String(id).padStart(2, '0')}`];
    assert.equal(find(id).candidateHash, record.after.proofSha256);
    for (const metric of [record.original, record.before, record.after]) {
      assert.equal(metric.repetitions, 3);
      assert.equal(metric.rawHeartbeats.length, 3);
      assert.equal(metric.heartbeats, median(metric.rawHeartbeats.map((v: number) => Math.floor(v / 1000))));
    }
    assert.equal(find(id).candidate.heartbeats, record.after.heartbeats);
  }
  const p8 = find(8);
  const record = evidence.CSLib.comparison.problems.find((p: { problemId: number }) => p.problemId === 8);
  assert.equal(record.candidateHash, p8.candidateHash);
  assert.equal(record.comparison.selected.repetitions, 3);
  assert.equal(p8.candidate.heartbeats, median(record.comparison.selected.rawHeartbeats.map((v: number) => Math.floor(v / 1000))));
  const p14 = find(14);
  const primary = evidence.P14.find((p: { version: string }) => p.version === 'v4.26.0');
  const c14 = primary.candidates[p14.selectedCandidateId];
  assert.equal(c14.sha256, p14.candidateHash);
  assert.equal(c14.measurements.length, 3);
  assert.equal(p14.candidate.heartbeats, median(c14.measurements.map((m: { raw: number }) => Math.floor(m.raw / 1000))));
  for (const id of [1, 2, 5, 8, 14]) {
    const problem = find(id);
    const chosen = problem.teamResults.find((c: { id: string }) => c.id === problem.selectedCandidateId);
    assert.equal(createHash('sha256').update(chosen.proof).digest('hex'), problem.candidateHash);
    assert.ok(problem.versions.every((v: { status: string }) => v.status === 'pass'));
  }
  for (const row of read('../public/research/warmup15/experiment.json').rows) {
    assert.equal(row.selectedHash, find(row.id).candidateHash, `P${row.id}: stale experiment description`);
  }
});
