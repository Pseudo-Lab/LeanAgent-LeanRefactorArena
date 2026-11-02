# HB 계측 경계: 비동기 옵션의 적용 위치

후속 연구: [HB-METRIC-AUDIT.ko.md](HB-METRIC-AUDIT.ko.md). proof-local async가 **보조 정리의 kernel task**에는 영향을 주는 별도 경계를 재현했다. 아래의 주 정리 scheduling 관측과 구분해야 한다. 실제 P11 비교와 realization counter 복원도 후속 문서에 기록했다.

2026-10-28의 별도 로컬 toy 진단이다. 대회 후보, 공식 worker 검증, 점수 개선으로 취급하지 않는다. 실제 후보 평가기의 코드나 옵션은 변경하지 않았다.

## 관측

Lean4.32에서 `(List.range 100).length = 100`을 `by decide`로 증명하고, 정리 명령의 elaboration 앞뒤 raw HB 차이를 비교했다. 세 정리는 모두 컴파일되었고 공리 의존성도 없었다.

| 진단 조건 | raw HB |
|---|---:|
| 정리 명령을 동기로 실행 |129,328|
| 동기 정리의 **증명 내부**에서 Elab.async=true |129,532|
| 계측 wrapper 안에서 **정리 명령 바깥**을 Elab.async=true로 변경 |7,503|

마지막 행은 비동기로 미룬 작업을 명령 반환 시점의 counter가 충분히 포함하지 않는다는 toy 측정 경계 사례다. 작업 자체가 제거된 결과로 해석하지 않는다. 제출 증명 내부 옵션은 같은 효과를 내지 않았다.

## 소스에서 확인한 이유

Lean4.32 `Lean/Elab/MutualDef.lean`의1238행 부근은 헤더를 elaboration한 뒤, **정리 본문 실행 전에** `Elab.async`를 읽어 `elabAsync` 또는 `elabSync`를 선택한다. 본문에서 바꾼 옵션이 이미 내려진 바깥 명령의 선택을 소급해서 바꾸지 않는다.

`Lean/Elab/Tactic/AsAuxLemma.lean`도 먼저 내부 tactic을 실행하여 목표를 모두 닫고, 그 뒤 완성된 표현식으로 `mkAuxTheorem`을 만든다. 이 소스만으로 as_aux_lemma가 본문 탐색을 계측 밖으로 옮긴다고 볼 근거는 없다. 이전 실제 P07/P11 whole-proof 실험도 이득이 없었다.

## 대회 결과와 구분

현재 공개 규정 스냅샷은 benchmark statement plus a proof를 제출하도록 하며 임의의 보조 최상위 선언 등을 금지한다. 마지막 toy 행은 정리 선언 바깥 명령 구조를 바꾼 것이므로 그대로 제출용 proof 교체로 사용할 수 없다. private worker 구현까지 확인한 것은 아니므로 현재 대회에서 이 설정으로 점수를 우회할 수 있다고 주장하지 않는다.

공개 필터가 모든 set_option을 금지하는 것은 아니지만, 로컬 제출 validator는 더 엄격하다. 이 차이를 근거 없이 이용해 인증된 점수로 기록하지 않았다.

## 재현 증거

- 소스/로그/명령/해시: `../../runs/portfolio-94/diagnostics/async-boundary-4096/Boundary.{lean,log,json}`
- 첫1GiB 제한 시도: `../../runs/portfolio-94/diagnostics/async-boundary/` — wrapper elaboration부터 memory error. 실패 그대로 보존했고 수학적 실패나 수치 관측으로 사용하지 않았다.
- 성공 재시도는 기존 독점 resource lease와4GiB 제한을 사용했다.
- 공개 규정 스냅샷 출처와해시: `rules/sources.json`, `rules/app.py`.
