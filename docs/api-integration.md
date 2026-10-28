# 실제 문제 실행과 API 사용량의 공통 하네스 통합

`lean_agent.harness.run()`에서 원본 검증 → 후보 생성 → Lean 검증 → 피드백 → 최선 갱신 →
최종 재검증을 실행한다. 실험 실행기가 공통 루프를 복제하거나 전역 함수를 바꾸지 않는다.
관련 이슈: [#28](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/28).

## 공통 코드와 실험 조건

| 위치 | 역할 |
| --- | --- |
| `src/lean_agent/harness.py` | 호출 수·누적 비용 종료, 응답 직후 사용량 기록, 후보 선택·replay |
| `src/lean_agent/models.py` | OpenRouter 요청, reasoning·가격 상한 설정, 명시적 dotenv 읽기 |
| `src/lean_agent/prepared.py` | 이미 빌드된 라이브러리의 해시 manifest, 모델 호출 전 검사, 명시적 `LEAN_PATH` |
| `src/lean_agent/accounting.py` | API/subagent 사용량 정규화·계산, 제공 비용과 API 환산 추정 분리 |
| `configs/openrouter-threshold.example.json` | 비용 도달 시 종료하는 기본 실행 예제 |
| `experiments/api-comparison/configs/p02-main-loop.json` | P02의 모델·reasoning·호출 제한·계측·허용 예산 조건 |
| `experiments/api-comparison/main_loop.py` | P02 원본 문맥 준비, 해당 모델의 호출 전 비용 예약, 전체 원본 모듈 확인 |

다른 PR의 비교 조건은 문제·문맥 template·prompt·모델·limits 설정으로 연결한다. 현재 하네스의
요청에는 원본 문제, 현재 최선, 직전 후보와 피드백이 포함된다. 부분 문맥/근방 실험에서 전체 증명을
숨기려면 `make_request()`의 packet 구성도 함께 검토해야 한다. 프롬프트 파일만 줄여서 독립된
문맥 비교가 됐다고 간주하지 않는다. P02의 과거 관측은 새 비교 실험의 결과와 섞지 않는다.

## 준비된 실제 문제 실행

문제 파일은 `id`, `name`, `statement`, `reference`를 담는다. 문맥 template에는
`{{HARNESS_IMPORT}}`, `{{HARNESS_COMMANDS}}`, `{{DECLARATION}}`를 이 순서로 각 한 번씩 둔다.
이름공간과 선언 이전 문맥을 보존한다. `configs/smoke.json`을 복사한 로컬 설정에서
`problem`, `template`, `project`, `prompt` 경로와 Lean 버전·직접 compiler 명령을 지정한다.
상대 경로는 설정 파일 위치를 기준으로 해석한다.

외부 라이브러리는 먼저 해당 문제의 지정 버전으로 빌드한다. 아래 명령은 준비된 파일을
읽어 manifest만 만들며 설치·빌드·모델 호출을 하지 않는다.

```sh
python -m lean_agent freeze-environment \
  --library-path /ABSOLUTE/PREPARED/LIB/lean \
  --revision PINNED_LIBRARY_COMMIT \
  --output configs/libraries.local.json
```

필요한 디렉터리마다 `--library-path`를 반복한다. Lean core 경로가 필요하면 같은 방식으로
명시한다. manifest는 절대 검색 경로와 파일 해시를 고정하며 실행 입력에 복사된다.
`lean.prepared_environment`에 해당 manifest의 경로를 지정한다.

```json
{
  "lean": {
    "prepared_environment": "libraries.local.json"
  }
}
```

위 조각은 기존 설정의 `lean`에 추가할 항목이다. 실행 전 사전 점검과 각 compiler 호출에서
파일 추가·삭제·변경을 확인하고, 종료 시 compiler·문맥·라이브러리 fingerprint도 확인한다.
컴파일된 파일 자체는 실행 폴더로 복사하지 않는다. 새 머신에서 실제 검증하려면 동일 환경을
준비하고 새 manifest를 만든다. 보관 코드의 offline replay에는 라이브러리나 Lean이 필요 없다.

### 반복 환경 검사의 비용 줄이기

기본 `full` 정책과 기존 manifest는 각 compiler 호출 전에 모든 라이브러리 내용을 읽고
SHA256을 다시 계산한다. 변경이 통제되는 로컬 라이브러리에서는 manifest 생성 시
`--verification stat-cache`를 명시해 evaluator별 메모리 캐시를 사용할 수 있다.

```sh
python -m lean_agent freeze-environment \
  --library-path /ABSOLUTE/PREPARED/LIB/lean \
  --revision PINNED_LIBRARY_COMMIT \
  --verification stat-cache \
  --output configs/libraries.local.json
```

실행 설정의 `lean.prepared_environment`에 이 manifest를 지정한다. 별도 CLI 옵션 없이
manifest의 정책을 사용하며 실행 입력에 그대로 보존한다. 각 compiler 호출에서는 파일 목록과
device/inode/size/mtime/ctime/mode를 다시 검사하고, metadata가 같을 때만 이미 검증한 내용 해시를
재사용한다. 추가·삭제·교체·내용 변경을 발견하면 검사하고, manifest와 다르면 compiler 실행 전에
실패한다. 첫 호출은 실제 내용을 읽으며 캐시는 프로세스 간에 공유하거나 디스크에 저장하지 않는다.
실행 시작과 종료의 `fingerprint()` 및 명시적인 `verify()`는 캐시와 관계없이 전체 내용을 읽는다.

이 정책은 변경을 통제하는 로컬 파일시스템의 반복 읽기를 줄이는 선택 기능이다. metadata를
신뢰할 수 없는 네트워크 파일시스템이나 적대적인 동시 변경에 대해 매 호출의 전체 내용 검사를
대체하지 않는다. OS 격리나 검사 후 실행까지의 변경 차단을 제공하지 않으므로, 그런 보장이 필요한
경우 기본 `full` 검사를 유지하고 별도 실행 격리를 적용한다. 증명 검증 결과나 heartbeat 표본은
캐시하지 않으며 매번 새 Lean 프로세스로 측정한다.

실제 main 대비 측정 방법과 결과는
[환경 검사 비용 비교](../experiments/environment-verification/README.md)에 기록한다.

macOS에서는 manifest 생성에 `--sandbox macos-readonly`를 지정하면 Lean 프로세스의 쓰기·네트워크를
차단한다. 요청한 sandbox가 없으면 실패하며 조용히 해제하지 않는다. 기본 `none`은 OS 격리를
적용하지 않는다. 두 모드 모두 Lean 자식 프로세스에 모델 인증값과 상속된 `LEAN_PATH`를 전달하지 않는다.

```sh
python -m lean_agent check --config configs/problem.local.json --output runs/manual/problem-check
python -m lean_agent run --config configs/problem.local.json --output runs/manual/problem-run
python -m lean_agent replay runs/manual/problem-run
```

`check`는 선언 없는 문맥까지 검사하고 모델을 호출하지 않는다. `run`은 별도 새 출력 폴더를 사용한다.
OpenRouter 인증은 환경 변수 또는 명시적인 `--dotenv .env`로 전달한다. dotenv는 실행하거나
확장하지 않고 읽으며 실행 산출물로 복사하지 않는다. `OPENROUTER`와 `OPENROUTER_API_KEY`가
함께 있으면 값이 같아야 한다. 일시 설정한 환경 변수는 실행 종료 시 복구한다.

## 비용 도달 기준과 호출 제한

```json
{
  "limits": {
    "max_calls": null,
    "cost_stop_usd": "2.50"
  }
}
```

위 두 항목을 기존 `limits`에 적용하면 횟수 제한 없이 누적 제공 비용이 기준 이상이 된 응답 뒤
종료한다. `max_calls`를 정수로 지정하면 호출 수와 비용 중 먼저 도달한 기준으로 종료한다.
`null`은 실제 비용을 반환하는 OpenRouter와 양의 유한한 비용 기준을 함께 지정할 때만 허용한다.
과금 미확정·환경 실패·문맥 한도는 기존 중단 정책을 유지한다. 성공·정체·동일 소스만으로
조기 종료하지 않는다. 종료 이유는 `cost_limit`이다.

마지막 호출에서 기준을 넘을 수 있다. 이 설정은 엄격한 다음 호출 비용 예약이 아니다.
`model.max_price`는 요청에 전달하는 입력·출력 USD/백만 토큰 가격 상한이며 총 지출 상한과 다르다.
P02 실험에는 별도 `BudgetQuery`가 공개 endpoint metadata를 확인하고 UTF-8 byte 기반 입력 상한과
최대 출력의 비용을 예약한다. 이 예약은 검증한 GPT-6.1 Sol 텍스트 요청에 한정되며 다른 모델로
그대로 일반화하지 않는다. 제공자가 단가·토큰 한도를 지키는 조건의 로컬 예약이다.
자동 재시도·병렬 유료 호출은 하지 않는다.

## 응답별 사용량과 회계 CLI

모든 응답은 후보 파싱·Lean 검증 전에 `response.json`과 `usage.json`으로 남는다.
실패한 증명과 중복 소스도 집계한다. `usage-summary.json`은 각 토큰 필드에 대해
합계·평균·중앙값, 관측 수·누락 수·알려진 부분합을 기록한다. 누락된 필드가 있으면 전체 합계와
평균·중앙값은 `null`이며 알려진 부분합만 제공한다. 잘못된 usage는 원문 응답을 보존하고
`usage_error`로 표시하며, 알려진 제공 비용을 지우지 않는다.

실행별 `usage-cost.json`에는 호출별 영수증과 agent/model별 집계, 제공 비용과 API 환산
추정액을 함께 보존한다. 선택 설정 `usage_cost.prices`의 단가·출처는
`input/usage-prices.json`으로 고정한다. `status`는 응답 없는 요청도 미확정으로 조회하고,
replay는 기존 `usage-summary.json`과 새 비용 보고서를 모두 재계산한다.
공통 계산기는 `lean_agent.accounting` 하나이며 `lean_agent.usage_cost`와
`lean-agent-usage`는 호환 진입점이다. [설정·조회·외부 기록 가져오기](usage-cost.md)를 참고한다.

- 캐시 읽기·쓰기는 입력에, reasoning은 출력에 이미 포함되므로 다시 더하지 않는다.
- `reported_cost_usd`는 API 제공 비용이다. 토큰 추정액을 하네스의 실제 비용 종료 판정에 넣지 않는다.
- replay는 원문 응답에서 사용량과 비용을 재계산해 응답별 기록과 전체 집계를 대조한다.
- 중단된 실행은 응답이 없는 요청을 미완료로 보존한다. 누락된 응답을 무료 호출로 간주하지 않는다.

API와 subagent 기록을 같은 형식으로 계산하는 offline CLI도 설치 패키지에서 제공한다.

```sh
python -m lean_agent usage-cost --mode api \
  --input experiments/usage-cost/examples/api-records.json \
  --prices experiments/usage-cost/examples/prices.json

python -m lean_agent usage-cost --mode subagent --format codex-jsonl \
  --input experiments/usage-cost/examples/codex-events.jsonl \
  --run-id example --agent-id agent-1 --model test-model \
  --prices experiments/usage-cost/examples/prices.json
```

예제 단가는 테스트용이며 실제 모델 가격이 아니다. subagent는 런타임이 제공한 개별 turn의
`exclusive_delta` usage를 입력하고 API 환산 추정액만 기록한다. 구독 청구액이나 부모·자식의
포함 범위를 추측하지 않는다. 이 CLI는 subagent를 실행하는 dispatcher가 아니다.
기존 `experiments/usage-cost/accounting.py` 명령은 패키지를 호출하는 호환 진입점으로 유지한다.

## P02 실험과 통합 검증

기존 실측 실행은 main `1f51537` 기반, GPT-6.1 Sol·high, Warm-up P02 한 문제에서
158회·$2.5019843으로 종료했다. 원본 222 proof-token / raw HB 2,695,001에서
최종 120 / 499,239로 개선했다. 입력 5,089,921, 출력 129,883토큰이며 입력 중앙값은
32,177, 출력 중앙값은 775.5다. 이는 한 실행의 관찰이며 공식 Arena 점수가 아니다.
[실험 요약](../experiments/api-comparison/threshold-results-20261028.json)에 집계를 보존했다.

해당 유료 실행은 통합 전의 보관 코드로 만들어졌다. 당시 `harness/code/replay.py`를 사용해
재생하며 원문 기록을 새 형식으로 덮어쓰지 않는다. 통합 코드는 저장된 최종 증명을 fixture로
받아 같은 P02·Strata 환경에서 실제 Lean 검증하고, native 기록 및 보관 코드 replay를 확인한다.
이 확인은 새 생성 성능 실험이나 추가 유료 호출이 아니다.

```sh
python -m unittest discover -s tests -p 'test_harness.py' -v
python -m unittest discover -s tests -p 'test_runtime_integration.py' -v
python -m unittest discover -s tests -p 'test_api_integration.py' -v
python -m unittest discover -s tests -p 'test_accounting.py' -v
python -m unittest discover -s experiments/api-comparison -p 'test_*.py' -v
python -m unittest discover -s experiments/usage-cost -p 'test_*.py' -v
```

CI는 Python 3.10·3.13에서 위 테스트를 네트워크·Lean·모델 호출 없이 실행한다.
실제 Lean P02 검증은 준비된 로컬 라이브러리를 사용하는 별도 확인이다.

로컬 검증 집계와 실행 코드 해시는 [api-integration-validation.json](api-integration-validation.json)에 기록했다.
