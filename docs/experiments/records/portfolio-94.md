# 94점 목표 포트폴리오 연구

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

길이·HB·호환성을 함께 감사하고 문제별 구조 후보를 제출 묶음으로 준비한다.

## 확인된 결과와 해석

94는 목표이며 달성한 공식 점수가 아니다. 단계별 README의 진행 중 상태와 submission-round의 후속 검증을 구분한다.

## 코드·Lean 보존 결정

대형 후보·공식 앱 사본·문제별 adapter는 PR #46에서 제외. MD 기록과 아카이브 복구 경로를 남긴다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/portfolio-94/HB-METRIC-AUDIT.ko.md` | `3ee67de` | `0c3a55207bd51d26e9bfc5eba53084252a3b3f04b6ed55b1dd062def4a06f983` |
| `experiments/portfolio-94/README.ko.md` | `3ee67de` | `caa9e549c3f5b3da1aae64bad134efd835e54fc3215e45c784fcc78c438ad3fb` |
| `experiments/portfolio-94/submission-round/README.ko.md` | `3ee67de` | `c6d003be730aec9fd43bb775da683bf3ea349b1cb6d43e6fe66eba05394f2473` |

## 원문: `experiments/portfolio-94/HB-METRIC-AUDIT.ko.md`

### Heartbeat 계측과 메트릭 경계 연구

2026-10-28. 기존 15문제 최적화를 잠시 멈추고 수행한 별도 연구다. 공식 제출, 기존 평가기 변경, 포트폴리오 점수 갱신, 커밋은 하지 않았다. 실제 worker 구현은 공개되지 않아 **로컬에서 확인한 계측과 공식 채점을 동일하다고 단정하지 않는다.**

#### 1. 먼저 읽을 결론

1. HB는 실행 시간이나 전체 프로세스의 계산량이 아니다. 현재 스레드의 작은 메모리 할당을 중심으로 한 counter다.
2. **비동기 보조 정리의 kernel checking이 현재 스레드의 HB에서 빠지는 현상을 재현했다.** proof 내부 옵션으로도 보조 정리에 영향을 줄 수 있다. 다만 실제 P11에서는 옵션만 켜도 종합점수가 내려갔고, 전체를 보조 정리로 만드는 방식은 크게 회귀했다.
3. **Lean의 `realizeValue`는 성공적으로 완료한 일부 준비 작업의 HB를 복원한다.** 캐시가 비어 있어 실제 작업을 수행해도 제외된다. 직접 setter를 호출하지 않는 별도 진단에서 확인했다.
4. `decide +kernel`은 다른 종류의 개선이다. elaborator와 kernel의 중복 계산을 줄인다. 작은 닫힌 명제에서 일반 `decide`보다 raw HB 64.85% 감소했다.
5. 이미 존재하는 일반 정리를 적용하는 방법이 같은 예제에서 가장 좋았다. `exact List.length_range`는 일반 `decide`보다 97.72% 감소했다. 기존 정리의 증명 생성 비용이 import 밖에 있고, 현재 선언에서는 적용만 검사하기 때문이다.
6. 따라서 다음 검색은 **계측되지 않는 기존 라이브러리 작업의 재사용**, **검증된 계산 결과의 재사용**, **중복 elaboration 제거**를 먼저 탐색한다. 어떤 경계가 존재한다는 사실만으로 실제 문제에서 이득이 보장되지는 않는다.

#### 2. 정확히 무엇을 측정하는가

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

#### 3. 작은 명제에서의 3회 독립 측정

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

#### 4. async가 실제로 영향을 주는 경계

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

##### 실제 P11에서의 결과

Lean 4.31, 원래 전체 파일과 기존 280-token 후보를 사용했다. 원래 wrapper를 보존하고 proof body만 정해진 option/aux wrapper로 감쌌다. 계측 `.olean` 생성과 별도 import/공리 검사를 수행했다. frozen submission validator 자체는 변경하지 않았다.

| 조건 | Length | raw HB | 횟수 | 종합점수 참고치 |
|---|---:|---:|---:|---:|
| 기준 | 280 | 6,657,167 | 3 | 90.22529 |
| 본문 async 옵션 | 284 | 6,615,074 | 3 | 90.18618 |
| 전체 `as_aux_lemma` | 282 | 9,471,858 | 1 | 88.12791 |
| 전체 보조 정리 + async | 286 | 9,052,823 | 1 | 88.36500 |

점수 열은 전체 버전 통과를 가정한 산식 비교일 뿐 추가 버전 인증이나 공식 점수가 아니다. 옵션만 켜면 HB가 0.6323% 내려가지만 Length가 늘어 **문제 점수는 0.03911 하락**한다. 전체 보조 정리는 closure/검사 비용 증가가 더 크다. 다른 문제에도 이 숫자가 적용된다고 가정하지 않는다.

증거: `runs/portfolio-94/diagnostics/metric-audit-p11-async/summary.json`과 각 후보의 source/log/command/hash/nonce/별도 Audit.

#### 5. 새 경계: realization은 실제로 실행된 작업의 HB를 복원한다

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

#### 6. 필터 통과, proof 검증, 대회 허용을 구분

공개 필터 함수만 AST로 추출해 서비스 실행 없이 검사했다. `Elab.async`, `as_aux_lemma`, `decide +kernel`, `maxHeartbeats` 예시는 이 regex 필터에서 거부되지 않았다. `native_decide`와 직접 counter API 예시는 거부됐다. 현재 공개 웹 소스도 재확인했다.

하지만 현재 프로젝트의 frozen validator는 `set_option` 전체를 거부한다. 따라서 async 실험은 별도 진단 경로에서만 실행했고 인증 후보에 섞지 않았다. **공개 regex가 통과시킨다는 사실은 worker 전체 검증이나 규정상 허용 판정이 아니다.** 공식 worker의 전체 실행/계측 구조도 알 수 없다.

직접 counter 변경, kernel 검사 생략, 추가 공리, 오류가 난 proof의 metric marker 채택은 유효한 성과로 계산하지 않는다. 독립 공리 검사는 필요하지만 `.olean` import 자체가 모든 원래 proof body를 처음부터 재검증하는 것은 아니므로, 원래 source 컴파일 성공과 함께 본다.

#### 7. 다음 실험의 우선순위

1. **닫힌 decidable 부분문제:** `decide` ↔ `decide +kernel` ↔ 기존 정리 적용을 같은 원본 환경에서 비교한다. 일반적인 매개변수 정리를 무조건 `decide`로 바꿀 수는 없다.
2. **반복 reduction:** 이미 존재하거나 Lean이 생성하는 equation/induction 정리의 적용으로 옮긴다. 탐색은 오래 해도 최종 proof에는 선택한 증명만 남긴다.
3. **캐시가 안정적인 형식:** 동일한 타입/lemma 인스턴스의 반복 사용을 공유하고, 함수 head와 universe를 필요한 만큼만 명시한다. 무작정 전체 타입을 길게 명시하면 손해일 수 있다.
4. **async 후보는 별도 연구군:** kernel 비용이 큰 국소 구간에서만 비용 증가와 누락을 분리해 평가한다. 현재 P11 결과는 채택 근거가 아니다.
5. **측정 품질:** 새 프로세스의 cold 측정, 전체 source/statement 보존, return code와 독립 Audit, 3회 중앙값, 요구 pin 확인을 유지한다. warmup을 추가해 만든 수치를 기존 후보와 섞지 않는다.

최적화 선택식은 기존과 같다. 길이가 ΔL 증가할 때 HB는 최소 `H₀/L₀ × ΔL` 이상 줄어야 종합점수가 좋아진다. P11은 토큰당 약 23,868 raw HB이므로 +4토큰에는 약95,472 감소가 필요했다. 실제 감소42,093은 부족했다.

#### 재현 파일

- `metric-audit/probe.py`: 60개 기본 toy 실행. 추가 18개 toy 실행의 정확한 source와 command는 각 receipt에 보존.
- `metric-audit/p11_async_probe.py`: P11 전체 파일 4조건, 기준/본문 옵션 3회 재측정 포함 총8개 계측 및8개 별도 Audit.
- `metric-audit/Realization3.lean`: realization counter 복원 진단3회.
- `metric-audit/public-filter-check.json`: 공개 regex 검사 결과.
- `../../runs/portfolio-94/diagnostics/metric-audit/allowed-axioms-summary.json`: 성공/실패와 허용 공리 구분.
- `../../runs/portfolio-94/diagnostics/metric-audit-p11-async/summary.json`: 실제 P11 결과.

이번 연구의 측정값으로 기존 `paused-score-snapshot.json`의 86.54/88.00 추정치를 갱신하지 않았다.

## 원문: `experiments/portfolio-94/README.ko.md`

### 94점 목표 후속 실험 — 2026-10-28

최신 제출 묶음과 이번 재검증은 [15문제 제출 라운드](portfolio-94.md) 및 [제출 폴더](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/submissions/warmup-hb-20261028/README.ko.md)를 기준으로 확인한다. 아래에는 초기 시점부터의 실험 기록이 누적되어 있으므로, 과거의 최선 후보·대기 상태·점수를 현재 상태와 혼동하지 않는다. 현재 선택과 버전별 검증 근거는 제출 폴더의 `manifest.json`에 있다.

진행 중이다. 이 디렉터리의 새 결과는 공식 리더보드 제출 결과가 아니다. 지정 버전을 모두 확인하기 전에는 기존 누적 점수에 확정 반영하지 않는다. 기존 15문제 누적 로컬 추정은 P12의 156-token 개선까지 약 82.797점이었다.

#### 목표와 선택 기준

모든 지정 버전을 통과한다고 가정하면 문제 점수는 `100 - (100/3) × (L/L₀ + H/H₀)`이다. 따라서 짧은 증명과 낮은 HB를 함께 비교한다. 검색 시간은 최종 증명 지표와 분리한다. 현재 로컬 검색은 모델/API 호출이나 대회 제출 없이 진행한다.

#### 재현 가능한 기록 구조

- `search.py`: 기존 offline-proof-search의 검증 절차를 복사해 문제별 측정 marker와 의존성 등록을 지원한다. 기존 실험 파일은 수정하지 않았다.
- `p07_adapter.py`: 모델 공리 대신 실제 CSLib 전체 소스에서 검증. 소스 아카이브와 빌드 입력을 대조한다.
- `p10_adapter.py`, `p11_adapter.py`: 고정된 ArkLib 환경과 native plugin 인자를 그대로 사용한다.
- `../../runs/portfolio-94/<problem>-<pin>/state.json`: 원본, 모든 성공/실패 후보, best, Pareto 기록.
- 각 `evaluations` 폴더: 후보, plain compilation, 공리 검사, nonce를 사용한 동기 측정, 소스/로그 해시.
- `diagnose.py`: 구간 비용 진단 전용. 그 수치는 제출 후보 점수로 사용하지 않는다.
- `rules/sources.json`: 공개 대회 코드 URL, 취득 시각, SHA256.

#### 현재 확인한 인사이트

1. **P07의 이전 모델 후보를 실제 환경으로 옮길 수 있었다.** Lean 4.31 전체 CSLib 원본 408 tokens / 61,915,956 raw HB에 대해, c50 후보 268 tokens / 1,045,358 raw HB가 독립 3회 측정 중앙값으로 통과했다. HB 감소율 약 98.31%. 아직 나머지 두 지정 버전 검증 전이다.
2. **P07의 남은 병목은 길이다.** 마지막 생성자 처리를 `aesop`으로 압축한 253-token 후보는 통과했지만 22,975,706 raw HB로 크게 나빠졌다. 단순한 자동화 호출 축약을 개선으로 간주하지 않는다. 전역 `grind`/`aesop` 후보의 실패·타임아웃도 보존한다.
3. **P10은 집합 합집합의 크기 계산을 단사함수로 바꿀 수 있었다.** 각 불일치 원소를 `(불일치 fiber, fiber 내부 위치)`로 보내고 decode가 원래 원소를 복원한다는 사실을 사용했다. 처음에는 rate 매개변수 추론이 막혔지만 명시 후 전체 소스에서 통과했다.
4. **P10의 마지막 산술도 중요하다.** 진단에서 단사함수/카디널리티 구간 약 186만, 산술 정리와 마지막 변환 약 331만 raw HB가 관찰됐다. 마지막 `omega` 대신 이미 얻은 부등식에 `Nat.lt_succ_of_le`를 적용하고 `exact_mod_cast`로 연결한 후보는 452 → 425 tokens, 7,012,827 → 6,253,250 raw HB로 개선됐다. 이 후보 수치는 탐색 1회이며 재확인이 필요하다.
5. **P11의 `singlePass`는 단계별로 다르다.** 모든 `simp`에 붙이면 증명이 실패한다. 정의 전개 단계 하나에만 적용한 후보는 통과하고 개선됐다. `set!`를 `let`으로 바꾸는 길이 절약과 합성했다.
6. **보조 정리 분리가 HB를 공짜로 없애지는 않는다.** 전체 증명을 `as_aux_lemma`로 감싸면 P07은 1,045,358 → 1,384,665, P11은 7,685,353 → 10,799,945 raw HB로 회귀했다. 생성된 보조 정리의 closure 생성 및 kernel 검사 비용도 생긴다. 이 결과를 모든 사용처에 대한 불가능성으로 일반화하지 않는다.

#### 대회 HB 규칙 조사

2026-10-28 취득한 [공개 app.py](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/raw/main/app.py)는 HB 카운터 API, `IO`, `run_tac`, `run_elab`, `run_meta`, `native_decide`, 사용자 정의 macro/elab 등을 금지한다. 주석에는 worker도 같은 검사를 한다고 명시되어 있다. 공개 UI 코드와 실제 worker 구현을 동일시하지 않는다.

`maxHeartbeats`는 예외지만 이는 실행 한도를 바꾸는 옵션이다. 소모한 HB 자체를 줄였다는 증거가 아니다. 공개 문자열 검사에 걸리지 않는다는 이유만으로 모든 계측 경계 변경이 공식적으로 허용된다고 판단하지 않는다. 표준 tactic, 기존 정리 재사용, 증거 직접 전달, 불필요한 탐색/전개 제거를 실제 커널 검증과 함께 실험한다.

#### 아직 해야 할 일

P07 다른 지정 버전 검증, P10 4개 지정 버전 검증, P11 새 최선 후보의 3개 버전 재확인, Physlib P05/P06 후보 실험, 최종 포트폴리오 재집계가 남아 있다. 94점 도달은 아직 확인되지 않았다. 커밋과 공식 제출은 하지 않았다.

#### 병렬 연구와 메모리 제한

2026-10-28 사용자의 병렬 에이전트 확대 요청에 따라 P07/P10/P11을 각각 전담하는 3개 에이전트를 가동했다. 루트는 P05/P06과 버전별 검증을 담당한다. 머신은 RAM 16GiB이며 시작 당시 swap 사용량 약 3.9GiB였다.

- `search_agents.py`: 1.5GiB 상한. 원본 또는 공리 검사부터 메모리 예외가 발생했다. 실패 기록을 보존한다.
- `search_agents3.py`: 3GiB 상한과 전역 Lean 최대 2개. P07은 원본/seed 3회 통과. P10은 원본 Check, P11은 원본 동기 측정에서 메모리 예외가 발생했다.
- `search_exclusive4.py`: 4GiB 상한. `resources_exclusive.py`가 두 공유 실행 슬롯을 모두 점유하여 다른 관리 대상 Lean과 겹치지 않게 한다. P10/P11 및 물리 문제의 전체 소스 검증에 사용한다. 따라서 4GiB 프로세스를 세 개 동시에 띄우지 않는다.
- 기존 runner는 실행 설정의 해시와 연결되어 있으므로 수정하지 않고 별도 버전을 만들었다. 메모리 예외는 증명 반례나 수학적 실패로 분류하지 않는다.
- 분석·후보 작성은 3개 에이전트에서 병렬로 진행하며, Lean 검증만 슬롯 대기열을 사용한다. 연구 병렬성과 메모리 집약적 검증 병렬성을 분리한다.

CSLib 4.32/4.33 및 Physlib 4.32의 필요한 의존성 빌드는 완료했다. P05/P06 원본과 보관 후보를 새 검증 환경에서 다시 측정하는 중이다.

#### 후속 관찰: 탐색 비용을 최종 증명에서 분리

- P07: 95-token 제한 Aesop 증명은 실제 전체 소스와 공리 검사를 통과했지만 약 87.6M raw HB로 원본보다 나빴다. 필요한 simp를 먼저 한 번 수행하고 Aesop 내부 simp를 끈 121-token 변형은 약 11.49M raw HB로 통과했다. 현재 단회 탐색 결과이며, 제한된 규칙 집합과 normalization 비용을 별개로 다뤄야 한다는 근거다.
- P05: 복원한 Physlib 4.32에서 원본 1372 / 26,982,659, 보관 후보 527 / 9,490,424를 각 3회 중앙값으로 재확인했다. 이 시점 산식 점수 75.472. 새 후보는 가우스 법칙을 미분한 등식을 별도 증거로 사용해 긴 중간 calc 식을 제거하는 방향이다.
- P06: 같은 환경에서 원본 1217 / 42,056,240, 제출 후보 450 / 14,130,388을 각 3회 중앙값으로 재확인했다. 점수 76.475. 리스트 연결의 결합 구조를 처음부터 맞추어 `have` 후 `simp`를 반복하지 않는 후보를 검증 중이다.
- P10/P11: 4GiB 단독 실행으로 원본·seed 3회 검증을 완료했다. P10 425 / 6,253,250, P11 430 / 7,496,561. 다른 지정 버전 검증은 아직 남아 있다.
- P10 4.28: 이전 버전 실제 타깃의 본문에 공백 한 개 차이가 있어 primary 원문 단순 replace가 실패한다. 명제는 정확히 같음을 확인했다. 이 버전 전용 adapter와 고정 소스/manifest 정보를 준비했고, 실제 dependency 복원 후 검증한다. 공백을 포함한 전체 문맥을 임의로 정규화하지 않는다.


##### 추가 호환성 입력 대조

P10의4.30/4.29 원본에도4.28과 같은 공백 한 개 차이가 있다. 기준4.31의 META.src를 그대로 쓰는 adapter는 전체 파일 대조에서 중단되며 Lean을 실행하지 않는다. 이 실패를 compat/p10-296-*-shared-prelude에 보존했다. 실제 옛 원문을 보존하는 p10_adapter428.py는4.30/4.29의 기존 고정 소스 해시도 검사하므로, 동일 옛 선언임을 확인한 뒤 이를 사용해 다시 검증한다. environment_P11.json은 P10과 같은 Prelude.lean의 고정 import 환경이다.

계측 경계 후속 연구(2026-10-28): [HB-METRIC-AUDIT.ko.md](portfolio-94.md) — async 보조 정리, realization HB 복원, decide +kernel의 차이를 소스·재현 실험으로 정리했다. 기존 점수와 분리된 진단이다.

## 원문: `experiments/portfolio-94/submission-round/README.ko.md`

### HB 조사 이후 15문제 제출 라운드

목표는 앞선 HB 계측 연구와 증명 탐색에서 얻은 후보를 실제 15문제 업로드 파일로 만드는 것이다. 최종 제출은 사용자가 한다. 작업 브랜치는 기존 `exp/cost-hypothesis-pipeline`을 이어 썼고, 공식 제출이나 커밋은 하지 않았다.

#### 구성

- `selection-baseline.json`: 이번 라운드 시작 시점의 후보 경로. 이후 최선 후보와 구분해 보존한다.
- `probe_small.py`, `small_batch.py`: P01·P02·P04·P13·P14·P15의 원본 문맥 Check, 독립 Audit, 동기식 전체 선언 HB 측정.
- `selection-current.json`: 실제 내보낼 후보의 SHA, 검증 기록, 요구 버전 성공 목록.
- `archival-evidence.json`: P01·P02·P03·P13·P14·P15의 과거 성공 기록을 현재 후보 SHA와 대조한 결과. 검증 강도의 차이와 원격 CI 로그 미보유를 명시한다.
- `evidence_gate.py`: 선택의 `verified_pins` 값을 신뢰하지 않고 성공 증거에서 버전을 유도한다. 다른 증명에 이전 성공 기록을 붙이면 실패한다.
- `export_bundle.py`: 정확한 15개 원문 선언, 이름, 공리 검사 증거, 공개 금지 패턴, proof SHA, JSON 왕복 파싱을 확인한 뒤 JSONL와 열람용 JSON을 만든다.
- `export-review.json`: 중간 묶음의 독립 검토.
- `final-export-review.json`: 최종 JSONL SHA에 대한 독립 검토. 파일이 바뀌면 이전 검토를 새 묶음의 검토라고 간주하지 않는다.

결과는 워크트리의 `submissions/warmup-hb-20261028/`에 저장한다. 최종 호환성 상태와 개별 증거는 그 폴더의 `manifest.json`을 기준으로 읽는다.

#### 이번 라운드에서 드러난 점

1. **자동 탐색을 지웠다는 이유만으로 더 좋다고 볼 수 없다.** P04의 `fun_prop`를 실제 Physlib용 `Continuous.inner'`로 바꾸면 raw HB가 1,406,888에서 1,406,735로 조금 줄지만 Length가 123에서 126으로 늘었다. 원본 대비 두 지표를 함께 보아 기존 후보를 유지했다. 앞선 `Continuous.inner` 대체는 이 문맥이 Mathlib의 `InnerProductSpace` 대신 Physlib의 `InnerProductSpace'`를 쓰므로 실패했다.
2. **명시할 부분과 추론시킬 부분을 함께 선택해야 한다.** P13에서 감소 조건에 `Nat.sub_lt`를 명시하면 HB가 줄지만 인덱스까지 반복하면 259→263 tokens가 된다. 인덱스를 `_`로 추론시키면 259 tokens를 유지하고 같은 환경의 raw HB가 3,659,724(기존 1회)→3,522,969(새 후보 3회 중앙값)로 감소했다. 새 후보는 전체 3개 요구 버전의 Check/Audit를 통과해 채택했다.
3. **P05·P06·P10·P11은 이득이 큰 구조적 후보를 확정하는 데 집중했다.** 분모의 순서, 쌍선형 기저를 통한 extensionality, cardinality/coercion 명시, 계수 순서와 `rfl`이 핵심이다. 성공했던 빠른 탐색 결과를 그대로 제출 확정으로 취급하지 않고 별도 Check/Audit와 HB 3회로 재검증했다.
4. **이미 해 본 실패 실험을 재사용하면 탐색 낭비를 줄일 수 있다.** P08의 직접 `refl`, 명시 witness, `let`/`match` 후보는 이전에 길이나 HB가 악화했다. 이번 읽기 전용 재검토에서도 더 나은 국소 변경의 근거가 없어 185-token 후보를 유지했다.
5. **내보내기 자체에도 후보 혼동 방지가 필요하다.** 초기 exporter는 `verified_pins`를 그대로 믿었다. 독립 검토 후 실제 증거의 proof SHA와 성공 버전에서 상태를 유도하도록 수정했다. 다른 유효한 증명으로 바꾸고 예전 증거를 유지한 사례들을 의도적으로 넣어 모두 거부되는지 확인했다.

#### 계측 연구와 제출 코드의 관계

`HB-METRIC-AUDIT.ko.md`의 counter restore/async 경계 실험은 측정 의미를 이해하기 위한 진단이다. 이번 제출에는 임의 counter 변경이나 커스텀 메타프로그램을 넣지 않았다. 함수 귀납 원리와 기존 정리의 재사용처럼 실제 증명에 적용할 수 있고 검증을 통과한 방법을 사용했다. P15에서는 `decide +kernel`, 일반 `decide`, `rfl`을 실제 닫힌 산술 목표에서 비교했다. 일반 `decide`와 불필요한 `push_cast` 제거 후 `ring1`을 결합한 후보가 283→281 tokens, 같은 4.25 환경 raw HB 2,628,784(기존 1회)→2,499,913(새 후보 3회 중앙값)으로 개선했다. 4.25·4.26·4.27의 Check/Audit를 모두 통과해 채택했다.

여러 후보를 찾는 데 쓴 시간은 제출 HB와 구분한다. 소스 코드가 짧아지는 변경과 검증 과정이 덜 드는 변경도 구분한다. 로컬 추정 점수, 역사적 공식 기록, 현재 공식 서버의 미확인 점수를 하나의 확정 수치로 섞지 않는다.

#### 최종 산출물

`submissions/warmup-hb-20261028/submission.jsonl`을 `--require-complete` 옵션으로 내보냈다. 필수 36개 문제·버전 조합의 증거가 모두 연결됐으며 pending은 없다. JSONL SHA-256은 `6ac28ac0292fd20a522bffb51734c74c30a6b7163f97c3f6955fe59fd6efa212`, 크기는 21,686 bytes다. 제출 Length 합계는 2,722 tokens, 문제별 평균 Length 감소율은 79.8465%다. 공식 제출과 채점은 아직 하지 않았다.
