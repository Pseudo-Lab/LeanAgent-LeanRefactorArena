# 오프라인 구조 탐색

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

과거 P12 최선에서 출발해 소스 검색·구조 후보·변형·fresh 평가를 수행한다.

## 확인된 결과와 해석

P12 362→178토큰, primary raw HB 4,111,012→3,017,981. 같은178토큰 후보의4.29/4.30/4.31검증 기록. 이후156토큰 후속은 별도 기록이며 새 문제 일반화 평가가 아니다.

## 코드·Lean 보존 결정

사후 개발 결과·후속 기록을 보존. 전체 자동 범용 solver로 표현하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/offline-proof-search/INSIGHTS.ko.md` | `3ee67de` | `3074ce3584c7fa96066438712e796fa7492c8cd4e7d755467ef3a4c2611ea0a4` |
| `experiments/offline-proof-search/ROUND2.ko.md` | `3ee67de` | `8456acc3999b2cf1731567a915f92de2ce64b2e828a37d71ca852f4feab47856` |
| `experiments/offline-proof-search/validated/20261028/README.md` | `3ee67de` | `63deda74edaff107178d6f642eeb3026b72369686e2239dec6af9e789b9ffa52` |

## 원문: `experiments/offline-proof-search/INSIGHTS.ko.md`

### 로컬 탐색을 제출 비용과 분리한 첫 실험

2026-10-27. 기존 `exp/cost-hypothesis-pipeline` 브랜치에서 별도 실행 디렉터리로 진행했다. 기존 48후보 A/B 코호트는 변경하지 않았다. 이번 실험은 과거 P12 최선에서 출발한 개발 실험이며 새로운 문제에 대한 일반화 평가나 정책 A/B가 아니다.

**상태: 동일한 178토큰 코드의 필수 3개 버전 검증과 최종 기록 감사 완료.** [검증된 선언](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/validated/P12.lean), [결과·증거 manifest](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/validated/manifest.json), [원시 결과 JSON](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/runs/offline-proof-search/p12-20261027/RESULTS.json).

#### 결과와 구현

P12 `interleaved_affine_gaps_imply_tensor_gaps`에서 원문 statement와 전체 앞뒤 문맥을 유지했다. 길이와 HB를 정규화한 합으로 후보를 선택했고, 탐색 시간·실패 횟수는 점수 벌점으로 넣지 않았다.

| 주 환경 Lean 4.31 | 본문 토큰 | fresh raw HB 중앙값 | 대회 산식의 로컬 점수 |
|---|---:|---:|---:|
| 원본 | 1,353 | 9,713,453 | 33.33 |
| 과거 전 버전 최선 | 362 | 4,111,012 | 76.97 |
| 이번 선택 후보 | **178** | **3,017,981** | **85.26** |

최종 확인에서는 원본·과거 최선·선택 후보를 각각 세 번 다시 측정했다. 선택 후보의 표본은 `3,017,977 / 3,017,982 / 3,017,981`이다. 단일 탐색 측정 3,017,977을 확정 중앙값으로 그대로 복사하지 않았다.

기존 최선 대비 **Length 50.83%, HB 26.59% 추가 감소**, 문제 점수 **+8.2841점**이다. 다른 14개 문제를 고정하면 전체 평균 기여는 **+0.5523점**이다. 이전 82.15994점 추정표에 이 교체만 반영하면 **82.71221점**이지만, 이는 누적 로컬 추정이며 공식 제출 결과가 아니다.

| 필수 pin | 원본 raw 중앙값 | 같은 178토큰 후보 raw 중앙값 | 원본 대비 HB 감소 | 해당 pin 로컬 점수 |
|---|---:|---:|---:|---:|
| 4.31.0 | 9,713,453 | 3,017,981 | 68.93% | 85.26 |
| 4.30.0 | 9,709,094 | 3,059,437 | 68.49% | 85.11 |
| 4.29.0 | 10,931,172 | 3,506,778 | 67.92% | 84.92 |

각 pin은 원본과 후보의 plain compile, 별도 공리 검사, fresh 3회 측정을 마쳤다. 감소율의 분모를 다른 버전과 섞지 않았다. 누적 포트폴리오 추정에는 기존 방식과 같이 primary 4.31의 비율을 사용하며, 세 pin 점수의 평균으로 바꾸지 않는다.

현재 파이프라인에는 읽기 전용 소스 검색, 구조 후보 제출, 규칙/인자 변형, 전체 소스 검증과 측정, 후보 계보·Pareto 보존, 최종 반복 측정 및 기록 감사가 연결되어 있다. 구조 후보는 이번 세션의 agent가 소스와 측정 결과를 읽어 작성했고, 반복 변형과 검증은 CLI로 실행했다. 완전 자동 LLM 실행기나 모든 문제에 대응하는 범용 adapter를 구현했다고 주장하지 않는다.

#### 실제로 효과가 있었던 변화

##### 1. 재작성의 순서를 바꾸어 중간 증명을 없앴다

기존 362토큰 후보는 확률을 먼저 분해한 뒤 `Fin.snoc`으로 함수를 복원하고, 별도의 `he` 등식을 증명해 다시 확률 가설을 바꿨다. 재귀식을 먼저 적용하고 확률을 나중에 분해하면 이 중간 등식과 복원 단계를 없앨 수 있었다.

첫 265토큰 초안은 실패했다. rewrite가 `WordStack`과 `Word`, `Fin.init`의 표현 차이를 기본 투명도에서 맞추지 못했다. 해당 경계만 `erw`로 바꾼 후보는 265토큰·3,556,461 raw로 통과했다. 실패한 초안의 길이는 성능 성과로 세지 않았다.

독립적인 중간 등식을 직접 rewrite로 바꾼 보수적인 대안도 320토큰·3,999,005 raw로 통과했다. 따라서 더 짧은 구조가 실패해도 유효한 대안을 잃지 않고 다음 수리의 출발점으로 둘 수 있었다.

##### 2. 라이브러리에 이미 정의된 확률 술어를 재사용했다

검색한 원문에 `multilinearCombine_affineComb_split_last_close`가 이미 있었다. 새로 긴 lambda를 작성하고 `U`를 도입하는 대신 이 정의를 `prob_split_last_uniform_sampling_of_finFun`의 인자로 전달했다. 226토큰·3,015,668 raw 후보가 나왔다.

이 변화는 단순한 글자 축약이 아니다. 이미 타입이 정해진 정의를 다음 정리의 인터페이스로 사용하여 같은 표현을 다시 구성하는 부분을 줄였다. 다만 Lean 내부의 특정 함수별 할당량을 단독 계측한 결과는 아니므로 그 내부 원인까지 확정하지 않는다.

새 helper를 target 밖에 추가하지 않았다. 사용하는 정의는 원래 문맥에 존재하며, 제출 대상 외의 원문은 그대로 보존했다.

##### 3. 전달하는 정보와 그 정보의 표기를 구분했다

알고 있는 explicit 인자를 `(이름 := 값)`으로 반복 표기하던 부분을, 정리의 binder 순서를 확인한 뒤 위치 인자로 전달했다. 이 단계는 **216→188토큰**, raw는 3,015,070→3,014,884였다. 같은 인자를 계속 전달하면서 표기의 토큰 수를 줄인 사례다. 최종 proof Expr의 byte 동일성까지 검사한 것은 아니다.

이어 결론과 이미 전달한 인자에서 복원할 수 있는 차원·ε 표기를 생략해 178토큰이 됐다. HB는 소폭 늘었지만 토큰 절감이 더 커서 종합점수는 좋아졌다. 이름 자체를 짧게 바꾸는 것과 named argument 구문의 토큰을 줄이는 것은 구분해야 한다.

다음 자동 변형 후보는 **선언 타입으로 binder 순서를 확인한 후 named explicit argument를 positional argument로 바꾸기**다. 이번에는 확인한 세 선언에 대해 agent가 변형했고, 임의 Lean 문법을 대상으로 안전하게 변환하는 일반 도구까지 만든 것은 아니다.

#### 역효과도 선택에 반영했다

- 첫 자동 규칙 삭제 8개는 모두 컴파일에 실패했다. 현재 증명 표현에서는 해당 삭제만으로 대체할 수 없었다는 결과다. 다른 구조에서도 그 규칙이 반드시 필요하다는 뜻은 아니다.
- 인자 삭제 14개 중 11개가 컴파일됐고 4개가 당시 best를 갱신했다. 나머지 유효 후보도 기록했다. 같은 인자의 삭제가 다른 부모에서 다시 시험된 경우도 포함한다.
- 한 변경은 5토큰을 줄였지만 HB를 약 7.9만 늘려 채택하지 않았다. “더 짧으면 좋다”는 선택이었다면 회귀했을 것이다.
- 확률 가설을 전체 rewrite하는 대신 등식·부등식을 직접 연결한 후보는 HB가 조금 줄었지만 길이가 늘어 종합 최선을 넘지 못했다. 직접 term 전달도 언제나 유리한 규칙은 아니다.
- `simp_rw`를 `simp only`로 바꾸는 작은 변화는 한 토큰을 늘리면서 HB를 줄였다. 그 변경은 점수상 유리했으며 구조 변경과 결합한 후보를 별도로 측정했다.

최종 채택에는 원본 대비 정규화한 두 비용을 사용했다. 탐색 시간은 목적함수에 없다. HB 전용 최선과 종합점수 최선이 다르면 둘을 보존하고 최종 제출은 종합점수로 결정한다.

#### 계측 도구의 비용도 확인했다

처음에는 경계마다 `run_tac` 안의 계측 코드를 elaboration했다. 265토큰 후보의 계측된 target HB가 7,914,711로 크게 늘어, 이 수치를 원래 구간 비용처럼 사용하지 않았다.

계측 tactic을 한 번 정의한 뒤 경계에서는 그 tactic만 호출하도록 바꾸자 전체 target 관측값은 3,557,974였다. 비계측 3,556,461과의 차이는 1,513 raw, 약 0.043%다. 이 비교도 구간 진단용이며 최종 성능 표에는 비계측 후보의 반복 측정만 사용했다.

가벼운 진단에서 기본 차원의 확률 변환과 귀납 단계의 확률 분해 구간이 다음 탐색 대상으로 드러났다. 이 정보를 바탕으로 직접 등식 연결과 기존 확률 술어 재사용을 시험했다. 둘 중 전자는 종합 최선을 넘지 못했고 후자는 큰 길이/HB 개선으로 이어졌다.

#### 검증 범위와 재현

- 원본·시작 후보를 fresh 3회 확인한 뒤 탐색했다. 탐색 후보는 유효할 때 1회 측정하고 최종 선택은 별도 3회 측정으로 확인했다.
- 전체 소스 plain compile, 별도 target 공리 검사, target 사전 부재/사후 존재 검사, 동기 계측, fresh nonce를 사용했다. 허용 공리는 `propext`, `Classical.choice`, `Quot.sound`다.
- `audit.py`는 저장된 소스와 로그 SHA, 원문 문맥 복원, nonce 중복 여부, raw 표본과 중앙값, 공리 결과를 다시 확인한다. 탐색 중 감사는 진행 중인 receipt가 있어 `passed=false`였고 최종 감사와 구분한다.
- 읽기 전용 검색은 원래 target prefix와 import 관계의 3,386개 소스를 다뤘다. 설치된 일부 core 소스가 없어 182개 unresolved module도 기록했다. 이 검색기는 Lean export/type checker가 아니며 실제 정리 가용성은 후보 컴파일로 확인했다.
- 교차 버전용으로 압축 보관 중이던 4.30·4.29 runtime을 기존 복원 도구로 복구했다. archive와 파일별 SHA를 검증하고 이전 저장 receipt도 이번 실행 폴더에 복사해 보존했다.
- 기존 A/B 코호트, 원래 source, 다른 문제의 후보는 수정하지 않았다. 공식 제출·커밋·별도 유료 API 호출은 하지 않았다.

원본·시작 후보를 제외한 탐색 후보는 **34개**, 유효 후보는 **22개**다. 구조·표현 후보 12개 중 11개, 규칙 삭제 8개 중 0개, 인자 삭제 14개 중 11개가 통과했다. 실패도 보존했다. 최종 감사 대상 receipt는 세 pin 합계 43개이며, fresh 측정 nonce 49개가 중복 없이 확인됐다. 이 수치에 별도 구간 진단 두 실행의 결과를 성능 표본으로 더하지 않았다.

실행법은 [README](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/README.md), solver 역할과 선택 규칙은 [SOLVER_PROMPT](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/SOLVER_PROMPT.ko.md)에 있다. 원시 기록은 `runs/offline-proof-search/p12-20261027/`에 저장했다. 호출당 `--steps`는 실행 묶음 크기이며 전체 탐색 예산이 아니다. 이번 확인 후보를 보존한 채 이후 검색과 새로운 구조 후보를 추가할 수 있다.

이 실험은 새로운 전략으로 P12의 기존 최선을 개선한 사례다. 전체 15문제의 공식 점수가 85점이라는 뜻도, 94점 목표를 달성했다는 뜻도 아니다. 모든 문제에서 같은 개선률이 날 것이라는 추정에도 사용하지 않는다.

## 원문: `experiments/offline-proof-search/ROUND2.ko.md`

### 두 번째 지속형 탐색: 반복 단순화와 설정 표기의 비용

2026-10-28, `exp/cost-hypothesis-pipeline`. **동일 코드의 필수 세 버전 검증과 기록 감사 완료.** [새 검증본](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/validated/20261028/P12.lean), [manifest](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/validated/20261028/manifest.json), [원시 확정 결과](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/runs/offline-proof-search/p12-20261028/RESULTS.json).

#### 결과부터 보기

P12 `interleaved_affine_gaps_imply_tensor_gaps`를 앞선 178토큰 검증본에서 이어서 줄였다. 원문 statement·전체 prefix/omit/suffix는 그대로다. 공식 제출이나 커밋은 하지 않았다.

| Lean 4.31 확인 측정 | 본문 토큰 | raw HB 중앙값 | 대회 산식의 로컬 점수 |
|---|---:|---:|---:|
| 원본 | 1,353 | 9,713,453 | 33.33 |
| 직전 검증본 | 178 | 3,017,981 | 85.2580 |
| 이번 검증본 | **156** | **2,805,356** | **86.5296** |

직전 대비 **길이 12.36%, HB 7.05% 추가 감소**, P12 점수 **+1.2717점**이다. 원본 대비 길이는 88.47% 감소했다. 이번 primary 최종 표본은 `[2805352, 2805357, 2805356]`다.

다른 14문제를 고정하면 전체 평균 기여는 **+0.08478점**이다. 이전 누적 로컬 추정 82.71221에 이 교체만 반영하면 **82.79699점**이다. 86점대 수치는 P12 한 문제의 로컬 점수이며 전체 공식 LB 점수가 아니다. 이번 결과로 94점 달성을 주장하지 않는다.

| 필수 pin | 토큰 | 후보 raw 중앙값 | 원본 대비 HB 감소 | 해당 pin 로컬 점수 |
|---|---:|---:|---:|---:|
| 4.31.0 | 156 | 2,805,356 | 71.12% | 86.5296 |
| v4.30.0 | 156 | 2,845,446 | 70.69% | 86.3877 |
| v4.29.0 | 156 | 3,317,516 | 69.65% | 86.0403 |

각 pin의 원본을 같은 환경에서 측정한 분모를 사용했다. 같은 코드 SHA로 plain compile, 별도 공리 검사, fresh 3회 측정을 마쳤다. 허용 공리는 `propext`, `Classical.choice`, `Quot.sound`다.

#### 어떤 실험이 효과가 있었나

1. **두 번의 단순화를 한 번으로 합쳤다.** 기본 차원의 `simp_rw` 두 개를 `simp only` 하나로 합친 단일 변경에서 178→175토큰, 3,017,981→2,873,123 raw를 얻었다. 같은 표현을 다시 순회하는 작업을 줄였다는 해석과 일치하지만 내부 호출별 프로파일링으로 원인을 확정한 것은 아니다.
2. **증명의 논리는 유지하면서 구조를 짧게 했다.** `intro` 후 `induction` 대신 목표에 `Nat.le_induction`을 직접 적용하고, 중간 `hc`를 실제 사용 위치로 옮겼다. 불필요한 `classical`과 연속 `intro`도 정리했다. 이 변경들을 결합한 152토큰 후보는 2,864,007 raw로 통과했다.
3. **정보 삭제와 표기 축약을 구분했다.** 확률 변환·확률 비교 정리에 필요한 술어와 증거를 계속 전달하면서 named argument를 positional argument로 바꿨다. 반대로 술어를 전부 추론시키는 형태는 실패했다.
4. **반복이 필요 없는 구간에서 `singlePass`를 썼다.** 같은 두 구간에 긴 `(config := { singlePass := true })`를 적용한 후보는 170토큰·2,820,106 raw였다. 짧은 `+singlePass` 문법은 156토큰·2,805,352 raw였다. 같은 의도의 설정이라도 표기를 처리하는 비용이 달라질 수 있다는 사례다. 최종 측정은 위 표의 별도 반복 측정값이다.
5. **단독으로 최선이 아닌 변경도 결합했다.** 귀납법 시작 부분의 11토큰 축약은 당시 단독 best가 아니었지만 최종 결합에 기여했다. 후보 전체 순위가 낮다는 이유로 그 후보의 모든 편집 요소를 버리면 놓칠 수 있다. 이번 결합은 agent가 작성했으며 범용 자동 crossover 구현이라고 주장하지 않는다.

#### 무엇이 안 됐나

- `apply` 연쇄를 완성된 term으로 바꾼 첫 초안은 일반화된 explicit `C` 인자를 빠뜨려 실패했다. 인자 순서를 수리한 뒤에는 186토큰·3,025,609 raw로 통과했지만 기존 연쇄보다 비쌌다. 수리한 두 `refine` 후보도 개선하지 못했다.
- 재작성 정리의 타입·대상을 더 명시한 후보, 코드 집합 타입을 더 명시한 후보 모두 종합 개선이 없었다. 타입 힌트를 많이 넣는 것은 보편적 최적화 규칙이 아니다.
- 목표를 먼저 제시한 `simpa`는 자연수/NNReal/ENNReal cast 표현 때문에 처음 실패했다. `ENNReal.coe_natCast`를 보충한 173토큰·2,887,058 raw 후보는 통과했지만 최선을 넘지 못했다.
- 같은 결합 구조에서 함수 동일성을 `fin_cases`로 증명하면 156토큰·3,021,155 raw, 기존 equivalence 증거를 쓰면 154토큰·2,866,727 raw였다. 두 원소 경우분석조차 준비된 증거 재사용보다 비쌀 수 있다. `Fin.forall_fin_two` 직접 전달도 이 경우 더 좋지 않았다.
- 정의 축약을 끄는 `dsimp := false`, `zeta := false` 설정은 개선하지 못했다. 설정은 각각 분리해 시험해야 한다.

귀납 단계만 `+singlePass`를 사용한 154토큰·2,819,782 raw 대안도 남겼다. 156토큰 후보와 탐색상 종합점수 차이는 **0.001점 미만**이다. 큰 우열로 해석하지 않으며 이번에는 HB가 더 낮은 156토큰 코드를 전 버전 검증했다. 154토큰 대안은 primary 탐색 결과이고 별도 all-pin 인증본이 아니다.

#### HB를 어디까지 줄일 수 있나

전체 명령 시작/본문 진입/완료를 따로 관측했다. 178토큰 시작 후보 진단에서 본문 진입 전 차이는 **1,191,603 raw**, 전체 계측값은 3,017,323 raw였다. 본문을 고쳐도 선언 처리 비용이 같이 줄어들지는 않을 수 있다는 단서다.

이 값은 **현재 선언·환경·계측에서의 관측치**이며 모든 proof나 공식 worker의 엄밀한 하한이 아니다. 계측된 전체값도 비계측 중앙값 3,017,981과 다르므로 최종 성과 수치에 넣지 않았다. marker 자체와 평가 경계의 영향이 있으므로 구간값을 공식 HB에서 빼서 보고하지 않는다.

원본 분모에서 토큰 하나의 점수 효과는 약 **7,179 raw HB**와 같다. 길이를 더 쓰는 설정이 그 이상의 HB를 줄이는지 판단할 수 있다. HB에만 집중하기보다, 선언 처리 비용·본문 비용·토큰 교환비를 함께 보고 다음 편집을 정하는 것이 좋다.

#### 기록과 다음 입력에 적용할 것

탐색 후보는 **42개**, 통과는 **32개**다. 원본·시작 후보, 확인 반복 측정, 진단 실행은 탐색 후보 수에서 제외했다. [모든 후보 표](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/ROUND2-CANDIDATES.ko.md)와 [실행 상태](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/runs/offline-proof-search/p12-20261028/state.json)에 실패도 보존했다.

원문 검색은 원래 target 앞부분과 import 관계만 사용했고 일부 미설치 core 소스는 검색 범위에 없었다. 검색 실패를 정리 부재 증거로 사용하지 않았다. 진단은 `diagnostic-seed/`, `diagnostic-boundaries/`에 별도로 저장했다. 실행 코드는 고정 지문으로 검증했고 새 후보를 이전 인증 결과에 섞지 않았다.

이번 인사이트를 [solver 지침](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/SOLVER_PROMPT.ko.md)에 반영했다. 다음 입력에서도 반복 단순화 합치기, recursor 직접 적용, 필요한 인자를 유지한 짧은 표기, 국소적인 `singlePass`, 명령/본문 비용 분리, 편집 요소 결합을 후보군으로 삼되 실제 컴파일과 측정으로 선택한다. P12에서의 결과를 새 문제의 보장된 개선률로 일반화하지 않는다.

앞선 [178토큰 검증본](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/offline-proof-search/validated/P12.lean)과 [첫 라운드 문서](offline-proof-search.md)는 그대로 보존했다. 기존 A/B 코호트도 변경하지 않았다. 검색 공간 전체를 소진한 것은 아니며, 이번 파일들은 다음 탐색의 재현 가능한 checkpoint다.

## 원문: `experiments/offline-proof-search/validated/20261028/README.md`

### 2026-10-28 검증된 P12 후보

P12.lean은 원래 전체 소스의 선언 교체 조각이며 독립 모듈이 아니다. 원래 imports/prefix/omit/suffix를 유지한다.

같은 코드 SHA로 Lean 4.31·4.30·4.29의 전체 소스 컴파일, 별도 공리 검사, 각 3회 fresh 측정과 증거 감사를 완료했다. manifest.json에 원시 기록과 지문을 연결했다. 공식 제출·커밋은 하지 않았다. 상위 폴더의 178토큰 과거 검증본도 그대로 보존했다.
