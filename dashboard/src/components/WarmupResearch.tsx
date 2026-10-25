import research from '../../public/research/warmup15/experiment.json';
import { waitingLabel } from '../lib/model';
import type { Snapshot } from '../lib/model';

const pair = (value: { tokens: number; heartbeats: number } | null, fallback: string) => value ? `${value.tokens.toLocaleString('ko-KR')} / ${value.heartbeats.toLocaleString('ko-KR')}` : fallback;

export function WarmupResearch({ publishedSnapshot }: { publishedSnapshot: Snapshot | undefined }) {
  if (!publishedSnapshot) return null;
  return <section className="panel research-panel" id="warmup-research" aria-labelledby="warmup-research-title">
    <div className="panel-title"><h2 id="warmup-research-title">P01–P15 · 문헌 기법 적용 결과</h2><span>{research.date}</span></div>
    <p className="section-intro">{research.core}를 유지하고 팀원 기법과 문헌의 방법을 더했습니다.</p>
    <p className="source-disclosure">{research.executionMode} {research.measurement} {research.adaptationScope}</p>
    <div className="research-table-wrap"><table className="research-table warmup-research-table"><caption>토큰 / HB · 종전 대표와 현재 선택 비교. 기존 후보 재선정과 새 증명 개선을 구분합니다.</caption><thead><tr><th>문제·적용 기법</th><th>종전 대표</th><th>현재 선택</th><th>결과·지정 버전</th></tr></thead><tbody>{research.rows.map(row => {
      const current = publishedSnapshot.problems.find(p => p.id === row.id)!;
      const pass = current.versions.filter(v => v.status === 'pass').length;
      const linked = row.selectedHash === current.candidateHash;
      return <tr key={row.id}><th>P{String(row.id).padStart(2, '0')}<p>{row.method}</p><small>{row.credit}</small><p>{row.references.map(id => <a key={id} href={`https://arxiv.org/abs/${id}`} target="_blank" rel="noreferrer">[{id}] </a>)}</p></th><td>{pair(row.previous, '종전 측정 없음')}</td><td>{pair(current.candidate, waitingLabel(current))}</td><td><strong>{linked ? row.status : '설명 갱신 대기'}</strong><p>{linked ? row.decision : '선택 후보가 바뀌어 이전 설명을 보류했습니다.'}</p><details><summary>현재 선택: {pass}/{current.versions.length} 통과</summary>{current.versions.map(v => <p key={v.version}>{v.version} · {v.revision.slice(0, 8)} · {v.status === 'pass' ? '통과' : v.status === 'fail' ? '실패' : '대기'}</p>)}</details></td></tr>;
    })}</tbody></table></div>
    <details className="collection-note"><summary>비교 기준·산식과 용어</summary><p>원본은 대회의 고정 증명, 종전 대표는 담당자 최종본 우선 선택, 출발 후보는 추가 실험을 시작한 기존 최선입니다. 개선 점수 = ((1 − 후보 토큰 / 원본 토큰) + (1 − 후보 HB / 원본 HB)) × 50. 추가 점수는 새 후보 점수에서 같은 조건의 출발 후보 점수를 뺍니다.</p><p>META·CREATE·REPAIR는 전략 선택·후보 작성·오류 수정입니다. Pareto는 두 지표 모두 더 나쁜 후보를 제외하는 비교입니다. 고정 PR3은 동일한 버전의 평가 코드를 뜻하며 공식 점수와 구분합니다. 이 표는 사이트의 고정 실험 기록을 표시합니다.</p><a href="/research/warmup15/verification.json" target="_blank" rel="noreferrer">정확한 버전·커밋과 측정 근거</a></details>
    <details className="collection-note"><summary>paperthin · 결과에 따라 바뀐 작업 경로</summary>{research.routeChanges.map(route => <p key={route.trigger}><strong>{route.trigger}</strong> · {route.route}<br/>{route.outcome}</p>)}<a href="/research/warmup15/experiment.json" target="_blank" rel="noreferrer">문제별 적용·판단 기록</a></details>
  </section>;
}
