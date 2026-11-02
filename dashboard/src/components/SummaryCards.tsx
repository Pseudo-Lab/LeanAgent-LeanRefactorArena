import { ArrowDownRight, ChartNoAxesCombined, Info } from 'lucide-react';
import { aggregate, format } from '../lib/model';
import type { Snapshot } from '../lib/model';

export function SummaryCards({ snapshot }: { snapshot: Snapshot }) {
  const scores = aggregate(snapshot.problems, 'improvement');
  const tokens = aggregate(snapshot.problems, 'tokens');
  const hb = aggregate(snapshot.problems, 'heartbeats');
  if (snapshot.dataset === 'final') {
    const references = snapshot.problems.flatMap(p => p.original?.versions ?? []);
    const primary = snapshot.problems.filter(p => p.baseline !== null).length;
    const complete = snapshot.problems.filter(p => p.original?.versions.every(v => v.status === 'pass')).length;
    return <>
      <div className="summary-grid">
        <article className="summary-card primary-summary"><div className="summary-label">Final 문제<ChartNoAxesCombined size={18}/></div><div className="big-number">{snapshot.problems.length}<span>문제</span></div><p>F001–F060 · 6개 출처 · 웜업과 별도 집계</p></article>
        <article className="summary-card"><div className="summary-label">원본 Length · HB</div><div className="big-number">{primary}<span>/ {snapshot.problems.length}</span></div><p>대표 버전 HB · 모든 버전 완료 {complete}문제</p></article>
        <article className="summary-card"><div className="summary-label">후보 개선 측정</div><div className="big-number">{scores.count}<span>/ {scores.total}</span></div><p>평균 개선 {format(scores.value)} · 미실행은 집계 대기</p></article>
      </div>
      <div className="measurement-note"><Info size={14}/><span>원본 버전 검증 <strong>{references.filter(v => v.status === 'pass').length} / {references.length}</strong> · 후보 지표는 원본과 별도로 집계 · HB는 raw // 1000</span><span className="local-only">공식 제출 점수 아님</span></div>
    </>;
  }
  return <>
    <div className="summary-grid">
      <article className="summary-card primary-summary"><div className="summary-label">평균 개선 점수<ChartNoAxesCombined size={18}/></div>
        <div className="big-number">{format(scores.value)}<span>/ 100</span></div>
        <p>토큰 · heartbeat 감소율 평균 <span className="dot-separator">·</span> 로컬 지표</p>
      </article>
      <article className="summary-card"><div className="summary-label">토큰 감소<ArrowDownRight size={18}/></div>
        <div className="big-number">{format(tokens.value)}<span>%</span></div><p>문제별 감소율 평균 <span className="dot-separator">·</span> {tokens.count}문제 측정</p>
      </article>
      <article className="summary-card"><div className="summary-label">Heartbeat 감소<ArrowDownRight size={18}/></div>
        <div className="big-number">{format(hb.value)}<span>%</span></div><p>동일 환경의 원본과 비교 <span className="dot-separator">·</span> {hb.count}문제 측정</p>
      </article>
    </div>
    <div className="measurement-note"><Info size={14}/><span><strong>{scores.count} / {scores.total}</strong> 문제 측정 · 미측정은 위 평균에서 제외 · 검색·필터와 무관한 전체 데이터 기준</span><span className="local-only">공식 제출 점수 아님</span></div>
  </>;
}
