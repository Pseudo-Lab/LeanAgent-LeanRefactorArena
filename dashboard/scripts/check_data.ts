import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { parseSnapshot } from '../src/lib/model.ts';
import { parseSummaryResults } from '../src/lib/final-summary-results.ts';
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
if (final.measurementPolicy !== 'all-pins-local-samples' || final.verification?.status !== 'passed') {
  throw new Error('Published Final data must contain complete all-version measurements.');
}
const baseline = JSON.parse(readFileSync(new URL('../../docs/measurements/final60-baselines.json', import.meta.url), 'utf8'));
const lock = JSON.parse(readFileSync(new URL('../../configs/final-environments.lock.json', import.meta.url), 'utf8'));
if (baseline.dataset_sha256 !== final.datasetSha256 || lock.dataset_sha256 !== final.datasetSha256 ||
    baseline.measured_problems !== 60 || baseline.environment_verification?.status !== 'passed') {
  throw new Error('Final publication requires 60 references and passed final environment-byte verification.');
}
for (const p of final.problems) {
  const expected = baseline.problems.find((r: { id: string }) => r.id === p.id);
  if (!expected || expected.status !== 'measured' || expected.name !== p.name || expected.source !== p.source ||
      expected.reference_sha256 !== p.referenceSha256 || expected.local_length !== p.local?.auditTokens ||
      expected.provided_length !== p.providedLength || p.local?.tokens !== p.providedLength ||
      expected.primary_environment !== `${p.source}-${p.primaryVersion}`) throw new Error(`${p.id}: reference identity differs`);
  const pins = lock.environments.filter((e: { source: string; problem_rows: number[] }) => e.source === p.source && e.problem_rows.includes(p.row));
  if (pins.length !== p.references?.length) throw new Error(`${p.id}: required version count differs`);
  for (const version of p.references ?? []) {
    const pin = pins.find((e: { id: string }) => e.id === version.environment);
    const measured = expected.environments[version.environment];
    if (!pin || pin.revision !== version.revision || pin.version !== version.version || !measured?.valid ||
        measured.median_raw_heartbeats !== version.rawHeartbeats || measured.median_heartbeats !== version.scaledHeartbeats ||
        JSON.stringify(measured.raw_samples) !== JSON.stringify(version.rawSamples)) throw new Error(`${p.id}: version or measured samples differ`);
  }
}
console.log('Verified Final identity, paper Length and all 127 pinned version samples against measurement docs');

const results = parseFinalResults(JSON.parse(readFileSync(new URL('final-results.json', root), 'utf8')), final);
const summary = parseSummaryResults(JSON.parse(readFileSync(new URL('physlib-cslib-results.json', root), 'utf8')), final);
for (const p of [...results.problems, ...summary]) {
  const saved = readFileSync(new URL(`../../${p.proofPath}`, import.meta.url), 'utf8');
  if ((p.evidenceLevel === 'published-summary' ? (saved !== p.proof && saved !== p.proof + '\n') || createHash('sha256').update(saved).digest('hex') !== p.proofFileHash : saved !== p.proof) || createHash('sha256').update(p.proof).digest('hex') !== p.candidateHash) throw new Error(`F${p.row}: proof hash mismatch`);
}
console.log(`Validated final-results.json: ${results.problems.length + summary.length} verified proofs, $${results.costUsd}`);
