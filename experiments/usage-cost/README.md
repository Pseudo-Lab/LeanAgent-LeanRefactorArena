# API / subagent 토큰 비용 계산 실험

기존 `proposal/problem-environment-lock` 브랜치에서 실행 방식별 비용을 같은 형식으로 기록하기 위한 실험이다.
`accounting.py`는 사용량 기록을 받아 계산하는 모듈과 CLI이며, Python 표준 라이브러리만 사용한다.
모델이나 Lean을 실행하지 않는다. 공통 구현은 `src/lean_agent/accounting.py`에 통합했고,
이 디렉터리의 `accounting.py`는 기존 명령의 호환 진입점이다. 설치 패키지에서는
`python -m lean_agent usage-cost ...`로 같은 계산기를 실행한다.
[실행 하네스 연결과 검증 범위](../../docs/api-integration.md)를 참고한다.

#29의 추가 검증은 같은 계산기로 통합했다. 고정 단가 보존, native 요청·응답 가져오기,
중단·미확정 비용 조회와 재생은 [사용량·비용 기록](../../docs/usage-cost.md)에 있다.
`lean_agent.usage_cost`는 호환 모듈이며 별도의 계산 구현을 유지하지 않는다.
공개된 실제 usage-only 자료는 `examples/observed-*.json`에 보존한다.

## 두 모드

| 모드 | 받는 기록 | 우선 사용할 비용 |
| --- | --- | --- |
| `api` | API 응답의 `usage`와 `usage.cost` | 제공자가 보고한 비용. 없으면 사용량·단가 기반 추정, 둘 다 없으면 미측정 |
| `subagent` | 런타임이 제공한 개별 agent/turn 사용량 | 고정 단가로 계산한 API 환산 추정 비용. 구독 청구액으로 표시하지 않음 |

`api` 모드는 고정 main 커밋 `ba593fc4357ee5c429b8f28f1aac512d05bb4355`의
`src/lean_agent/models.py:receipt()`가 사용하던 OpenRouter `usage.cost` 경로를 유지한다.
공통 토큰 형식 외에 Chat Completions의 `prompt_tokens/completion_tokens`도 받는다.

`subagent` 모드는 기존 실험 브랜치 `93cc6bb28da1616d75286ce2ea992fdc38efacf2`의
`experiments/first-harness-jwkweon/subagent_trials.py`가 비용을 미측정으로 기록했던 경계를 보완한다.
그 bridge의 `calls`는 제안 횟수이므로 내부 모델 호출 수나 토큰 수로 사용하지 않는다.
과거 결과를 임의의 토큰 수로 소급 환산하지 않는다.

## 계산 방식

```text
추정 USD = (
  (입력 토큰 - 캐시 읽기 토큰 - 캐시 쓰기 토큰) × 일반 입력 단가
  + 캐시 읽기 토큰 × 캐시 입력 단가
  + 캐시 쓰기 토큰 × 캐시 쓰기 단가
  + 출력 토큰 × 출력 단가
) / 1,000,000
```

- 단가는 모델별 USD / 100만 토큰이며 설정 파일에서 고정한다. 소수 계산은 `Decimal`을 사용한다.
- 출력 토큰에 포함된 reasoning 토큰을 다시 더하지 않는다. 최종 답변 문자열 길이만으로 토큰을 추측하지 않는다.
- 입력·출력 usage가 없거나 모델 단가가 없으면 추정액은 `null`이다.
- 캐시 세부 정보가 없으면 일반 입력 단가를 적용하고 그 가정을 명시한다. 실제 청구액이나 엄밀한 비용 상한을 뜻하지 않는다.
- 캐시 사용량이 명시됐는데 해당 단가가 없으면 임의의 할인율을 적용하지 않고 미측정으로 둔다.
- 캐시 쓰기 정책이 여러 개라면 단일 쓰기 단가로 정확히 계산할 수 있는 기록만 입력한다.
  정책별 단가가 다른 사용량은 사전에 분리하거나 계산 지원 범위 밖으로 처리한다.
- 도구·검색·이미지·음성 등의 별도 비용은 토큰 추정액에 포함하지 않는다. API 제공 비용은 제공자가 반환한 범위의 값이다.
- subagent의 숨겨진 문맥·도구 왕복·reasoning을 포함한 **런타임 usage**가 필요하다.
  agent가 답변에 적은 자기 추정치는 근거로 쓰지 않는다. 현재 도구가 usage를 노출하지 않으면 `null`로 남긴다.

## 입력과 중복 방지

`records` 입력은 호출/turn별 객체 배열이다. 필수 메타데이터는 `run_id`, `agent_id`, `event_id`,
`model`, `status`, `usage_scope`다. status는 `completed/failed/incomplete` 중 하나다.
subagent는 `usage`, api는 원 응답을 담은 `response`를 추가한다. 예제 파일을 참고한다.

- `usage_scope`는 `exclusive_delta`여야 한다. 자기 호출/turn에 해당하는 사용량만 입력한다.
- 대화 누적 토큰과 개별 turn 토큰을 동시에 더하지 않는다. 부모가 자식 사용량을 포함한 합계와 자식 개별 기록도 섞지 않는다.
- `(run_id, agent_id, event_id)`가 같고 기록도 같으면 합계에서 한 번만 센다. 동일 ID에 다른 기록이 들어오면 오류로 알린다.
- API는 응답/request ID가 있으면 이를 event_id로 사용한다. 응답 전 실패는 호출 전에 만든 attempt ID를 유지한다.
- 재시도는 별개 ID의 호출이다. 폐기·검증 실패 후보도 기록에서 제외하지 않는다.
- 누락된 응답도 `status: failed`, `response: {}` 또는 `usage: null`로 등록한다. 아예 기록에서 빼면 합계의 완전성을 검사할 수 없다.
- API 응답에 모델 ID가 있으면 메타데이터의 모델과 일치해야 한다. 모델 별칭·요금제 대응은 입력 수집 단계에서 명시적으로 정한다.

원본 로그를 임의로 탐색하지 않는다. 호출자가 전달한 파일만 읽으며 결과에는 원본 파일·이벤트·단가의 해시를 남긴다.
원본 증명·대화·인증 정보는 계산기 출력으로 복사하지 않는다. 원본 사용량 로그는 별도 실행 기록에 보존한다.

## 실행 예제

`examples/prices.json`의 `test-model`과 가격은 **가상의 테스트 단가**다. 실제 모델 가격이 아니다.
실험에 적용할 때 모델별 단가와 출처·기준일을 별도 파일로 지정한다. 예시 숫자를 공식 가격으로 사용하지 않는다.

저장소 루트에서 현재 프로젝트 환경의 Python을 사용한다.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
```

```sh
python3 experiments/usage-cost/accounting.py --mode api \
  --input experiments/usage-cost/examples/api-records.json \
  --prices experiments/usage-cost/examples/prices.json --budget-usd 0.01

python3 experiments/usage-cost/accounting.py --mode subagent \
  --input experiments/usage-cost/examples/subagent-records.json \
  --prices experiments/usage-cost/examples/prices.json --budget-usd 0.01
```

출력 예: API는 제공 비용 `0.0042`, 동일 usage의 subagent는 토큰 추정액 `0.0027`이다.
차이는 계산 오류가 아니라 제공자가 보고한 비용과 지정 단가의 토큰 환산액을 따로 취급한 결과다.
`--output runs/usage-cost/<run-id>/report.json`으로 저장할 수 있으며 기존 파일은 덮어쓰지 않는다.

Codex CLI의 JSONL export도 읽을 수 있다. 아래는 외부 호출 없이 예제 로그를 읽는 명령이다.

```sh
python3 experiments/usage-cost/accounting.py --mode subagent --format codex-jsonl \
  --input experiments/usage-cost/examples/codex-events.jsonl \
  --run-id example-run --agent-id agent-1 --model test-model \
  --prices experiments/usage-cost/examples/prices.json
```

`turn.started`부터 `turn.completed/turn.failed`까지 순서대로 읽고, 종료 기록이 없는 turn은 비용 미확정으로 남긴다.
`turn.completed` 자체에는 모델 식별자가 없으므로 `--model`은 실행 시 고정한 설정에서 전달한다.
이 importer는 **단일 agent의 중복 없는 전체 turn 스트림**용이다. 실행마다 run/agent 식별자를 구분해야 한다.
자식 호출의 포함 범위를 알 수 없는 로그나 여러 모델이 섞인 turn을 한 모델 단가로 환산하지 않는다.
그 경우 런타임에서 개별 사용량을 분리해 `records`로 제공하거나 미측정으로 둔다.

## 하네스 연결 위치

실행 backend와 회계 mode는 별개다. `api`/`subagent` 인자는 현재 **사용량 입력·계산 모드**를 선택하며
API 또는 agent를 직접 호출하는 dispatcher가 아니다. 기존 하네스에 연결할 함수는 다음 두 개다.

```python
# 응답/사용량을 저장한 직후, 후보 파싱과 Lean 검증 전에 기록한다.
receipt = make_receipt(event, mode="api", prices=price_snapshot)
# subagent 경로에서는 mode="subagent"와 런타임 usage를 전달한다.
summary = summarize(all_receipts, budget_usd="1.00")
```

이 위치에서 기록해야 잘못된 응답·실패 후보도 비용에 남는다. 현재 native 하네스는 응답 직후
`usage.json`을 기록하고 최종 `usage-summary.json`과 함께 replay에서 대조한다. 별도의 외부 dispatcher를 연결할 때는
실행 전에 expected attempt를 저장하고 응답·사용량 수신 후 갱신해야 한다. 현재 CLI는 저장된 기록을 재계산하는 실험이다.
main의 `state.cost_usd`에 추정액을 실제 API 비용처럼 넣지 않는다. `reported_cost_usd`와
`estimated_token_cost_usd`를 각각 보존하고 사용량이 없는 기존 subagent 실행은 계속 미측정으로 둔다.

## 결과와 예산의 의미

- `reported_cost_usd`: API 제공 비용. subagent 구독 청구액을 만들어 넣지 않는다.
- `estimated_token_cost_usd`: 고정 단가에 따른 토큰 비용 추정.
- `accounted_cost_usd`: 제공 비용이 있으면 우선 사용, 없으면 추정액. `accounting_basis`로 구분한다.
- `*_known_subtotal_usd`: 알려진 기록만의 부분합. 전체가 완전하다는 뜻이 아니다.
- 미측정 항목이 있으면 전체 해당 합계는 `null`; 예산 잔액도 확정하지 않는다.
- `budget_status`: `not_configured/below_limit/exhausted/unknown`. 현재까지 받은 기록에 대한 비교다.

이 기능은 다음 호출의 비용 예약이나 동시 호출 예산 잠금을 구현하지 않는다.
`below_limit`은 다음 호출을 해도 한도를 넘지 않는다는 보장이 아니며, 대회 예산 준수 증거도 아니다.
사용량만으로 호출 전의 출력 길이와 실제 제공 비용을 정확히 알 수는 없다.

## 확인

```sh
python3 -m unittest discover -s experiments/usage-cost -p 'test_*.py' -v
```

공식 usage 구조를 본뜬 합성 입력으로 계산, 캐시·reasoning 중복 방지, 실패·미측정 기록,
중복 이벤트, 모델·단가 검증, 두 CLI 모드 및 기존 출력 보존을 검사한다.
유료 API 호출, 실제 subagent 생성, Lean 실행은 이 검사에 포함하지 않는다.

## 공식 문서 확인 — 2026-10-27

- [Codex 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode): JSONL의 turn 완료 usage와 입력·캐시·출력 필드.
- [사용량 관측](https://developers.openai.com/api/docs/guides/agents-api/observability): usage가 미확정일 수 있으며, 캐시는 입력에, reasoning은 출력에 포함됨.
- [토큰 계산](https://developers.openai.com/api/docs/guides/token-counting): 출력 사용량은 사용자에게 보이는 최종 텍스트보다 넓은 범위임.

문서의 토큰 필드 의미만 사용했다. 특정 모델의 현재 가격이나 구독 과금 방식을 가정하지 않았다.
