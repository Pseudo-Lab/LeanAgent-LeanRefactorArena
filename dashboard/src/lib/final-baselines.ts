export type FinalBaselineProblem = {
  id: string; row: number; name: string; source: string; providedLength: number;
  primaryVersion: string; primaryRevision: string; requiredVersions: string[];
  local: null | {
    runId: string; sampleCount: 1 | 3; tokens: number; rawHeartbeats: number; scaledHeartbeats: number; rawSamples: number[];
    measuredAt: string; evidence: { path: string; sha256: string }[];
  };
};
export type FinalBaselines = {
  schemaVersion: 1; dataset: 'final-baselines'; datasetSha256: string; generatedAt: string;
  runId: string; measurementPolicy: 'primary-pin-local-samples'; problems: FinalBaselineProblem[];
};
const sha = 'd53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682';
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const date = (v: unknown) => text(v) && Number.isFinite(Date.parse(v));
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
export function parseFinalBaselines(input: unknown): FinalBaselines {
  if (!record(input) || input.schemaVersion !== 1 || input.dataset !== 'final-baselines' || input.datasetSha256 !== sha
      || !date(input.generatedAt) || !text(input.runId) || input.measurementPolicy !== 'primary-pin-local-samples'
      || !Array.isArray(input.problems) || input.problems.length !== 60) throw new Error('최종 60문제 원본 데이터 형식 오류');
  const ids = new Set<number>();
  for (const p of input.problems) {
    if (!record(p) || !integer(p.row) || p.row < 1 || p.row > 60 || ids.has(p.row)
        || p.id !== `F${String(p.row).padStart(3, '0')}` || !text(p.name) || !text(p.source)
        || !integer(p.providedLength) || !text(p.primaryVersion) || !text(p.primaryRevision)
        || !Array.isArray(p.requiredVersions) || !p.requiredVersions.every(text)
        || p.requiredVersions[0] !== p.primaryVersion) throw new Error('최종 문제 목록 형식 오류');
    ids.add(p.row);
    if (p.local === null) continue;
    const m = p.local;
    if (!record(m) || !text(m.runId) || !integer(m.tokens) || !integer(m.rawHeartbeats) || !integer(m.scaledHeartbeats)
        || !date(m.measuredAt) || ![1, 3].includes(Number(m.sampleCount)) || !Array.isArray(m.rawSamples)
        || m.rawSamples.length !== m.sampleCount || !m.rawSamples.every(integer)
        || [...m.rawSamples].sort((a, b) => a - b)[Math.floor(m.rawSamples.length / 2)] !== m.rawHeartbeats
        || Math.floor(m.rawHeartbeats / 1000) !== m.scaledHeartbeats
        || !Array.isArray(m.evidence) || m.evidence.length < 2 + 2 * (1 + Number(m.sampleCount)) || !m.evidence.every(e => record(e)
          && text(e.path) && e.path.startsWith(`problems/${p.id}/`) && !e.path.split('/').includes('..')
          && text(e.sha256) && /^[a-f0-9]{64}$/.test(e.sha256))) throw new Error(`${p.id}: 원본 측정 근거 오류`);
  }
  return input as FinalBaselines;
}
