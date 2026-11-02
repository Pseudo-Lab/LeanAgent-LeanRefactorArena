import { useEffect, useState } from 'react';
import { Download, Search } from 'lucide-react';
import { parseFinalBaselines } from '../lib/final-baselines';
import type { FinalBaselines as BaselineData } from '../lib/final-baselines';
import { format, sourceName } from '../lib/model';

export function FinalBaselines() {
  const [data, setData] = useState<BaselineData | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('all');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('number');
  const [selectedId, setSelectedId] = useState('F001');
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
  const needle = query.trim().toLowerCase();
  const visible = data.problems.filter(p => (source === 'all' || source === p.source)
    && (status === 'all' || (status === 'measured' ? p.local !== null : status === 'provisional' ? p.local?.sampleCount === 1 : p.local === null))
    && (!needle || `${p.id} ${p.name} ${p.source}`.toLowerCase().includes(needle))).sort((a, b) => {
      if (sort === 'length') return b.providedLength - a.providedLength || a.row - b.row;
      if (sort === 'hb') return (b.local?.rawHeartbeats ?? -1) - (a.local?.rawHeartbeats ?? -1) || a.row - b.row;
      return a.row - b.row;
    });
  const selected = visible.find(p => p.id === selectedId) ?? visible[0];
  const updated = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }).format(new Date(data.generatedAt));
  return <main id="main" className="final-baselines">
    <div className="page-heading"><div><h1>최종 60문제 · 원본 기준값</h1><p>원본 proof length와 기존 실행에서 측정한 heartbeat를 모았습니다.</p></div>
      <a className="button" href="/data/final-baselines.json" download><Download size={16}/>원본 데이터 JSON</a></div>
    <div className="summary-grid">
      <article className="summary-card"><div className="summary-label">원본 length 확보</div><div className="big-number">60<span>/ 60문제</span></div><p>제공된 최종 데이터셋의 proof_length</p></article>
      <article className="summary-card"><div className="summary-label">원본 HB 확보</div><div className="big-number">{measured}<span>/ 60문제</span></div><p>3회 중앙값 {measured - provisional}개 · 1회 잠정값 {provisional}개</p></article>
      <article className="summary-card"><div className="summary-label">HB 미측정</div><div className="big-number">{60 - measured}<span>문제</span></div><p>측정값 없음 · 0점으로 처리하지 않음</p></article>
    </div>
    <p className="measurement-note">기본 버전의 원본 기준값이며 HB는 raw 단위입니다. 1회 잠정값은 반복 검증 전 수치입니다. 공식 점수나 전체 버전 검증 결과가 아닙니다.</p>
    <section className="panel baseline-list" aria-labelledby="baseline-list-heading">
      <div className="panel-title"><h2 id="baseline-list-heading">문제별 원본 length · HB</h2><span aria-live="polite">{visible.length} / 60문제 표시</span></div>
      <div className="grid-toolbar baseline-toolbar">
        <label className="search-field"><Search size={16}/><input aria-label="최종 문제 검색" placeholder="F001, 정리 이름 검색" value={query} onChange={e => setQuery(e.target.value)}/></label>
        <select aria-label="최종 문제 출처" value={source} onChange={e => setSource(e.target.value)}><option value="all">모든 출처</option>{[...new Set(data.problems.map(p => p.source))].map(s => <option key={s} value={s}>{sourceName(s)}</option>)}</select>
        <select aria-label="원본 측정 상태" value={status} onChange={e => setStatus(e.target.value)}><option value="all">전체 상태</option><option value="measured">HB 확보 ({measured})</option><option value="provisional">1회 잠정값 ({provisional})</option><option value="missing">HB 미측정 ({60 - measured})</option></select>
        <select aria-label="원본 정렬" value={sort} onChange={e => setSort(e.target.value)}><option value="number">문제 번호순</option><option value="length">Length 높은 순</option><option value="hb">HB 높은 순</option></select>
      </div>
      <div className="baseline-table-scroll"><table className="baseline-table"><caption className="sr-only">60문제 원본 기준값. HB가 없으면 미측정으로 표시합니다.</caption>
        <thead><tr><th scope="col">문제 · 정리</th><th scope="col">출처 / 기본 버전</th><th scope="col">Length<span>데이터셋 제공</span></th><th scope="col">원본 HB<span>raw · 로컬 측정</span></th><th scope="col">측정 상태</th></tr></thead>
        <tbody>{visible.map(p => <tr key={p.id} className={selected?.id === p.id ? 'baseline-selected' : ''}>
          <th scope="row"><button aria-pressed={selected?.id === p.id} onClick={() => setSelectedId(p.id)}><strong>{p.id}</strong><span>{p.name}</span></button></th>
          <td>{sourceName(p.source)}<small>{p.primaryVersion}</small></td><td>{format(p.providedLength, 0)}</td>
          <td>{p.local ? format(p.local.rawHeartbeats, 0) : <span className="baseline-missing">—</span>}</td>
          <td><span className={`baseline-status ${p.local?.sampleCount === 1 ? 'provisional' : p.local ? 'ready' : ''}`}>{p.local?.sampleCount === 1 ? '1회 잠정값' : p.local ? '3회 중앙값' : 'HB 미측정'}</span></td>
        </tr>)}</tbody>
      </table></div>
      {!visible.length ? <p className="baseline-empty">조건에 맞는 문제가 없습니다.</p> : null}
    </section>
    {selected ? <section className="panel baseline-detail" aria-labelledby="baseline-detail-heading">
      <h2 id="baseline-detail-heading">{selected.id} · 측정 근거</h2><p className="theorem-name">{selected.name}</p>
      <dl className="baseline-facts">
        <div><dt>제공 length</dt><dd>{format(selected.providedLength, 0)} tokens</dd></div>
        <div><dt>로컬 측정 length</dt><dd>{selected.local ? `${format(selected.local.tokens, 0)} tokens` : '미측정'}</dd></div>
        <div><dt>로컬 HB · raw</dt><dd>{selected.local ? format(selected.local.rawHeartbeats, 0) : '미측정'}</dd></div>
        <div><dt>로컬 HB · raw ÷ 1,000 내림</dt><dd>{selected.local ? format(selected.local.scaledHeartbeats, 0) : '미측정'}</dd></div>
      </dl>
      <p>기본 측정 버전: {selected.primaryVersion} · 필수 버전: {selected.requiredVersions.join(', ')}</p>
      {selected.local ? <>
        <p>raw HB 표본 {selected.local.sampleCount}회: {selected.local.rawSamples.map(n => format(n, 0)).join(' / ')}{selected.local.sampleCount === 1 ? ' · 잠정값, 반복 검증 전' : ' · 중앙값 사용'}</p>
        <p>측정 시각: {new Date(selected.local.measuredAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST</p>
        {selected.local.tokens !== selected.providedLength ? <p>제공 length와 로컬 토큰 계산값이 다릅니다. 두 값은 별도로 보존합니다.</p> : null}
        <details><summary>기존 실행의 근거 파일 · SHA-256</summary><p>실행 기록: {selected.local.runId} · 가져오기 시 원본 입력, 소스·로그 해시, 실제 표본 {selected.local.sampleCount}개를 대조했습니다.</p>
          <ul className="baseline-evidence">{selected.local.evidence.map(e => <li key={e.path}><code>{e.path}</code><small>{e.sha256}</small></li>)}</ul></details>
      </> : <p>재사용할 원본 HB 완료 기록이 없습니다. 모델 탐색이나 추가 측정을 실행하지 않았습니다.</p>}
    </section> : null}
    <footer><span>저장된 스냅샷 · {updated} KST · 자동 갱신 아님</span><span>최종 데이터셋 {data.datasetSha256.slice(0, 12)}</span></footer>
  </main>;
}
