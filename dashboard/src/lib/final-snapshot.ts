import type { FinalBaselines } from './final-baselines.ts';
import type { Snapshot } from './model.ts';

// Original measurements establish the baseline; they are not improved candidates.
export function baselineSnapshot(data: FinalBaselines): Snapshot {
  return {
    schemaVersion: 1, id: 'final60-baselines', label: '최종 60문제 원본', dataset: 'final',
    measuredAt: data.generatedAt, releaseDate: null, provenance: data.datasetSha256,
    problems: data.problems.map(p => ({
      id: p.row, name: p.name, source: p.source, status: 'pending',
      baseline: p.local ? { tokens: p.local.tokens, heartbeats: p.local.rawHeartbeats } : null,
      candidate: null, baselineCompatibility: null, candidateHash: '',
      versions: p.requiredVersions.map(version => ({ version, revision: version === p.primaryVersion ? p.primaryRevision : '', status: 'pending' })),
      environment: `${p.primaryVersion} · raw heartbeat`,
      evidence: p.local?.evidence.map(e => `${e.path} · ${e.sha256}`) ?? [],
      note: `${p.local ? p.local.sampleCount === 1 ? '원본 HB: 1회 잠정값.' : '원본 HB: 3회 중앙값.' : '원본 HB 미측정.'} 개선 후보 결과는 아직 연결되지 않았습니다. 버전 표시는 후보 검증 상태입니다.`,
    })),
  };
}
