export type FinalReference = {
  environment: string; version: string; revision: string; status: 'pass';
  rawHeartbeats: number; scaledHeartbeats: number; rawSamples: number[]; sampleCount: 1 | 3;
};
export type FinalBaselineProblem = {
  id: string; row: number; name: string; source: string; providedLength: number;
  primaryVersion: string; primaryRevision: string; requiredVersions: string[];
  referenceSha256?: string; references?: FinalReference[];
  local: null | {
    runId: string; sampleCount: 1 | 3; tokens: number; auditTokens?: number;
    rawHeartbeats: number; scaledHeartbeats: number; rawSamples: number[];
    measuredAt: string; evidence: { path: string; sha256: string }[]; referenceSinglePass?: boolean;
  };
};
export type FinalBaselines = {
  schemaVersion: 1; dataset: 'final-baselines'; datasetSha256: string; generatedAt: string;
  runId: string; measurementPolicy: 'primary-pin-local-samples' | 'all-pins-local-samples'; problems: FinalBaselineProblem[];
  verification?: { status: 'passed'; problemVersions: number; environments: number; compilerVersions: number; auditSha256: string };
};
const sha = 'd53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682';
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const date = (v: unknown) => text(v) && Number.isFinite(Date.parse(v));
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const checksum = (v: unknown) => text(v) && /^[a-f0-9]{64}$/.test(v);
function samples(m: Record<string, unknown>): boolean {
  return integer(m.rawHeartbeats) && integer(m.scaledHeartbeats) && [1, 3].includes(Number(m.sampleCount))
    && Array.isArray(m.rawSamples) && m.rawSamples.length === m.sampleCount && m.rawSamples.every(integer)
    && [...m.rawSamples].sort((a,b)=>a-b)[Math.floor(m.rawSamples.length/2)] === m.rawHeartbeats
    && Math.floor(m.rawHeartbeats/1000) === m.scaledHeartbeats;
}
export function parseFinalBaselines(input: unknown): FinalBaselines {
  if (!record(input) || input.schemaVersion !== 1 || input.dataset !== 'final-baselines' || input.datasetSha256 !== sha
      || !date(input.generatedAt) || !text(input.runId) || !['primary-pin-local-samples','all-pins-local-samples'].includes(String(input.measurementPolicy))
      || !Array.isArray(input.problems) || input.problems.length !== 60) throw new Error('최종 60문제 원본 데이터 형식 오류');
  const complete = input.measurementPolicy === 'all-pins-local-samples';
  const ids = new Set<number>(), environments = new Set<string>(), versions = new Set<string>();
  let pairCount = 0;
  for (const p of input.problems) {
    if (!record(p) || !integer(p.row) || p.row < 1 || p.row > 60 || ids.has(p.row)
        || p.id !== `F${String(p.row).padStart(3,'0')}` || !text(p.name) || !text(p.source)
        || !integer(p.providedLength) || !text(p.primaryVersion) || !text(p.primaryRevision)
        || !Array.isArray(p.requiredVersions) || !p.requiredVersions.every(text) || new Set(p.requiredVersions).size !== p.requiredVersions.length
        || p.requiredVersions[0] !== p.primaryVersion) throw new Error('최종 문제 목록 형식 오류');
    ids.add(p.row);
    if (p.local === null) {
      if (complete) throw new Error(`${p.id}: 전체 버전 완료 데이터에 원본 측정 누락`);
      continue;
    }
    const m = p.local;
    if (!record(m) || !text(m.runId) || !integer(m.tokens) || !date(m.measuredAt) || !samples(m)
        || (m.auditTokens !== undefined && !integer(m.auditTokens))
        || (m.referenceSinglePass !== undefined && typeof m.referenceSinglePass !== 'boolean')
        || !Array.isArray(m.evidence) || m.evidence.length < 2 + 2 * (Number(m.sampleCount) + (m.referenceSinglePass === true ? 0 : 1))
        || !m.evidence.every(e => record(e) && text(e.path) && !e.path.split('/').includes('..')
          && (e.path.startsWith(`problems/${p.id}/`) || (e.path.startsWith('runs/manual/') && e.path.split('/').some(s=>s===p.id || s.startsWith(p.id+'-'))))
          && checksum(e.sha256))) throw new Error(`${p.id}: 원본 측정 근거 오류`);
    if (complete) {
      if (!checksum(p.referenceSha256) || m.tokens !== p.providedLength || !Array.isArray(p.references)
          || p.references.length !== p.requiredVersions.length) throw new Error(`${p.id}: 전체 버전 근거 누락`);
      const seen = new Set<string>();
      for (const r of p.references) {
        if (!record(r) || !text(r.version) || !p.requiredVersions.includes(r.version) || seen.has(r.version)
            || r.environment !== `${p.source}-${r.version}` || !text(r.revision) || !/^[a-f0-9]{40}$/.test(r.revision)
            || r.status !== 'pass' || !samples(r)) throw new Error(`${p.id}: 지정 버전 측정 오류`);
        seen.add(r.version); environments.add(String(r.environment)); versions.add(r.version); pairCount++;
      }
      const primary = p.references.find(r=>r.version===p.primaryVersion)!;
      if (primary.revision !== p.primaryRevision || primary.rawHeartbeats !== m.rawHeartbeats
          || JSON.stringify(primary.rawSamples) !== JSON.stringify(m.rawSamples)) throw new Error(`${p.id}: 대표 버전 불일치`);
    }
  }
  if (complete) {
    const v = input.verification;
    if (!record(v) || v.status !== 'passed' || v.problemVersions !== 127 || pairCount !== 127
        || v.environments !== 17 || environments.size !== 17 || v.compilerVersions !== 8 || versions.size !== 8
        || !checksum(v.auditSha256)) throw new Error('전체 환경 종료 검증 오류');
  }
  return input as FinalBaselines;
}
