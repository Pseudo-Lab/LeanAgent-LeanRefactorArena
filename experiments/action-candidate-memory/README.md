# 행동 선택과 후보 이력을 갖는 하네스 실험

`origin/main`의 `ba3de4f`에서 시작한 `exp/action-candidate-memory` 실험이다.
기존 증명 전체 생성 루프와 같은 평가기·선택 규칙·비용 장부를 사용하면서,
모델이 도구를 선택하고 실패·비최선 후보에서 다시 탐색할 수 있게 한다.
별도 `agent` 설정이 없는 실행은 기존 proof-only 프로토콜을 사용한다.

## 구현 범위

| 행동 | 입력 | 동작 |
| --- | --- | --- |
| `search` | `query` | 명시적으로 준비한 소스 corpus를 어휘로 검색. 최대 5개 결과 |
| `inspect` | `name`, 선택적인 `offset` | 검색한 소스 확인. 한 번에 3,000자, 다음 offset 제공 |
| `analyze` | `candidate_id` | 줄 수·반복 줄·키워드 등 가벼운 정적 힌트 |
| `read_candidate` | `candidate_id`, 선택적인 `offset` | 과거 후보 소스와 검증 피드백 확인 |
| `propose` | `parent_id`, `strategy`, `proof` | 부모 후보에서 새 증명 제안, 즉시 기존 Lean 평가기로 검증·측정 |
| `repair` | `parent_id`, `strategy`, `proof` | 실패한 부모의 수리, 즉시 검증·측정 |
| `finish` | 없음 | 현재 검증된 best를 최종 재검증하고 종료 |

`propose/repair`는 증명 본문 전체를 받는다. 평가를 별도 모델 호출로 분리하지 않는다.
부분 패치나 tactic 단위 세션은 이번 범위에 포함하지 않는다.

후보 ID는 원본 `c000`, 이후 제안 시점의 `cNNN`이다. 도구 행동은 후보를 만들지 않아
ID가 연속적이지 않을 수 있다. 모든 후보의 소스·부모·전략·성공 여부·측정값·진단을
`state.exploration.candidates`에 보관한다. 점수가 낮거나 검증에 실패해도 삭제하지 않는다.
`best_candidate_id`는 현재 선택된 후보를 가리킨다.

모델에는 원본·best·최근 후보 요약과 최근 행동만 보낸다. 창에서 빠진 후보도 ID로
다시 읽을 수 있다. `candidate_limit`과 `history_limit`은 문맥에 보여주는 개수이며,
보관한 후보를 지우는 설정이 아니다. 모든 호출은 도구 행동까지 `max_calls`와
실측 비용에 포함한다. 기존 비용 임계값은 마지막 한 호출의 초과를 허용한다.

## 입력과 재현

설정 예시는 [smoke.json](smoke.json), 행동 지침은 [prompt.txt](prompt.txt)다.

```json
"agent": {
  "mode": "actions-v1",
  "corpus": "corpus.json",
  "history_limit": 4,
  "candidate_limit": 4
}
```

corpus는 `schema_version: 1`과 `entries` 배열을 가진 JSON이다. 각 항목은
`name`, `source`, `text`를 가진다. [예제 corpus](corpus.json)는 Lean 4.26.0의
`Init/Core.lean:737`에서 추출한 `Nat.add_zero` 선언 한 개다.
새 문제에서는 고정된 라이브러리 버전과 대상 선언 이전 문맥에서 자료를 준비해야 한다.
이 프로토타입은 corpus 작성자가 넣은 자료를 검색하며, import 범위나 선언의 접근
가능성을 판정하지 않는다. 검색 결과는 타입 검사 결과가 아니고 실제 후보 검증이 필요하다.
소스 출처 문자열은 자료 설명으로만 쓰며 모델이 보낸 경로를 열거나 실행하지 않는다.

실행 시작 시 corpus·설정·프롬프트·실행 코드를 함께 동결한다. 각 단계의 행동과
관찰값은 `steps/NNN/event.json`에 남는다. replay는 저장된 corpus로 검색·분석 결과를
다시 계산하고 후보 이력을 재구성한다. 모델, 외부 파일, Lean을 다시 호출하지 않는다.
보관 코드의 replay를 사용하면 이후 소스 변경과 무관하게 실행을 재생할 수 있다.

## 실제 Lean으로 구조 확인

Lean 4.26.0이 설치된 환경에서 저장소 루트 기준으로 실행한다.

```sh
PYTHONPATH=src python3 -B experiments/action-candidate-memory/run_smoke.py \
  --output runs/action-candidate-memory/MY-SMOKE
```

두 조건 모두 고정 응답을 사용하고, 같은 네 개의 증명 후보를 실제 Lean으로 평가한다.
행동 조건은 분석·검색·자료 확인·과거 후보 읽기·종료를 더 수행한다.
실패 후보 수리와 비최선 후보에서 갈라지는 경로를 의도적으로 넣었다.

2026-10-28 실행 결과는 [smoke-results.json](smoke-results.json)에 보관한다.
원문 기록은 `runs/action-candidate-memory/20261028-smoke-02/`에 있다.
두 조건 모두 최종 증명이 검증됐고 원본 14토큰에서 2토큰을 선택했다.
행동 조건은 원본 포함 후보 5개를 보존했고 `c004 → c005` 수리와
`c006 → c008` 대안 경로가 유지됐다. 두 실행 모두 최종 재검증과 replay를 통과했다.
모델 API 호출이나 과금은 없다.

이 결과는 실행 구조 검증이다. 후보를 미리 정했으므로 탐색 능력, 비용 절감,
실행 속도 우위를 보여주지 않는다. 도구 행동은 무료 모델 추론으로 취급해서는 안 된다.

## 다음 성능 비교 조건

원본 증명에서 시작해 `whole`과
`actions-memory`를 같은 모델·reasoning 설정·비용 임계값·출력 한도·Lean 환경으로 비교한다.
후보 생성뿐 아니라 검색·자료 확인에 사용한 모델 비용도 모두 집계한다.
두 조건에서 이용할 수 있는 원본 자료 범위는 같게 정하고, 기존 개선 증명은 넣지 않는다.
기준선에 제공한 자료와 검색 corpus를 함께 동결해 정보 차이를 확인할 수 있게 한다.

같은 예산의 최종 토큰·heartbeat, 누적 비용별 최선, 유효 후보 비율,
고유 후보 수, 전략별 개선, 모델 호출 수, Lean 컴파일 횟수, 총 실행 시간을 비교한다.
한 문제 한 실행의 차이를 일반화하지 않도록 여러 문제와 반복 실행으로 확인한다.
이 비교는 행동 선택과 기억을 묶은 효과를 본다. 각각의 기여는 후속 ablation으로 분리한다.

현재 `analyze`는 어휘 기반 힌트이며 기존 proof-analyze의 블록 분석이나 Lean AST를
통합하지 않았다. 검색은 의미 검색·실제 Lean 선언 검사와 다르다. 후보 재평가 캐시,
정체 시 자동 전략 전환, 병렬 실행, 중단 후 재개도 아직 구현하지 않았다.
후보 이력을 매 단계 상태에 포함하므로 장시간 실행에서는 저장량이 제곱으로 증가할 수 있다.
이번 실험은 호출 수를 제한한 소규모 비교를 대상으로 한다.

## P02 OpenRouter 비교: 합계 $0.30 상한

아래는 초기 **strict 모드** 실행 기록이다. 현재 `live_p02.py`의 기본값은 뒤의
실패 분석에서 설명하는 실측 비용 threshold 모드이며, 과거 strict 조건은 명시적으로 선택한다.
`live_p02.py`는 두 조건을 직렬로 실행한다. GPT-6.1 Sol / OpenAI, reasoning `high`,
출력 상한 4,096토큰(추론 포함), seed 42, 최대 12회 호출로 고정한다.
요청한 $0.30을 합계 상한으로 해석해 조건마다 $0.15를 배정한다.

검증에는 Strata `451e5f047bafa010d178856db76c00029bfa4d7f`, Lean 4.26.0과
원본 모듈의 대상 이전 문맥 전체를 사용한다. 생성 모델에는 두 조건 모두 같은
6,652자 원본 task packet을 제공한다. 기존 장시간 P02 실행의 91,086자 소스 prefix는
생성 입력에 넣지 않으므로 그 실행과 수치를 직접 비교하지 않는다.
행동 조건의 검색 corpus는 같은 packet의 정의·생성자·로컬 보조정리 8개 구간이다.
추가 지식이나 기존 개선 증명은 넣지 않는다. 행동별 프롬프트는 분리하지 않았다.

기존 `cost_stop_usd`는 마지막 호출의 초과를 허용한다. 이 비교에는 별도의
`cost_cap_usd`를 사용한다. 요청의 UTF-8 byte 수와 framing 여유 4,096을 입력 토큰
상한으로 잡고, 최대 출력·추론 토큰까지 포함한 비용을 호출 전에 예약한다.
캐시 할인은 예약에 반영하지 않는다. 다음 요청의 최대 비용이 잔액 안에 들어오지
않으면 `budget_reservation`으로 종료하고 best를 최종 검증한다.
예약이 거절된 호출은 API 전송·과금·호출 수에 포함하지 않는다.

각 실제 호출 직전에 provider의 현재 가격과 도달 가능한 가격 tier, cache-write 가격을
확인한다. 두 조건 공통 가격 ceiling은 입력 $2.50/M, 출력 $10/M이다.
같은 장부에서 조건별·합계 비용을 확인하고, API 전송 전에 예약을 디스크에 기록한다.
비용 불명 응답이나 예약 초과 응답이 생기면 이후 유료 호출을 막는다.
이 보수적인 예약 방식은 실제 비용이 상한에 미달한 상태에서 종료될 수 있다.

```sh
PYTHONPATH=src python3 -B experiments/action-candidate-memory/live_p02.py prepare \
  --output runs/action-candidate-memory/MY-P02 \
  --budget-mode strict --target-usd 0.15 \
  --common /ABSOLUTE/P02-ORIGINAL/common \
  --strata /ABSOLUTE/PINNED-STRATA \
  --toolchain /ABSOLUTE/LEAN-4.26.0
PYTHONPATH=src python3 -B experiments/action-candidate-memory/live_p02.py run \
  --output runs/action-candidate-memory/MY-P02 --dotenv /ABSOLUTE/OPENROUTER.env
```

두 조건의 preflight를 마친 뒤 API를 호출한다. 각 조건은 원본에서 독립적으로 시작하며,
최종 후보는 원본 모듈 전체에 다시 넣어 컴파일한다. `report.json`에 비용·후보·행동·
점수·replay와 전체 모듈 검증 결과를 기록하고 비밀값이 섞였는지도 확인한다.

### 2026-10-29 결과

[결과·비용 감사 기록](p02-results-20261029.json). 원문은
`runs/action-candidate-memory/20261028-p02-budget030/`에 있다. 실행 폴더 이름은 준비 시 붙인 식별자다.

| 항목 | 기존 whole | 행동·후보 기억 |
| --- | ---: | ---: |
| API 호출 | 4 | 3 |
| 새 후보 검증 통과 | 3 / 4 | 0 / 2 |
| 최종 proof-token | 166 | 222 (원본 유지) |
| 최종 raw heartbeat 중앙값 | 488,671 | 2,695,022 |
| 로컬 비율 점수 (낮을수록 좋음) | 0.464536 | 1.000000 |
| 실제 보고 비용 | $0.0670090 | $0.0533791 |
| 최종·전체 모듈 검증 / replay | 통과 | 통과 |

공통 원본은 222토큰, raw heartbeat 2,695,022이다. 합계 비용은 **$0.1203881**로 $0.30 이내다.
API generation ID 7개가 모두 고유하고, transport의 실제 요청·응답과 native 실행 기록이
일치한다. 조건별 $0.15 한도, 각 응답의 비용 예약액 이하 정산, 전체 artifact inventory,
비밀값 미기록을 확인했다.

기존 버전은 첫 후보 실패 후 194 → 170 → 166토큰의 유효 후보를 얻었다.
행동 버전은 `search → propose(c000) → repair(c002)`를 수행했다. 첫 후보는 분기의
미해결 목표로 실패했고, 수리 후보는 `No goals to be solved`와 `simp_all made no progress`로
실패했다. 환경 오류나 실행기 중단으로 인한 실패는 아니었다.

두 실행 모두 `budget_reservation`으로 종료됐다. 기존 버전의 다음 요청 예약액은 $0.084330,
잔액은 $0.082991이었다. 행동 버전은 예약액 $0.112460, 잔액 $0.0966209였다.
예약할 수 없어 API 요청을 추가 전송하지 않았다. 도구 결과·후보 이력이 요청을 늘려
행동 버전의 보수적 예약액도 더 컸다. 이 실행은 같은 지출액까지 소진한 비교가 아니라
같은 상한과 동일한 예약 규칙을 적용한 소규모 비교다.

이번 한 번의 실행에서는 기존 버전이 더 나았다. 행동·계보 기록은 동작했지만 탐색 품질
개선으로 이어지지 않았다. 문제당 반복 실행 없이 구조 자체의 우열을 일반화하지 않는다.

## 실패 분석과 수정 (2026-10-29)

[오프라인 복구·요청 크기·검색 회귀 확인](repair-results-20261029.json),
[검증한 수동 복구 후보](p02-manual-repair.lean).
과거 유료 실행은 변경하지 않았으며 추가 API 요청은 0회다.

| 확인한 문제 | 원인과 수정 |
| --- | --- |
| 검색 0건 | `List.append_subset_append append_subset`를 통째로 검색해, 이름이 다른 로컬 `List.Subset.app` 자료를 놓쳤다. 점·밑줄로 나눈 identifier 성분도 검색하며, 부분 일치임을 명시한다. 같은 원본 corpus에서 관련 로컬 보조정리가 검색된다. 요청한 이름 자체가 존재한다고 주장하지 않는다. |
| 첫 후보 실패 | 후보 24행의 `aesop`은 고정 환경에서 unknown tactic이었다. 12행은 `[v].Subset [v]`가 남았고, 17행의 `hfalse rfl`은 종속 인자 타입이 맞지 않았다. 다른 분기에도 미해결 목표가 남았다. |
| 수리 후보 실패 | 일부 분기를 `simp_all`이 이미 닫은 뒤 26행의 `intro`를 무조건 실행해 `No goals to be solved`가 5번 발생했다. 27행에는 `simp_all made no progress`도 있었다. 후속 전술을 `<;>`로 남은 목표에 한정하고 선택적인 simplifier 정리를 보호한 최소 수동 수정으로 컴파일이 통과했다. |
| 수리 입력 | 오류는 기존 요청에도 들어 있었다. 다만 원본 파일의 2,800번대 줄 번호와 긴 텍스트였고, 후보 줄 위치·오류별 안내가 없었다. 현재는 후보 행·문제 전술·오류 종류·목표를 구조화한다. 문맥의 warning과 후보 error를 구분하고 같은 위치의 반복 오류를 합친다. |
| 중복 문맥 | 실패 코드와 진단이 latest·history·archive에 중복 노출됐다. 보관 이력은 유지하고 모델 요청에는 repair_context에서 한 번 보여준다. 수리 전용 안내를 같은 호출의 문맥으로 전달하며 별도의 계획 모델 호출은 추가하지 않는다. |
| 조기 종료 | strict 예약 규칙을 비용 도달 규칙과 혼동했다. 현재 기본은 `cost_stop_usd`, `max_calls: null`이다. strict 예약은 `--budget-mode strict`일 때만 적용한다. threshold에서는 agent의 finish도 비활성화해 모델의 조기 종료를 막는다. |

### 재현과 한계

기록된 실패 후보 두 개와 수동 수정 후보를 같은 환경에서 다시 평가했다.
검증 결과는 **실패 → 실패 → 통과**였고, 수동 수정 후보의 원본 전체 모듈 컴파일과
실행 replay도 통과했다. `reproduce_p02_repair.py`는 검증된 원본 기록만 읽으며
기존 whole 실행의 개선 증명은 복구에 사용하지 않는다.

```sh
PYTHONPATH=src python3 -B experiments/action-candidate-memory/reproduce_p02_repair.py \
  --original-run runs/action-candidate-memory/20261028-p02-budget030 \
  --output runs/action-candidate-memory/MY-OFFLINE-REPAIR
```

수동 복구 후보는 **123토큰 / raw heartbeat 중앙값 3,980,769**였다.
로컬 비율 점수는 1.015568로 원본의 1보다 나빠 최종 best는 원본을 유지했다.
이는 올바르게 컴파일되는 복구본이지 최적화 성능이 향상됐다는 결과는 아니다.
모델이 새 안내로 더 잘 수리하는지는 유료 재실험 전까지 확인하지 않은 상태다.

동일한 과거 state·prompt를 새 문맥 형식으로 구성했을 때 요청은
26,962 → 20,799 UTF-8 bytes로 줄었다. 토큰 수나 청구 비용 감소를 측정한 값은 아니다.
오류를 버려서 줄인 것이 아니라 과거 이력의 중복 진단과 원본 best 코드 복제를 줄였다.
원본 로그·후보·전체 진단은 저장하며 `read_candidate`로 다시 읽을 수 있다.

### 다음 실행의 예산 설정

기본 준비 명령은 `--budget-mode threshold --target-usd 0.15`다.
두 조건 각각 **실제 누적 비용이 $0.15에 도달한 응답 뒤에 종료**한다.
마지막 한 호출은 초과할 수 있어 합계 $0.30은 엄격한 절대 상한이 아니다.
호출 전 가격 확인과 요청 최대 비용 기록, 미확정 과금 시 중단은 계속 적용한다.
단위 테스트는 $0.04 응답을 세 번 받은 $0.12에서 멈추지 않고 네 번째의 $0.16에서
종료하며, 다섯 번째 요청을 보내지 않는 것을 확인한다.

`runs/action-candidate-memory/20261029-p02-threshold-prepared/`에 수정된 설정을
준비했다. 준비만 했으며 이 설정으로 유료 API를 실행하지 않았다.

## 실제 비용 $0.20 도달 비교 (2026-10-29)

[전체 결과·단계·비용 감사](p02-threshold020-results-20261029.json),
[기존 버전 선택 증명](p02-threshold020-whole-selected.lean),
[개선 버전 선택 증명](p02-threshold020-actions-selected.lean).
선택 증명 파일은 고정된 원본 문맥에 삽입해서 검증한 선언 조각이다.

커밋 `183ddf4`로 두 조건을 각각 원본부터 새로 시작했다. 과거 실행의 best나
수동 복구 증명을 생성 입력에 넣지 않았다. GPT-6.1 Sol / OpenAI, reasoning `high`,
최대 출력 4,096, seed 42, Lean 4.26.0 / Strata 고정 버전, 원본 task packet은 동일하다.
조건마다 `cost_stop_usd: "0.20"`, `max_calls: null`을 사용했다. `cost_cap_usd`는 없으며
행동 조건의 `finish`도 비활성화했다. 생성은 공통 실행 루프, 수리는 오류별 문맥 안내를 사용한다.

| 항목 | 기존 whole | 개선 actions-memory |
| --- | ---: | ---: |
| 모델 호출 | 11 | 14 |
| 새 후보 검증 통과 | 8 / 11 | 7 / 10 |
| 최종 proof-token | 203 | **144** |
| 최종 raw heartbeat 중앙값 | 1,309,350 | **437,002** |
| 로컬 비율 점수 (낮을수록 좋음) | 0.700127 | **0.405400** |
| 실제 보고 비용 | $0.2062915 | $0.2112618 |
| 전체 모듈 검증 / replay | 통과 | 통과 |

원본은 222토큰 / raw heartbeat 2,695,022였다. 이번 실행에서 개선 버전은 기존 버전보다
토큰 29.1%, raw heartbeat 66.6%가 작았다. 두 조건 모두 마지막 종료 이유는 `cost_limit`이다.

| 조건 | 마지막 호출 직전 누적액 | 마지막 응답 후 누적액 |
| --- | ---: | ---: |
| whole | $0.1960702 | $0.2062915 |
| actions-memory | $0.1956252 | $0.2112618 |

각각 $0.20 미만에서 마지막 호출을 보냈고, 도달한 뒤에는 더 보내지 않았다.
마지막 호출의 초과분을 포함한 총비용은 **$0.4175533**이다. 고유 generation ID 25개,
transport/native 요청·응답 일치, 전체 artifact inventory, 비밀값 미기록을 확인했다.
원문은 `runs/action-candidate-memory/20261029-p02-threshold020-r1/`에 보관했다.

행동 조건은 `propose` 7회, `repair` 3회, `search` 2회, `read_candidate` 1회,
JSON 형식 거절 1회였다. 5회차 수리에서 처음 유효한 새 후보를 얻었고,
7회차에서 160토큰 / 504,017 HB, 최종 14회차에서 144토큰 / 437,002 HB를 선택했다.
검증에 실패한 후보에서 수리를 이어가는 계보도 보존했다.

이는 문제 하나에서 조건별 한 번 실행한 결과다. 예산과 모델 설정을 맞췄지만,
검색·수리 안내·후보 기억 각각의 기여나 반복 실행에서의 우위까지 입증한 비교는 아니다.
