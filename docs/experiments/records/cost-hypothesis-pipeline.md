# 비용 가설 A/B 파이프라인

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

P01·P13×A/B×2반복, 총48후보를 계획하고 후보 registry·family·Pareto·회계·replay를 비교한다.

## 확인된 결과와 해석

보존된 README의 최신 조회는 41/48평가·6/8실행 완료. PROGRESS의 31평가 기록은 앞선 디스크 중단 시점이다. 전체 완료 A/B 결과로 취급하지 않는다.

## 코드·Lean 보존 결정

원본은 아카이브 커밋. 잔여 비율·구조 부모·Pareto 개념은 PR #46 공통 정책으로 옮기고 구형 실행기는 제외한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/cost-hypothesis-pipeline/INSIGHTS.ko.md` | `3ee67de` | `43051a8f7e72afb9d98425aae7e30e4823a6a6b9c59790f59d064d8ad0c94786` |
| `experiments/cost-hypothesis-pipeline/ORDERING_FIX.ko.md` | `3ee67de` | `cf543fbbda662e4eb20f18b3e5a47d187d54276c52e4908c8b3cef9b5340f06b` |
| `experiments/cost-hypothesis-pipeline/README.md` | `3ee67de` | `24be48b18737501be699fee0a685076ed5c277ccea5b3c93ce8c2e8ee43ce228` |

## 원문: `experiments/cost-hypothesis-pipeline/INSIGHTS.ko.md`

### 비용 가설 파이프라인: 결과를 이해하는 순서

> 작성 중. 31/48개 평가 후 디스크 부족으로 중단됐다가 공간 확보 후 재개했다. [실행 현황](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/cost-hypothesis-pipeline/PROGRESS.ko.md). 8개 독립 실행과 마지막 runtime 검사가 모두 끝난 뒤 결과와 결론을 확정한다.

#### 1. 무엇을 검증했나

첫 하네스의 자유 탐색을 대조군 A로 두고, B에는 비용 가설·단계 지침·분기별 부모·Pareto 대안을 함께 넣었다. 핵심 질문은 “같은 여섯 번의 후보 제출로 더 싼 유효 증명을 얻는가?”다. 이 비교는 모델 계산량을 맞춘 비교도, 각각의 기능을 분리한 실험도 아니다.

원본 성능은 같은 환경에서 새로 측정하고 두 조건이 공유한다. 원본 대비 증명 토큰 비율과 raw heartbeat 비율의 평균을 local cost로 사용한다. 낮을수록 좋고 원본은 1이다. 공식 LB 점수와 구분한다.

#### 2. 하네스에서 달라진 부분

1. **입력 고정:** 원본 전체 문맥, 컴파일러·라이브러리와 프롬프트를 스냅샷으로 남긴다.
2. **후보 생성:** A는 기존 자유 탐색, B는 어디의 어떤 작업을 없앨 것인지 짧은 가설과 부모를 기록한다.
3. **검증·측정:** 두 조건 모두 전체 소스 컴파일, fresh 계측 세 번, target 공리 검사를 수행한다. 실패도 후보 예산을 소비한다.
4. **선택·기억:** 종합 비용 best를 보존하고, B에는 다른 분기의 부모와 길이/HB Pareto 후보도 제한적으로 제시한다. 원본은 fallback이다.
5. **완료 검사:** 선택본을 다시 검증하고, 기록으로 요청과 상태 전이를 replay하며 공유 runtime의 전후 hash를 확인한다.

구현과 실행 명령은 [README](cost-hypothesis-pipeline.md), 해석 기준은 [분석 계획](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/cost-hypothesis-pipeline/ANALYSIS_PLAN.ko.md)에 있다.

#### 3. 측정과 함께 읽어야 할 사례

##### P01: 짧아지는 것과 싸지는 것은 다르다

A의 첫 반복에서 24토큰 후보는 raw HB가 10,068,529였다. 뒤의 35토큰 후보는 3,504,141로 줄었다. 더 짧은 증명이 종합 목적함수에서도 더 좋을 것이라고 가정하면 이 차이를 놓친다.

B의 첫 반복에서는 `grind` 범위를 제한한 변경의 HB 감소가 매우 작았다(12,288,359 → 12,271,687). 다음 후보에서 반복적인 `simp_all`을 한 번의 단순화로 바꾸자 5,964,219로 줄었다. 이 수치는 각 전체 후보의 측정값이며 구간 profiler의 원인 분해 결과는 아니다. 실패한 가설도 다음 변경을 좁히는 근거로 남겨야 한다.

P01 B의 두 번째 반복에서도 문맥 단순화 범위를 바꾼 후보 4→5에서 raw HB가 5,940,942→4,451,307로 줄었다. 처음부터 일반 `simp ... at *`를 적용하는 대신 목표를 먼저 단순화하고, 분기 이후 가정에는 `simp only`로 변수·리스트 멤버십 표현 규칙만 적용했다. 토큰은 32→37로 늘었고 종합 비용은 0.625310→0.489324로 좋아졌다. 이는 `simp only`를 무조건 쓰자는 규칙보다 **어떤 문맥을 어떤 규칙으로 다시 처리하는가**를 확인할 이유가 된다.

##### P13: 같은 수학적 구조에 도달해도 표현 비용은 다르다

첫 반복의 A와 B 모두 유한 구간의 반복 상태와 강한 귀납법을 사용했다. 따라서 이 전략을 B만의 발견으로 해석할 수 없다. B 내부에서는 유한성 증명을 현재 표현에 맞는 `Set.finite_Icc`로 직접 연결하고 기존 좌표별 경계를 tuple로 공급한 후보에서 HB가 65,046,424 → 20,235,598로 감소했다. 이어 충돌 증거를 직접 전달하며 중복 existential 포장을 줄인 후보는 6,375,735였다.

각 후보에는 여러 관련 편집이 있으므로 특정 tactic 하나가 그 감소 전체를 만들었다고 주장하지 않는다. 실제 선택본과 후보 계보를 함께 읽어야 한다.

##### P13의 작은 경계 변경: 기존 증거를 바로 전달하기

A의 두 번째 반복에서 후보 1→2의 proof diff는 아래 기저 사례 블록에만 있었다.

```lean
-- 후보 1
interval_cases m <;> simp_all

-- 후보 2
interval_cases m
· simpa only [Nat.add_zero] using he.1
· exact he.2.1
· exact he.2.2.1
· exact he.2.2.2
```

토큰은 562→577로 늘었지만 raw HB는 23,891,912→6,239,574로 줄었다. 전체 비용은 0.262119→0.190057이었다. 다른 블록까지 함께 바뀐 사례보다 변경 위치를 좁혀 해석할 수 있는 증거다. 다만 tactic별 시간을 직접 계측한 것은 아니다.

이미 `he`에 있는 네 등식을 각각 전달하면 되는 경계에서 전체 문맥을 다시 단순화할 필요가 없었다. 그렇다고 증명 전체를 수동 term으로 바꾸자는 결론은 아니다. 이런 경계를 찾아 자동화의 일을 줄이는 것이 다음 실험의 구체적인 후보가 된다. 이 개선이 A에서도 발견됐으므로 B 프롬프트만의 효과로 세지 않는다.

##### 귀납의 대상 자체를 다시 고르기

P13 A의 두 번째 반복은 후보 3에서 개별 항 `u (i+m) = u (j+m)` 대신 네 연속 항을 묶은 상태 `f (i+m) = f (j+m)`를 귀납 명제로 사용했다. 초기 상태의 일치 `he`를 그대로 기저 사례에 쓰고, 다음 상태의 앞 세 좌표는 귀납 가정의 뒤 세 좌표를 재사용한다. 새로 증명할 것은 마지막 좌표 하나뿐이다.

이 변경 하나로 HB가 줄지는 않았다. 후보 2→3은 raw HB 6,239,574→6,437,151, 토큰 577→547이었다. 종합 비용은 0.190057→0.182431로 개선됐다. 후보 4에서는 중복된 `change` 명제를 제거해 475토큰, 후보 5에서는 중간 포장과 마지막 인덱스 처리를 정리해 427토큰·5,832,123 HB에 도달했다.

이는 더 강한 불변식이 자동으로 더 싼 HB를 준다는 증거가 아니다. 대신 **원하는 결론과 재사용할 증거에 맞춰 귀납 대상을 바꾸면 이후 줄일 수 있는 작업이 달라진다**는 사례다. A가 중간 회차에도 구조를 바꿨다는 점은 고정 단계 지침의 필요성을 별도로 검증할 이유가 된다.

##### 후보 기록의 이점과 성능의 이점은 별개다

B의 P01 첫 반복은 종합 best가 아닌 유효 후보를 부모로 삼아 계속 수정했다. 이런 경로가 실제로 사용됐다는 점은 확인할 수 있다. 다만 A 역시 자기 대화·요청·응답 이력을 유지하므로 “A는 기억이 없고 B만 기억이 있다”는 비교는 아니다. B의 유효 후보 수나 기록의 상세함만으로 최종 비용 개선을 주장하지 않는다.

#### 4. 재현성에서 발견한 결함

JSON 저장 전후 dictionary 순서가 달라져 replay가 실패하는 문제가 있었다. 부모 선택 전에 family를 정렬하도록 고쳤고, 기존 요청 20개가 수정된 정책과 같음을 확인했다. 원래 trial 스냅샷과 측정은 보존하고 별도로 고정한 bridge를 통해 후속 실행했다.

정렬은 이후 노출되는 부모의 순서뿐 아니라 구성도 바꿀 수 있다. 따라서 “사전에 고정한 코드가 수정 없이 끝났다”고 표현하지 않는다. 자세한 증거와 적용 시점은 [수정 이력](cost-hypothesis-pipeline.md)에 있다.

디스크 사전 검사에서도 두 제출이 Lean 실행 전에 중단됐다. 원래 응답과 후보를 보존한 복구 경로를 준비했으며, 공간 확보 후 같은 후보를 이어서 평가한다. [복구 절차](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/cost-hypothesis-pipeline/STORAGE_RECOVERY.ko.md)에 재개 조건과 검사를 기록했다.

#### 5. 아직 확정하지 않을 것

- 두 개발 문제·조건별 두 반복으로 통계적 우위나 새로운 문제에서의 일반화를 주장하지 않는다.
- 프롬프트, 단계 지침, 부모 기억 중 어느 기능이 효과를 냈는지 분리하지 않는다.
- syntax count를 profiler로 부르지 않는다.
- 요청 bytes를 모델 토큰·청구 비용으로 바꾸어 해석하지 않는다.
- 주 Lean 버전 결과를 공식 LB 또는 모든 버전 호환 결과로 보고하지 않는다.

#### 6. 후속 실험 후보 — 아직 검증된 결론은 아님

이번 묶음이 이기든 지든 다음 비교에서는 요소를 분리할 필요가 있다.

1. **자유 탐색에 비용 힌트만 추가하기:** 단계 순서와 “한 번에 한 주요 변경” 지침을 빼고, 이미 있는 증거의 직접 전달과 반복 문맥 단순화 제거만 짧게 제시한다. 비용 가설을 설명하는 부담과 탐색 제한을 구분한다.
2. **정체될 때만 진단하기:** 처음부터 매번 큰 구조화 요청을 보내는 대신, 개선이 정체됐을 때 후보 diff·오류·계측을 바탕으로 다른 분기로 전환한다. 전환 조건은 새 실험 전에 고정한다.
3. **부모 기억의 효과를 따로 검증하기:** 현재 A도 자기 대화 이력이 있으므로 명시적 registry의 인과 효과를 분리할 수 없다. 후속 비교에서는 후보별 모델 문맥 관리도 맞추고, 부모 후보를 항상 주는 방식과 필요할 때 조회하는 방식을 비교한다.
4. **측정 횟수와 탐색 시간을 함께 설계하기:** 현재 세 번의 후보 계측과 최종 재검증에서 관측된 변동을 확인한 뒤, 후보는 빠르게 선별하고 최종 후보만 반복 측정하는 정책을 별도 비교한다. 이번 코호트의 측정 횟수는 바꾸지 않는다.

새 문제를 미리 정하고 반복 수를 늘린 뒤 비교해야 한다. 지금 관찰한 성공 사례에 맞춰 같은 문제의 프롬프트만 계속 조정한 결과를 일반화 성능이라고 부르지 않는다.

최종 비교표와 현재 권장 운영 방식은 전체 실행 종료 후 이 문서에 연결한다.

## 원문: `experiments/cost-hypothesis-pipeline/ORDERING_FIX.ko.md`

### 첫 pilot의 부모 순서 수정

2026-10-25 10:47 UTC, 첫 P13-B 실행을 재생하면서 발견한 구현 결함을 수정했다.
당시 완료된 제안은 P01-A-r1 6개, P13-B-r1 6개, P01-B-r1 2개였다.
새 solver 배정을 잠시 멈추고 진행 중이던 solver도 현재 submit 이후에 대기시켰다.

#### 원인과 영향

`parents` dictionary의 삽입 순서와 JSON의 key 정렬 순서가 달랐다.
예를 들어 메모리의 structure → representation → evidence 순서가 저장 후
evidence → representation → structure가 됐다. 요청의 alternatives는 list이므로
같은 후보 집합이어도 순서가 다르면 동일한 요청으로 볼 수 없다.
P13-B-r1의 기존 replay는 4번째 요청에서 이 차이로 실패했다.

평가 지표와 선택 상태는 일치했다. 그렇더라도 replay 실패를 무시하지 않고,
요청이 프로세스 경계를 넘어 동일하게 생성되도록 family 이름 정렬을 명시했다.
새 회귀 테스트는 최선 후보를 추가하는 경우와 비최선 부모를 추가하는 경우 모두에서
`packet(state) == packet(JSON roundtrip(state))`를 검사한다.

정렬은 마지막 세 family를 고르는 **앞**에서 일어난다. 따라서 아직 관측하지 않은
미래 상태에서는 순서뿐 아니라 노출되는 부모 구성도 바뀔 수 있다. 예를 들어 기존
representation/sharing/structure 뒤에 compression을 추가한 경우, 예전 방식은
sharing/structure/compression, 수정 방식은 representation/sharing/structure를 고른다.
이는 단순 표시 변경이 아니라 부모 선택을 결정적으로 만드는 정책 수정이다.
기존 요청 20개의 동일성이 미래 treatment 전체의 동일성을 증명하는 것은 아니다.

#### 기존 측정을 보존한 방법

- 원래 trial의 code, manifest, 요청, 응답, 소스, 계측 로그를 수정하지 않았다.
- `policy.py`의 부모 순회 한 줄만 바꾼 사본과 bridge를 코호트의
  `amendments/canonical-parent-order/`에 별도로 고정했다.
- bridge는 자신과 정책의 SHA256을 검사하고, 정책 변경이 정확히 그 한 줄인지 확인한다.
  원래 worker의 평가·예산·선택·기록 코드를 그대로 호출한다.
- 당시 생성돼 있던 요청 **20개 전부**가 수정 정책과 동일함을 확인했다.
  비교 기록은 `existing-request-equivalence.json`에 있다.
- 완료된 P01-A-r1·P13-B-r1 모두 수정된 replay를 통과했다. 새 Lean 측정이나 모델
  재실행으로 결과를 바꾸지 않았다.
- 이후 A/B 모두 같은 bridge를 사용한다. 기존 P01-B-r1 solver는 자신의 3번째 요청부터
  계속하며, 6개라는 총 제안 예산과 원래 독립 실행 단위를 유지한다.
- bridge의 submit/finish 호출은 별도 invocation 로그로 남고, 집계기가 나머지 예산과 대조한다.

최초 고정 코드가 수정 없이 실험을 끝냈다고 주장하지 않는다. 이는 실행 중 발견한
정렬 결함에 대한 명시적인 수정이며, 모델에 이미 제공한 입력이나 관측 결과는 바꾸지 않았다.

#### 실행 경로

새 코호트는 수정된 `policy.py`를 준비 단계에서 복사하므로 일반 `worker.py`를 쓴다.
이 첫 코호트는 보존된 구버전 스냅샷 대신 아래 entrypoint를 사용해야 한다.

```sh
python3 -B <cohort>/amendments/canonical-parent-order/canonical_order_bridge.py replay <trial>
```

submit과 finish도 같은 entrypoint를 사용한다. `report.py`는 이 수정이 있는 코호트에서
자동으로 bridge를 사용하고 기존 요청 hash·수정 코드 hash·후속 호출 수를 함께 감사한다.

## 원문: `experiments/cost-hypothesis-pipeline/README.md`

### 비용 가설을 사용하는 Lean 리팩터 파이프라인

브랜치 `exp/cost-hypothesis-pipeline`. 첫 하네스가 보존된
`exp/feedback-followup-20261025`의 `93cc6bb`에서 별도 worktree로 시작했다.
기존 첫 하네스와 다른 작업의 미추적 파일을 수정하지 않는다.

#### 현재 실행 상태

2026-10-27 상태 조회 기준 48개 후보 중 41개 평가 기록이 있으며, 독립 실행 8개 중 6개가 완료됐다.
P01-A-r2는 5/6, P13-B-r2는 평가 완료 기록이 0/6이다. pending 표시는 현재 프로세스 생존을 보장하지 않는다.
이전에는 31개 평가 후 디스크 사전 검사에서 중단됐으나, 공간 확보 후 저장된 후보부터 재개했다.
[실행 현황](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/cost-hypothesis-pipeline/PROGRESS.ko.md), [인사이트 초안](cost-hypothesis-pipeline.md),
[기록을 보존한 재개 절차](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/cost-hypothesis-pipeline/STORAGE_RECOVERY.ko.md)를 참고한다. 전체 비교 결과는 아직 확정하지 않았다.

기존 연구와 공개 산식을 연결한 [94점 목표 전략](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/cost-hypothesis-pipeline/STRATEGY_94.ko.md)에 길이·HB별 병목,
측정 착시 확인 항목, 검색 기능과 구간 진단을 분리한 다음 실험안을 정리했다.
이는 새 Lean 실험 결과가 아니라 2026-10-27의 전략 분석이다.

#### 실험 질문

원본과 최선·직전 후보만 제공하는 자유 탐색에 비해, **없앨 증명 작업에 대한 가설,
단계별 탐색 지침, 분기별 부모와 Pareto 대안**을 함께 제공하면 같은 후보 예산에서
더 좋은 검증된 증명을 얻는가?

이번 비교는 프롬프트와 상태 관리의 묶음이다. 개별 문장이나 개별 기능의 효과를
분리하는 ablation은 아니다. P01·P13은 개발에 사용한 문제이므로 일반화 평가가 아니다.

#### 바꾼 구조

```text
원래 전체 소스와 runtime 고정
  → 원본 plain compile와 fresh measurement 3회
  → 문제별 공통 baseline 고정
  → 독립 solver에 원본과 요청만 제공
  → 후보 제안
      A: proof
      B: proof + 부모 + 변경 위치 + 변경 종류 + 줄어들 작업의 가설
  → 원문 검증 + fresh measurement 3회 + target 공리 검사
  → 전체 후보 기록 / 종합점수 best / 분기별 부모 / Pareto 갱신
  → 실패 진단 또는 다음 단계 요청
  → 6개 후보 예산 종료
  → 선택본 재검증 / 기록 replay / 결과 집계
```

B 요청은 초반 구조 변경, 중반 불필요한 추론·반복 제거, 후반 정리·압축을 제시한다.
실패 시에는 수리 또는 가설 포기를 제시한다. 이는 강제 tactic 순서가 아니라
현재 상태에 따른 탐색 지침이며, 실제 선택한 family와 parent를 기록한다.
명제에 맞는 정리, 더 적절한 귀납, 기존 증거·witness·instance의 직접 전달을 우선한다.
`clear`, `simp only`, 공유, 명시적 term을 보편적인 개선 규칙으로 취급하지 않는다.

syntax inventory는 원문 구문 횟수일 뿐 profiler가 아니다. 실제 구간 프로파일링과
라이브러리 검색 도구는 이번 파일 기반 solver 인터페이스에 추가하지 않았다.
정확한 원인 분해가 필요한 후보는 후속 진단 대상으로 남긴다.

#### 공통 평가와 선택

두 조건은 같은 원문·baseline·검증기·오류 피드백·6개 후보 예산을 사용한다.
선택은 `tokens × baseline_raw + raw × baseline_tokens` 최소화로 하고,
동점은 토큰과 선언 SHA256으로 결정한다. 원본이 유효한 fallback이다.
후보가 짧아져도 HB가 늘면 종합 목적함수로 판단한다.

실패와 중복 제출도 예산을 소비한다. 같은 선언을 다시 측정한 값으로 등록 지표를
덮어쓰지 않아, 반복 측정의 작은 변동으로 best가 개선되는 것을 막는다.
증명 항이 같아도 소스가 다른 후보는 서로 보존한다.
두 조건의 컴파일 통과 후보에 모두 3회 계측을 적용해 측정 절차를 맞췄다.
실제 총 평가 작업 수·시간은 성공과 실패에 따라 달라진다. 공유 머신의 부하를 통제하지 않아 실행 초는 조건별 속도의 인과 비교로 해석하지 않는다.
최종 재검증이나 환경 동일성 검사가 실패하면 집계기는 비교 점수 표를 발행하지 않는다.
요약에 기록된 baseline·선택본·유효 후보 수도 재생된 상태와 대조한다.

B는 유효한 후보 전체를 registry에 남기고, family별 종합점수 최선과 Pareto 대안을
다음 요청에서 제한된 수만 노출한다. 실패 카드와 실제 피드백도 기록한다.
가설 설명은 짧은 공개 실험 메모이며 모델의 내부 추론 추적을 요구하지 않는다.

#### 고정 실험 조건

- P01·P13 × A/B × 조건별 두 반복 = 독립 실행 8개, 후보 48개.
- 관측 회차 2·4·6. 문제별 최종 local cost와 유효 후보 수, HB·길이 및 반복 편차를 보고한다.
- solver 최대 2개, Lean 평가 최대 1개. 코호트 공통 파일 잠금으로 직렬화한다.
- 각 solver는 `fork_turns=none`으로 시작하며 자기 입력·요청·피드백만 읽는다.
- 과거 해답과 이 대화의 증명 코드는 solver 입력에 넣지 않는다.
- 기존 원본 입력과 runtime 연결만 재사용하며 원본 성능은 새로 측정한다.
- 컴파일러·라이브러리는 읽기 전용으로 사용하고 실행 전후 파일 SHA256을 비교한다.
- 모델 backend는 Codex 서브에이전트이며 정확한 모델 ID·seed·내부 호출량·청구 비용은 관측할 수 없다.
- OpenRouter나 별도 유료 API를 호출하지 않는다. Codex 사용 비용을 0달러라고 기록하지 않는다.
- 파일 접근은 지시로 제한하며 OS 수준 격리를 주장하지 않는다.
- 각 solver는 자기 대화·요청·응답 이력을 유지한다. A도 과거 후보를 기억하거나 다시 읽을 수 있으므로 B의 명시적 registry만이 기억의 유일한 출처는 아니다.
- 주 환경 Lean 4.26만 비교하며 결과를 공식 LB 점수로 보고하지 않는다.

#### 실행과 재현

저장소 루트에서 실행한다. 기존 환경이 준비되어 있어야 한다.

```sh
python3 -B experiments/cost-hypothesis-pipeline/prepare.py \
  --output runs/cost-hypothesis-pipeline/new-cohort \
  --legacy-runs /absolute/path/to/original-repo/runs/first-harness-jwkweon
```

독립 solver는 할당된 trial의 `requests/001.json`과 `input/source.lean`을 읽고
`responses/001.json`에 정확한 응답 JSON을 저장한다. 그다음 스냅샷 코드를 실행한다.

```sh
python3 -B <trial>/code/worker.py submit <trial> --response <trial>/responses/001.json
# 다음 requests/002.json을 읽고 같은 절차로 고정 예산까지 진행
python3 -B <trial>/code/worker.py finish <trial>
python3 -B <trial>/code/worker.py replay <trial>
```

replay는 저장된 요청·응답·평가로 상태와 선택을 재계산하며 모델이나 Lean을 호출하지 않는다.
실행 기록은 덮어쓰지 않는다. 모든 작업에는 새 output 경로를 사용한다.

이 버전의 모델 실행은 수동 Codex 서브에이전트 bridge다. `prepare.py` 자체가 모델을
호출하지는 않는다. coordinator가 `design.frozen.json` 순서로 `fork_turns=none`의
새 agent를 배정하고, 최대 두 개의 solver를 유지한다. `SOLVER_DISPATCH.txt`의 경로를
치환해 동일한 운영 지시를 전달한다. 조건별 전략은 trial의 고정된 prompt에만 들어 있다.
coordinator는 코호트의 `dispatch.jsonl`에 `dispatched`/`completed`, `trial_id`,
`agent`, `observed_at`을 기록하며 dispatched에는 `fork_turns: "none"`을 포함한다.
처음 pilot의 두 agent는 초기화 완료를 제한된 시간 동안 기다린 뒤 동일 절차를 시작했다.

공유 runtime의 전후 inventory는 readiness 폴더별로 기록한다. 모든 trial 완료 후
집계기는 입력·코드·평가 로그·공리·fresh nonce·replay·dispatch·runtime을 검사한다.

```sh
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P01 before
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P13 before
# 위 before는 solver 시작 전, 아래 after는 모든 Lean 실행이 끝난 뒤 실행한다.
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P01 after
python3 -B experiments/first-harness-jwkweon/feedback-ablation-v1/runtime_inventory.py <cohort>/readiness-P13 after
python3 -B experiments/cost-hypothesis-pipeline/report.py <cohort> --output <new-results-directory>
```

결과를 해석하는 기준과 후속 검증 방향은 [분석 계획](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/cost-hypothesis-pipeline/ANALYSIS_PLAN.ko.md)에 적었다.

첫 pilot에서는 JSON 저장 전후 부모 순서가 달라지는 replay 결함을 발견해 수정했다.
원래 측정 기록과 기존 요청 20개를 보존·대조한 절차 및 해당 코호트 전용 실행 경로는
[정렬 수정 이력](cost-hypothesis-pipeline.md)에 있다. 새 코호트에는 수정된 정책이 바로 적용된다.

#### 코드와 검증

| 파일 | 책임 |
|---|---|
| `policy.py` | 응답 카드 검증, registry·분기 부모·Pareto, 단계별 요청과 순수 상태 전이 |
| `worker.py` | immutable 기록, Lean 직렬 평가, 최종 검증과 replay |
| `prepare.py` | 원본 입력·실행 코드 스냅샷, 원본 재측정, 독립 trial 준비 |
| `prompts/` | A 자유 탐색과 B 비용 가설 프롬프트 |
| `error_feedback.py` | 이전 피드백 실험의 structured_v1 formatter를 두 조건 공통으로 재사용 |
| `test_policy.py` | 무효 후보 배제, 길이/HB 교환, 분기 보존, 중복 측정, 요청 정책 검증 |
| `report.py`, `test_report.py` | 결과·탐색 비용 집계와 증거 불일치/변조 거절 검증 |
| `status.py` | 모델·Lean 호출 없이 현재 진행 상태 조회 |

원래 검증기·토큰 계산·공리 허용 목록은 `first-harness-jwkweon`에서 그대로 복사해 실행한다.
검증기의 공리 검사는 target을 계측하는 명령에서 수행한다. 원문 전체 plain compile는 별도다.
기존 연구의 별도 importer 공리 감사와 동일하다고 표현하지 않는다.

```sh
python3 -B -m unittest discover -s experiments/cost-hypothesis-pipeline -p 'test_*.py' -v
python3 -B -m unittest discover -s experiments/first-harness-jwkweon -p 'test_*.py' -v
```

공식 문서의 명확한 입력·출력 계약과 실제 workload 검증 원칙을 참고했다.
실험은 API tool calling을 추가하는 대신 기존 manual bridge를 유지한다.
[OpenAI prompting guidance](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra#prompting-best-practices)
