import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { parseSnapshot } from '../src/lib/model.ts';

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
  if (snapshot.dataset === 'final') {
    const baseline = JSON.parse(readFileSync(new URL('../../docs/measurements/final60-baselines.json', import.meta.url), 'utf8'));
    const lock = JSON.parse(readFileSync(new URL('../../configs/final-environments.lock.json', import.meta.url), 'utf8'));
    if (baseline.dataset_sha256 !== snapshot.datasetSha256 || lock.dataset_sha256 !== snapshot.datasetSha256 ||
        baseline.measured_problems !== 60 || baseline.environment_verification?.status !== 'passed') {
      throw new Error('Final publication requires 60 fully measured references and passed environment-byte verification.');
    }
    for (const p of snapshot.problems) {
      const expected = baseline.problems.find((r: { id: string }) => r.id === p.original!.benchmarkId);
      if (!expected || expected.status !== 'measured' || expected.name !== p.name || expected.source !== p.source ||
          expected.reference_sha256 !== p.original!.sha256 || expected.local_length !== p.original!.localTokens ||
          expected.provided_length !== p.original!.providedTokens || expected.primary_environment !== p.original!.primaryEnvironment ||
          p.candidate !== null || p.status !== 'pending' || p.versions.some(v => v.status !== 'pending')) {
        throw new Error(`F${p.id}: reference identity differs or baseline checks are presented as candidate results.`);
      }
      const pins = lock.environments.filter((e: { source: string; problem_rows: number[] }) => e.source === p.source && e.problem_rows.includes(p.id));
      if (pins.length !== p.original!.versions.length) throw new Error(`F${p.id}: required version count differs.`);
      for (const version of p.original!.versions) {
        const pin = pins.find((e: { id: string }) => e.id === version.environment);
        const measured = expected.environments[version.environment];
        if (!pin || pin.revision !== version.revision || pin.version !== version.version || !measured?.valid ||
            measured.median_raw_heartbeats !== version.rawHeartbeats || measured.median_heartbeats !== version.heartbeats ||
            JSON.stringify(measured.raw_samples) !== JSON.stringify(version.rawSamples)) {
          throw new Error(`F${p.id}: pinned version or HB evidence differs.`);
        }
      }
    }
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
