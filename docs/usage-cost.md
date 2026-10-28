# 기능 5 — src 사용량·비용 기록

이슈 [#29](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/29)의
검증 코드를 최신 main의 `lean_agent.accounting`에 통합했다.
`lean_agent.usage_cost`는 같은 계산기를 공개하는 호환 모듈이다. `python -m lean_agent usage-cost`,
기존 실험 CLI, `lean-agent-usage`도 같은 구현을 사용한다.
실험 자료와 과거 실행의 보관 코드는 각각 당시 검증을 재현하는 근거다.

## 실행과 저장

기존 `lean-agent run --config CONFIG --output RUN` 실행에 자동 적용된다.
추정용 단가가 없어도 API 응답의 `usage.cost`는 누적한다. 단가가 필요한 경우
설정 JSON에 다음 항목을 추가한다. 경로는 설정 파일의 디렉터리 기준이다.

```json
"usage_cost": {"prices": "prices.json"}
```

단가 파일은 schema_version 1, currency USD, rate_card_id, source, as_of,
models를 갖는다. models의 각 모델에는 input_per_million, output_per_million과
선택적인 cached_input_per_million, cache_write_per_million을 문자열로 지정한다.
단위는 USD/백만 토큰이다. 실제 호출의 모델·provider·서비스 등급·문맥 길이에 맞는
고정 단가를 사용해야 한다. 자동 가격 조회는 하지 않는다.
형식 예제는 `experiments/usage-cost/examples/prices.json`이며 합성 단가다.

| 파일 / 필드 | 내용 |
| --- | --- |
| `input/usage-prices.json` | 실행 시작 시 동결한 단가와 출처. 미설정이면 빈 모델 단가표 |
| `steps/NNN/request.json`, `response.json` | 호출 이전 요청 기록과 원본 응답. 증명 성공 여부와 무관하게 집계 |
| `usage-cost.json` | 종료·처리 가능한 중단 시 호출별 영수증, 토큰·비용 합계, agent/model별 합계, 근거 해시 |
| `usage-cost-error.json` | 중단 정리 중 보고서를 만들 수 없을 때의 명시적 오류 |
| `steps/NNN/usage.json`, `usage-summary.json` | 기존 응답별 기록과 전체 토큰 합계·평균·중앙값. 새 비용 보고서와 함께 유지 |
| `status --json`의 `usage_cost` | 조회 순간 저장된 요청·응답으로 재계산한 누적치 |
| `status --json`의 `usage_cost_error` | 부분 쓰기·손상 등으로 집계가 불가능하거나 저장 보고서와 불일치 |

호출별 `reported_cost_usd`는 API 보고 비용, `estimated_token_cost_usd`는 고정 단가
추정액이다. `accounted_cost_usd`는 보고 비용을 우선하고 없으면 추정액을 사용한다.
합계는 누락이 있으면 `null`이며 `*_known_subtotal_usd`에 확인된 부분만 표시한다.
reasoning은 출력 토큰에 포함되어 이중 가산하지 않는다. 캐시 읽기·쓰기는 일반 입력과
분리한다. 멀티모달 사용량은 텍스트 단가로 추정하지 않는다.

응답 없는 요청은 `incomplete`이며 비용을 0으로 취급하지 않는다. SIGKILL처럼 정리 코드가
실행되지 않으면 최종 `usage-cost.json`이 없어도 status는 저장된 요청·응답으로 집계한다.
부분 JSON을 읽으면 집계 불가로 표시하고 다음 조회 때 다시 계산한다.
사전 점검 실패·check 전용 실행처럼 요청이 기록되지 않은 native 실행은 0건이다.
외부의 빈 사용량 파일은 무과금 근거로 인정하지 않는다. fixture의 비용은 모의 값이다.

```sh
lean-agent status RUN --json
lean-agent replay RUN
python3 -B RUN/code/replay.py replay RUN
```

replay는 동결된 코드·단가·응답으로 보고서를 재계산해 비교한다. 모델과 Lean을 호출하지
않으며 폴더 이동 후에도 재현된다. 과거 실행은 그 실행에 보관된 코드로 replay한다.

## API / subagent 외부 기록 가져오기

설치된 패키지는 `lean-agent-usage` 명령을 제공한다.
`python3 -m lean_agent.usage_cost`로도 같은 기능을 실행할 수 있다.

```sh
lean-agent-usage --mode api --format harness-run --input RUN \
  --run-id experiment-1 --agent-id harness --prices prices.json --output api-cost.json

lean-agent-usage --mode subagent --format codex-jsonl --input runtime.jsonl \
  --run-id experiment-1 --agent-id worker-1 --model FIXED_RUNTIME_MODEL \
  --prices prices.json --output subagent-cost.json
```

`--format records`는 정규화 이벤트 목록을 받는다. 각 이벤트의 run_id/agent_id/event_id,
model/status/usage_scope(`exclusive_delta`)를 명시하고 API는 response, subagent는 usage를
넣는다. 여러 worker는 고유 agent_id로 같은 목록에 합칠 수 있다. API/subagent 모드는
별도 보고서로 만든다. 같은 이벤트의 중복 전달은 제거하고 서로 다른 내용은 거부한다.
부모의 누적치와 자식의 사용량을 함께 합산하지 않는다. Codex JSONL에서 자식 호출이
감지되면 범위 불명으로 거부하므로 배타적인 agent별 사용량을 제공해야 한다.

subagent는 런타임이 제공한 토큰과 실행 설정의 모델을 사용한다. 모델에게 토큰 수를
추측하게 하지 않는다. 결과는 **API 환산 추정액**이며 구독 실제 청구액은 `null`이다.
현재 native 실행 backend는 fixture/openrouter다. 이 통합은 subagent 기록 가져오기를
제공하며 subagent 실행·배치를 새로 구현하지 않는다.

## 정책과 검증 범위

추정액을 얻더라도 API 보고 비용이 없으면 기존 `unknown_cost` 종료 규칙을 유지한다.
공통 `limits.cost_stop_usd`의 응답 후 누적 비용 종료도 유지한다. 별도의 $2.8 사전 최종화
정책과 엄격한 $3 상한, 일반 동시 호출 예산 예약, 자동 재시도·재개는 이 작업 범위에서
제외한다. importer의 선택 `--budget-usd`는 관측 기록 비교에만 쓰며 호출을 제어하지 않는다.

검증은 계산·캐시·중복·부모/자식 범위, 실패 증명의 비용 포함, 호출 중 조회,
중단/부분 응답, SIGKILL 이후 조회, 단가 동결·폴더 이동·변조 검출·보관 코드 replay를 포함한다.
기존 실제 API 6건의 보고/추정 합계는 $0.2011327로 일치하며 기존 subagent 3건의
환산액은 $0.1259104다. src 통합 검증에서는 추가 유료 호출·새 subagent 실행을 하지 않았다.

최신 main과 통합한 회귀·설치 패키지·실제 Lean 검증 근거는
[usage-cost-validation.json](usage-cost-validation.json)에 보존한다. 단위·연결 검사의 compiler는
fixture이며, 설치 wheel의 Lean 4.26.0 스모크는 실제 compiler와 고정 모델 응답을 사용했다.
