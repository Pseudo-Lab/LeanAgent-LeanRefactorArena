# P10 추가 탐색 — 진행 중

목표는 원래 1463-token 증명의 fiber별 거리 상계를 짧고 낮은 HB의 증명으로 바꾸는 것이다. 최신257-token 후보는 지정4개 버전 검증을 통과했다. 공식 제출은 하지 않았다.

## 최신 상태 — 2026-10-28 제출용 인증

|구분|후보|Tokens|Raw HB|검증|
|---|---|---:|---:|---|
|현재 최선|range_explicit_direct_coe|257|3,160,359 중앙값|4.31 Check·독립 Audit·3회 HB; 4.30/4.29/4.28 Check·독립 Audit|
|이전 3회 재검증본|range_delay_explicit_bound|256|3,285,404 중앙값|4.31 Check·독립 Audit·3회 HB|

최선의 raw samples는 `[3160359, 3160366, 3160343]`이다. 4.31 원본 1463 tokens / 15,887,701 raw HB 중앙값을 기준으로 한 조건부 로컬 문제 점수는 **87.5138325430점**이다. 원본 대비 길이는82.4334%, HB는80.1081% 줄었다. 아래 단계별 탐색 수치는 당시 상태를 보존한 기록이다.

제출용 불변 사본과 증거 manifest는 `runs/portfolio-94/p10-export-20261028/candidate.lean`, `manifest.json`이다. 4.31 인증 receipt는 `p10-exclusive4-431/evaluations/manual-5eb60e8d21/result.json`; 추가 핀은 `compat/p10-257-export-430/result.json`, `compat/p10-257-export-429/result.json`이다. **4.28 의존성 복원과 전체 Check·독립 Audit도 통과했다.** receipt는 `compat/p10-257-export-428/result.json`이다. 지정 버전4개 모두 검증했고, HB3회 측정은4.31에만 해당한다. 공식 제출은 하지 않았다.

## 확인된 기준선

`runs/portfolio-94/p10-exclusive4-431`에서 전체 소스 커널 검사, 허용 공리 검사, 서로 다른 nonce의 동기 HB 측정 3회를 수행했다.

|증명|Tokens|Raw HB 중앙값|
|---|---:|---:|
|원본|1463|15,887,701|
|부모 에이전트의 `finish_exact_cast`|425|6,253,250|

425-token 증명은 HB가 0이 되어도 해당 문제 점수 상한이 약 90.32점이므로, 길이의 구조적 축약을 병행한다.

## 실험 방향

1. `Nat.sInf_mem`이 이미 반환한 subtype witness를 직접 분해한다. 기존 증명의 `∃ g ∈ C_i, ...`로 다시 포장했다가 풀던 단계를 없앤다.
2. 단사함수 구성 대신 불일치 집합을 `decode(B × Fin (2^steps))`로 덮는다. 집합 포함과 `Set.ncard_image_le`만 있으면 되고, decode의 injectivity 또는 모든 decode 결과의 불일치는 필요하지 않다.
3. 덮개의 quotient와 index witness를 metavariable로 두고, 기존 `is_fiber_iff_generates_quotient_point`의 결론에서 추론시킨다.
4. 자연수 산술을 먼저 끝내고 ENat 변환을 마지막으로 미룬다. 불필요한 타입 annotation, 반복 `omega`, 단일 단계 simplification을 별도 실험한다.

## 이미 발견한 제한

- 전체 원본 Check가 `-M1536`, `-M3072` 모두 Lean memory_exception으로 실패했다. 두 실패 root를 보존했다. 부모가 제공한 `search_exclusive4.py`로 `-M4096`, 전역 Lean 1개 실행을 강제한 뒤 원본과 seed가 정상 통과했다. OOM을 증명 실패로 분류하지 않는다.
- `Fin.castSucc`로 짧게 표현한 인덱스는 타입상 같은 값이어도 이 문맥에서 Submodule/Set, subtype/OracleFunction coercion 추론을 막았다. 원래 Fin literal을 사용하는 별도 후보로 분리했다. 이 결과를 모든 Fin.castSucc 사용에 대한 일반 결론으로 삼지 않는다.
- 직접 얻은 최소 witness의 등식은 `rw`가 `d_fw` 정의까지 자동으로 매칭하지 않았다. `change _ = d_fw at hg`로 타입을 먼저 맞추는 별도 후보를 준비했다. 최소 witness를 직접 사용하는 아이디어와 rewrite 입력 정규화를 구분한다.

## 재현 위치

- 후보: `experiments/portfolio-94/candidates/p10_agent/`
- 가변 탐색 순서: 같은 폴더의 `queue.json`
- 실행: `batch4.py`는 frozen `search_exclusive4.py`를 사용한다.
- 모든 성공·실패 기록: `runs/portfolio-94/p10-exclusive4-431/state.json`, `evaluations/*/result.json`, `Check.log`
- 메모리 제한 실패: `runs/portfolio-94/p10-agent-431`, `runs/portfolio-94/p10-agent3-431`

## 현재 탐색 결과 (4.31만; 최선은 3회 재검증)

- 직접 최소 witness + h3 타입 축약: 381 tokens / 5,787,664 raw HB.
- image 덮개: 343 tokens / 6,238,202 raw HB. 길이는 짧지만 381-token 후보보다 점수는 근소하게 낮다.
- `cover_minimum_finish`: 310 tokens / 5,431,779 raw HB. 원본 기준 문제 로컬 점수 약 81.54점. seed 대비 길이 약 27.1%, HB 약 13.1% 감소했다. 독립 3회 재측정 전이며 전체 핀 인증 결과는 아니다.

새 최소 witness 패턴은 `obtain ⟨⟨g', hmem⟩, _, hg⟩ : d_fw ∈ (_ : Set ℕ) := Nat.sInf_mem (Set.univ_nonempty.image _)`이다. 원하는 원소가 `d_fw`임을 먼저 주면 Lean이 `d_fw`의 정의에서 최소 집합과 함수를 추론한다. 별도 `C_i` 정의와 함수 본문 재기술을 제거할 수 있었다.

덮개의 두 witness를 생략하려면 기존 정리 적용까지 같은 `exact ⟨...⟩` 안에 두어야 했다. `refine`에서 `_`를 남기고 다음 tactic에서 채우려는 버전은 미해결 metavariable로 실패했다. **3회 재검증된 `range_lemma`: 296 tokens / 5,274,258 raw HB 중앙값.** 로컬 문제 점수는 약 82.19016점이다. `Finite.card_range_le`로 image/univ를 range로 바꾸고, 기존 `distFromCode_le_dist_to_mem`으로 수동 최소값 상계 구성을 대체했다. 전체 소스 Check와 공리 Audit을 통과했고, fresh nonce 3회 HB는 `[5,274,513, 5,274,258, 5,274,255]`로 재현됐다. 인증 결과와 원본은 `runs/portfolio-94/p10-exclusive4-431/checkpoint-best.json`, `.lean`에 있다. 이 결과는 Lean 4.31만 해당하며 전체 핀/공식 제출 검증은 아니다.

이후 조건부 산술 rewrite와 decoder inline을 측정한 결과는 아래에 이어진다. 메모리 압박 때문에 기존 전역 독점 lease를 유지하며 순차 평가한다.

## 하네스 프롬프트에 반영할 일반화

- 타입 annotation을 모두 지우는 전략보다, **정의의 결과가 알려진 작은 타입 anchor**를 먼저 준다. `d_fw ∈ (_ : Set ℕ)`처럼 원하는 최소값을 명시하면 큰 함수·집합 정의는 역으로 추론할 수 있다. 반대로 `rw` 입력에는 `change _ = d_fw at hg` 같은 정규화가 필요할 수 있다.
- 존재 witness가 기존 정리의 결론으로 결정되면, tuple 구성과 그 정리 적용을 **하나의 exact term**에 묶는다. tactic 경계를 지나기 전에 metavariable을 모두 풀 수 있게 한다.
- 단사함수와 전사 덮개를 모두 Pareto에 남긴다. 덮개 단독은 HB가 늘어 점수가 나빴지만, 최소 witness 축약과 합성한 뒤 최선이 됐다. 단일 변경의 순위만 보고 구조를 폐기하면 이 합성을 놓친다.
- API 검색은 lemma 이름의 예상 namespace에 한정하지 않는다. `Finite.card_range_le`는 `Nat.card_*`만 검색하면 놓치기 쉽다.

## 296-token 증명의 단계별 HB 진단

`diagnostics/range296-e72a82d5/result.json`은 phase marker를 넣은 탐색 전용 결과이며 후보 선택/점수에 쓰지 않는다. 독점 lease, -M4096에서 1회 수행했다.

|구간|계측 HB|
|---|---:|
|거리 let 정의|31,115|
|최소 witness|212,646|
|집합 크기 상계|1,839,452|
|자연수 산술|1,583,771|
|마지막 ENat 상계 연결|672,761|

집합 크기 상계와 산술이 계측 구간 비용의 약 79%다. 이전 seed의 witness 및 finish는 이미 크게 줄었으므로, 준비한 모든 ablation을 무작정 돌리기보다 decoder inline과 산술 rewrite/omega 문맥 축약을 먼저 평가한다. Marker 구간 합계와 공식 raw는 범위 및 계측 영향이 달라 일치하지 않는다.

## 조건부 산술 rewrite의 실제 개선

`range_conditional`이 전체 Check·공리 Audit·HB 1회 측정을 통과했다. **해당 단계의 탐색 최선은 262 tokens / 3,973,709 raw HB**, 로컬 문제 점수 85.69346점이다. 기존 296-token 3회 검증 후보 대비 HB가 약 24.7% 줄었다. 아직 새로운 후보의 3회 재검증은 하지 않았다.

핵심 산술은 다음과 같다.

```lean
simp (disch := omega) only [Nat.sub_mul, ← Nat.pow_add, Nat.mul_assoc,
  ← Nat.sub_add_comm, Nat.add_sub_add_right] at h3
```

두 긴 `show exponent equality by omega`를 직접 입력하는 대신, 조건부 표준 rewrite로 목표 모양을 맞추고 `omega`는 그 rewrite의 작은 전제만 해결하게 한다. 이는 단순 글자 축약이 아니라 정규화 및 재해석 비용도 낮추는 변화였다. 다음은 같은 산술을 유지한 decoder inline 250-token 후보다.

후속 확인에서 `range_conditional_clear`는269 tokens /3,922,168 HB로 통과했다. `omega`의 문맥을 `h_i_add_steps`만 남기는 방식은 HB를 약51.5k 줄였지만7-token 증가가 더 비싸서 점수 최선은262 후보를 유지한다. `range_inline_conditional` 250-token 초안은 qMap bound의 미확정 Fin 인덱스를 `omega`가 별도 변수로 처리하여 실패했다. 구조를 폐기하지 않고, 기존 typed bound lemma가 인덱스 추론을 유도하는253-token 수정안을 준비했다.

`range_inline_conditional_term`은253 tokens /3,992,337 raw HB(1회)로 통과하여 새로운 점수 최선이 됐다. 로컬 문제 점수 85.85943점이다.262 대비 HB18.6k 증가가 있었지만9-token 절약으로 더 유리하다. decoder의 예상 결과 타입으로 rate 인자를 추론시키고, bound는 기존 typed lemma를 사용해 Fin 인덱스가 tactic 실행 전에 결정되게 했다. 이253-token 후보를 새로운3회 checkpoint 대상으로 선택했다.

**253-token 3회 checkpoint 완료:** raw samples `[3,992,337, 3,992,301, 3,992,297]`, 중앙값3,992,301, 로컬 문제 점수85.859506점. 전체 Check·공리 Audit을 통과했다. 인증 결과는 `runs/portfolio-94/p10-exclusive4-431/checkpoint-conditional.json`, 정확한 후보는 `checkpoint-conditional.lean`에 있다. 원본 대비 길이82.71%, HB74.87% 감소다.4.31 단독 검증이며 다른 핀 검증은 부모 에이전트가 담당한다.

## 253-token 증명의 세부 진단과 다음 가설

`diagnostics/inline253-detail-af2a5363/result.json`의 주요 비용은 카드 표현 정규화510,926, 덮개 구성562,150, 카드 상계 계산602,380, 산술287,157, 최종 ENat 연결673,230이다. 산술은 기존1.58M에서287k로 줄었다. 최소값 등식 rewrite 자체는61,392여서 주된 병목이 아니었다. 따라서 이후에는 카드 표현 정규화·상계 연결을 작은 직접 증명항으로 재생하는 데 초점을 둔다.

카드 상계의 타입을 직접 추론시키는234-token 초안은 `Nat.card B`와 `B.ncard` 사이에서 `rw [hg]`가 패턴을 찾지 못했다. 등식을 `show Nat.card B = d_fw from hg`로 먼저 정규화하는240-token 수정안을 준비했다. 이는 앞서 최소값 witness에서 본 것과 같은 현상이다. 정의상 같은 표현이어도 rewrite 검색이 자동으로 정규화하는 범위와 명시적 타입검사의 범위는 다르다.

현재 `show_term` 진단으로 성공한 정규화 rw 및 카드 calc가 만든 실제 증명항을 조사한다. 출력과 계측은 모두 탐색 전용이며 선정 점수/제출물에 포함하지 않는다. local `classical` 제거 후보의 이름에 constructive가 있으나, 이 이름은 해당 tactic을 제거했다는 뜻이며 증명 전체가 choice-free라는 주장이 아니다.

## 최소값을 보존하지 않는 witness의 가능성

부모 제안에 따라 `sInf`보다 큰 threshold 아래의 witness를 직접 뽑는 API도 조사했다. 이 버전에는 일반 `exists_lt_of_csInf_lt`, `csInf_lt_iff`가 있다. 입력은 `2 * sInf S < N+1`이므로 단순히 `sInf S < N+1`에서 witness를 뽑으면 필요한2배 상계를 잃는다. `/2` 변환을 왕복하는 방법은 가능하지만 현재 witness+hg 비용이약274k이므로 우선순위를 낮췄다.

더 유망한 API는 well-founded order용 `Monotone.map_csInf`다(`Mathlib/Order/ConditionallyCompleteLattice/Basic.lean:540`). 자연수에 대해 `2 * sInf S = sInf ((2*·) '' S)`를 만들고 일반 strict-witness 정리를 쓰면 division 없이2배 상계를 보존할 수 있다. 중첩 image의 witness를 바로 분해하면 `d_fw`와 최소값 등식 `hg` 자체를 제거할 수 있다. 다만 monotonicity proof와 image 분해의 토큰비용이 있어 현재 카드/ENat 정규화 실험보다 후순위 가설로 남긴다. 아직 실제 측정 후보의 개선이라는 주장은 아니다.

## Rewrite 위치와 실제 증명항

`range_inline_delay_hg_typed`가254 tokens /3,484,447 HB로 통과했다. 앞의253-token 증명보다 HB가약508k 줄었다. 최소값 등식을 카드 상계의 시작에 적용하는 대신 마지막 숫자 등식에만 적용한 변화다. 최소값 rewrite 자체의 진단비용은61k였지만 전체 절약은 훨씬 컸다. 단계 비용을 고정 상수처럼 더하면 이런 문맥 상호작용을 놓친다.

표준 `show_term`은 생성 제안을 `addExactSuggestion(checkState)`에서 재검사하다 whnf의 기본200k HB 제한에 걸렸다. 증명 실패로 취급하지 않고 별도 진단 실패로 보존했다. 성공한 tactic의 결과 Expr만 `logInfo`로 읽는 탐색 전용 `inspectProof`는 같은 제한에서 정상 완료됐다(`diagnostics/inspect252-ba7eb039`).

실제 항에서 hammingDist 정규화는 큰 우변을 캡처한 `congrArg`와 `Eq.mpr`를3번 중첩했다. 최소값 등식을 늦춰 우변을 작은 `d_fw` 표현으로 유지하는 전략을 뒷받침한다. 또한 qMap의 Fin bound에 사용한 `omega`가 f, g', hmem까지 매개변수로 가진 보조 증명을 만들었다. `i.isLt.trans (Nat.lt_of_add_right_lt h_ℓ_add_R_rate)`로 재생하는 직접 bound 후보를 준비했다. 이 후보까지 비교한 후 라벨 기반 watcher가 최선3회 checkpoint를 저장한다.

`range_delay_noclassical`은 같은 후기 rewrite 구조에서 local `classical`만 제거하여253 tokens /3,422,224 HB로 통과했다. 현재 카드 상계의 타입 추론 분기는 단순 `simpa`가 Set membership 및 hammingDist를 정규화하지 못하거나 Fintype instance를 합성하지 못해 실패했다. 이런 실패는 작은 타입 연결의 문제로 분류하며 원래 덮개 구조의 반례가 아니다.

직접 Fin bound 후보는256 tokens /3,285,404 HB로 통과하여 다시 점수 최선이 됐다. local omega를 없앤 효과는 약136.8k HB이며, 3-token 비용보다 점수 이득이 크다. 이 후보로 기존 독립 평가기의3회 체크포인트를 진행한다. 이어지는 탐색은 `fast_probe.py`의 전체소스+동일 프로세스 공리 검사를 잠정 screen으로 사용하고, 선정된 승자만 기존 Check/독립 Audit/3회 측정으로 확정한다.

## 후속 탐색의 판단 기준

이 원본에서1 token 증가는 약10,860 raw HB 감소와 같은 점수 가치를 갖는다(`15,887,701 / 1463`). 따라서256-token 직접 bound는253-token 후보보다3 tokens 길지만136,820 HB를 줄여 유리하다. 최소 길이만 선택하거나 최소 HB만 선택하면 모두 현재의 점수 최선을 놓친다.

후속 가설은 다음 세 가지다. 결과가 나오기 전의 가설이며 검증 성공으로 읽으면 안 된다.

1. 카드 표현의 `rw`3회가 만든 `Eq.mpr/congrArg` 연쇄를 작은 등식의 `.trans`와 `.le.trans`로 직접 재생한다.
2. ENat의 `coe_mul`이 정의상 같은 항이라는 사실을 이용해 마지막 `exact_mod_cast`를 `ENat.coe_lt_coe.2`로 직접 재생한다.
3. Hamming 거리→범위 덮개→`Nat.card` 상계를 작은 일반형 local lemma로 먼저 증명한다. 추가 토큰 비용을 지불하더라도 실제 대상의 큰 타입·문맥을 반복 정규화하는 비용이 충분히 줄어드는지 확인한다.

**직접 bound 3회 체크포인트 완료:**256 tokens, raw samples [3285404, 3285412, 3285386], 중앙값3,285,404, 로컬 문제 점수87.274265점. 전체 Check·독립 공리 Audit·fresh nonce3회 측정이 모두 통과했다. 정확한 후보와 결과는 `checkpoint-cardinality.lean`, `checkpoint-cardinality.json`에 보존했다. 원본 대비 길이82.50%, HB79.32% 감소다.

## Fast screening 1차 결과

아래는 잠정 탐색이며, 독립 Check/Audit/3회 확정 결과를 대체하지 않는다.

|후보|Tokens|Raw HB|판단|
|---|---:|---:|---|
|range_infer_delta_forward_mem|241|3,666,878|통과했으나256-token 확정본보다 점수 낮음|
|range_exact_ncard_classical|240|채택 안 함|Decidable instance kernel typing 오류로 rc1; raw marker가 있어도 거부|
|range_delay_exact_normalize|254|3,427,069|통과했으나 직접 equality 재생만으로는 개선 없음|
|range_delay_direct_coe|254|3,296,997|ENat 직접 변환으로 동일 구조 대비 약125k 절약|

`exact_mod_cast`를 `ENat.coe_lt_coe.2 (Nat.lt_succ_of_le h3)`로 바꿀 수 있었다. 이 문맥의 곱셈 cast가 정의상 같은 항이므로 일반적인 cast 정규화 탐색을 반복할 필요가 없었다. 다음 실험은 모든 자연수 상계를 먼저 합성한 후 최종 결과에서 한 번만 ENat로 변환한다.

Finset→Fintype subtype→Nat.card 왕복의 대안도 준비했다. 불일치 집합을 처음부터 `↑(Finset.univ.filter ...)`로 덮고 `Set.ncard_coe_finset`으로 직접 크기를 연결한다. Decidable instance가 달라지는 정확한 실패를 통해 얻은 구조 가설이다.
