import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { parseFinalBaselines } from '../lib/final-baselines';
import type { FinalBaselines as BaselineData } from '../lib/final-baselines';
import { format, valueOf } from '../lib/model';
import type { Metric, Problem } from '../lib/model';
import { parseFinalResults } from '../lib/final-results';
import type { FinalResults } from '../lib/final-results';
import { resultSnapshot } from '../lib/final-snapshot';
import { ProblemGrid } from './ProblemGrid';
import { DetailPanel } from './DetailPanel';
import { ScoringGuide } from './ScoringGuide';

export function FinalBaselines() {
  const [data, setData] = useState<BaselineData | null>(null);
  const [results, setResults] = useState<FinalResults | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('all');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('number');
  const [selectedId, setSelectedId] = useState(1);
  const [metric, setMetric] = useState<Metric>('combined');
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(['/data/final-baselines.json', '/data/final-results.json'].map(url =>
      fetch(url, { signal: controller.signal }).then(r => { if (!r.ok) throw new Error(`데이터 요청 실패 (${r.status})`); return r.json(); })))
      .then(([originals, candidates]) => {
        const baseline = parseFinalBaselines(originals);
        const verified = parseFinalResults(candidates, baseline);
        setData(baseline); setResults(verified);
      })
      .catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, []);
  if (!data || !results) return <main id="main"><h1>최종 60문제 · 검증 풀이</h1>{error
    ? <div role="alert" className="notification error">{error}<button className="button" onClick={() => window.location.reload()}>다시 불러오기</button></div>
    : <p className="loading-state">원본 측정 기록을 불러오고 있습니다…</p>}</main>;

  const measured = data.problems.filter(p => p.local !== null).length;
  const provisional = data.problems.filter(p => p.local?.sampleCount === 1).length;
  const snapshot = resultSnapshot(data, results);
  const meanScore = results.problems.reduce((sum, p) => sum + p.score, 0) / results.problems.length;
  const needle = query.trim().toLowerCase();
  const visible = snapshot.problems.filter(p => {
    const original = data.problems.find(row => row.row === p.id)!;
    return (source === 'all' || source === p.source)
      && (status === 'all' || (status === 'verified' ? p.status === 'measured' : status === 'pending' ? !p.candidate : status === 'provisional' ? original.local?.sampleCount === 1 : original.local === null))
      && (!needle || `F${String(p.id).padStart(3, '0')} ${p.name} ${p.source}`.toLowerCase().includes(needle));
  }).sort((a, b) => {
    if (sort === 'number') return a.id - b.id;
    const av = valueOf(a, metric), bv = valueOf(b, metric);
    if (av === null) return bv === null ? a.id - b.id : 1;
    if (bv === null) return -1;
    return (sort === 'high' ? bv - av : av - bv) || a.id - b.id;
  });
  const selected = visible.find(p => p.id === selectedId) ?? visible[0] ?? null;
  const original = data.problems.find(p => p.row === selected?.id);
  const candidate = results.problems.find(p => p.row === selected?.id);
  function chooseProblem(p: Problem) {
    setSelectedId(p.id);
    if (window.matchMedia('(max-width: 959px)').matches) requestAnimationFrame(() => document.getElementById('problem-detail')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }));
  }
  const updated = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }).format(new Date(results.generatedAt));
  return <main id="main" className="final-baselines">
    <div className="page-heading"><div><h1>최종 60문제 · 검증 풀이</h1><p>Strata·LeanPool 20문제의 검증 풀이를 반영했습니다. 타일을 선택하면 원본 대비 점수와 증명을 볼 수 있습니다.</p></div>
      <a className="button" href="/data/final-results.json" download><Download size={16}/>검증 결과 JSON</a></div>
    <div className="summary-grid">
      <article className="summary-card"><div className="summary-label">원본 length 확보</div><div className="big-number">60<span>/ 60문제</span></div><p>제공된 최종 데이터셋의 proof_length</p></article>
      <article className="summary-card"><div className="summary-label">원본 HB 확보</div><div className="big-number">{measured}<span>/ 60문제</span></div><p>3회 중앙값 {measured - provisional}개 · 1회 잠정값 {provisional}개</p></article>
      <article className="summary-card"><div className="summary-label">검증 풀이 · 20 / 60문제</div><div className="big-number">{format(meanScore)}<span>점</span></div><p>검증된 20문제 평균 · 대회식 종합 로컬 추정</p></article>
    </div>
    <p className="measurement-note">검증 풀이 20개는 지정 버전 전체 통과, HB는 원본·후보 각각 3회 중앙값(raw 단위)입니다. 나머지 40개는 개선 결과 없음으로 회색 표시됩니다. 공식 점수가 아닙니다.</p>
    <div className="dataset-bar">
      <span className="warmup-label">F001–F010 · F041–F050 검증 완료</span>
      <label className="snapshot-picker"><span>결과 상태</span><select aria-label="결과 상태" value={status} onChange={e => setStatus(e.target.value)}><option value="all">전체 60문제</option><option value="verified">검증 완료 (20)</option><option value="pending">개선 결과 없음 (40)</option><option value="provisional">1회 잠정값 ({provisional})</option><option value="missing">HB 미측정 ({60 - measured})</option></select></label>
    </div>
    <div className="workbench final-workbench">
      <ProblemGrid {...{ snapshot, metric, query, source, sort, visible, selected }} compact onMetric={setMetric} onQuery={setQuery} onSource={setSource} onSort={setSort} onSelect={chooseProblem}/>
      <DetailPanel problem={selected} metric={metric} snapshot={snapshot}>
        {candidate ? <section className="team-results" aria-label="선택한 검증 증명">
          <h3>선택한 검증 증명</h3>
          <p>{candidate.runId === results.runId ? '이번 $3 실행' : '기존 $1 실행'} · 동일 환경의 검증 결과 중 종합 점수가 가장 높은 풀이</p>
          <p>원본 HB: {candidate.baseline.raw_samples.map(n => format(n, 0)).join(' / ')}<br/>후보 HB: {candidate.candidate.raw_samples.map(n => format(n, 0)).join(' / ')}</p>
          <details className="team-candidate"><summary>Lean 증명 보기 · {candidate.candidateHash.slice(0, 10)}</summary>
            <p className="candidate-origin">{candidate.proofPath}<br/>{candidate.runId}</p>
            <pre className="candidate-code"><code>{candidate.proof}</code></pre>
          </details>
        </section> : null}
        {original?.references ? <section className="final-reference-versions" aria-label="원본 버전별 측정"><h3>원본 버전별 측정</h3>
          <p>비교 Length는 Final 평가기 기준입니다. 후보 검증과 원본 검증은 별도로 집계합니다.</p>
          <div className="reference-table-wrap"><table className="metrics-table"><thead><tr><th>Lean</th><th>raw HB</th><th>환산 HB</th><th>표본</th></tr></thead><tbody>{original.references.map(v=><tr key={v.environment} title={`고정 revision ${v.revision}`}><th>{v.version}</th><td>{format(v.rawHeartbeats,0)}</td><td>{format(v.scaledHeartbeats,0)}</td><td>{v.sampleCount}</td></tr>)}</tbody></table></div>
          <details><summary>원본 해시와 고정 revision</summary><code>{original.referenceSha256}</code>{original.references.map(v=><p key={v.environment}><code>{v.version} @ {v.revision}</code></p>)}</details>
        </section> : null}
        {original ? <details className="baseline-detail-evidence">
          <summary>원본 측정 근거 · {original.local?.sampleCount === 1 ? '1회 잠정값' : original.local ? '3회 중앙값' : '미측정'}</summary>
          <p>제공 length: {format(original.providedLength, 0)} · 로컬 length: {format(original.local?.tokens ?? null, 0)}</p>
          {original.local ? <>
            <p>raw HB 표본 {original.local.sampleCount}회: {original.local.rawSamples.map(n => format(n, 0)).join(' / ')}</p>
            <p>scaled HB (raw ÷ 1,000 내림): {format(original.local.scaledHeartbeats, 0)}</p>
            <p>실행 기록: {original.local.runId}</p>
            <p>측정 시각: {new Date(original.local.measuredAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST</p>
            <ul className="baseline-evidence">{original.local.evidence.map(e => <li key={e.path}><code>{e.path}</code><small>{e.sha256}</small></li>)}</ul>
          </> : <p>원본 HB 미측정</p>}
        </details> : null}
      </DetailPanel>
    </div>
    <ScoringGuide/>
    <footer><span>저장된 스냅샷 · {updated} KST · 자동 갱신 아님</span><span>이번 실행 ${format(Number(results.costUsd))} · 사용량 기준 비용</span></footer>
  </main>;
}
