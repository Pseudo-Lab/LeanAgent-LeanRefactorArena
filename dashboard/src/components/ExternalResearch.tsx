import research from '../../public/research/external/problem-literature.json';

const papers = new Map(research.papers.map(paper => [paper.id, paper]));

export function ExternalResearch() {
  function route(problem: typeof research.problems[number]) {
    return <article className="external-route" key={problem.problem}>
      <h3>P{String(problem.problem).padStart(2, '0')} · {problem.bottleneck}</h3>
      <p className="source-disclosure">{problem.coverage}</p>
      <p>{problem.nextExperiment}</p>
      <p className="source-disclosure">{problem.limitation}</p>
      <p>{problem.papers.map(id => <a key={id} href={papers.get(id)!.url} target="_blank" rel="noreferrer">{papers.get(id)!.title}</a>)}</p>
    </article>;
  }
  return <section className="panel research-panel" id="external-research" aria-labelledby="external-research-title">
    <div className="panel-title"><h2 id="external-research-title">기존 63편 밖 · 문제별 추가 문헌</h2><span>{research.date}</span></div>
    <p className="section-intro">{research.scope}</p>
    <p className="source-disclosure">P05–P12를 우선 설계했습니다. 직접 대응하는 문헌이 부족한 문제는 간접 유추·추가 조사 필요로 표시합니다. 아래는 다음 실험 계획이며 위의 검증된 성능 결과와 구분합니다.</p>
    <figure className="external-figure"><img src={research.figure.path} width="802" height="516" loading="lazy" alt="LeanGraphSearch 원문 그림: 의미 검색으로 찾은 정리에서 의존 그래프로 후보를 확장한 뒤 재평가하는 흐름"/><figcaption>{research.figure.label}. {research.figure.qualification} <a href={papers.get(research.figure.paper)!.url} target="_blank" rel="noreferrer">원문 Figure 2 · p. 4</a></figcaption></figure>
    <div className="external-routes">{research.problems.filter(p => p.problem >= 5 && p.problem <= 12).map(route)}</div>
    <details className="collection-note"><summary>P01–P04·P13–P15 · 추가 조사 범위</summary><div className="external-routes">{research.problems.filter(p => p.problem < 5 || p.problem > 12).map(route)}</div></details>
    <details className="collection-note"><summary>새 원문 6편 · 읽은 방법과 적용 한계</summary>{research.papers.map(paper => <article className="external-paper" key={paper.id}>
      <h3><a href={paper.url} target="_blank" rel="noreferrer">{paper.title}</a></h3>
      <p className="source-disclosure">{paper.section}</p><blockquote>{paper.quote}<a href={`https://www.alphaxiv.org/pdf/${paper.id}?page=${paper.quotePage}`} target="_blank" rel="noreferrer">원문 p. {paper.quotePage}</a></blockquote>
      <p>{paper.method} {paper.adaptation}</p><p className="source-disclosure">{paper.limitation}</p>
    </article>)}</details>
    <details className="collection-note"><summary>paperthin · 작은 실험·검증·전환 순서</summary><ol>{research.routing.order.map(step => <li key={step}>{step}</li>)}</ol><p>{research.routing.decision}</p><p>{research.routing.budget}</p><p className="source-disclosure">비용에 따른 전환 원리: <a href={papers.get(research.routing.commonPaper)!.url} target="_blank" rel="noreferrer">Cost–Quality Tradeoff · pp. 4–5</a>. 출력 토큰을 비용으로 쓰는 원문의 가정과 실제 달러 비용을 구분합니다.</p></details>
    <p className="source-disclosure">검색 반환 {research.search.returnedRecords}건·중복 제거 {research.search.uniqueRecords}건 중 방법 대조 6편. OpenAlex는 요청 제한으로 결과를 확보하지 못했습니다. {research.search.coverage} <a href="/research/external/problem-literature.json" target="_blank" rel="noreferrer">문제별 설계 기록</a> · <a href="/research/external/reading-evidence.json" target="_blank" rel="noreferrer">PDF 해시·원문 확인 근거</a></p>
  </section>;
}
