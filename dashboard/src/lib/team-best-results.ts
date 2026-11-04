import type { FinalBaselines } from './final-baselines.ts';
import type { FinalResult, FinalResultsView } from './final-results.ts';

export type SharedResults = {schemaVersion: 1; datasetSha256: string; generatedAt: string; problems: FinalResult[]};
const record = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v);
const hash = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const positive = (v: unknown) => Number.isSafeInteger(v) && Number(v) > 0;
function measurement(v: unknown): boolean {
  return record(v) && positive(v.tokens) && positive(v.raw_heartbeats)
    && (v.raw_samples === null || (Array.isArray(v.raw_samples) && [1,3].includes(v.raw_samples.length)
      && v.raw_samples.every(positive) && [...v.raw_samples].sort((a,b)=>a-b)[Math.floor(v.raw_samples.length/2)] === v.raw_heartbeats));
}

// These are shared observations, not fresh compiler or API receipts.
export function parseSharedResults(input: unknown, baselines: FinalBaselines): SharedResults {
  if (!record(input) || input.schemaVersion !== 1 || input.datasetSha256 !== baselines.datasetSha256
    || input.officialEvaluation !== false || input.measurementPolicy !== 'reported-paired'
    || input.apiCallsDuringImport !== 0 || input.leanRunsDuringImport !== 0
    || typeof input.generatedAt !== 'string' || !Number.isFinite(Date.parse(input.generatedAt))
    || !Array.isArray(input.problems) || input.problems.length !== 40) throw new Error('팀원 공유 결과 형식 오류');
  const seen = new Set<number>();
  for (const p of input.problems) {
    if (!record(p) || !Number.isInteger(p.row) || seen.has(p.row)
      || !(p.row >= 11 && p.row <= 40 || p.row >= 51 && p.row <= 60)) throw new Error('팀원 공유 문제 범위 오류');
    seen.add(p.row);
    const original = baselines.problems.find(b=>b.row===p.row)!;
    const author = p.row <= 30 ? '남성우' : '손지연';
    const key = p.row <= 30 ? 'seongwoo' : 'jiyeon';
    const expected = original.references!;
    if (p.name !== original.name || p.source !== original.source || p.author !== author
      || p.runId !== `team-report-${key}-20261102` || p.evidenceLevel !== 'shared-report'
      || p.proofPath !== `solutions/team-shared-20261102/${key}/F${String(p.row).padStart(3,'0')}.lean`
      || typeof p.proof !== 'string' || !p.proof.length || p.proof.length > 200000
      || !hash(p.candidateHash) || p.proofFileHash !== p.candidateHash
      || !measurement(p.baseline) || !measurement(p.candidate) || p.baselineCompatibility !== 100
      || !Array.isArray(p.versions) || p.versions.length !== expected.length
      || p.versions.some((v: any,i: number)=> !record(v) || v.version !== expected[i].version
        || v.revision !== expected[i].revision || v.environment !== expected[i].environment || v.status !== 'pass' || v.fingerprint !== null)
      || !expected.some(v=>v.environment===p.measurementEnvironment)
      || typeof p.measurementNote !== 'string' || !p.measurementNote.length
      || !Array.isArray(p.evidence) || p.evidence.length !== 1
      || p.evidence[0].path !== 'solutions/team-shared-20261102/reported-results.zip' || !hash(p.evidence[0].sha256)
      || p.currentRunCostUsd !== '0'
      || !(p.reportedCostUsd === null || typeof p.reportedCostUsd === 'number' && Number.isFinite(p.reportedCostUsd) && p.reportedCostUsd >= 0)
      || !(p.measuredAt === null || typeof p.measuredAt === 'string' && Number.isFinite(Date.parse(p.measuredAt)))) throw new Error(`F${p.row}: 팀원 공유 근거 오류`);
    const score = 100-100/3*(p.candidate.tokens/p.baseline.tokens+p.candidate.raw_heartbeats/p.baseline.raw_heartbeats);
    if (typeof p.score !== 'number' || !Number.isFinite(p.score) || Math.abs(score-p.score)>1e-9) throw new Error(`F${p.row}: 공유 결과 점수 오류`);
  }
  return input as SharedResults;
}

// Incumbents win exact score ties. Strata/LeanPool have no new competitors.
export function selectTeamBest(incumbents: FinalResultsView, shared: SharedResults): FinalResultsView {
  const groups = new Map<number, FinalResult[]>();
  for (const result of incumbents.problems) {
    if (groups.has(result.row)) throw new Error('기존 결과 문제 중복');
    groups.set(result.row, [{...result, author: result.row >= 11 && result.row <= 30 ? '정소미' : '권주원'}]);
  }
  const incoming = new Set<number>();
  for (const result of shared.problems) {
    if (incoming.has(result.row)) throw new Error('공유 결과 문제 중복');
    incoming.add(result.row);
    const group = groups.get(result.row) ?? [];
    group.push(result); groups.set(result.row, group);
  }
  const problems = [...groups.values()].map(group=>{
    const best = group.reduce((best,p)=>p.score > best.score + 1e-9 ? p : best);
    return {...best, comparisons: group.map(p=>({author:p.author!,runId:p.runId,score:p.score,
      candidateHash:p.candidateHash,proofPath:p.proofPath,selected:p===best}))};
  }).sort((a,b)=>a.row-b.row);
  return {...incumbents,generatedAt: new Date(incumbents.generatedAt) > new Date(shared.generatedAt) ? incumbents.generatedAt : shared.generatedAt,problems};
}
