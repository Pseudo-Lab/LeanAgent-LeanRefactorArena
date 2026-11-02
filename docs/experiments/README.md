# 실험 정리

2026-11-02 기준. **목적·방법·실제 결과·한계·코드 보존 결정을 Markdown만으로 읽는 기록**이다. 로컬 실험 디렉터리와 보존 커밋 `3ee67de`의 실험 39종을 대조했다. 원래 미커밋 연구 자료를 공통 코드에 전부 반입했다는 뜻은 아니다.

- [10/28–29 종합 기록](2026-10-28-29.md): API·프롬프트·후처리와 환경 실패.
- [연구 기법과 비교](research-techniques.md): 작은 코드 예·구조적 기법·v5–v11·경쟁형 실험 비교.
- [보존·정리 기준](retention.md): 어떤 Lean과 실행 코드를 남기는가.
- [PR #46·워크트리 감사](worktree-audit-2026-11-02.md): 반영 범위·남은 구현·검사·복구 경로.

## 읽는 기준

`T`는 proof 소스 토큰 수, `H`는 각 시행이 정의한 heartbeat다. 모델 사용 토큰·요금과 구분한다. 보통 `O=T/T0+H/H0`를 최소화하지만 구조 후속은 공개 환산 HB 분모를 사용한다. raw HB·환산 HB·분모가 다른 시행의 O를 바로 비교하지 않는다. 조건부 점수는 호환성 가정의 로컬 계산이며 공식 제출 결과가 아니다.

완료·중단·미실행, 원본 출발·incumbent 출발, 탐색·golf 이후, 합성 검사·실제 Lean 검증을 구분한다. 아래 숫자는 과거 기록에서 옮겼다. 이번 정리 중 새 API·Lean 측정·공식 제출은 수행하지 않았다. 원문에 등장하는 오래된 경로·유료 명령은 재실행하지 않아도 된다.

## 실험별 기록

| 실험 | 결과와 해석 |
| --- | --- |
| [행동 선택과 후보 기억](records/action-candidate-memory.md) | 고정 응답은 14→2토큰·replay 통과. P02 strict 소규모 유료 비교에서는 whole 166토큰, 행동 조건은 222토큰 원본 유지였다. 구조 검증과 성능 효과를 구별한다. |
| [실제 API와 공통 루프](records/api-comparison.md) | 비용 예약과 실측 threshold를 구분한다. 아래 결과는 각 실행의 모델·입력·예산 조건에 한정되며 범용 전략 우위를 뜻하지 않는다. |
| [캐시된 Lean 검증](records/cached-verification.md) | P01·P02·P04·P05·P06 검증 범위의 로컬 구현이다. stat-cache와 지속 worker는 다른 기능이며 이 결과로 HB 개선을 주장하지 않는다. |
| [v5 공통 지침 연구](records/common-v5-study-20261030.md) | 유료 matched-arm 연구는 유예, API 비용 $0. 별도 P01–P03 local-agent 120후보 중 100유효·20실패, 평균 O는 6회 0.870857→40회 0.369471. 두 연구를 합쳐 유료 비교 성공으로 읽지 않는다. |
| [경쟁형 탐색 파일럿](records/competitive-search-20261031.md) | 216후보 중 148유효·68실패, 18 final. 이 파일럿에서 portfolio의 평균 고정 O가 가장 낮았지만 조건당 1회·개발 3문제다. |
| [원본 출발 portfolio 40회](records/competitive-search40-20261031.md) | 120후보와 독립 final 3개. P02는 후반 merger에서 추가 개선. Lean 4.26 primary 결과이며 모든 지정 버전 성공이나 통계적 우위를 뜻하지 않는다. |
| [fresh40 추가 네 문제](records/competitive-search40-extra-20261101.md) | 160/160후보, 118유효·42실패, 독립 final 4개. 네 문제 모두 pool18 이후 개선. P06 4.32, 나머지 4.26; Putnam 축소 import·추가 버전 미검증이다. |
| [incumbent 출발 구조 탐색](records/competitive-structure-20261101.md) | 160평가 중 120유효·40실패, 독립 final4개. 최종 길이는 409/187/31/181토큰. 원본 출발 fresh40과 달리 incumbent-seeded이며 full header·추가 버전은 미검증이다. |
| [비용 가설 A/B 파이프라인](records/cost-hypothesis-pipeline.md) | 보존된 README의 최신 조회는 41/48평가·6/8실행 완료. PROGRESS의 31평가 기록은 앞선 디스크 중단 시점이다. 전체 완료 A/B 결과로 취급하지 않는다. |
| [환경 점검·오류 피드백·상태](records/environment-preflight.md) | 기능1–3 실험68검사와 고정 main19회귀 통과 기록. 강제 종료·기록 무결성 검사와 실제 Lean 스모크를 구분한다. |
| [지정 환경 검증](records/environment-verification.md) | 환경 확인과 개별 proof의 컴파일·공리·측정 성공은 별개다. 아래 문서의 버전 범위를 넘는 주장을 하지 않는다. |
| [v8 빠른 실험 모드](records/fast-harness-20261031.md) | P10 40회+제한 golf: 37분29초, 비용 추정 $2.0348133. 조건부 점수 79.84→78.09로 악화. 동등 품질의 속도 개선 실험이 아니다. |
| [오류 요약 후속 비교](records/feedback-summary-20261025.md) | 8실행·80후보, 8 final/replay 감사 통과. 3회차 개선 수는 두 조건이 같았다. 요약8건 중 전달 내용이 달라진 것은 P01의2건뿐이어서 일반 효과를 식별하기 어렵다. |
| [이전 Final 배치](records/final-batch.md) | 실행기 존재를 60문제 성능 실험 완료로 보지 않는다. 후속 final-batch-next와 중복된다. |
| [공통 Final 배치 adapter](records/final-batch-next.md) | PR #46 합성 회귀 검사에 포함된다. 이번 정리는 실제 모델 호출·새 Lean 컴파일·Final 성능 측정을 수행하지 않았다. |
| [Final 환경 준비](records/final-environment.md) | 환경 준비 코드·lock·snapshot은 실행 기반이며 그 자체로 모든 Final 문제의 성공 결과가 아니다. |
| [초기 하네스·prompt/feedback ablation](records/first-harness-jwkweon.md) | 34독립실행·312후보의 기록. prompt20개 final은 통과했으나 초기 P13 예산10회 두 실행의 final은 timeout. 지침의 효과가 문제·회차에 따라 달랐다. |
| [tactic HB 프로파일링](records/hb-profile.md) | 진단 계측은 전체 최종 검증을 대체하지 않는다. 길이 감소와 HB 감소가 충돌할 수 있다. |
| [v10 증분 하네스](records/incremental-harness-20261031.md) | 3문제 유료 실행105호출·77평가·$5.8509499. v9 대비 조건부 평균69.212969→86.077089, 경과2.754배 비율. 후보·작업량이 다른 과거 대조이며 모두40회 이전 예산 예약 중단이다. |
| [Final 길이 하한 정적 분석](records/length-bounds.md) | API·Lean·proof search 0회. 2토큰 floor는 각 문제가 2토큰으로 풀린다는 뜻이 아니며 최단 증명을 인증하지 않는다. term proof 허용 시 보편 하한도 아니다. |
| [P06·P11 수동 기법 적용](records/oai-techniques-p06-p11-20261101.md) | P06 528토큰, P11 1120토큰. P06은 이전 팀450토큰보다 길고 HB가 낮다. 각각 지정 버전 검증 기록은 있지만 전역 최적·외부 증명 직접 이식의 증거는 아니다. |
| [오프라인 구조 탐색](records/offline-proof-search.md) | P12 362→178토큰, primary raw HB 4,111,012→3,017,981. 같은178토큰 후보의4.29/4.30/4.31검증 기록. 이후156토큰 후속은 별도 기록이며 새 문제 일반화 평가가 아니다. |
| [예산 제한 API 실행기](records/openrouter-budget-trial.md) | 10/28–29 종합 문서에 문제별 호출·실패·비용·후처리 결과를 기록했다. timeout은 무료 실패로 세지 않고 미확정 비용을 유지한다. |
| [94점 목표 포트폴리오 연구](records/portfolio-94.md) | 94는 목표이며 달성한 공식 점수가 아니다. 단계별 README의 진행 중 상태와 submission-round의 후속 검증을 구분한다. |
| [문제별 원본 입력 준비](records/problem-inputs.md) | 입력 준비는 최종 검증 성공과 별개다. agentkit의 P01–P05 입력 수정과 tactic probe는 미커밋으로 남아 있다. |
| [규칙 기반 문제 라우팅](records/problem-routing.md) | warmup15문제 계획을 생성했다. 비용0·컴파일 없음의 구조 작업으로 모델 성능 개선 실험은 아니다. |
| [공통 프롬프트 설계](records/prompt-design.md) | v4는 선택된 세 문제에서 이전 실행보다 나았으나 이전88참조를 넘은 것은 P03. v5 matched-arm은 유예이므로 우수성을 주장하지 않는다. |
| [정적 증명 분석](records/proof-analyze.md) | warmup15문제의 정적 요약을 생성했다. focus 파일은 자동 생성되는 표시용 소스이며 실행 fixture가 아니다. |
| [결정적 proof golf](records/proof-golf.md) | 10/28–29 후처리에서 일부 후보가 개선됐지만 모든 문제의 구조적 병목을 해결하지는 못했다. 휴리스틱 floor를 최적성 인증으로 읽지 않는다. |
| [v9 컴파일러 사실·변경 기억](records/research-harness-20261031.md) | P01/P10/P14 유료 실행은 11/2/24평가, 합계$6.5364999, 비용76.74%가 inspection. 문맥 회귀·반복 조회·파서 본문 유실을 확인했다. |
| [v9 세 문제 유료 시행](records/research-trial-20261031.md) | 선택3문제 조건부 평균69.21297, 목표40회 미달. 무작위 표본이나15문제 점수 추정이 아니다. |
| [v11 검색 통합 하네스](records/retrieval-harness-20261101.md) | P11 28호출·19평가·12유효·$1.8724256. post-golf368토큰/9,067,259raw HB. 외부 검색 도구를 호출하지 않았고4.31만 검증했다. |
| [v7 상태·복구](records/stateful-harness-20261031.md) | recovery/replay 및 로컬 검증이며 v7만의 새 유료 최적화·점수 개선 결과는 없다. unknown 유료 요청은 자동 재호출하지 않는다. |
| [구조화 v6 API 15문제](records/structured-openai-20261031.md) | 710고유 응답·$20.8474525,14문제40평가·P06은36평가. golf4689변형 중P03만84→80토큰. 평균O0.523951,사후88참조0.357309;2문제 개선·13악화. |
| [구조화 API 사후 분석](records/structured-openai-analysis-20261031.md) | 새 API·Lean 호출0. 호환성100% 가정의 평균점수 차이5.554732점 중 길이71.21%,HB28.79%;golf 이득0.039882점. 무작위 ablation이 아니다. |
| [구조화 v6 local](records/structured-reasoning-20261030.md) | P02는20토큰/370,630raw HB로 강하게 개선, P01/P03은 과거보다 O 악화. 평균 효과는 P02에 집중되며 prompt·장부 효과를 분리할 수 없다. |
| [v6 local 사후 대조](records/structured-reasoning-analysis-20261031.md) | 15개 대조 중12개 통과 기록. 결과를 알고 설계한 사후 실험이므로 blind solver 성능이나 일반 prompt 효과로 읽지 않는다. |
| [로컬 정리 검색](records/theorem-retrieval-20261101.md) | 162,417외부모듈 색인. P11 유용 정리 순위4/2/4/3,P01은1위. API0,선정된 진단 query이며 proof 점수·성공률 개선은 입증하지 않았다. |
| [사용량·비용 집계](records/usage-cost.md) | reported 비용과 토큰 기반 추정액·예약액을 구분한다. subagent 환산액을 실제 API 청구액으로 기록하지 않는다. |

## 새 실험을 기록할 때

`records/<실험명>.md`에 다음을 직접 기록하고 이 표에 연결한다. 원시 파일이나 HTML만 열어야 결과를 알 수 있는 형태를 피한다.

1. 질문·가설과 비교 조건: 문제·출발 후보·모델·예산·평가 수·compiler/library revision.
2. 방법과 실제 수행: 계획한 수와 끝낸 수, 실패·중단·미확정 비용.
3. 결과 표: 원본·선택본 토큰/HB·최종 독립 검증·지정 버전 범위.
4. 결론과 한계: 관찰과 인과 주장, 재현 검사와 성능 비교를 구분.
5. 채택·보류·폐기 및 PR/공통 코드 대응.
6. 원본 경로·커밋·SHA256, 재현에 필요한 최소 입력과 명령. 필요한 짧은 proof는 fenced Lean 코드로 포함.

문서는 결과 이해를 보장한다. 원시 영수증·로그의 독립 재감사와 동일 환경 실행은 별도 증거가 필요하며 Markdown 요약만으로 대체하지 않는다.
