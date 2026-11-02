# P11 병렬 에이전트 실험 — 2026-10-28

진행 중. 공식 제출 결과가 아니며, 아직 새 후보의 지정 버전 교차 검증을 수행하지 않았다.

## 재개 지점과 실험 경계

- 목표: `fold_advances_evaluation_poly`의 Length/HB 동시 감소.
- 시작 후보: `candidates/p11/qmap_rw.lean` (430 tokens / 기존 단일 탐색 7,496,578 raw HB).
- 원본: 1,906 tokens / 기존 측정 45,492,117 raw HB.
- 소유 후보: `candidates/p11_agent/`. 다른 에이전트·기존 인증 파일을 수정하지 않는다.
- 새 runner는 전역 Lean 슬롯을 공유하고, 후보마다 전체 소스 plain compile, 공리 검사, 별도 동기 HB 측정을 수행한다.

## 메모리 한도 확인

1. `runs/portfolio-94/p11-agent-431`: `search_agents.py`의 `-M1536`에서 원본 plain compilation이 Lean `memory_exception`으로 실패했다. 원본이 틀린 것으로 취급하지 않는다.
2. `runs/portfolio-94/p11-agent3-431`: 승인된 `search_agents3.py`의 `-M3072`에서 원본 plain compilation(약 28.9초)과 공리 검사는 통과했지만, 원본 `Measure1`이 같은 예외로 실패했다.
3. 두 실패 기록은 보존했다. 초기화 완료를 기다리던 배치 프로세스는 중단했다. 임의로 무제한 Lean을 실행하거나 메모리 상한을 올리지 않았다.

## 준비한 구조 실험

- `fiber_simp_qmap`: fiber 양 끝점을 각각 등식으로 만들어 `congrArg₂`로 결합하던 부분을 한 번의 명시적 `simp only`로 대체.
- `no_first_calc`: 긴 첫 `calc` 중간식을 제거하고, 목표에서 직접 평가 다항식 분해 정리를 적용.
- `final_simp_ac`: 마지막 합의 항마다 `ring1`을 호출하는 대신 분배법칙과 교환·결합법칙으로 정규화.
- `fiber_add`: `x₁ - x₀ = 1` 대신 이후 치환에 직접 필요한 `x₁ = 1 + x₀`를 증명해 중간 변환을 제거.
- qMap 등식의 `apply Eq.symm`·`rw`·`simpa` 표현과 simp 단계 합성도 비교할 예정.

후보 파일의 존재만으로 개선이나 성공을 주장하지 않는다. 실제 검증 결과와 반복 측정은 아래에 추가한다.

## 직렬 4 GiB 실행 재개

부모 에이전트가 제공한 `search_exclusive4.py`로 `runs/portfolio-94/p11-exclusive4-431`을 새로 만들었다. 모든 Lean 호출은 공유 슬롯 두 개를 함께 점유하여 다른 Lean과 동시에 실행하지 않는다.

- 원본: 1,906 tokens, raw `[45,491,359, 45,492,117, 45,493,439]`, 중앙값 **45,492,117**. 기존 중앙값과 같다.
- 시작 후보: 430 tokens, 독립 3회 중앙값 **7,496,561**.
- `fiber_simp_qmap`: **400 tokens / 7,236,524 raw**, 전체 소스·공리 검사·독립 계측 1회 통과. 확정 교차 버전 후보로 아직 승격하지 않았다.
- `no_first_calc`: 349 tokens, plain compilation 통과, 나머지 검증 진행 중.

첫 개선은 fiber 양 끝점 등식을 각각 생성하고 `congrArg₂`로 빼는 과정을 한 번의 명시적 `simp only`로 대체한 것이다. 자동화 범위를 키우지 않고 이미 필요한 정리와 인자를 지정하여 길이와 HB를 함께 줄였다.

## 구조 개선과 실패의 원인

현재 탐색 최선은 `fiber_add_explicit_positional.lean`: **306 tokens / 6,946,575 raw**, 로컬 추정 **89.5585307075점**이다. 원본과 시작 후보는 각각 3회 검증했고 이 새 최선은 아직 1회 탐색값이다. 5개 추가 후보 후 같은 최선을 독립 3회 확인하는 checkpoint를 별도로 진행한다.

- `no_first_calc`: **349 / 7,148,371**. 긴 `calc` 중간식을 따로 작성하지 않고 원래 목표에 `simp only`로 분해식을 적용했다. 길이와 HB 모두 감소했다.
- fiber 관계를 `x₁ - x₀ = 1` 대신 이후 대입에 필요한 `x₁ = 1 + x₀`로 바로 증명했다. `sub_eq_iff_eq_add`를 통한 재변환을 없앴다.
- `qMap_total_fiber`의 인자를 positional로 전달하여 불필요한 이름·괄호를 줄였다.
- `final_simp_ac` / `no_first_calc_simp_ac`는 실패했다. `mul_comm`을 같은 simp 단계에 넣자 **다항식 곱** `C a * p`가 `p * C a`로 먼저 바뀌어 `Polynomial.eval_C_mul`과 이후 합 분배가 적용되지 않았다. scalar 정규화는 평가·합 변환 후 별도 단계로 분리하는 후보를 준비했다.
- 실패한 AC 변형을 물려받은 미실행 파일은 검증된 `ring1` 말단으로 수리했다. 수리 전 텍스트는 각 `.lean.before_ac_repair.txt`에 보존했으며, 이미 실행했거나 실행 중인 후보는 수정하지 않았다.

## HB 구간 진단

`diagnostics/p11-phases-cb2d02cb`는 306-token 후보에 관찰용 마커를 삽입한 별도 실행이다. **후보 지표·점수에 넣지 않는다.** 부모의 승인된 `search_exclusive4.execute`로 동일한 메모리 상한과 전역 슬롯을 사용했다.

| 본문 구간 | 진단 raw HB |
|---|---:|
| 도입·fiberMap 정의 | 130,323 |
| qMap 평가 증거 | 438,724 |
| fiber 두 점의 관계 | 1,314,839 |
| 다항식 이름·분해 정리 준비 | 44,405 |
| 분해식 대입·평가 | 416,764 |
| 주 대수식 정리 | 585,987 |
| 마지막 합·계수 선형성 | 878,243 |

본문 구간 합은 3,809,285이고 전체 진단 raw는 6,947,203이다. 차이 약 3,137,918은 본문 전후의 선언 처리·검사 등을 합한 값이다. 아직 전후를 분리하지 않았고, 고정 비용 하한이나 공식 worker 비용으로 단정하지 않는다. 본문 안에서 가장 큰 비용은 `ring1`보다 **fiber 관계의 증명**이다.

## Checkpoint: 새 최선 독립 3회 통과

`runs/portfolio-94/p11-exclusive4-431/checkpoint.json`에 306-token 후보의 독립 확인을 저장했다.

- raw samples: **6,946,575 / 6,946,581 / 6,946,606**
- 중앙값: **6,946,581**
- 원본 중앙값 대비 로컬 추정 점수: **89.5585263111**
- 선언 SHA256: `7f171e769c13f4781d523fad4eadcc4dc6067ed4af57741ef569953f767ee369`
- 증명: `runs/portfolio-94/p11-exclusive4-431/checkpoint.lean`
- 세 차례 모두 동일한 pinned Lean 4.31 환경에서 full compilation 및 공리 검사 후 측정했다. 부모 에이전트가 Lean 4.30 / 4.29에서도 전체 소스와 공리 검사를 완료하여 지정 버전 **3/3 호환성**을 확인했다. 다른 두 버전의 HB를 이 중앙값에 섞지 않았다. 안전본과 manifest는 `experiments/portfolio-94/validated/P11-7f171e769c13/`에 보존한다.

현재 추가 연구는 fiber 증거의 전문 정리를 더 직접 적용하는 방법과, 마지막 선형 합을 `dotProduct`의 가법성·스칼라 호환성으로 처리하는 방법에 집중한다. `linear_combination`과 scalar atom을 `generalize`한 뒤 `ring1`을 적용하는 두 시도는 원래 단계보다 나빠졌다.


## 두 번째 탐색: 기준 증거를 보존한 축소

`fiber_add_positional_repaired.lean`이 **294 tokens / 6,744,107 raw**로 전체 소스·공리 검사와 1회 측정을 통과했다. `get_sDomain_first_basis_eq_1`의 인자를 simp가 목표에서 추론하게 하면 별도 `rw`와 bound 증거가 사라진다. 이것은 아직 탐색 1회 값이며, 제출 안전본은 위 306-token 3/3 확인본이다.

추가로 확인한 구조적 주의점:

- `change (_ : L) + _ = _`는 덧셈 바깥 모양만 드러낸다. 각 항의 `f_i`는 남으므로 이어지는 simp에 `f_i`도 넣어야 한다.
- fold 직접 전개와 `Fin.eta` 제거를 함께 적용한 후보에서는 qMap 평가 증거가 matching되지 않았다. 원인은 인덱스 정규화와 `fiberMap` 별칭의 형태를 분리하여 확인 중이다. Lean의 definitional equality가 성립하더라도 simp의 패턴 매칭은 별도 확인이 필요하다.
- 마지막 합을 dotProduct로 표현하는 접근은 λ에 함수 타입을 주면 `change`가 통과한다. 다만 선형성 정리 적용 후 dotProduct를 합으로 펼치는 마지막 단계도 필요하다.
- `add_mul`만 넣고 `mul_comm`도 넣으면 합이 곱의 오른쪽으로 이동하여 다시 남을 수 있다. 두 방향의 분배법칙(`add_mul`, `mul_add`)을 모두 포함하는 수리 후보를 준비했다.

후보 수리본은 새 이름으로 저장하며, 실행한 실패 후보와 로그를 덮어쓰지 않는다.


### 전역 큐 대기 중 정리한 가설과 반례

| 변경 | 관측 | 판단 |
|---|---|---|
| one-level fiber 정리에 `y`까지 명시 | 307 tokens / 6,924,701 raw | 306 대비 약 21.9k HB 절약, 토큰 1개 비용을 감안하면 순점수 이득 없음 |
| fiber 증명에 기본 `simp` 사용 | 279 / 7,593,435 | 15 tokens 감소보다 HB 약 849k 증가가 더 커서 294 안전 후보보다 나쁨 |
| fiber 별칭을 `dsimp`로 먼저 전개 | 309 / 6,992,898 | 단계 추가가 계산량 감소로 연결되지 않음 |
| one-level 정리 적용을 별도 singlePass 단계로 분리 | 314 / 7,002,702 | 여러 단계로 나눈다는 사실만으로 이득 없음 |
| 전체 fiber simp를 singlePass로 처리 | 실패 | rewrite 후 새로 생기는 정규화 작업을 한 번 더 처리해야 함 |

대기 중인 수리 실험은 다음의 구체적 관측에 대응한다.

1. **평가 인자만 명시한 change**: 기존에 성공한 `P_i.eval x₀.val`과 `P_i.eval x₁.val`은 그대로 두고, 긴 곱의 계수만 `_`로 추론시킨다. 임의의 `(_ : L) + _`로 바꿨을 때 사라진 별칭 앵커를 유지하는 실험이다. 분해 정리의 지역 이름을 유지/직접 인라인한 두 경우만 비교한다.
2. **Fin.eta 복구**: fold 직접 전개 후보에서 인덱스 정규화만 복구하여 앞선 실패의 원인을 분리한다. 아직 이것이 원인이라고 확정하지 않는다.
3. **dotProduct를 마지막에 합으로 펼치기**: λ 타입을 명시한 후보는 change와 선형성 정리를 통과했다. 남은 목표가 dotProduct와 동일한 합의 비교이므로 마지막 `simp only [dotProduct, mul_comm]`만 추가한다.
4. **양방향 분배**: 실패 목표에서 `basis * (a * ce + b * co)`가 남은 것을 확인했다. `mul_add`를 추가하는 것과, 먼저 평가식을 scalar 합으로 만든 뒤 같은 정규화를 하는 것을 비교한다.
5. **fiber 관계 증거의 인라인**: 별도 등식과 rewrite 대신 최종 대수식에서 필요한 fiber 정의만 직접 simp한다. 증거 공유가 없어져 더 비쌀 가능성도 있으므로 한 번만 비교한다.

다음 유효 점수 개선이 나오면 독립 3회 checkpoint로 먼저 확정한다. 이 구조 수리에도 개선이 없다면 후보 폭을 늘리지 않고, 선언 전후 HB 분해나 show_term 재생을 통해 고정되는 비용을 구분하는 한 가지 가설로 좁힌다.


### qMap 타입 추론으로 새 최선

`qmap_infer_type.lean`이 **280 tokens / 6,657,136 raw**, 로컬 추정 **90.2253151165점**으로 전체 소스·공리 검사 및 탐색 1회를 통과했다. 기존 정리의 결과에 `congrArg Subtype.val`을 적용하고 방향을 뒤집은 등식에서 타입을 추론하게 했다. 같은 qMap 평가 식과 index bound를 새로 적는 부분이 사라져, 길이와 HB가 함께 감소했다.

독립 3회 checkpoint를 `checkpoint-qmap_infer_type.*`에 저장했다. raw는 **6,657,136 / 6,657,166 / 6,657,174**, 중앙값 **6,657,166**, 로컬 추정 **90.2252931346점**이다. 세 차례 모두 통과했다. 부모 에이전트가 Lean 4.30 / 4.29 전체 소스·공리 검사도 완료하여 **3/3 호환성 안전본**을 `validated/P11-8a33b2dfc592/`에 저장했다. 다른 버전의 HB는 4.31 중앙값에 섞지 않는다. 앞선 306-token 3/3 안전본과 기존 checkpoint 파일은 덮어쓰지 않는다. qMap 타입 추론과 이미 검증한 fiber 축소를 결합한 `qmap_infer_fiber.lean`은 다음 구조 실험의 첫 후보이며 아직 검증 결과가 없다.

추가 관측: fiber 부분만 `as_aux_lemma`로 분리한 후보는 304 tokens / 7,707,861 raw였다. 보조 선언 생성 자체는 이 구간의 비용을 낮추지 않았다.


## 단일 프로세스 fast 탐색으로 전환

기존 두 번째 배치와 280-token checkpoint를 끝내고, 아직 실행하지 않았던 후속 배치부터 부모가 승인한 `fast_probe.py`를 사용한다. 같은 전체 소스에서 동기 HB와 공리 로그를 수집하지만 **탐색용 잠정 결과**다. `state.json`에 fast 결과를 섞지 않으며 최선 하나를 기존 평가기의 Check + 별도 Audit + 독립 Measure 3회로 다시 확인한 뒤 기록한다.

- P11 calibration: 이미 검증한 280-token 후보가 fast **6,657,202 raw**. 독립 3회 중앙값 6,657,166과 차이 36 raw다. 이는 이 후보의 교차 확인이며 모든 후보의 일반적 동일성을 증명하지 않는다.
- `qmap_infer_fiber`: fast **268 tokens / 6,456,734 raw**. qMap 타입 추론과 bare fiber 정리의 개선이 결합되어 유지됐다. 아직 확정 측정이나 다른 버전 검증 결과가 아니다.

fast receipt는 `runs/portfolio-94/p11-exclusive4-431/fast-probes/`, 배치 요약은 `fast-batch3.json`에 별도 보존한다.


### 평가 인자 앵커와 자연스러운 곱 순서

압축 change를 분리 실험한 결과는 다음과 같다.

- `compact_eval_skeleton`: fast **274 / 6,603,889**. `P_i.eval x₀.val * _ + P_i.eval x₁.val * _`를 유지하면 긴 곱의 계수는 추론할 수 있다.
- `compact_eval_inline`: fast **270 / 6,603,666**. 위 구조에서 분해 정리의 지역 이름도 직접 인라인할 수 있다.
- `compact_fold_eta`, `compact_skeleton_f_eta`: 둘 다 실패. Fin.eta 복구만으로는 fold 전개 후 qMap 평가 증거가 적용되지 않았다. 문제를 Fin.eta 하나로 설명했던 초기 가설은 반박됐으며, 평가 인자의 별칭 앵커를 유지하는 압축이 검증된 대안이다.

P05에서 확인한 자연스러운 곱 순서 아이디어를 적용했다. 중간 목표를 `(1-r) * P₀.eval y + r * P₁.eval y`로 쓰면 `new_coeffs`의 스칼라 순서와 같다. 이때 마지막 합에는 전역 교환법칙 정규화나 항별 ring 인증서가 필요하지 않다. `Finset.mul_sum`, `add_mul`, `mul_assoc`를 적용하고 마지막 정의적 동등성을 `rfl`로 닫는다.

`natural_coeff_compact_rfl.lean`은 **248 tokens / 6,209,058 raw**, 잠정 **91.1132705062점**으로 fast 통과했다. 자연 곱 순서만 적용한 첫 후보는 겉보기 같은 합이 남아 실패했고, raw marker가 있었어도 실패 결과로 거부했다. `rfl`까지 포함한 수정본만 성공 후보로 취급한다. 독립 Check + Audit + Measure 3회 checkpoint를 시작했다.

248-token 후보에 대해서는 별도 진단 복사본으로 declaration before/body start/body done/declaration after를 읽어 header와 closing/kernel 비용을 분리한다. 마지막 logging에서 이미 포착한 before/after 값을 출력하므로 시작부 관찰 코드를 추가하지 않는다. 이 진단은 제출 지표나 후보 점수에 포함하지 않는다.


## 사용자 요청에 따른 일시 중단 시점

새 실험을 시작하지 않고 모든 자체 실행·대기 프로세스를 중단했다. 중단 시점의 네 프로세스는 모두 lease 또는 파일을 기다리고 있었으며, 실행 중인 자체 Lean 프로세스는 없었다. 완료 및 미완료 receipt를 모두 보존했다.

- **확정 평균에 사용할 후보**: `validated/P11-8a33b2dfc592/`, 280 tokens, raw 중앙값 **6,657,166**, Check + 독립 Audit + 독립 3회 측정 및 지정 버전 3/3. 로컬 점수 **90.2252931346**.
- **최고 잠정 후보**: `candidates/p11_agent/natural_coeff_compact_rfl.lean`, 248 tokens, fast raw **6,209,058**, 잠정 **91.1132705062**. 같은 프로세스의 전체 소스·공리 검사는 통과했고 추가 plain Check도 통과했다. 그러나 독립 Audit 대기에서 중단되어 **독립 Measure는 0/3**이다. 확정 평균에 넣지 않는다.
- 248-token 후보의 완료된 fast receipt: `fast-probes/natural-coeff-compact-rfl-1a6fd6c32c/result.json`.
- 중단된 별도 확정 receipt: `evaluations/checkpoint-natural_coeff_compact_rfl-8a7d37b855/result.json` (`interrupted: KeyboardInterrupt()`).
- 선언 전후 분리 진단도 실행 슬롯 대기 중에 중단됐으므로 새 header/closing 수치는 없다. 기존 구간 진단의 잔여 비용을 고정 하한으로 재해석하지 않는다.
- `batch3-final_simp_ac_staged_both`와 `batch3-final_dot_product_unfold`는 실패했다. 그 뒤의 후보는 중단되었거나 미실행이며 성공으로 취급하지 않는다.

## 제출 JSON 준비를 위한 248-token 후보 확정

2026-10-28 재개 요청에 따라 중단 기록을 보존하고 새 label로 독립 검증했다. `natural_coeff_compact_rfl.lean`은 이제 잠정 후보가 아니라 지정 버전 **3/3 검증 완료본**이다.

- 길이: **248 tokens**. 원본 1,906 tokens 대비 **86.99% 감소**.
- Lean 4.31 raw HB 독립 3회: **6,209,061 / 6,209,046 / 6,209,080**, 중앙값 **6,209,061**.
- 원본 raw 중앙값 45,492,117 대비 **86.35% 감소**. 로컬 산식 추정 점수 **91.11326830799328**.
- Lean 4.31은 전체 소스 Check + 별도 프로세스 Audit + 독립 Measure 3회 완료. Lean 4.30 / 4.29는 각각 전체 소스 Check + 별도 프로세스 Audit 완료. 모든 target axiom은 `propext`, `Classical.choice`, `Quot.sound`뿐이다.
- `audit_selected.py`로 선택 receipt의 소스·로그 해시, 원본 context 보존, fresh nonce, 중앙값을 재검사했다. 추가 두 버전도 manifest 생성 전에 소스·로그·runner 해시와 환경 identity를 재검사했다.
- 새 primary receipt: `runs/portfolio-94/p11-exclusive4-431/evaluations/submission-checkpoint-natural-coeff-248-970dd6ae8c/result.json`.
- 호환성 receipts: 같은 run root의 `compat-submission-248-430/result.json`, `compat-submission-248-429/result.json`.
- 제출 조립용 증명: `experiments/portfolio-94/validated/P11-c7968b607b27/candidate.lean`.
- 검증 manifest: 같은 폴더의 `manifest.json`. SHA256: `c7968b607b27165f48d1a8f9ab79a672348f7390c6403e4630cca09d0cc626d7`.

최종 개선은 qMap 타입 추론, fiber 증거 축소, 평가 인자 앵커 유지, 정의와 같은 자연스러운 계수 곱 순서, 마지막 `rfl`의 결합이다. async 옵션이나 측정 API는 넣지 않았다. 새로운 추측 후보를 추가하지 않고 이미 fast 검증된 구조 개선을 확정했다. 이전 280-token 안전본과 중단된 248-token receipt는 보존했다. 모든 heavy Lean 호출은 exclusive lease와 `-j1 -M4096`을 사용했으며 커밋·공식 제출은 하지 않았다.
