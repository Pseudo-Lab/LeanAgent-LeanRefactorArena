import type { FinalBaselines } from './final-baselines.ts';
import type { FinalResult, FinalResults, FinalResultsView } from './final-results.ts';
const record = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v);
const hash = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const positive = (v: unknown) => Number.isSafeInteger(v) && Number(v) > 0;

// The source publishes aggregates and pass counts, not raw compiler observations.
export function parseSummaryResults(input: unknown, baselines: FinalBaselines): FinalResult[] {
  if (!record(input) || input.publicationSchemaVersion !== 1 || input.originPr !== 54
      || input.evidenceLevel !== 'published-summary' || input.dataset_sha256 !== baselines.datasetSha256
      || input.api_calls !== 0 || input.sourceManifest !== 'solutions/physlib-cslib20/manifest.json'
      || !hash(input.sourceManifestSha256) || !hash(input.submissionSha256)
      || !Array.isArray(input.results) || input.results.length !== 20) throw new Error('PhysLib·CSLib 검증 요약 형식 오류');
  const seen = new Set<number>();
  const rows = input.results.map((r: unknown): FinalResult => {
    if (!record(r) || !Number.isInteger(r.row) || r.row < 11 || r.row > 30 || seen.has(r.row)) throw new Error('검증 요약 문제 번호 오류');
    seen.add(r.row);
    const original = baselines.problems.find(p => p.row === r.row)!;
    const versions = Array.isArray(r.versions) ? r.versions.flatMap((v: unknown) => record(v) ? Object.entries(v) : []) : [];
    const expected = original.references ?? [];
    if (r.name !== original.name || r.source !== original.source || typeof r.route !== 'string'
        || !hash(r.proof_sha256) || !hash(r.proofFileSha256) || typeof r.proof !== 'string' || !r.proof.length || r.proof.length > 200000
        || r.proofPath !== `solutions/physlib-cslib20/F${String(r.row).padStart(3,'0')}.lean`
        || ![r.original_tokens,r.candidate_tokens,r.original_raw_heartbeats,r.candidate_raw_heartbeats].every(positive)
        || versions.length !== expected.length || new Set(versions.map(([v]: [string, unknown])=>v)).size !== expected.length
        || expected.some(v => !versions.some(([version, revision]: [string, unknown]) => version === v.version && revision === v.revision))
        || !record(r.checks) || Object.keys(r.checks).length !== expected.length
        || expected.some(v => !record(r.checks[v.environment]) || r.checks[v.environment].valid !== true || !positive(r.checks[v.environment].repeats))) {
      throw new Error(`F${r.row}: 검증 요약 근거 오류`);
    }
    const score = 100 - 100/3*(r.candidate_tokens/r.original_tokens+r.candidate_raw_heartbeats/r.original_raw_heartbeats);
    if (typeof r.score_local !== 'number' || Math.abs(score-r.score_local)>1e-9 || !Number.isFinite(r.score_local)) throw new Error('검증 요약 점수 오류');
    return {row:r.row,name:r.name,source:r.source,runId:'pr54-physlib-cslib20',proofPath:r.proofPath,proof:r.proof,
      candidateHash:r.proof_sha256,proofFileHash:r.proofFileSha256,evidenceLevel:'published-summary',
      baseline:{tokens:r.original_tokens,raw_heartbeats:r.original_raw_heartbeats,raw_samples:null},
      candidate:{tokens:r.candidate_tokens,raw_heartbeats:r.candidate_raw_heartbeats,raw_samples:null},
      versions:expected.map(v=>({version:v.version,revision:v.revision,environment:v.environment,status:'pass',fingerprint:null})),
      baselineCompatibility:100,measuredAt:null,score,currentRunCostUsd:'0',alternatives:[],
      evidence:[{path:input.sourceManifest,sha256:input.sourceManifestSha256}]};
  });
  if (typeof input.local_mean !== 'number' || !Number.isFinite(input.local_mean) || Math.abs(rows.reduce((sum: number,p: FinalResult)=>sum+p.score,0)/20-input.local_mean)>1e-9) throw new Error('검증 요약 평균 오류');
  return rows;
}

export function mergeFinalResults(primary: FinalResults, summary: FinalResult[]): FinalResultsView {
  const problems = [...primary.problems,...summary].sort((a,b)=>a.row-b.row);
  if (new Set(problems.map(p=>p.row)).size !== problems.length) throw new Error('검증 결과 문제 중복');
  return {runId:primary.runId,generatedAt:primary.generatedAt,costUsd:primary.costUsd,problems};
}
