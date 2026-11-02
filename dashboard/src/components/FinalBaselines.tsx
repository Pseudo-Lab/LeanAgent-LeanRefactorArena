import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { parseFinalBaselines } from '../lib/final-baselines';
import type { FinalBaselines as BaselineData } from '../lib/final-baselines';
import { format, valueOf } from '../lib/model';
import type { Metric, Problem } from '../lib/model';
import { baselineSnapshot } from '../lib/final-snapshot';
import { ProblemGrid } from './ProblemGrid';
import { DetailPanel } from './DetailPanel';
import { ScoringGuide } from './ScoringGuide';

export function FinalBaselines() {
  const [data, setData] = useState<BaselineData | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('all');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('number');
  const [selectedId, setSelectedId] = useState(1);
  const [metric, setMetric] = useState<Metric>('improvement');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/data/final-baselines.json', { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(`데이터 요청 실패 (${r.status})`); return r.json(); })
      .then(value => setData(parseFinalBaselines(value)))
      .catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, []);
  if (!data) return <main id="main"><h1>최종 60문제 · 원본 기준값</h1>{error
    ? <div role="alert" className="notification error">{error}<button className="button" onClick={() => window.location.reload()}>다시 불러오기</button></div>
    : <p className="loading-state">원본 측정 기록을 불러오고 있습니다…</p>}</main>;

  const measured = data.problems.filter(p => p.local !== null).length;
  const provisional = data.problems.filter(p => p.local?.sampleCount === 1).length;
  const snapshot = baselineSnapshot(data);
  const needle = query.trim().toLowerCase();
  const visible = snapshot.problems.filter(p => {
    const original = data.problems.find(row => row.row === p.id)!;
    return (source === 'all' || source === p.source)
      && (status === 'all' || (status === 'provisional' ? original.local?.sampleCount === 1 : original.local === null))
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
  function chooseProblem(p: Problem) {
    setSelectedId(p.id);
    if (window.matchMedia('(max-width: 959px)').matches) requestAnimationFrame(() => document.getElementById('problem-detail')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }));
  }
  const updated = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }).format(new Date(data.generatedAt));
  return <main id="main" className="final-baselines">
    <div className="page-heading"><div><h1>최종 60문제 · 원본 기준값</h1><p>60문제의 원본 기준값과 개선 현황을 확인하세요. 타일을 선택하면 상세 수치가 표시됩니다.</p></div>
      <a className="button" href="/data/final-baselines.json" download><Download size={16}/>원본 데이터 JSON</a></div>
    <div className="summary-grid">
      <article className="summary-card"><div className="summary-label">원본 length 확보</div><div className="big-number">60<span>/ 60문제</span></div><p>제공된 최종 데이터셋의 proof_length</p></article>
      <article className="summary-card"><div className="summary-label">원본 HB 확보</div><div className="big-number">{measured}<span>/ 60문제</span></div><p>3회 중앙값 {measured - provisional}개 · 1회 잠정값 {provisional}개</p></article>
      <article className="summary-card"><div className="summary-label">HB 미측정</div><div className="big-number">{60 - measured}<span>문제</span></div><p>측정값 없음 · 0점으로 처리하지 않음</p></article>
    </div>
    <p className="measurement-note">기본 버전의 원본 기준값이며 HB는 raw 단위입니다. 1회 잠정값은 반복 검증 전 수치입니다. 공식 점수나 전체 버전 검증 결과가 아닙니다.</p>
    <div className="dataset-bar">
      <span className="warmup-label">F001–F060 · 원본 기준값 확보</span>
      <label className="snapshot-picker"><span>원본 측정 상태</span><select aria-label="원본 측정 상태" value={status} onChange={e => setStatus(e.target.value)}><option value="all">전체 60문제</option><option value="provisional">1회 잠정값 ({provisional})</option><option value="missing">HB 미측정 ({60 - measured})</option></select></label>
    </div>
    <div className="workbench final-workbench">
      <ProblemGrid {...{ snapshot, metric, query, source, sort, visible, selected }} compact onMetric={setMetric} onQuery={setQuery} onSource={setSource} onSort={setSort} onSelect={chooseProblem}/>
      <DetailPanel problem={selected} metric={metric} snapshot={snapshot}>
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
    <footer><span>저장된 스냅샷 · {updated} KST · 자동 갱신 아님</span><span>최종 데이터셋 {data.datasetSha256.slice(0, 12)}</span></footer>
  </main>;
}
