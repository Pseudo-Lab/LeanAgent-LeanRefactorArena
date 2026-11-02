# P06 후속 구조 실험: 선형성 증거를 라이브러리 조합으로 재사용

2026-10-28. P07의 101-token 개선안 확인 후 P08을 탐색했고, P08에서 기존 185-token 최선을 넘지 못해 상위 에이전트의 요청으로 P06으로 전환했다. 커밋과 공식 제출은 하지 않는다.

## 가설

상위 에이전트의 진단에서 span_induction₂ 마지막 여섯 closure 분기가 약 6.2M raw HB를 소모했다. 이들은 수학적으로 새로운 기저 성질이 아니라 양변의 선형성이다. `LinearMap.mul`, `comp`, `compr₂`, `flip`으로 양변을 bilinear map으로 구성하면 이미 검증된 선형성 증거를 재사용할 수 있다. 두 번의 `Basis.ext`로 기저 원소만 비교하고 `LinearMap.congr_fun₂`로 임의 a/b의 결과를 얻는다.

A를 FieldOpFreeAlgebra, c를 두 생성자의 super-commutator, i를 ι의 linear map, t를 timeOrderF, M을 A의 곱셈 bilinear map이라 두면:

- 좌변 map: `(M.comp (M.flip c)).compr₂ (i.comp t)`
- 우변 map: `M.compr₂ (i.comp ((M c).comp t))`

상위 에이전트의 394-token `existential_factors_typed.lean`에서 기저 부분은 그대로 재사용했다. 양쪽 외부 인자를 uniform existential witness로 얻는 증명을 바꾸지 않았다.

## 실행 경계

동일한 frozen `search_exclusive4.py`, `p06_adapter.py`, 환경을 사용하며 상위 에이전트의 허가에 따라 `runs/portfolio-94/p06-432`를 lock하여 후보만 append한다. 원본과 seed의 기존 3회 검증을 재사용한다. 새 `p06-agent4-432` init은 메시지 도착 직전 시작했으나 첫 original Check의 lease 대기 중 Ctrl-C로 중단했고, 실제 Lean은 실행되지 않았다. 중단 기록을 보존한다.

후보/보고서는 `candidates/p06_agent`와 이 파일에만 작성한다. 4GiB runner가 두 공유 슬롯을 모두 잠그므로 다른 Lean과 동시에 메모리를 쓰지 않는다. 모든 후보는 실제 전체 소스 Check, 별도 공리 검사, fresh nonce 동기 HB 측정과 환경 해시 검사 후에만 비교한다.

## 진행 상태

- `bilinear_basis.lean`: 명시적인 change를 둔 첫 구조 후보, 평가 대기.
- `bilinear_no_change.lean`: 동일 목표를 Lean의 definitional equality로 연결해 change 문장의 길이를 제거할 수 있는지 보는 후속 후보, 미실행.

map 구성 자체의 타입 추론과 커널 비용도 측정값에 포함한다. closure 분기를 없앴다는 사실만으로 HB가 줄었다고 판단하지 않는다.


## 첫 실측

`bilinear_basis.lean`은 전체 Check/Audit를 통과했고 462 tokens / 11,279,609 raw HB였다. 394 /13,359,032 seed보다 HB는 2,079,423 줄었지만 68토큰 증가의 비용이 더 커 종합 점수는 소폭 회귀했다. 마지막 여섯 분기의 진단 비용 6.2M이 그대로 절약되는 것은 아니다. map 구성과 equality 연결에서 비용이 다시 발생한다.

`bilinear_no_change.lean`은 실패했다. 일반 `simp`가 목표 안의 compr₂/comp 표현을 모두 열지 않아, 기저 증명의 rewrite가 필요한 pattern을 보지 못했다. 이에 전체 목표를 길게 다시 쓰는 대신 `change ι 𝓣ᶠ(_ * _ * _) = ι (_ * 𝓣ᶠ(_ * _))`처럼 계산 형태만 고정하고 인자는 unification으로 채우는 후보를 준비했다. 이 change는 증명과 HB 계측 범위를 바꾸지 않는다. `LinearMap.ext_basis` 및 불필요한 let 제거와 조합해 순차 평가 중이다.

`diagnose.py`는 구간 HB 진단 전용으로 작성했으며 아직 실행하지 않았다. 실행할 경우에도 frozen exclusive runner의 lease와4GiB 제한을 사용하고, 진단 결과는 후보 점수에 사용하지 않는다.


## Bilinear 구성의 표현 비교

| 후보 | 상태 | tokens | raw HB | 관찰 |
|---|---:|---:|---:|---|
| 원본 | 3회 검증 | 1217 | 42,056,240 | 고정 기준 |
| root existential_factors_typed | 검증 | 394 | 13,359,032 | uniform 외부 인자 |
| bilinear_basis | 통과 | 462 | 11,279,609 | closure 제거, 길이 때문에 순회귀 |
| bilinear_no_change | 실패 | 422 | — | comp/compr₂가 rewrite 목표를 가림 |
| bilinear_basis_shape | 실패 | 444 | — | 형태 change는 성공하지만 local c가 남음 |
| bilinear_basis_shape_unfold | 통과 | 446 | 11,146,487 | c를 명시적 simp 규칙으로 넣어 해결 |
| bilinear_inline_maps_shape_unfold | 통과 | 422 | 11,134,816 | i/t let 제거 + LinearMap.ext_basis |
| bilinear_mul_sided_shape_unfold | 통과 | 436 | 11,629,734 | mulLeft/mulRight 표현은 회귀 |

현재 최선은 `bilinear_inline_maps_shape_unfold.lean`, primary local score 약79.6162점이다. root394 후보 대비 약0.996점 개선이다. 아직 후보당1회 측정으로, 최종 선택은 추가 비교와3회 재검증 뒤 한다. 단계별 실행 기록은 공유 run의 `evaluations/agent-*` 및 `state.json`이 기준이다.

추가 가설은 기존 span-induction closure에서 `simp only [*,…]`가 복잡한 식마다 귀납 가설을 rewrite하는 비용을 줄이는 것이다. 구조 규칙만 simp한 뒤 `congr 1 <;> assumption`으로 직접 귀납 가설을 연결하는 후보, map_mul을 귀납 전에 수행하는 후보를 준비했다. 이는 결과를 얻기 전의 가설이며 성공으로 계산하지 않는다.

`closure_congr.lean`은397 tokens /13,358,046 raw로 통과했다. 원래394-token 증명의13,359,032와986 raw 차이뿐이며 길이 증가를 상쇄하지 못한다. 따라서 closure6.2M의 주된 원인이 귀납 가설 rewrite dispatch라는 가설은 실측에서 지지되지 않았다. 구조 정규화와 map 관련 타입/증거 구성이 더 중요한 원인으로 남는다. 동일 효과의compact 변형은 준비만 하고 실행하지 않는다.

탐색 대기 시간을 줄이기 위해 상위 에이전트가 검증한 `fast_probe.py`를 다음 batch부터 사용한다. 같은 전체소스 HB 측정과 같은 프로세스의 공리 검사를1회 실행하며 결과는 `fast-probes`에만 기록한다. 최선은 기존 동결 evaluator의 독립 Check/Audit/3회측정으로 다시 확인한다. fast만 통과한 결과를 확정 후보로 부르지 않는다.

타입 구성 분리 실험: `bilinear_ext_basis_shape_unfold`443/11,103,252, `bilinear_ext_basis_scalar`463/11,106,705. R/A=ℂ 계수를 명시해도HB가 줄지 않았고20토큰이 늘었다. 따라서 이 경로에서 scalar 메타변수 추론은 큰 병목이 아니다. inline422/11,134,816은HB가 약3만 높아도21토큰 짧아 더 높은 점수다.

`bilinear_ext_basis_i_typed`는443 /11,216,841로 통과했지만 i 타입을 명시하지 않은443 /11,103,252보다HB가 늘었다. 이 실험 묶음에서는 explicit type anchor가 이득을 주지 않았다. 현재 확정평가기1회 최선은422 /11,134,816이며, 다음 단계의 fast 결과와 최종3회 재측정 결과를 분리해 기록한다.

## 중단 시점의 확정 범위 (2026-10-28)

사용자가 현재15개 평균을 보기 위해 잠시 중단을 요청하여 모든 신규 실행을 멈췄다. 마지막 실행의 fast 새 후보 `closure_composed_map`은 lease 대기 중 KeyboardInterrupt로 중단됐고, 해당 후보 Lean 실행은 시작하지 않았다. 이전 완료 receipt는 보존한다. 준비만 된 나머지 후보를 성공 결과로 계산하지 않는다.

- 현재 탐색 best: `candidates/p06_agent/bilinear_inline_maps_shape_unfold.lean`,422 tokens /11,134,816 raw.
- 독립 검증: Check0, Audit0, Measure1 0. 허용 공리 propext/Classical.choice/Quot.sound. **3회 재측정은 아직 하지 않았다.**
- receipt: `runs/portfolio-94/p06-432/evaluations/agent-bilinear_inline_maps_shape_unfold-31e13bd801/result.json`.
- fast calibration도 동일422 후보에서11,135,247 raw로 통과했다(기존과431raw차이). 이 탐색용 추가 측정은 독립3회 checkpoint를 대체하지 않는다.
- 기존 root394 /13,359,032의3회 안전본은 유지한다.

단계 진단(`diagnostics/p06-agent-fd4887eb4f`)은 성공했지만 점수 자료로 사용하지 않는다. 구간 비용은 lets381,485; map equality/suffices+congr_fun₂2,219,744; basis ext478,195; change705,335; basis simp550,904; uniform factors555,495; pair expansion3,395,424; centrality/empty402,662; statistics1,853,760이었다. 다음 재개 시 우선 검토할 곳은 map 등식에서 원래 목표로 연결하는2.22M과 pair expansion3.40M이다. `bilinear_congr_arg`, `bilinear_congr_term` 및 fast_batch6의 구조 후보들은 준비만 했으며 새 후보의 성공/HB 결과는 없다.

## 재개 후422 후보 인증 완료

제출 JSON 준비 요청으로 재개하여 frozen evaluator로 Check+독립Audit+3회Measure를 완료했다.422 tokens,raw [11,134,816,11,134,736,11,134,877],중앙값11,134,816,local score79.6161848627이다. 선택본은 `candidates/p06_agent/confirmed-primary.lean`,receipt는 `runs/portfolio-94/p06-432/evaluations/agent-final-checkpoint-6fac5d43df/result.json`이다. 별도 saved source/log/hash audit도 통과했다. 기존394 안전본은 보존한다. 신규구조후보 탐색은15문제 전체 인증에 필요한P09 검증을 우선하여 보류한다.
