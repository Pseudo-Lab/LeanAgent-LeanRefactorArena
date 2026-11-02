# Heartbeat 계측과 메트릭 경계 연구

2026-10-28. 기존 15문제 최적화를 잠시 멈추고 수행한 별도 연구다. 공식 제출, 기존 평가기 변경, 포트폴리오 점수 갱신, 커밋은 하지 않았다. 실제 worker 구현은 공개되지 않아 **로컬에서 확인한 계측과 공식 채점을 동일하다고 단정하지 않는다.**

## 1. 먼저 읽을 결론

1. HB는 실행 시간이나 전체 프로세스의 계산량이 아니다. 현재 스레드의 작은 메모리 할당을 중심으로 한 counter다.
2. **비동기 보조 정리의 kernel checking이 현재 스레드의 HB에서 빠지는 현상을 재현했다.** proof 내부 옵션으로도 보조 정리에 영향을 줄 수 있다. 다만 실제 P11에서는 옵션만 켜도 종합점수가 내려갔고, 전체를 보조 정리로 만드는 방식은 크게 회귀했다.
3. **Lean의 `realizeValue`는 성공적으로 완료한 일부 준비 작업의 HB를 복원한다.** 캐시가 비어 있어 실제 작업을 수행해도 제외된다. 직접 setter를 호출하지 않는 별도 진단에서 확인했다.
4. `decide +kernel`은 다른 종류의 개선이다. elaborator와 kernel의 중복 계산을 줄인다. 작은 닫힌 명제에서 일반 `decide`보다 raw HB 64.85% 감소했다.
5. 이미 존재하는 일반 정리를 적용하는 방법이 같은 예제에서 가장 좋았다. `exact List.length_range`는 일반 `decide`보다 97.72% 감소했다. 기존 정리의 증명 생성 비용이 import 밖에 있고, 현재 선언에서는 적용만 검사하기 때문이다.
6. 따라서 다음 검색은 **계측되지 않는 기존 라이브러리 작업의 재사용**, **검증된 계산 결과의 재사용**, **중복 elaboration 제거**를 먼저 탐색한다. 어떤 경계가 존재한다는 사실만으로 실제 문제에서 이득이 보장되지는 않는다.

## 2. 정확히 무엇을 측정하는가

현재 P11 평가기의 `full_probe.py`는 다음 구간을 측정한다.

```text
앞선 import·선언·command parsing
    ↓ 계측 시작: IO.getNumHeartbeats
원래 omit … in theorem … 명령의 elabCommand
    - 정리 header elaboration
    - proof elaboration / tactic 실행
    - proof closing, 동기 kernel checking
    ↓ 계측 종료: IO.getNumHeartbeats
차이 출력 → 후속 선언 → 프로세스 종료
```

| 항목 | 현재 로컬 측정 |
|---|---|
| import와 선행 선언, 원본 파일의 suffix | 구간 밖 |
| 선언 command의 parsing | 구간 밖; macro expansion은 elaboration에 속함 |
| header에 포함된 `by omega` 등 | 구간 안 |
| proof 본문과 closing | 구간 안 |
| 동일 스레드의 동기 kernel 검사 | 구간 안 |
| 다른 스레드의 kernel 할당 | 부모 counter에 자동 합산되지 않음 |
| 내부 realization이 복원하는 작업량 | 구간 안에서 실행돼도 counter에서 제외될 수 있음 |
| 별도 Check / Audit / 로컬 후보 검색 | HB 점수 구간 밖 |

원본 파일과 후보를 같은 pin/환경/wrapper로 비교해야 한다. 다른 버전의 counter를 섞거나 `IO` raw 값과 사용자 표시 HB를 섞으면 안 된다. `#count_heartbeats`의 command 출력은 통상 raw 차이를 1000으로 나눈 정수다. tactic 형태와 command 형태의 표시 방식도 확인해야 한다.

`maxHeartbeats`는 허용 한도이고, `Core.Context.initHeartbeats`는 한도를 계산하는 기준점이다. 둘을 바꾸는 것과 외부 wrapper의 `IO.getNumHeartbeats` 차이를 바꾸는 것은 다르다. `maxHeartbeats := 0`이 사용한 HB를 0으로 만드는 것은 아니다.

더 세밀하게는 현재 스레드의 allocation counter와 C++ kernel timeout용 step counter도 별개다. 작은 tagged scalar 산술은 CPU 연산이 있어도 작은 객체 할당을 만들지 않을 수 있다. HB가 낮다는 이유로 실행 시간이 반드시 짧거나 메모리 바이트 사용량이 작다고 해석하지 않는다. `CoreM.lean:393–404`의 snapshot 재사용은 저장된 HB를 다시 더하므로, 모든 캐시가 realization처럼 비용을 지우는 것도 아니다.

Mathlib의 확인한 `CountHeartbeats.lean`에서는 tactic helper에 async=false가 있지만, command용 `#count_heartbeats in`은 maxHeartbeats=0만 감싼다. 우리 wrapper는 선언 바깥에 async=false를 명시한다. 공식 페이지의 `#count_heartbeats`라는 설명만으로 worker의 정확한 wrapper를 역추론하면 안 된다.

소스:

- `insights-20261024-round7/p11/full_probe.py:13–26,44–54` — 로컬 wrapper.
- Lean 4.32 `Init/System/IO.lean:588–612` — thread counter와 API.
- `Lean/CoreM.lean:489–506` — limit/기준점 검사.
- `Lean/Util/Heartbeats.lean:21–29` — raw/사용자 HB 배율.
- `Mathlib/Util/CountHeartbeats.lean` — command/tactic별 계측 차이.
- [공식 IO Timing 문서](https://lean-lang.org/doc/reference/latest/IO/Timing/).
- [공개 Arena 앱 소스](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/raw/main/app.py) — UI와 별도 worker 구분. 2026-10-28 재확인.

## 3. 작은 명제에서의 3회 독립 측정

Lean 4.32, 매 실행 새 프로세스, `-j1 -M4096`. 명제는 `(List.range 300).length = 300`. table의 값은 raw HB 중앙값이다. 완전한 command wrapper를 사용하고 `.olean`을 생성했다. `List.length_range`는 허용되는 `propext`에 의존하고 나머지 성공한 계산 증명들은 공리 의존성이 없었다.

| 증명 방식 | raw HB | 해석 |
|---|---:|---|
| `decide` | 361,837 | 기준 |
| `rfl` | 415,170 | 단어 수가 작아도 계산량은 큼 |
| `decide +kernel` | 127,173 | 기준보다 64.85% 감소; kernel에서 계산 후 보조 정리를 재사용 |
| `exact List.length_range` | 8,253 | 기준보다 97.72% 감소; 이미 있는 일반 정리 적용 |
| `set_option maxHeartbeats 0 in decide` | 362,072 | 한도 변경은 측정값을 줄이지 않음 |
| proof 내부 async=true + `decide` | 362,061 | 주 정리 본문의 scheduling은 소급 변경되지 않음 |
| `as_aux_lemma => rfl` | 416,599 | 보조 정리를 만들기만 해서는 이득 없음 |
| proof 내부 async=true + `as_aux_lemma => rfl` | 299,851 | 같은 보조 정리 동기 버전보다 28.02% 낮게 집계 |
| 미리 같은 명제를 `decide +kernel`로 증명한 뒤 다시 측정 | 9,675 | 타입 기반 캐시 효과. 추가 선행 선언을 넣는 제출 방식은 아님 |

100 크기에서도 같은 방향을 관측했다. 전체 자료는 `runs/portfolio-94/diagnostics/metric-audit/allowed-axioms-summary.json`에 있다.

실패/계측 주의도 보존했다. 최초 `exact List.length_range _`는 암묵 인자를 명시 인자처럼 사용해 실패했다. 이후 `_`를 제거한 코드는 컴파일됐지만 toy runner가 공리 의존성 없음만 요구해 `propext`를 과도하게 거부했다. 원본 receipt를 고치지 않고 별도의 allowed-axioms summary에서 구분했다. 실패 코드의 HB marker는 성과에 포함하지 않는다.

## 4. async가 실제로 영향을 주는 경계

Lean 4.32의 연결은 다음과 같다.

```text
proof-local set_option
 → withOptions 안에서 as_aux_lemma 실행
 → 내부 tactic은 현재 스레드에서 완료
 → mkAuxTheorem / closure 생성
 → mkAuxLemma / addDecl
 → Elab.async=true이면 auxiliary kernel checking을 별도 task로 실행
 → checked environment / .olean export에서는 완료를 기다림
```

`AsAuxLemma.lean:19–23`, `Meta/Closure.lean:457–459`, `Meta/Tactic/AuxLemma.lean:43–77`, `AddDecl.lean:151–180`에서 확인했다. `Environment.lean:649–650,1122–1135,1840`은 checked 환경과 export가 결과를 기다리는 경로다.

즉 **kernel 검사를 없애지 않고도 현재 스레드의 HB만 낮아질 수 있다.** `Task.get`으로 기다리는 것은 자식 counter를 부모에 합산하는 것과 다르다. `-j1`도 모든 별도 task의 비용을 자동으로 부모 counter에 귀속시키지는 않는다.

기존 `ASYNC_BOUNDARY.ko.md`의 “proof 내부 async 옵션은 주 정리 scheduling을 바꾸지 않는다”는 관측은 유지된다. 이번 발견은 그 뒤 생성되는 **보조 정리 kernel task**라는 별개의 경계다. 기존 결론을 모든 내부 작업으로 일반화하면 안 된다.

### 실제 P11에서의 결과

Lean 4.31, 원래 전체 파일과 기존 280-token 후보를 사용했다. 원래 wrapper를 보존하고 proof body만 정해진 option/aux wrapper로 감쌌다. 계측 `.olean` 생성과 별도 import/공리 검사를 수행했다. frozen submission validator 자체는 변경하지 않았다.

| 조건 | Length | raw HB | 횟수 | 종합점수 참고치 |
|---|---:|---:|---:|---:|
| 기준 | 280 | 6,657,167 | 3 | 90.22529 |
| 본문 async 옵션 | 284 | 6,615,074 | 3 | 90.18618 |
| 전체 `as_aux_lemma` | 282 | 9,471,858 | 1 | 88.12791 |
| 전체 보조 정리 + async | 286 | 9,052,823 | 1 | 88.36500 |

점수 열은 전체 버전 통과를 가정한 산식 비교일 뿐 추가 버전 인증이나 공식 점수가 아니다. 옵션만 켜면 HB가 0.6323% 내려가지만 Length가 늘어 **문제 점수는 0.03911 하락**한다. 전체 보조 정리는 closure/검사 비용 증가가 더 크다. 다른 문제에도 이 숫자가 적용된다고 가정하지 않는다.

증거: `runs/portfolio-94/diagnostics/metric-audit-p11-async/summary.json`과 각 후보의 source/log/command/hash/nonce/별도 Audit.

## 5. 새 경계: realization은 실제로 실행된 작업의 HB를 복원한다

Lean 4.32 `Environment.lean:2582–2634`는 realization 진입 때 counter를 읽고, 성공한 cache hit/miss 처리 후 `IO.setNumHeartbeats`로 복원한다. 주석에는 이 경로의 HB 비결정성을 제거하려는 목적이 명시돼 있다.

별도 진단에서 같은 1,000개 metavariable 생성 작업을 직접 실행하거나 `Meta.realizeValue` callback으로 실행했다. 진단 자체는 counter setter를 호출하지 않는다. 결과는 세 프로세스 모두 동일했다.

| 조건 | 바깥에서 관측한 raw HB | callback 내부 raw HB | 결과 |
|---|---:|---:|---:|
| 직접 실행 | 7,566 | 7,545 | 1,000 |
| realization 캐시 miss | 254 | 7,419 | 1,000 |
| realization 캐시 hit | 5 | 재실행 없음 | 1,000 |

**cache miss에서도 내부에서는 7,419 HB를 썼지만 바깥에는 254만 남았다.** hit 로그의 `cached_inner=7419`는 캐시된 값이지 두 번째 작업이 실행됐다는 뜻이 아니다. 직접 실행과 callback은 MetaM context가 달라 내부 할당량까지 동일하다고 가정하지 않는다.

증거: `metric-audit/Realization3.lean`, `runs/portfolio-94/diagnostics/realization-boundary3/`. 첫 버전의 컴파일 실패와 두 번째 버전의 부적절한 pure-work 계측도 각각 보존했다. 두 번째 버전은 내부 counter 0/결과 0이므로 본 결론의 수치 근거로 쓰지 않는다.

이 custom metaprogram은 제출 코드가 아니다. 실제 proof에서 활용을 검토할 대상은 이미 제공되는 다음 기능이다.

| 기존 기능 | 관련 realization | 검토 방향 |
|---|---|---|
| `rw` / `simp` / `unfold` | 함수 equation/eq_def 생성, `Meta/Eqns.lean:185` | 반복적인 직접 reduction과 equation theorem 적용 비교 |
| `split`, matcher의 simp | 조건부 equation/splitter 생성, `Meta/Match/MatchEqs.lean:156,265` | 직접 case tree 전개와 생성 원리 비교 |
| `fun_induction` / `fun_cases` | 귀납/분해 원리, `Meta/Tactic/FunInd.lean:797,913,1044,1394` | 직접 수동 induction 대신 기존 함수의 원리 적용 |
| 상수 함수 정보 | `Meta/FunInfo.lean:36` | universe가 확정된 상수 head와 불안정한 metavariable head 비교 |

생성 비용이 제외되는 것과 그 정리를 적용하는 비용이 없는 것은 다르다. 구현에서 비싼 계산을 callback **이전에** 수행하면 그 부분은 그대로 집계된다. 모든 `simp`나 `deriving`이 공짜라는 뜻도 아니다. 현재는 소스와 계측 경계를 확인했으며, 이 전략으로 15문제 점수가 실제 개선됐다는 결과는 아직 없다.

예를 들어 `Meta/CongrTheorems.lean:419–420,434–436`의 비싼 congr proof construction은 realization 이전에 있다. `Meta/Injective.lean:300–301`도 마찬가지다. `realizeConst`로 만든 정리는 `Environment.lean:2520–2554,2648–2716`의 kernel replay 경로에서 검사되므로, 생성 비용을 제외한다고 검증 자체가 사라지는 것은 아니다. `Meta.realizeValue` 역시 해당 상수의 realization이 비활성화돼 있으면 callback을 직접 실행하므로 모든 호출이 복원 경로로 가는 것은 아니다.

## 6. 필터 통과, proof 검증, 대회 허용을 구분

공개 필터 함수만 AST로 추출해 서비스 실행 없이 검사했다. `Elab.async`, `as_aux_lemma`, `decide +kernel`, `maxHeartbeats` 예시는 이 regex 필터에서 거부되지 않았다. `native_decide`와 직접 counter API 예시는 거부됐다. 현재 공개 웹 소스도 재확인했다.

하지만 현재 프로젝트의 frozen validator는 `set_option` 전체를 거부한다. 따라서 async 실험은 별도 진단 경로에서만 실행했고 인증 후보에 섞지 않았다. **공개 regex가 통과시킨다는 사실은 worker 전체 검증이나 규정상 허용 판정이 아니다.** 공식 worker의 전체 실행/계측 구조도 알 수 없다.

직접 counter 변경, kernel 검사 생략, 추가 공리, 오류가 난 proof의 metric marker 채택은 유효한 성과로 계산하지 않는다. 독립 공리 검사는 필요하지만 `.olean` import 자체가 모든 원래 proof body를 처음부터 재검증하는 것은 아니므로, 원래 source 컴파일 성공과 함께 본다.

## 7. 다음 실험의 우선순위

1. **닫힌 decidable 부분문제:** `decide` ↔ `decide +kernel` ↔ 기존 정리 적용을 같은 원본 환경에서 비교한다. 일반적인 매개변수 정리를 무조건 `decide`로 바꿀 수는 없다.
2. **반복 reduction:** 이미 존재하거나 Lean이 생성하는 equation/induction 정리의 적용으로 옮긴다. 탐색은 오래 해도 최종 proof에는 선택한 증명만 남긴다.
3. **캐시가 안정적인 형식:** 동일한 타입/lemma 인스턴스의 반복 사용을 공유하고, 함수 head와 universe를 필요한 만큼만 명시한다. 무작정 전체 타입을 길게 명시하면 손해일 수 있다.
4. **async 후보는 별도 연구군:** kernel 비용이 큰 국소 구간에서만 비용 증가와 누락을 분리해 평가한다. 현재 P11 결과는 채택 근거가 아니다.
5. **측정 품질:** 새 프로세스의 cold 측정, 전체 source/statement 보존, return code와 독립 Audit, 3회 중앙값, 요구 pin 확인을 유지한다. warmup을 추가해 만든 수치를 기존 후보와 섞지 않는다.

최적화 선택식은 기존과 같다. 길이가 ΔL 증가할 때 HB는 최소 `H₀/L₀ × ΔL` 이상 줄어야 종합점수가 좋아진다. P11은 토큰당 약 23,868 raw HB이므로 +4토큰에는 약95,472 감소가 필요했다. 실제 감소42,093은 부족했다.

## 재현 파일

- `metric-audit/probe.py`: 60개 기본 toy 실행. 추가 18개 toy 실행의 정확한 source와 command는 각 receipt에 보존.
- `metric-audit/p11_async_probe.py`: P11 전체 파일 4조건, 기준/본문 옵션 3회 재측정 포함 총8개 계측 및8개 별도 Audit.
- `metric-audit/Realization3.lean`: realization counter 복원 진단3회.
- `metric-audit/public-filter-check.json`: 공개 regex 검사 결과.
- `../../runs/portfolio-94/diagnostics/metric-audit/allowed-axioms-summary.json`: 성공/실패와 허용 공리 구분.
- `../../runs/portfolio-94/diagnostics/metric-audit-p11-async/summary.json`: 실제 P11 결과.

이번 연구의 측정값으로 기존 `paused-score-snapshot.json`의 86.54/88.00 추정치를 갱신하지 않았다.
