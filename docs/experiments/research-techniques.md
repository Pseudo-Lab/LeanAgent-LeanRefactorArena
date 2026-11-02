# 실험을 가로지르는 연구 기법

[실험 목록](README.md)

`codex/research-techniques-20261101`의 `5fc7bff`에서 정리한 기법·비교·설계 근거를 Markdown으로 모았다. 원문은 main `7f9508a` 기준의 2026-11-01 snapshot이다. **현재 main에는 PR #46의 scout→merger와 환율 정책이 추가 통합됐으므로 반영 상태는 [PR·워크트리 감사](worktree-audit-2026-11-02.md)를 우선한다.** 아래 미반영 표현은 과거 main에 대한 기술이다.

별도의 Lean 14개·JSON·수집 도구는 이 문서 묶음에 복사하지 않았다. 코드 원문은 보존된 커밋에서 복구하며 기법·비교 수치·한계는 본문만으로 읽는다.

## 원문: `docs/research/techniques-20261101/experiments.md`

### 실험 결과와 해석 범위

이 문서는 원래 결과를 고쳐 새로운 성공 실험으로 만들지 않는다. 아래 수치는 보존된 실행·사후 분석을 읽어 정리한 것이며, 이번 문서화 중 모델이나 Lean을 새로 실행하지 않았다. 원본 출발 / incumbent 출발, pre-golf / post-golf, raw / 환산 HB, 독립 검증 / 과거 대조를 구별한다.

#### 완료·중단·미실행 구분

| 연구 | 실제 수행 | 핵심 관찰 | 남은 해석 제한 |
| --- | --- | --- | --- |
| 10/28–29 후처리·API·v4 prompt | 과거 로컬/API 실행 | 고정 목적식으로 결정적 변형을 수락; 길이 감소와 HB 감소가 충돌 | 기본 도구·v4 prompt는 이후 PR #35에 이미 반영 |
| v5 유료 matched-arm 연구 | **실행 유예**, API 비용 0 | 준비·paired original controls만 검증 | 공통 prompt가 API에서 우수하다는 결과가 없음 |
| v5 공통 local-agent 40회 | P01–P03 총 120후보, 유효100/실패20 | 6회→40회 평균 O 0.870857→0.369471 | API 금액 예산 연구와 다름; 단회·선택 문제 |
| 구조화 v6 local | P01–P03 각40회와 별도 golf | P02에서 강한 내부 성질 효과, P01/P03은 표현 비용 문제 | 과거 대조로 컨트롤러·prompt의 인과 효과를 분리하지 못함 |
| structured v6 API 15문제 | 710 unique 응답, 비용 추정 $20.8474525 | 14문제40회, P06은36회; golf 4,689새 변형 중 P03만 84→80 T | 모든 지정 버전 검증 완료가 아님; conservative 예약으로 실제 비용이 남아도 중단 |
| v7 | recovery/replay·합성/실제 로컬 검증 | 상태·receipt·실패 기억 보존 | v7 단독 새 유료 성능 결과는 없음 |
| v8 P10 | 40회 + 제한 golf | 실행 37분29초, 비용 추정 $2.0348133 | 과거보다 품질 저하; 동등 품질의 속도 개선 아님 |
| v9 세 문제 API | P01/P10/P14, 총 $6.5364999 | 실제 평가 11/2/24회; 비용 76.74%가 inspection | 목표40회 미달, 문맥 회귀·타입 조회 지연 |
| v10 세 문제 API | 105호출, 77평가, $5.8509499 | 조건부 세 문제 평균 69.212969→86.077089 | 과거 대조, 다른 후보·작업량; 모두40회 이전 예산 예약 중단 |
| v11 P11 API | 28호출, 19평가, 12유효, $1.8724256 | post-golf 368 T / 9,067,259 raw HB | 목표40회 미달; external 도구를 호출하지 않음; 4.31만 검증 |
| 경쟁형 6조건×3문제 | 216후보, 유효148/실패68; 18 final | portfolio 평균 고정 O가 이번 파일럿에서 가장 낮음 | 조건당1회·3개 개발 문제; 공통 경쟁 피드백 자체의 효과는 분리되지 않음 |
| 원본 출발 portfolio40 | P01–P03 총120후보, 3 final | P02 후반 merge에서 큰 추가 개선 | 원본6/6/6 scout + merger22; 4.26만 검증 |
| 원본 출발 fresh40 추가4문제 | 160후보, 유효118/실패42; 4 final | P06/P13/P14/P15 모두 pool18 이후 추가 개선 | Putnam은 축소 import; full header·추가 버전 미검증 |
| 구조 후속 탐색 | 총160회, 유효120/실패40; 독립 final4개와 전체 감사 완료 | 409/187/31/181 T 후보 | incumbent-seeded. 공개 분모 고정. full header·추가 버전 미검증 |
| 수동 P06/P11 기법 적용 | baseline·checkpoint·독립3회 최종 측정 | P06 528 T, P11 1,120 T | 전역 최적 기록 아님. 지정 버전은 각각 전부 확인 |

금액은 그 실행의 기록된 가격/usage에 따른 추정이며 현재 가격이나 독립 청구서 검증 결과가 아니다. 문서화 목적의 신규 유료 호출은 없었다.

#### 구조화 계획의 성과와 한계

v6 local 사후 비교의 golf 이후 값은 다음과 같다. raw HB 단위다.

| 문제 | 과거 T / HB | v6 T / HB | 고정 O 변화 |
| --- | ---: | ---: | ---: |
| P01 | 24 / 1,241,990 | 36 / 1,268,892 | +13.75%, 악화 |
| P02 | 42 / 517,777 | 20 / 370,630 | −40.31%, 개선 |
| P03 | 75 / 199,415 | 86 / 180,765 | +11.95%, 악화 |

평균 O는 약6.05% 개선됐지만 P02에 집중됐다. 계획·장부 형식이 자체적으로 싼 증명을 보장한다는 결과가 아니다. 이후 동일 코드 부분만 바꾼 사후 대조 15개 중12개가 통과했으며, 그 대조가 [증명 기법](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/proof-techniques.md)의 국소 원인 근거다.

15문제 API 실행의 최종 평균 O는 0.523951, 뒤늦게 같은 primary 환경에서 재검증한 참조88의 평균 O는 0.357309였다. 새 실행은 2문제만 더 좋고13문제는 더 나빴다. 참조 후보는 API 탐색이 끝난 후에만 읽어 비교했으며, 입력 seed로 사용하지 않았다.

#### 속도 측정에서 서로 다른 것을 섞지 않기

v10 준비+실행 4,597.40초와 과거 v9의12,659.55초는 관측된 2.754배 elapsed ratio다. 모델 선택 후보·조회 횟수·queueing이 달라 전부 LSP/병렬화의 인과 효과로 해석하지 않는다.

같은 최종 증명에 대한 별도 serial/parallel 짝 검증은 다음과 같다.

| 문제 | serial 초 | parallel 초 | 중앙 raw HB 차이 |
| --- | ---: | ---: | ---: |
| P01 | 41.69 | 22.23 | −60 |
| P10 | 33.20 | 19.56 | 0 |
| P14 | 7.80 | 2.72 | +13 |

validity·토큰은 일치했다. 한 번의 짝 관찰이며 cold worker 비용과 짧은 batch의 더 느린 결과도 원래 worker 검증 보고에 남아 있다. process wall-hours 합계는 병렬로 겹치므로 실제 경과 시간과 합산하지 않는다.

#### 경쟁형 탐색의 실제 결과

12회×18셀 파일럿의 평균 O는 portfolio 0.449443, 큰 블록 교체0.461496, 역방향0.471975였다. portfolio 우위 대부분은 P02에서 나왔고 P01에서는 control보다 나빴다. reencode만으로 원본 출발한 조건은 평균0.975863으로 control보다 나빴다. 단회 결과이며 일반적 전략 우열이 아니다.

원본 출발40회 portfolio에서 pool18→final 고정 O의 추가 감소는 P01 5.05%, P02 50.87%, P03 2.25%였다. 40회를 모두 채웠다는 운영적 사실과 세 문제 모두 새로운 수학적 경로를 찾았다는 주장은 다르다. 특히 P03은 세 scout가 같은 전체 갱신 경로로 수렴했다.

추가 fresh40은 다음 값이다. P13–P15의 전체 header는 미검증이다.

| 문제 | final T | raw HB | pool18 이후 O 추가 감소 |
| --- | ---: | ---: | ---: |
| P06 | 418 | 22,877,043 | 44.10% |
| P13 | 235 | 3,012,079 | 25.35% |
| P14 | 126 | 1,071,111 | 23.35% |
| P15 | 244 | 1,366,707 | 28.61% |

후속 구조 탐색의 409/187/31/181토큰은 이 표의 final을 고쳐 쓴 값이 아니다. 앞서 찾은 incumbent을 입력으로 준 새 시행이며, published normalizer와 `floor(raw/1000)`를 쓰는 선택식도 구분해 기록했다.

후속 구조 탐색은 이후 P15까지 독립 검토를 완료했다. 유효120개·실패40개, baseline4개·독립 final4개다. 같은 호환율·나머지11문제 불변 조건에서15문제 평균 증가량은 출발 incumbent 대비+0.185464, 참조88 대비+0.306707이다. 이는 전체 새 제출본의 실측 점수가 아니다. [구조 탐색 설계 인사이트](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/structural-insights.md)와 [완료 검토](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/structural-review.md)를 참고한다.

#### 아직 성공으로 집계하지 않는 것

- 미실행 v5 matched API study.
- 준비·회귀 검사만으로 입증됐다고 할 수 없는 일반적 prompt/상태 머신의 품질 향상.
- v8의 동등 품질 가속, v9/v10/v11의40회 완주.
- 외부 OpenAI 예제 검색이 P11의 성능 향상을 유발했다는 주장.
- 선행 정리 lexical 검색을 타입 unification·실제 적용 가능성 판정과 동일시하는 것.
- 축소 header에서의 통과를 공식 전체 header·모든 지정 버전 통과로 바꾸는 것.
- 수동 P06/P11 결과를 로컬 아카이브 전체의 새 최적 기록 또는 실제 제출 변경으로 보고하는 것.

숫자의 출처 파일과 해시는 [source-records.json](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/source-records.json)에, 기계 판독 비교는 [facts.json](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/facts.json)에 있다. 이번 패키지는 원시 API 응답·대형 라이브러리·실행 DB를 복사하지 않는다.

## 원문: `docs/research/techniques-20261101/proof-techniques.md`

### 증명 의무와 표현을 줄이는 기법

아래는 기존 실험에서 관찰한 기법이다. 모든 수치는 로컬 기록이다. 표의 HB는 별도 표시가 없으면 **raw heartbeat**이며, 여러 시행의 서로 다른 분모를 한 순위로 합치지 않는다. 예제는 전체 선언만 담고 원래 import·선행 문맥을 포함하지 않으므로 단독 Lean 파일로 실행할 수 없다.

#### 1. 더 강하지만 합성하기 쉬운 내부 성질

##### P02: Subset을 직접 증명하는 대신 Sublist

외부 명제는 그대로 두고 내부에서는 정규화 전제가 없는 `Sublist`를 증명한다. 함수의 실제 분기대로 귀납하면 nil·append·cons가 직접 합성되고, 마지막에 `List.Sublist.subset`으로 내려온다. 이 환경의 panic 분기는 논리적으로 빈 리스트 기본값으로 환원된다. 실행 시 panic이 안전하다는 일반 명제는 아니다.

```lean
rintro -
apply List.Sublist.subset
fun_induction extractOldExprVars post <;>
  repeat first
    | assumption
    | apply List.nil_sublist
    | apply List.Sublist.append
    | apply List.Sublist.cons₂
```

[40회 portfolio 예제](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p02-portfolio40.lean)는 22토큰 / 301,702 raw HB다. main은 정규화 증거를 귀납하는 43토큰 증명이므로 이 내부 성질 변경은 아직 반영되지 않았다.

사후 대조에서는 v6의 20토큰 / 370,630 HB anchor에서 `clear h`만 제거하면 실패했다. 불필요한 전제를 남기면 귀납가정에도 그 전제를 요구하게 된다. 따라서 전제 삭제는 주석성 정리가 아니라 귀납 의무 자체를 바꾸는 선택이다.

##### 일반화할 때의 조건

입력이 여러 번 등장하면 먼저 입력들을 매개변수로 받는 내부 성질을 찾는다. 그 성질의 합성 법칙이 목표보다 짧은지, 외부 목표로 돌아오는 bridge가 싼지 실제로 검사한다. “더 강하다”만으로 더 저렴한 것은 아니다. 불필요 전제 제거가 원래 명제나 허용 문맥을 바꾸는 방식이어서는 안 된다.

#### 2. 인자 추론과 국소 보조 사실의 배치

P01의 사후 대조는 같은 v6 증명에서 다음 변화만 검사했다.

```lean
-- 이전: 명시 인자 묶음을 유지
fun_induction substOld h2 (Lambda.LExpr.fvar m h1 ty) post
-- 대조: 추론에 맡김
fun_induction substOld
```

36토큰 / 1,268,813 HB → 28토큰 / 1,263,496 HB. 이 생략 후보가 기존 golf의 seed 주변 생성 목록에 없었던 점도 확인했다. 함수 귀납·타입 추론을 활용하는 실험 후보는 아직 main의 구조적 귀납 증명을 대체하지 않았다.

반대로 모든 타입 인자·국소 사실을 없애는 규칙도 적절하지 않다. P02의 익명 `have := @List.Sublist.append`는 이름을 직접 쓰지 않아도 자동 합성의 인터페이스다.

| P02 동일 경로의 사후 대조 | T | raw HB | 결과 |
| --- | ---: | ---: | --- |
| local append anchor | 20 | 370,630 | 통과 |
| local append만 제거 | 16 | — | 실패 |
| global rule 목록에 append 직접 등록 | 18 | 410,168 | 통과하지만 고정 O 악화 |
| 같은 global rule을 목록 뒤로 이동 | 18 | 460,701 | 더 비쌈 |
| local 사실에 타입 인자 복원 | 21 | 364,952 | HB는 감소하지만 고정 O 악화 |

근거: [ablation·규칙 순서 대조](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/facts.json)의 `posthoc_ablation`, `posthoc_rule_order`. 이는 매칭 우선순위·타입 추론·재사용의 기여를 모두 분리한 결과가 아니다.

#### 3. 중간 상태와 전체 연산의 기존 API

P03의 긴 상태 관계 귀납을 전체 update 교환 정리로 바꾸는 경로는 **이미 main의 `updatedStatesComm` 사용에 들어 있다**. 새로 얻은 것은 그 경로의 연결 비용 차이다.

사후 v6 anchor에서 disjointness를 초기 상태로 운반하지 않고 가정이 직접 말하는 중간 상태에서 증명하고, 한 번만 쓰게 된 `hn`·`hd`를 인라인했다.

| 대조 | T | raw HB |
| --- | ---: | ---: |
| v6 anchor | 86 | 180,765 |
| 중간 상태에서 직접 증명 | 82 | 206,043 |
| 추가로 단일 사용 사실 인라인 | 78 | 199,965 |

HB가 늘어도 길이 감소로 총비용은 개선됐다. [독립 portfolio의 P03](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p03-portfolio40.lean)은 별도 시행의 81토큰 / 238,714 HB이며, 위 사후 후보와 같은 결과로 취급하지 않는다.

#### 4. P06: 두 입력을 쌍선형 사상으로 묶기

기존 main은 두 span 귀납을 사용한다. 수동 후보는 양변을 `LinearMap.mul`, `.comp`, `.compr₂`로 만든 쌍선형 사상으로 표현하고, 기저 ext를 두 번 적용한다. 반복된 span 닫기 의무를 선형 구조의 인터페이스에 맡기는 방식이다.

```lean
suffices h : f = g from congrArg (fun F => F a b) h
apply ofCrAnListFBasis.ext fun x => ofCrAnListFBasis.ext fun y => ?_
```

정렬·중심성·부호를 처리하는 기저 계산은 기존 팀 증명에서 재사용했다. 그 부분까지 새로 발견한 것으로 표시하지 않는다.

| 같은 4.32.0 환경에서의 최종 3회 중앙값 | T | 환산 HB |
| --- | ---: | ---: |
| 원본 | 1,217 | 42,028 |
| 기존 main 팀 후보 | 450 | 14,127 |
| [쌍선형 ext 후보](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p06-manual.lean), candidate-0003 | 528 | 10,849 |

원본 대비 길이 −56.6%, HB −74.2%. 기존 팀 후보 대비로는 **78토큰 더 길고 HB는 23.2% 감소**한다. 길이만 줄인 성공 사례가 아니다. 로컬 종합 선택식에서 이 후보가 선택됐으며, 지정 버전 4.32.0의 전체 모듈·공리 검사를 통과했다.

이후의 [incumbent 구조 탐색](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p06-structural.lean)에는 409토큰 / 11,003,038 raw HB 후보도 있다. 그 시행은 이미 개선된 422토큰 후보에서 시작한 별도 후속 탐색이다. main의 450토큰, 88점 참조의 422토큰, fresh40의 418토큰, 수동 ext의 528토큰을 하나의 같은 출발점으로 섞지 않는다.

#### 5. P11: 유한 입력 일반화와 다항식 선형성

##### 0·1 보조증명을 `Fin 2` 하나로 합치기

`have h_eval (k : Fin 2)`와 `have h_split (k : Fin 2)`로 같은 fiber 평가·분해를 통합한다. 별도 두 증명을 복사하는 대신 필요한 곳에서 0·1로 특수화한다.

##### 긴 eval 계산을 다항식 단계에서 닫기

먼저 다음 항등식을 sum 분배·`C_add`·`C_mul`·`ring`으로 보인다.

```lean
have h_poly : P_i_plus_1 = Polynomial.C (1 - r_chal) * P₀ +
    Polynomial.C r_chal * P₁ := by
  ...
```

평가의 덧셈·곱·상수 보존으로 내려간 뒤, 알려진 fiber 차이 식의 명시적 `linear_combination` certificate로 닫는다. 여러 목표에 넓은 자동화를 독립적으로 반복시키는 비용을 줄인다.

| 수동 실험, 대표 4.31.0 | T | 환산 HB |
| --- | ---: | ---: |
| 원본 | 1,906 | 45,535 |
| [선택 후보](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p11-manual.lean), candidate-0002 | 1,120 | 33,354 |

길이 −41.2%, HB −26.8%. main의 1,656토큰 후보보다도 짧지만, 전역 최적 증명이라는 뜻은 아니다. 같은 최종 선언 SHA `fc81d460…`가 **4.29.0·4.30.0·4.31.0**에서 원본 전체 모듈과 허용 공리 검사를 통과했다. HB 반복 측정은 4.31.0에서만 수행했다.

##### 더 짧은 기존 API가 있으면 큰 내부 계산부터 제거

수동 1,120토큰 후보는 긴 fiber 차이 계산을 유지했다. 반면 [retrieval 시행의 368토큰 후보](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p11-retrieval.lean)는 원래 import 범위의 `qMap_total_fiber_one_level_eq`와 `normalizedWᵢ_eval_βᵢ_eq_1`로 그 계산을 짧게 닫는다. 이 원리는 0·1 중복 통합보다 큰 의무 삭제를 만든다.

이 후보의 최종 HB는 9,067,259 raw, 검증 범위는 4.31.0뿐이다. 같은 시행의 참조88 후보는 248토큰 / 6,215,475 raw HB이고 후처리 기록에는 240토큰 후보도 있다. **최근 수동 후보를 새 최적 기록으로 보고하면 잘못이다.** 다만 더 짧은 모든 후보의 추가 버전 검증이 이번에 완료됐다는 뜻도 아니다.

one-level lemma는 그 유료 시행에서 새 `retrieve` 호출보다 먼저 사용됐다. 검색이 그 lemma를 발견하게 했다는 인과 주장은 하지 않는다.

#### 6. P13–P15: 기존 아이디어의 정리 인터페이스·표현 압축

| 문제 | main에 이미 있는 핵심 | 후속 후보의 실제 변화 | 저장한 대표 후보 |
| --- | --- | --- | --- |
| P13 | 유한한 4개 연속항 상태 충돌 → 강한 귀납 → 주기 | `hprev` 보조정리·전달 인자 제거, 귀납가정으로 제한된 simplification | [187 T / 2,559,918 raw HB](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p13-structural.lean) |
| P14 | 여집합 짝 중 정확히 하나를 세어 절반 | `Set.Intersecting.is_max_iff_card_eq`에 연결하고 자연수 곱/거듭제곱 bridge만 처리 | [31 T / 969,083 raw HB](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p14-structural.lean) |
| P15 | 두 입력에 대한 자릿수 교체 합 항등식, 합산 불변식, Bézout 약분 | 관계에서 나눗셈 식까지 하나의 보조정리로 통합; `sum_erase_eq_sub`; 약분을 먼저 적용; certificate를 `rfl`로 닫음 | [181 T / 1,171,287 raw HB](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p15-structural.lean) |

이 3개 후속 후보는 **축소된 supplied Mathlib 문맥의 4.26.0**에서 검증됐다. 전체 benchmark header와 다른 지정 버전은 미검증이다. 이후 P15까지 독립 검토가 완료돼, 구조 후속 연구의160회·유효120개·4개 final과 비교 산출물 전체가 감사에 통과했다. [확정된 설계 인사이트](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/structural-insights.md)에 완료 근거와7가지 원칙을 추가했다.

P13은 귀납 내부의 불필요한 순서 가정 한 줄 제거로277,280 raw HB를 줄였다. P14의 직접 최대 교차집합 정리 경로는 후속 연구의55토큰 incumbent에 이미 있었으며,31토큰 최종 후보는 그 연결·정규화를 압축한 결과다. P15는32번에 `sum_erase_eq_sub`에 맞게 중간 표현을 다시 설계했고, 앞서 비용상 졌던 분리 구조도 후속 탐색에 활용했다.

fresh40과 구조 후속 시행은 같은 실험도 아니다. 예를 들어 fresh40 P13은 235토큰 / 3,012,079 HB, P15는 244토큰 / 1,366,707 HB다. 후속 시행의 더 짧은 표현을 fresh40의 독립 발견으로 소급하지 않는다.

#### 7. 길이·HB 절충과 실패에서 얻은 규칙

- **탐색 자동화를 닫힌 증명으로 정제:** `aesop?`·`simp?` 제안을 그대로 복사하면 길이가 늘 수 있다. P08의 아주 짧은 넓은 자동화 후보도 HB 때문에 손해였다.
- **묶음 변경:** P05의 정칙성 사실 공유는 단독 임계값에 못 미쳤지만, term-mode 인자와 `ContinuousLinearMap.sub_apply` 조합에서는 개선됐다. 한 단계 탐욕 수락이 조합 이득을 모두 찾지는 못한다.
- **명시 simp가 항상 이득은 아님:** P06의 두 simp를 동시에 명시 목록으로 바꾸면 422→452토큰, 환산 HB 11,133→10,762로 통과했지만 가중식상 손해였다.
- **고정 길이에서의 산술적 한계:** 현재 T가 정해졌다면 HB를 0으로 해도 `O ≥ T/T0`다. 이 값이 incumbent O 이상이면 그 길이로는 바로 이길 수 없다. 중간 구조 탐색까지 금지하는 근거는 아니다.
- **`floor.py`는 별도 휴리스틱:** `2k+3`은 이 문제의 최단 증명에 대한 수학적 하한 증명이 아니다. 위의 고정 T 산술 부등식과 혼동하지 않는다.

기법 선택은 “짧은 문법”, “싼 tactic” 하나로 고정하지 않는다. 내부 의무 삭제 → 기존 정리 인터페이스 → 표현 압축을 후보로 만들고, 같은 문맥에서 Length·HB·모든 지정 버전을 다시 확인한다.

## 원문: `docs/research/techniques-20261101/harness-techniques.md`

### 탐색·하네스·검증 기법

구현 경로는 원래 arena 체크아웃 기준이다. 이 문서 브랜치가 아래 모든 구현을 기본 패키지에 편입하는 것은 아니다. 경로별 존재·내용 비교는 [Git 감사](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/git-audit.json), 실제 시행 수치는 [실험 비교](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/experiments.md)에 있다.

#### 1. 이미 main에 있는 기반을 중복 구현하지 않기

| 기반 | 현재 상태 | 후속 실험과의 차이 |
| --- | --- | --- |
| preflight·오류 피드백·status/replay | PR #3 반영 | 장기 실패 기억과 SQLite 복구는 아님 |
| prepared 환경의 SHA 검증·stat cache | PR #33 반영 | 같은 파일 stat을 이용해 **내용 검증 작업**을 재사용. Lean 성공 판정을 재사용하는 기능이 아님 |
| usage/cost 통합 | PR #31·#34 반영 | 기록·비용 보고 기능과 발송 전 금융 예약·불확실 응답 처리 정책을 분리 |
| 예산 API runner·direct adapter·기본 golf·프로파일러 | PR #35 반영 | local v5 이후의 컨트롤러·검색·작업 큐까지 기본 탑재된 것은 아님 |

prepared cache는 opt-in이고 기본값은 full 검사다. 수정된 라이브러리·다른 compiler/pin을 검증 생략하는 허가가 아니다. 실험 보고 시간에 시작/종료의 전체 해시 비용을 포함했는지도 구분해야 한다.

#### 2. 공통 전략·구조화 계획: v5와 v6

v5 연구는 문제별 정답 힌트 없이 공통 지침과 원래 문제/허용 문맥을 주는 실험이다. 하지만 준비된 API 대조군 연구는 `deferred_after_user_scope_correction`, 비용 0으로 남아 있다. 실제 완료한 local-agent 40회 연구와 유료 API 연구를 같은 것으로 부르면 안 된다.

v6는 route 가설, 인용 근거, 2–8개 claim DAG, bridge, falsifier와 explore/refine/repair를 기록한다. exact/comment-only 반복을 거절하고 평가 예약·소스 해시·best/Pareto·최종 독립 검증을 장부로 연결한다.

**검증된 것은 최종 Lean 증명과 컨트롤러 계약이다.** 인용문 일치가 가설의 의미를 증명하지 않고, 완성 증명 검증이 각 claim DAG 노드를 독립적으로 증명하지 않는다. 경로 설명의 개수가 수학적 경로 다양성도 보장하지 않는다.

초기 v6의 두 번 실패 시 route quarantine, 여섯 번 정체 시 재고 힌트는 나중 v9에서 제거됐다. 모든 버전의 정책을 한꺼번에 쓰는 단일 완성 설계처럼 정리하지 않는다.

원래 구현: `experiments/common-v5-study-20261030/`, `structured-reasoning-20261030/`, `structured-openai-20261031/`. 모두 main 미반영이다.

#### 3. 상태와 외부 비용을 안전하게 이어가기: v7

`src/lean_agent/workflow.py`와 v7 실행기는 case/API call/Lean 관찰/실패 기억/해시 연결 이벤트를 SQLite 트랜잭션에 기록한다. FULL sync, Decimal 금액 문자열, case lock을 사용한다.

API 발송 의도와 응답 receipt를 외부 HTTP 실행 전후에 저장한다. 응답이 불확실한 요청은 예약 비용을 유지하고 차단하며, **자동 재발송하지 않는다**. 로컬 Lean 중단은 같은 immutable 후보·같은 평가 slot을 복구한다. 알려진 response receipt가 있으면 이를 조정하되 새 유료 호출로 바꾸지 않는다.

영구 진단은 metavariable 주소만 정규화하고 상수·타입·실패 표현을 유지한다. route를 바꿨다고 같은 실패를 잊지 않는다. 다만 v7의 top-eight 표시와 정체 임계값은 후속 연구에서 바뀐 정책이다.

오프라인 recovery/replay 근거가 있으며 main에는 해당 파일이 없다. 이후 실험에서 상태 머신을 계승했다는 것과 v7 단독 새 유료 실험의 효과가 검증됐다는 것은 별개다.

#### 4. workload를 줄인 빠른 모드: v8

중간 측정 1회, case별 golf 40 screen/180초, API 탐색과 golf 큐 분리로 컴파일 작업량을 줄였다. baseline/final은 3회 측정을 유지했다.

P10 파일럿에서 실행은 약 37분 29초였지만 과거보다 조건부 점수가 79.84→78.09로 낮아졌다. 과거 실행은 queueing/resumption을 포함하므로 wall ratio도 순수한 동일 품질 가속 실험이 아니다. **검증이 된 tradeoff 모드이며, 동일 품질의 가속으로 증명된 것은 아니다.**

후속 v9/v10은 중간 3회와 전체 golf를 복원했다. v8 cap을 v10의 상시 규칙으로 소급하지 않는다.

#### 5. 원래 범위의 완전한 타입·실행 경험: v9

소스의 첫 `:=`를 정리 본문 경계로 삼으면 P11처럼 결과 타입 안의 `let :=`에서 타입이 잘린다. compiler syntax의 실제 declaration-body span으로 본문만 제거해 타입과 타입 안의 proof term을 유지하는 파서가 필요했다.

v9는 원래 import 범위에서 canonical type/axiom을 조회하고, 이번 실행에서 검증된 변경을 소스 span·증명 해시와 연결해 기록·조합한다. helper import로만 보이는 이름을 솔버에게 노출하지 않는다. 관찰된 patch는 일반적 의미 보존 rewrite 정리가 아니므로 조합 후보도 Lean으로 검사한다.

shared source transformation은 `src/lean_agent/proof_experience.py`에 있다. 준비 입력·원래 prefix·compiler/project/index/helper 해시를 맞춰 다른 scope의 조회 결과가 섞이지 않게 한다.

하지만 완료된 유료 세 문제 연구는 작업 문맥 누락으로 같은 정보를 반복 조회했고, 비용의 76.74%가 inspection에 쓰였다. 40회 목표를 채우지 못했다. “타입 조회를 제공하면 점수가 개선된다”는 결론은 나오지 않았다.

#### 6. 바이트 보존 golf와 검증 선별·병렬화: v10

| 요소 | 구현한 보장 | 하지 않는 것 |
| --- | --- | --- |
| 소스 구간 편집 golf | 편집하지 않은 바이트·줄·문자열·주석 유지 | 재구성 과정에서 본문을 버린 옛 parser 사용 |
| LSP snapshot negative prefilter | 같은 immutable prefix에서 후보+suffix만 교체, version·diagnostic completion·nonce 확인 | 이전 후보 정리를 다음 후보가 사용하는 것 |
| fresh CLI admission | 완료된 실패만 선별에서 거절; pass/unknown은 새 CLI 검증 | LSP 성공만으로 후보 채택 |
| fresh final 측정 | plain check 후 독립 프로세스 3개 측정 | warm/LSP heartbeat로 순위 계산 |
| shared FIFO | 전역 compiler slot·owner lock으로 큐 관리; 죽은 ticket 복구 | 살아 있는 느린 compiler를 TTL만으로 만료 |
| 관찰 기억 | 검증된 원래-scope fact·현재 증명·최근 실패와 provenance 유지 | 마지막 몇 개 메시지 밖의 모든 사실 삭제 |

유료 P01/P10/P14 시행과 serial/parallel 동일 최종 소스의 후속 검증을 구분한다. 후속 병렬 검증은 validity·토큰이 같고 raw HB 차이가 −60/0/+13이었다. 단회 짝 관찰이므로 모든 환경에서 그 비율의 가속을 보장하지 않는다.

보수적인 UTF-8 byte 기반 입력 예약 때문에 실제 지출 한도가 남아도 다음 호출이 막히는 문제는 해결되지 않았다. v10도 세 문제 모두 40회 전에 중단됐다.

#### 7. 실제 검색 도구와 외부 예제: v11

`experiments/theorem-retrieval-20261101/`는 기존 이름 AND 검색의 빈 결과 문제를 다룬다. preceding declaration의 완전한 signature와 외부 소스에 FTS5/BM25를 적용하고 name/signature/source 순위를 RRF로 합친다.

`experiments/retrieval-harness-20261101/`는 이를 v10에 연결한다.

- `retrieve`: 이름·선행 선언 signature 검색.
- `type_search`: 원래-scope compiler 타입의 상수·결론 head·선언 종류·binder 수 필터. **타입 unification 검색은 아니다.**
- `external`, `external_source`, `external_refs`: OpenAI math의 참고 증명·소스 줄·사용 가능 이름 힌트.

외부 index는 `openai/math` commit `4eaee87548250b2682affda7d05d947c05554bae`의 **162,417개 OAI 모듈**을 대상으로 한다. target stub은 제외한다. 실제 대상 환경의 이름·타입·적용 가능성 검증을 대체하지 않는다. lexical reference는 검증된 의존 그래프가 아니다.

외부 working tree를 줄였어도 Git object와 index SHA가 남으면 고정 commit의 `git show`로 필요한 파일만 복원한다. lazy fetch를 금지하고 원래 SHA가 맞아야 materialize한다. byte가 바뀐 기존 파일을 덮어쓰지 않는다.

P11 실제 유료 시행에서 `retrieve`·`type_search`는 각각 1회 사용됐지만 external source 호출은 없었다. 외부 예제 검색의 점수 효과는 이 실행으로 입증되지 않았다. 검색 도구 구현과 성능 입증을 분리한다.

#### 8. 현재 후보군 경쟁과 구조 탐색

공통 피드백은 현재 champion 전체 소스, Length/HB frontier, 최근 유효 통계·실패 소스/진단, 고정 길이의 하한을 보여 준다. 상대 anchor는 표시값만 갱신하고 채택은 고정 목적식으로 한다.

독립 portfolio는 서로 격리된 scout 3개와 새 merger를 둔다. 40회 버전은 **6/6/6/22**이며, 18개 scout 평가 완료 전에 merger가 pool을 읽거나 평가할 수 없다. scout-a는 원본 proof를 숨기고 명제/타입에서 출발한다. 실패·수정도 credit을 쓴다.

이는 host와 지침에 의한 연구 입력 격리다. OS 수준 접근 차단으로 증명된 것은 아니다. 세 scout가 같은 큰 수학적 경로로 수렴한 P03처럼 독립 문맥이 구조적 다양성을 보장하지 않는다. backward·replace-block·distill·reencode는 모델 탐색 정책으로 시험했으며, AST 합성기나 전역 unification 엔진을 새로 구현한 것이 아니다.

후속 `competitive-structure-20261101`은 기존 best를 제공한 **incumbent-seeded continuation**이다. 독립 원본 출발 연구로 합산하거나, 새 구조를 전부 독립 재발견한 것으로 세지 않는다.

이 후속 연구는160회·유효120개·독립 final4개와 전체 오프라인 감사를 완료했다. [7가지 설계 인사이트](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/structural-insights.md)에 공개 분모와 경쟁 anchor의 분리, 문제별 교환비·손익분기점, API에 맞춘 중간 표현, 문맥 가정 비용, 비승리 구조 보존, 기존 구조 진단, 정체 시 재검색을 정리했다. 현재 packet에 이미 있는 Pareto·전체 이력·최근8개 통계·교환비와, 아직 일반 정책으로 구현하지 않은 구조 아카이브·자동 재검색은 구분한다.

#### 9. 작은 머신의 빌드 재사용과 저장 정책

`experiments/cached-verification/worker.py`는 기존 고정 compiler/library를 등록하고, 매 후보를 원본 파일 한 곳에 교체한 전체 모듈로 새 프로세스에서 검사한다. 새 Mathlib 복사본 대신 이미 있는 빌드를 연결한다. `#print axioms`로 허용 공리도 확인하지만 이 worker 경로 자체는 HB/공식 점수를 계산하지 않는다.

P01/P02/P04/P05/P06 로컬 batch 검증 근거가 있다. 이것은 REPL 성공 결과 재사용이나 공식 비공개 평가 worker의 복제품이 아니다. 새 pin에 native plugin·module 옵션이 있으면 별도 준비·검사가 필요하다. P11 구버전 준비에서 Loom plugin과 메모리 한도 문제가 실제로 확인됐다.

완료한 P11 4.29/4.30 전용 환경·빌드는 정리했고, 고정 소스와 빌드 로그/config archive·재현 코드는 남겼다. 기본 P06 4.32/P11 4.31 캐시는 유지했다. 재현 가능성은 모든 build 산출물을 영구 보관한다는 뜻이 아니다.

#### 10. 별도 커밋된 repair 연구

`origin/codex/verification-repair-*`의 설계·과거 실패 corpus 평가·bounded native recursive repair는 관련 있지만 다른 브랜치의 구현이다. main 미병합이며 이 문서가 합치지 않는다. v7의 장기 실패 기억이나 v9의 조회 기능 전체가 이미 그 브랜치에 편입됐다는 주장도 하지 않는다.

## 원문: `docs/research/techniques-20261101/structural-insights.md`

### 160회 구조 후속 탐색: 다음 설계에 반영할 것

기존 최선 후보에서 출발한 P06/P13/P14/P15 연구다. `gpt-6.1-sol / high`, 각40회·총160회 평가, **유효120개·실패40개**, 원본 역할의 fresh incumbent baseline4개와 최종 독립 재검증4개를 완료했다. [최종 독립 검토](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/structural-review.md)도 네 case와 비교 산출물 전체에 대해 통과했다.

첫 문서 커밋 `7752ec1`은 P15 검토가 끝나기 전 snapshot을 담았다. 이번 갱신은 최종 보고·비교·검토를 다시 읽어 그 상태를 완료로 바꾼 것이다. 아직 원본부터 출발한 독립 실험이 아니며, full official imports와 추가 Lean 버전 검증도 완료한 것은 아니다.

#### 1. 현재 후보군의 도전 기준과 점수 분모를 분리한다

이 연구가 공개 benchmark 분모로 계산한 비용은 다음과 같다.

```text
C(T, rawHB) = T / T0 + floor(rawHB / 1000) / published_H0
relative_cost = 100 * C(candidate) / C(epoch_anchor)
```

anchor는 현재 후보군에 맞춰 갱신하지만 **T0·published_H0는 고정**한다. 새로 측정한 로컬 원본 HB, 현재 champion HB, 원본 대비 개선율을 분모로 대체하면 Length/HB 가중치가 달라져 순위가 바뀔 수 있다. 과거 실험의 별도 로컬 정규화값도 이 연구의 공개 분모로 소급 교체하지 않는다.

| 문제 | 공개 T0 | 공개 H0, 환산 단위 | 토큰1개와 교환 가능한 raw HB 근사값 |
| --- | ---: | ---: | ---: |
| P06 | 1,217 | 42,225 | 34,696 |
| P13 | 1,769 | 111,476 | 63,016 |
| P14 | 1,754 | 134,499 | **76,681** |
| P15 | 4,085 | 14,130 | **3,459** |

교환비는 `1000 * published_H0 / T0`다. 실제 순위는 floor를 포함한 유리수 비용으로 정하고, 근사 교환비는 후보 설계 설명에 쓴다.

#### 2. Hard/soft route와 타입 명시를 일괄 정책으로 정하지 않는다

P14에서 토큰1개는 약7.7만 raw HB, P15에서는 약3.5천 raw HB와 교환된다. 같은 타입 명시·자동화·인자 생략도 문제에 따라 득실이 다르다.

P14의55→31토큰 변화는 raw HB가821,229→969,083으로 늘어도 비용을33.59% 줄였다. P15의 마지막34→39번 변화는186→181토큰과1,164,239→1,171,287 raw HB의 절충이었다. HB가 가장 작은 타입 명시를 무조건 선택하는 것보다 고정 비용이 낮았다.

다음 설계에서는 후보별 손익분기점을 같이 전달한다. 예를 들어 champion 비용이 `C*`, 새 후보 길이가 T라면, 이기기 위해 허용되는 환산 HB의 최대값은 다음과 같다.

```text
B = published_H0 * (C* - T/T0)
max_scaled_HB = ceil(B) - 1       # 엄격한 비용 개선 기준
```

B가0 이하이면 그 길이로는 HB가0이어도 바로 이길 수 없다. 다만 다른 구조를 발견하기 위한 중간 후보까지 자동으로 거절하는 규칙은 아니다. 현재 제어기는 교환비를 제공하지만 이 식의 후보별 설명을 일반 planner로 구현한 것은 아니다.

#### 3. 발견한 정리에 맞춰 중간 표현을 바꾼다

P15의 전환점은32번 시도의 `Finset.sum_erase_eq_sub` 적용이다. 교체한 한 항의 합을 `bᵢw + (D - aᵢw)`로 표현하자, 항별 합 비교와 별도 덧셈 정리를 단일 `simpa`로 대체할 수 있었다.32번은190토큰 /1,193,199 raw HB, 최종39번은181토큰 /1,171,287 raw HB다.

라이브러리 검색을 목표와 같은 정리를 찾는 데서 끝내지 않는다. 정리의 입력 형태와 결론이 **바로 적용되도록 중간 표현을 재설계**하고, 그때 사라지는 합 비교·분기·대수 bridge를 명시한다. main에도 자릿수 합 불변식과 Bézout 약분은 이미 있지만, 이 정리 인터페이스에 맞춘 압축은 아직 로컬 후보다.

#### 4. 불필요 가정도 측정할 비용이다

P13의28→36번 소스 차이는 귀납의 recurrence leaf에 `clear hij`를 넣은 한 줄이다. 길이는186→188토큰, raw HB는2,994,238→2,716,958로 **277,280 감소**했다. 두 offset의 산술 문제를 불필요한 순서 가정이 연결하던 비용을 줄인 사례다.

`hij : i < j`는 나중에 주기의 양수성을 보이는 데 필요하므로 바깥 문맥 전체에서 삭제한 것이 아니다. 사용 범위에 맞게 귀납 내부에서만 제거했다. “모든 가정 삭제”가 아니라 가정의 관련성과 자동화가 보는 문맥을 분석하고 측정하는 정책이 필요하다.

#### 5. 현재 승자가 아닌 구조도 보존한다

P15의3번 filter/erase 후보는244→213토큰으로 짧아졌지만 raw HB가1,366,707→1,540,787로 늘어 기존 최선을 이기지 못했다. 이를 폐기하지 않고 표현을 재설계해32번 이후의 짧은 erase-subtraction 경로와 최종 결과로 이어 갔다.

현재 제어기는 모든 후보와 메타데이터·실패를 장부에 보존하고 Pareto 후보도 제공한다. 그러나 **비용이 가까운 후보와 구조가 다른 후보를 별도로 선별하는 일반 구조 아카이브**까지 구현됐다는 뜻은 아니다. 다음 설계에서는 아래를 구분해서 유지하는 것이 좋다.

- 현재 최선과 Length/HB Pareto 후보.
- 비용이 가까운 후보와, 비용이 더 높아도 다른 중간 의무를 제거하는 후보.
- 실패로 확인한 타입·정규화·가정·사용 가능한 API 제약.

후보를 보관하는 것과 효과적인 재사용·조합 정책은 별개이며, 후자의 일반적 효과는 추가 검증이 필요하다.

#### 6. 기존 증명이 이미 좋은 구조인지 먼저 진단한다

P06은 incumbent의 쌍선형 기저 비교·공통 인수분해를 유지한 채 반복 정리와 추론을 줄인 후보가 이겼다. P14도 incumbent에 있던 최대 교차집합 정리를 유지하고 조건 정규화·마지막 연결만 줄였다. 대체 구조를 실제 검사했으나 승리하지 못했다.

따라서 매 새 route는 “새로워 보이는가”보다 **어떤 중간 증명 의무가 없어지는가, 목표로 돌아오는 bridge 비용은 얼마인가**를 명시하도록 한다. 큰 구조를 바꿔야 한다는 요청과 이미 좋은 구조를 일부러 버리는 정책을 동일시하지 않는다.

#### 7. 정체 시 라이브러리 재검색을 포함한다

P15 핵심 정리는 초기 조사에서 끝난 것이 아니라32번에 적용됐다. 이후 tactic 미세 수정만 반복하지 않도록, 정체 시 목표 표현과 라이브러리 API를 다시 조사하는 경로를 설계할 가치가 있다.32번이라는 시점이 최적의 재검색 주기라는 근거는 없다.

기록에는 실제 뒤늦은 소스 조사·정리 적용이 있다. 이를 자동으로 감지·실행하는 재검색 scheduler를 현재 코드에 이미 넣었다고 표시하지 않는다.

#### 공통 탐색 상태: 구현과 다음 권고

| 상태·정책 | 구조 탐색 제어기의 현재 상태 | 다음 설계에서 추가할 것 |
| --- | --- | --- |
| champion 소스·T·raw HB·공개 분모 비용 | 제공 | 후보별 손익분기점 설명 |
| Pareto와 전체 후보/실패·가설·부모 | 제공 | 근접 비용·구조 다양성을 별도로 선별·보존 |
| 최근 유효 후보 평균·중앙값 | 최근8개를 제공 | 창 크기의 효과를 비교 |
| 경쟁 anchor | 4평가마다 갱신 | 갱신 주기의 효과를 비교 |
| 문제별 토큰/HB 교환비 | 제공 | 후보의 구체적 손익과 연결 |
| 현재 비용의50% 목표 | 도전 목표, gate 아님 | 유효성·채택 조건과 계속 분리 |
| 라이브러리 재조사 | 실제 연구 과정에서 수행 | 정체 감지와 재검색 경로의 명시적 정책 |

8개·4회·50%가 최적이라는 증거는 없다. 입력·출발 후보·소스 조사·탐색 방식이 함께 달라졌으므로 개선을 경쟁형 프롬프트만의 인과 효과로 돌리지 않는다.

#### 최종 결과와 검증 범위

| 문제 | incumbent T / raw HB | 독립 최종 T / raw HB | 고정 비용 감소 |
| --- | ---: | ---: | ---: |
| P06 | 422 /11,133,579 | [409 /11,003,038](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p06-structural.lean) | 2.25% |
| P13 | 211 /4,156,941 | [187 /2,559,918](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p13-structural.lean) | 17.82% |
| P14 | 55 /821,229 | [31 /969,083](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p14-structural.lean) | 33.59% |
| P15 | 244 /1,366,707 | [181 /1,171,287](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/5fc7bffbcba22d1b8995fcccb3dd99d372d25e1a/docs/research/techniques-20261101/evidence/proofs/p15-structural.lean) | 18.68% |

새 독립 final의 중앙값을 사용한다. P13의 탐색 시2,559,919와 final2,559,918, P14의 탐색 시969,137과 final969,083은 별도 측정으로 유지한다.

같은 호환율과 나머지11문제가 그대로임을 가정한15문제 평균 증가량은 이번 incumbent 대비+0.185464, 참조88 대비+0.306707이다. 새 전체 제출본의 실측 점수나 최종 표시 점수는 아니다. 공개 축의 반올림 전후도 구분한다.

P06은4.32.0, P13/P14/P15는 축소 imports의4.26.0에서 검증했다. 공식 전체 header와 추가 버전은 미검증이다. 활성 서브에이전트 최대2개와 공통 잠금 아래 native Lean1개를 유지했으며, 그 잠금에 참여하지 않는 외부 작업은 이 보장의 대상이 아니었다.

이7점은 **문서와 다음 설계의 입력으로 반영**하며, main의 기본 하네스나 제출 후보에 구현·채택된 상태와는 구분한다.

## 원문: `docs/research/techniques-20261101/evidence/structural-review.md`

### Independent review — complete

**Pass.** All four cases and the generated comparison outputs pass this offline review. No blocking issue remains. No native Lean, model, network or installation calls were made by this reviewer. The central account check exited 0; Git configuration was unchanged. This review file is the reviewer's only written artifact.

The unchanged offline `audit_case` passed P06, P13, P14 and P15 after finalization. Each has exactly 40 reservations, 40 measurement starts, 40 completed evaluations, no inflight credit, one fresh baseline and one independent final check. Across the experiment there are **160 candidates: 120 valid, 40 invalid**, plus four baselines and four independent finals. Frozen inputs/runtime/compiler fingerprints, hash-chain replay, immutable candidate/final sources, raw source/log inventories, rendered contexts, prescribed compiler commands, plain checks, three heartbeat samples, medians, allowed axioms and proof-token replay passed. Independent rational arithmetic selected the same four winners.

| Case | Valid / invalid | Winner | Final T / raw HB | Cost reduction vs fresh incumbent | Unrounded conditional problem gain |
| --- | ---: | --- | ---: | ---: | ---: |
| P06 | 23 / 17 | attempt-25 | 409 / 11,003,038 | 2.254333% | +0.4586916583 |
| P13 | 35 / 5 | attempt-40 | 187 / 2,559,918 | 17.816363% | +0.9297646856 |
| P14 | 29 / 11 | attempt-30 | 31 / 969,083 | 33.588583% | +0.4194210111 |
| P15 | 33 / 7 | attempt-39 | 181 / 1,171,287 | 18.684058% | +0.9740900417 |

P15 final SHA256 is `ac5b1fadac0923a96cbce17eefa0d38625f3b35490b190e27821d7ec27277325`; its fresh samples are `[1171287, 1171281, 1171308]`. Its exact final cost is `1468213/11544210`.

All four published normalizer pairs match the pinned benchmark metadata at `56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c`; every snapshot-file hash matches. The complete frozen input manifest also matches. Archived reference88 sources and metrics for all four cases, and the distinct P13/P15 incumbent sources and metrics, match their cited archived source digests and evaluation records. P06/P14 start from reference88; P13/P15 start from stronger prior-search incumbents. These are incumbent-seeded continuations, not independent original starts. The archived reference88 same-case gains are respectively +0.4586916583, +1.3707525470, +0.4194210111 and +2.3517330333.

All 160 charged sources remain distinct after removing comments and whitespace. Every attempt has route, hypothesis, parent and expected-tradeoff metadata. Source and metadata samples support meaningful exploration: P06 span/list/output-map/free-algebra/pair-difference alternatives; P13 scalar/window/finite-range/real-transition alternatives; P14 explicit adapter/extension/division/direct-theorem alternatives; P15 sum decomposition/reverse-kernel/quotient-witness/modular-omega/factored-row/erase-subtraction alternatives. Repairs and normalization/tactic ablations have concrete recorded hypotheses. No padding evidence was found. P06's selected gain is an elaboration refinement of the incumbent structure, not a newly superior mathematical route. P15's winning erase-subtraction identity materially shortens the coordinate replacement argument.

Reviewed the unfrozen `compare_results.py` without editing it. Independent arithmetic checks every per-case cost, exact score, delta, reduction, selected rank, final digest, raw samples and rounded display in `comparison.json`, and checks completion/count/final evidence fields in `report.json`. Offline helper reproduction matches both JSON outputs and `comparison.md`; the Markdown numbers were also inspected. The `report.md` champion table retains search measurements (P13 raw HB 2,559,919; P14 969,137); `comparison.md/json` correctly report the authoritative fresh finals (2,559,918; 969,083). These measurements remain separately identified.

The helper uses exact rational `T/T0 + floor(rawHB/1000)/published_H0` ranking. Independently recomputed aggregate unrounded conditional 15-task mean gains are **+0.185464493111957** versus fresh incumbents and **+0.306706549980739** versus archived reference88. The corresponding rounded-axis contributions before final overall rounding are exactly **167/900 = +0.185555555555556** and **23/75 = +0.306666666666667**. Secondary displays use Python rounding of the two reduction axes followed by problem-score rounding; the aggregate uses rounded axes before final full-score rounding. The root inspected the official formula page and reported last-file commit `88057731673d44e231788e3e87a9c797d585042a`; this reviewer did not independently fetch that page.

All score gains are conditional on unchanged compatibility and unchanged other 11 cases. The full displayed two-decimal score change depends on the unchanged aggregate's rounding phase. The exact supplied local primary compiler/context is the verification scope; Putnam imports are narrowed, and additional versions/full official headers remain unverified. No measured full-submission score or exact displayed full total is claimed. The final comparison states these limitations accurately.
