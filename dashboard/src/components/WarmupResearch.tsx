import research from '../../public/research/warmup15/experiment.json';
import literature from '../../public/research/literature.json';
import { waitingLabel } from '../lib/model';
import type { Snapshot } from '../lib/model';

const paperTitles = new Map([...literature.papers, ...literature.additionalPapers].map(p => [p.id, p.title] as const));
const pair = (value: { tokens: number; heartbeats: number } | null, fallback: string) => value ? `${value.tokens.toLocaleString('ko-KR')} / ${value.heartbeats.toLocaleString('ko-KR')}` : fallback;

export function WarmupResearch({ publishedSnapshot }: { publishedSnapshot: Snapshot | undefined }) {
  if (!publishedSnapshot) return null;
  return <section className="panel research-panel" id="warmup-research" aria-labelledby="warmup-research-title">
    <div className="panel-title"><h2 id="warmup-research-title">P01–P15 · 독립 검증과 성능 개선</h2><span>{research.date}</span></div>
    <p className="section-intro">정소미의 15문제 독립 검증 기록입니다. 귀납 구조 변경·국소 축약·정리 재사용·오류 수정을 시도하고 검증 결과와 성능 변화를 기록했습니다.</p>
    <p className="source-disclosure">HB는 Lean 내부 작업량 단위입니다. 토큰 / HB가 작을수록 짧고 가벼운 증명입니다. 설명 속 출발 후보는 종전 대표와 다를 수 있습니다. 별도 검증 수치는 공통 평균에 합산하지 않습니다.</p>
    <div className="research-table-wrap"><table className="research-table warmup-research-table" role="table"><caption>토큰 / HB · 종전 대표와 현재 선택 비교. 유지·개선·실패와 남은 검증을 함께 표시합니다.</caption><thead><tr><th>문제·시도한 기법</th><th>종전 대표</th><th>현재 선택</th><th>결과·지정 버전</th></tr></thead><tbody>{research.rows.map(row => {
      const current = publishedSnapshot.problems.find(p => p.id === row.id)!;
      const pass = current.versions.filter(v => v.status === 'pass').length;
      const linked = row.selectedHash === current.candidateHash;
      return <tr key={row.id} id={`trial-P${String(row.id).padStart(2, '0')}`}>
        <th scope="row"><strong className="trial-number">P{String(row.id).padStart(2, '0')}</strong><p>{linked ? row.method : '선택 기법 설명 대기'}</p><p>{linked ? row.references.map(id => <a key={id} href={`https://arxiv.org/abs/${id}`} target="_blank" rel="noreferrer" title={paperTitles.get(id)}>{(paperTitles.get(id) ?? id).split(':')[0]} </a>) : null}</p></th>
        <td><span className="mobile-cell-label">종전 대표</span>{pair(row.previous, '종전 측정 없음')}</td>
        <td><span className="mobile-cell-label">현재 선택</span>{pair(current.candidate, waitingLabel(current))}</td>
        <td><strong>{linked ? row.status : '설명 갱신 대기'}</strong><p>{linked ? row.decision : '선택 후보가 바뀌어 이전 설명을 보류했습니다.'}</p>{row.trialEvidence ? <p><a href={row.trialEvidence} target="_blank" rel="noreferrer">별도 검증 근거 · 공통 평균 미포함</a></p> : null}<details><summary>현재 선택: {pass}/{current.versions.length} 버전 통과</summary>{current.versions.map(v => <p key={v.version}>{v.version} · {v.revision.slice(0, 8)} · {v.status === 'pass' ? '통과' : v.status === 'fail' ? '실패' : '확인 중'}</p>)}</details></td>
      </tr>;
    })}</tbody></table></div>
    <details className="collection-note"><summary>비교 기준·산식과 재현 범위</summary><p>원본은 대회의 고정 증명, 종전 대표는 이전 선택 기록, 출발 후보는 추가 실험을 시작한 기존 최선입니다. 개선 점수 = ((1 − 후보 토큰 / 원본 토큰) + (1 − 후보 HB / 원본 HB)) × 50. 추가 점수는 새 후보 점수에서 같은 조건의 출발 후보 점수를 뺍니다.</p><p>META·CREATE·REPAIR는 전략 선택·후보 작성·오류 수정입니다. Pareto는 두 지표 중 하나도 더 좋지 않고 하나 이상이 더 나쁜 후보를 제외하는 비교입니다. 공통 평가 경로는 비교 조건을 고정한 검증 코드이며 공식 점수와 구분합니다.</p><p>{research.executionMode} {research.measurement} {research.adaptationScope}</p><a href="/research/warmup15/verification.json" target="_blank" rel="noreferrer">정확한 버전·커밋과 측정 근거</a></details>
    <details className="collection-note"><summary>paperthin · 결과에 따라 바뀐 작업 경로</summary>{research.routeChanges.map(route => <p key={route.trigger}><strong>{route.trigger}</strong> · {route.route}<br/>{route.outcome}</p>)}<a href="/research/warmup15/experiment.json" target="_blank" rel="noreferrer">문제별 적용·판단 기록</a></details>
  </section>;
}
