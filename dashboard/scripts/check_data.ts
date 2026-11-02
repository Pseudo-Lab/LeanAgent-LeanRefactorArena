import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { parseSnapshot } from '../src/lib/model.ts';
import { parseFinalResults } from '../src/lib/final-results.ts';
import { parseFinalBaselines } from '../src/lib/final-baselines.ts';

const root = new URL('../public/data/', import.meta.url);
const files: unknown = JSON.parse(readFileSync(new URL('index.json', root), 'utf8'));
if (!Array.isArray(files) || new Set(files).size !== files.length) {
  throw new Error('data/index.json must be a list of snapshot filenames without duplicates.');
}
for (const file of files) {
  if (typeof file !== 'string' || !/^[a-z0-9-]+\.json$/.test(file) || file === 'index.json') {
    throw new Error(`Invalid snapshot filename: ${String(file)}`);
  }
  const snapshot = parseSnapshot(JSON.parse(readFileSync(new URL(file, root), 'utf8')));
  if (`${snapshot.id}.json` !== file) {
    throw new Error(`Snapshot ID does not match filename: ${file}`);
  }
  for (const problem of snapshot.problems) {
    for (const candidate of problem.teamResults ?? []) {
      if (createHash('sha256').update(candidate.proof).digest('hex') !== candidate.candidateHash) {
        throw new Error(`P${problem.id} ${candidate.id}: published proof does not match its verified hash.`);
      }
    }
  }
  console.log(`Validated ${file}: ${snapshot.problems.length} problems`);
}
if (files.length === 0) console.log('No published results.');
const final = parseFinalBaselines(JSON.parse(readFileSync(new URL('final-baselines.json', root), 'utf8')));
console.log(`Validated final-baselines.json: ${final.problems.length} problems, ${final.problems.filter(p => p.local !== null).length} measured baselines`);

const results = parseFinalResults(JSON.parse(readFileSync(new URL('final-results.json', root), 'utf8')), final);
for (const p of results.problems) {
  const saved = readFileSync(new URL(`../../${p.proofPath}`, import.meta.url), 'utf8');
  if (saved !== p.proof || createHash('sha256').update(saved).digest('hex') !== p.candidateHash) throw new Error(`F${p.row}: proof hash mismatch`);
}
console.log(`Validated final-results.json: ${results.problems.length} verified proofs, $${results.costUsd}`);
