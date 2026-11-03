import { useState } from 'react';
import catalogue from '../../public/research/literature.json';

export function LiteratureMethods() {
  const [family, setFamily] = useState('all');
  const [query, setQuery] = useState('');
  const needle = query.trim().toLowerCase();
  const papers = catalogue.papers.filter(p => (family === 'all' || p.family === family) && `${p.id} ${p.title} ${p.mechanism} ${p.disposition}`.toLowerCase().includes(needle));
  return <section className="panel research-panel" id="literature-methods" aria-labelledby="literature-title">
    <div className="panel-title"><h2 id="literature-title">저장소 문헌 · 기법과 적용 조건</h2><span>63편 + 추가 조사 4편</span></div>
    <p className="section-intro">정소미님의 META·CREATE·REPAIR, 고정 명제 검증, 실패 포함 집계와 토큰·HB 선택을 기준으로 확장합니다.</p>
    <p className="source-disclosure">{catalogue.scope} 원문 초록을 확인한 자료와 방법 절까지 확인한 자료를 구분합니다. 학습·전용 서버·분야 도구가 필요한 방법은 조건을 표시합니다.</p>
    <div className="paper-list">{Object.entries(catalogue.families).map(([id, item]) => <article key={id}><h4>{item.label}</h4><p>{item.action}</p><p className="paper-application">연결 근거: {item.evidence}</p></article>)}</div>
    <div className="activity-toolbar literature-toolbar"><input className="literature-search" aria-label="문헌 검색" placeholder="논문·기법·arXiv 번호 검색" value={query} onChange={e => setQuery(e.target.value)}/><select aria-label="문헌 기법 분류" value={family} onChange={e => setFamily(e.target.value)}><option value="all">모든 기법</option>{Object.entries(catalogue.families).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}</select></div>
    <p className="activity-count" role="status">저장소 문헌 {papers.length} / 63편</p>
    <div className="paper-list">{papers.map(paper => <article key={paper.id}><h4><a href={paper.url} target="_blank" rel="noreferrer">{paper.title}</a></h4><p>{paper.mechanism}</p><p className="paper-application">{paper.disposition} · {paper.basis}</p><small className="activity-count">{paper.id}</small></article>)}</div>
    {!papers.length ? <p className="empty-search">조건에 맞는 문헌이 없습니다.</p> : null}
    <details className="collection-note"><summary>추가 조사 4편과 적용 범위</summary>{catalogue.additionalPapers.map(p => <p key={p.id}><a href={p.url} target="_blank" rel="noreferrer">{p.title}</a> · {p.mechanism} · {p.disposition}</p>)}{catalogue.adaptationNotes.map(note => <p key={note}>{note}</p>)}</details>
  </section>;
}
