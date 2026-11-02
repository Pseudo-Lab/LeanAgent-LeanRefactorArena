import type { FinalBaselines } from './final-baselines.ts';
import type { VersionCheck } from './model.ts';
export type FinalMeasurement = { tokens: number; raw_heartbeats: number; raw_samples: number[] };
export type FinalResult = {
  row: number; name: string; source: string; runId: string; proofPath: string; proof: string;
  candidateHash: string; baseline: FinalMeasurement; candidate: FinalMeasurement;
  versions: (VersionCheck & { environment: string; fingerprint: string })[];
  baselineCompatibility: number | null; measuredAt: string; score: number; currentRunCostUsd: string;
  alternatives: {runId: string; score: number; candidateHash: string}[];
  evidence: {path: string; sha256: string}[];
};
export type FinalResults = {
  schemaVersion: 1; datasetSha256: string; runId: string; generatedAt: string;
  officialEvaluation: false; costUsd: string; invoiceVerified: false; auditPassed: true;
  apiCalls: number; problems: FinalResult[];
};
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const hash = (v: unknown): v is string => text(v) && /^[a-f0-9]{64}$/.test(v);
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const date = (v: unknown) => text(v) && Number.isFinite(Date.parse(v));
function measurement(v: unknown): v is FinalMeasurement {
  return record(v) && integer(v.tokens) && v.tokens > 0 && integer(v.raw_heartbeats) && v.raw_heartbeats > 0
    && Array.isArray(v.raw_samples) && v.raw_samples.length === 3 && v.raw_samples.every(integer)
    && [...v.raw_samples].sort((a,b) => a-b)[1] === v.raw_heartbeats;
}
export function parseFinalResults(input: unknown, baselines: FinalBaselines): FinalResults {
  if (!record(input) || input.schemaVersion !== 1 || input.datasetSha256 !== baselines.datasetSha256
      || input.officialEvaluation !== false || input.invoiceVerified !== false || input.auditPassed !== true
      || !text(input.runId) || !date(input.generatedAt) || !integer(input.apiCalls)
      || !text(input.costUsd) || !Number.isFinite(Number(input.costUsd)) || Number(input.costUsd) < 0 || Number(input.costUsd) > 60
      || !Array.isArray(input.problems) || input.problems.length !== 20) throw new Error('최종 20문제 결과 형식 오류');
  const ids = new Set<number>();
  let cost = 0;
  for (const p of input.problems) {
    if (!record(p) || !integer(p.row) || !(p.row >= 1 && p.row <= 10 || p.row >= 41 && p.row <= 50) || ids.has(p.row)) throw new Error('최종 결과 문제 번호 오류');
    ids.add(p.row);
    const original = baselines.problems.find(b => b.row === p.row)!;
    if (p.name !== original.name || p.source !== original.source || !text(p.runId) || !date(p.measuredAt)
        || !hash(p.candidateHash) || !text(p.proof) || p.proof.length > 200000
        || p.proofPath !== `solutions/final20/F${String(p.row).padStart(3, '0')}.lean`
        || !measurement(p.baseline) || !measurement(p.candidate)
        || !Array.isArray(p.versions) || p.versions.length !== original.requiredVersions.length
        || p.versions.some((v, i) => !record(v) || v.version !== original.requiredVersions[i] || v.status !== 'pass'
          || !text(v.revision) || !/^[a-f0-9]{40}$/.test(v.revision) || !hash(v.fingerprint) || !text(v.environment))
        || p.versions[0].revision !== original.primaryRevision
        || !(p.baselineCompatibility === null || p.baselineCompatibility === 100)
        || !Array.isArray(p.evidence) || !p.evidence.length || p.evidence.some(e => !record(e) || !text(e.path)
          || !e.path.startsWith(`problems/F${String(p.row).padStart(3, '0')}/`) || e.path.split('/').includes('..') || !hash(e.sha256))
        || !text(p.currentRunCostUsd) || !Number.isFinite(Number(p.currentRunCostUsd)) || Number(p.currentRunCostUsd) < 0 || Number(p.currentRunCostUsd) > 3) throw new Error(`F${p.row}: 검증 근거 오류`);
    const score = 100 - 100 / 3 * (p.candidate.tokens / p.baseline.tokens + p.candidate.raw_heartbeats / p.baseline.raw_heartbeats);
    if (typeof p.score !== 'number' || !Number.isFinite(p.score) || Math.abs(p.score - score) > 1e-9) throw new Error(`F${p.row}: 점수 불일치`);
    cost += Number(p.currentRunCostUsd);
  }
  if (Math.abs(cost - Number(input.costUsd)) > 1e-7) throw new Error('실행 비용 합계 불일치');
  return input as FinalResults;
}
