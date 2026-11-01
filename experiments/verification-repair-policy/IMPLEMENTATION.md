# PR B: Auto Solver → Recursive Repair

[PR A의 설계](README.md)와 [이슈 #40](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/40)를 구현한다.
이 문서는 PR B의 **고정 응답을 사용하는 fixture Controller**를 설명한다.
후속으로 [#37 설계 기반 Planner/Worker 생성 루프](INTEGRATION.md)를 별도 추가했다.
새 루프의 실제 Lean 검사는 고정 응답으로 실행하며, 실제 LLM 실험은 아직 실행하지 않았다.
#37 작성자의 미공유 구현을 통합했다고 주장하지 않는다.

## 구현 구조

| 파일 | 책임 |
| --- | --- |
| `Support.lean` | native InfoTree에서 전술 전후 목표, 지역 가정·정의·binder 정보, UTF-8 source 범위와 오류 코드·위치 수집 |
| `native.py` | 고정 문맥에 진단 도구 삽입, native 상태와 수정 위치 대응, 하위 증명 삽입, 공통 평가기 호출 |
| `repair.py` | 자동 전술 → 미해결 목표의 Worker 요청 → 자식 수리 → 부모 재조립, 깊이·순환·호출 제한 |
| `runtime.py` | 루트 실행 소유의 예산·시계·중복 집합, 고정 응답 transport, 요청 전 기록, 관측 기록과 재생 |
| `adapter.py` | 제안하는 `repair_candidate` 연결점, 한 후보를 처리하는 fixture Controller, best 선택과 최종 검증 |
| `common.py` | 고정 한도와 공통 도구. 기존 `api-comparison/compare.py`의 예약·정산·원자적 저장 재사용 |
| `run.py` | prepare/check/run/replay/status, 입력·실행 코드 보존, API 호출 차단 |

기존 이분법 정책과 전용 프롬프트·테스트는 교체했다. 이전 budget runner에 추가했던 정책 hook도 제거했다.
공통 `src/` 평가·수락 규칙은 유지한다. 모델 응답 파싱, 비용 영수증, 예산 예약·정산, 상태 기록을 재사용한다.
실행 코드가 `experiments/openrouter-budget-trial/run.py`를 import하지 않으므로 #37의 runner 이름 변경에 직접 묶이지 않는다.

## 실제 수리 범위

전체 `by` proof와 native 위치·문맥을 확보할 수 있는 중첩 `have ... := by ...`, bullet의 전술 구간을 다룬다.
구체적 오류에는 실패 전술부터 해당 전술 sequence 끝까지를 수정한다.
미해결 목표에는 해당 sequence 끝에 증명을 추가한다. 문자열에서 목표를 추측하지 않는다.

각 목표에 `exact (by ...)`를 삽입해 하나의 하위 증명 범위를 만든다.
Worker가 만든 이 범위 안에 새 미해결 목표가 생기면 자식 노드로 내려간다.
범위 밖에 남은 목표는 같은 루트의 다음 목표로 처리한다. source 이동량을 반영해 부모 범위를 갱신한다.
하위 증명 완료는 native 상태와 해당 범위의 오류 부재로 확인하며, 루트 전체의 수락은 별도 공통 평가기가 맡는다.
재조립 검증도 같은 수리용 호출·시간 한도를 사용한다. 전체 평가에 필요한 최대 4회분이 남아 있어야 시작한다.

기본 전술 순서는 `rfl`, `assumption`, `trivial`, `simp`, `omega`, `grind`다.
고정 환경에서 native parser로 가용성을 먼저 확인한다. 파싱 가능과 목표 해결은 다르다.
해당 목표를 닫지 못한 자동 전술 시도는 되돌린다. 자동 전술 조합의 무제한 탐색은 하지 않는다.
진단 도구가 추가로 import한 Lean 기능 때문에 통과한 경우라도, 최종 증명은 원래 문맥에서 재검증해야 한다.

이 버전은 임시 `sorry`를 source에 추가하지 않고 실패 구간을 직접 교체한다.
직접·간접 sorry, 명제 변경, 금지 명령은 공통 guard·공리 검사에서 거절한다.
Lean이 오류 복구 중 내부적으로 만든 미완성 항을 유효한 증명으로 인정하지 않는다.
지역 문맥의 `implementation_detail` 항목은 compiler metadata로 구분해 Worker에 전달한다.

구문을 읽지 못하거나 범위를 안정적으로 대응시킬 수 없는 경우는 추출 불가다.
모든 `induction` 경우 누락·macro·custom syntax를 지원하지 않는다. 실패를 기록하고 검증된 best를 보존한다.
현재 실제 검증 대상은 설치된 Lean **4.26.0**이다. 다른 버전의 InfoTree API 호환성은 별도 검사 대상이다.

## #37 연결 계약

현재 연결점은 `adapter.repair_candidate(runtime, code, route_id, arm, tactics)`다.
호출자는 원래 명제·환경과 공유 예산·Worker·기록·중복 집합을 가진 runtime을 전달한다.
중복이 아니며 검증에 실패한 후보만 이 연결점으로 넘긴다.
반환값에는 상태, 수리 후보 또는 미완성 코드, 부모·자식 노드, native 목표·문맥, 원시 검증 근거와 반환 사유가 포함된다.
`remaining_goals`는 반환 코드와 해시가 일치하는 마지막 native 관측에서 얻는다.
첫 미해결 상태의 목표만 포함하며 모든 독립 블록의 목표를 완전히 열거했다는 뜻은 아니다. 미수집은 null이다.
전체 경로 변경은 이 함수가 결정하지 않는다.

fixture CLI는 루트 Worker 1회와 필요한 하위 Worker 호출을 같은 원장으로 처리한다.
별도 Planner 호출이나 반복적인 경로 탐색을 흉내 내지 않는다.
추후 #37의 Controller가 이미 소유한 자원과 이 인터페이스를 연결하고, Planner 비용까지 같은 원장에 들어가는지 통합 검사해야 한다.
현재 공개되지 않은 #37 API와 동등하다고 간주하지 않는다.

## 실행

Python 3.10 이상과 미리 설치한 `leanprover/lean4:v4.26.0`이 필요하다.
toolchain을 자동 다운로드하지 않는다. 기본 fixture에는 Mathlib나 GPU가 필요하지 않다.

```sh
python3 experiments/verification-repair-policy/run.py prepare \
  --output runs/manual/recursive-F04 \
  --case F04 --condition recursive-repair-v1
python3 experiments/verification-repair-policy/run.py check \
  --output runs/manual/recursive-F04
python3 experiments/verification-repair-policy/run.py run \
  --output runs/manual/recursive-F04
python3 experiments/verification-repair-policy/run.py status \
  --output runs/manual/recursive-F04
python3 experiments/verification-repair-policy/run.py replay \
  --output runs/manual/recursive-F04
```

`--condition`은 `planner-worker-v1`, `auto-solver-v1`, `recursive-repair-v1` 중 하나다.
조건마다 새 실행 폴더를 사용한다. 기준 조건도 실제 Planner를 사용한 성능 결과가 아닌 연결 검사다.
`--cases`로 고정 입력 JSON, `--environment`로 준비된 단일 환경 JSON을 지정할 수 있다.
환경 JSON은 공통 평가기의 `id/project/toolchain/command/timeout_seconds/template` 계약을 따른다.
외부 환경·문맥은 신뢰하는 프로젝트만 사용한다. 모델이 환경이나 명제를 변경할 수 없다.

F04는 자동 전술이 풀지 못한 함수 존재 목표를 Worker의 고정 응답이 분해하고,
그 하위 목표를 Auto Solver가 해결하는 루트 → 자식 → 손자 사례다.
F09는 같은 사례에 깊이 1 한도를 적용하는 테스트에서 사용한다.
F11의 최종 재검증 실패·원본 복귀는 실패를 주입한 계약 테스트로 검사한다.

`--simulated-budget-usd`와 고정 응답의 비용은 예약·미정산 동작 검사용 모의 금액이다.
실제 API 비용과 합산하지 않는다. 실제 backend·API key·자동 재시도 옵션은 없다.
하위 목표마다 원장을 초기화하지 않는다. 미정산·예약액 초과 응답은 다음 dispatch를 막는다.

## 기록과 재생

| 경로 | 내용 |
| --- | --- |
| `protocol.json`, `fixture.json`, `frozen-inputs.json` | 조건, 명제·환경·응답·코드 해시, 모든 한도 |
| `code/repo/` | 실행에 사용한 Python·Lean 코드와 공통 도구의 보존 사본 |
| `preflight/` | 실제 compiler pin·환경 fingerprint와 문맥 검사 |
| `native/` | 전술 가용성, native 진단 source·로그, baseline/후보/재조립/최종 평가 원문 |
| `tape/` | 각 결정·요청·관측. 모델 요청과 예약은 dispatch 전에 원자적으로 저장 |
| `budget.json` | 같은 실행의 루트·하위 Worker 모의 예약과 정산 |
| `events.jsonl` | 공통 `status.py`가 읽는 단계 기록 |
| `result.json`, `selected.lean`, `artifacts.json` | 수리 트리, 비용·호출, 최종 선택·품질, 파일 무결성 목록 |

replay는 저장된 관측을 입력으로 수리 로직·source 변환·요청·예산·선택을 다시 실행한다.
외부 호출 callback은 실행하지 않는다. 입력·결정·최종 결과가 달라지거나 기록이 남으면 실패한다.
원시 파일을 변경한 경우 무결성 검사도 실패한다. 실행 재개 기능은 없다.
코드가 바뀌었다면 보존한 코드로 재생한다.

```sh
python3 runs/manual/recursive-F04/code/repo/experiments/verification-repair-policy/run.py \
  replay --output runs/manual/recursive-F04
```

수리 성공과 최종 best 개선은 별도 필드다. `repair.status=verified`여도 best가 원본일 수 있다.
최종 proof 오류이면 원본을 다시 검사한다. timeout·환경·계측 때문에 확정하지 못하면 null로 남긴다.
무과금 fixture의 결과는 실제 LLM 성능이나 동일 API 예산 비교가 아니다.

## 검증

```sh
python3 -m unittest discover \
  -s experiments/verification-repair-policy -p 'test_*.py' -v
REPAIR_RUN_LEAN_TESTS=1 python3 -m unittest discover \
  -s experiments/verification-repair-policy -p 'test_recursive_lean.py' -v
```

`REPAIR_EVIDENCE_DIR`에 새 경로를 지정하면 실제 Lean 검사의 모든 실행 기록을 보존한다.
Python CI job에서는 Lean 검사를 건너뛰고 계약·무과금 검사만 실행한다.
별도 `Recursive repair (Lean 4.26.0)` job은 고정 Elan·Lean을 설치하고 실제 Lean 검사를 수행하며 원시 기록을 artifact로 보존한다.
CI의 toolchain 설치와 달리 로컬 실행 CLI는 준비되지 않은 toolchain을 자동 설치하지 않는다.
정확한 실행 명령·버전·검증 결과는 `validation.json`에 남긴다.
이 파일은 PR B 당시 revision의 검증 기록이다. PR C에서 추가한 고정 실패 corpus 평가와 명시적 `lean_path` 연결의 검증은 [evaluation/README.md](evaluation/README.md)에서 별도로 관리한다.

InfoTree 순회는 [Week 4 Support.lean의 고정 revision](https://github.com/Pseudo-Lab/LeanAgent/blob/e302e89eadf2c7eb2b65f0035f7dbba0b8e09130/docs/research/verification-repair/%EC%86%90%EC%A7%80%EC%97%B0/experiment%28week4%29/evidence/implementation/verification-repair/lean_repair/Support.lean)을 참고했다.
여기에 구조화된 native 지역 문맥, source 대응과 재귀 조립을 추가했다.
