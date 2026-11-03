import type { FinalBaselines } from './final-baselines.ts';
import type { FinalResults } from './final-results.ts';
import type { Snapshot } from './model.ts';

// Original measurements establish the baseline; they are not improved candidates.
export function baselineSnapshot(data: FinalBaselines): Snapshot {
  return {
    schemaVersion: 1, id: 'final60-baselines', label: '최종 60문제 원본', dataset: 'final',
    measuredAt: data.generatedAt, releaseDate: null, provenance: data.datasetSha256,
    problems: data.problems.map(p => ({
      id: p.row, name: p.name, source: p.source, status: 'pending',
      baseline: p.local ? { tokens: p.local.tokens, heartbeats: p.local.rawHeartbeats } : null,
      candidate: null, baselineCompatibility: p.references?.length === p.requiredVersions.length ? 100 : null, candidateHash: '',
      versions: p.requiredVersions.map(version => ({ version, revision: p.references?.find(r=>r.version===version)?.revision ?? (version === p.primaryVersion ? p.primaryRevision : ''), status: 'pending' })),
      environment: `${p.primaryVersion} · raw heartbeat`,
      evidence: p.local?.evidence.map(e => `${e.path} · ${e.sha256}`) ?? [],
      note: `${p.local ? p.local.sampleCount === 1 ? '원본 HB: 단일 표본.' : '원본 HB: 3회 중앙값.' : '원본 HB 미측정.'} 개선 후보 결과는 아직 연결되지 않았습니다. 버전 표시는 후보 검증 상태입니다.`,
    })),
  };
}

// Candidate scores use their own paired baseline, never an unrelated baseline run.
export function resultSnapshot(data: FinalBaselines, results: FinalResults): Snapshot {
  const snapshot = baselineSnapshot(data);
  const candidates = new Map(results.problems.map(p => [p.row, p]));
  return { ...snapshot, id: 'final60-results', label: '최종 60문제 · 검증 풀이', measuredAt: results.generatedAt,
    problems: snapshot.problems.map(p => {
      const c = candidates.get(p.id);
      if (!c) return p;
      return { ...p, status: 'measured',
        baseline: { tokens: c.baseline.tokens, heartbeats: c.baseline.raw_heartbeats },
        candidate: { tokens: c.candidate.tokens, heartbeats: c.candidate.raw_heartbeats },
        baselineCompatibility: c.baselineCompatibility, candidateHash: c.candidateHash,
        versions: c.versions.map(v => ({version:v.version, revision:v.revision, status:v.status})),
        evidence: c.evidence.map(e => `${c.runId}/${e.path} · ${e.sha256}`),
        note: `지정 버전 전체 통과 · 원본/후보 HB 각 3회 중앙값. ${c.runId === results.runId ? '$3 실행' : '기존 $1 실행'}에서 선택한 검증 풀이입니다. 공식 점수가 아닙니다.`,
      };
    }),
  };
}
