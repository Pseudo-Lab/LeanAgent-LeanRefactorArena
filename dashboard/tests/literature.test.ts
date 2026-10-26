import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('literature map preserves all observed repository references and their application boundaries', () => {
  const data = JSON.parse(readFileSync(new URL('../public/research/literature.json', import.meta.url), 'utf8'));
  assert.equal(data.papers.length, 63);
  assert.equal(new Set(data.papers.map((p: { id: string }) => p.id)).size, 63);
  assert.equal(data.papers.filter((p: { id: string }) => /^\d{4}\.\d{4,5}$/.test(p.id)).length, 61);
  for (const paper of data.papers) {
    assert.ok(paper.repositorySources.length);
    assert.ok(data.families[paper.family]);
    assert.ok(paper.mechanism && paper.disposition && paper.basis);
    const url = new URL(paper.url);
    assert.equal(url.protocol, 'https:');
    assert.ok(['www.alphaxiv.org', 'aclanthology.org'].includes(url.hostname));
  }
  assert.equal(data.additionalPapers.length, 4);
  assert.ok(data.adaptationNotes.some((note: string) => note.includes('META/CREATE/REPAIR')));
});
