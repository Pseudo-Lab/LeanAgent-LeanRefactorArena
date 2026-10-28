# API / subagent 사용량·비용 기록 — 기능 5

상위 [#28 API 비교 테스트](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/28)의
하위 [#29](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/29)에서 진행한다.
브랜치는 `codex/usage-cost-accounting`, 기준은 PR #3이 병합된 main `1f51537`이다.
기존 비용 계산 초안을 보완하고 실제 응답으로 검증한 experiments 기록이다.
검증 당시 코드는 재현을 위해 보존한다. 이후 src 통합 사용법은 [기능 5 통합 문서](../../docs/usage-cost.md)를 참고한다.

| 파일 | 역할 |
| --- | --- |
| `accounting.py` | 사용량 정규화, 비용 계산, 합계·agent/model별 집계, 기록 가져오기 |
| `live_check.py` | 공개된 짧은 고정 입력으로 OpenRouter 1회 호출, 원본 저장, 오프라인 replay |
| `examples/` | 합성 예제 및 실제 사용량만 추출한 검증 자료 |
| `validation-20261028.json` | 실제 호출·재사용 기록 검증, 소스·입력 해시와 한계 |
| `test_accounting.py`, `test_capture.py` | 계산·실패·부분 기록·중복 방지·실제 usage 회귀 검사 |

## 두 모드와 계산

- `api`: 응답의 `usage.cost`를 보고 비용으로 보존하고, usage와 고정 단가로 계산한 추정액을 별도로 표시한다.
- `subagent`: 런타임이 제공하는 입력·출력 usage로 API 환산 추정액을 계산한다. 실제 구독 청구액은 `null`이다.

```text
추정 USD = ((입력 - 캐시 읽기 - 캐시 쓰기) × 일반 입력 단가
           + 캐시 읽기 × 캐시 읽기 단가
           + 캐시 쓰기 × 캐시 쓰기 단가
           + 출력 × 출력 단가) / 1,000,000
```

단가는 USD/100만 토큰이다. Decimal로 계산하며 단가·출처·기준 시각·해시를 고정한다.
reasoning은 전체 출력에 이미 포함되어 다시 더하지 않는다. 모델이 답변에 적은 자체 추정 토큰이나
문자열 길이로 usage를 만들지 않는다. 음성·이미지·영상 usage가 있으면 텍스트 단가 추정은 미지원으로
남기고, API가 제공한 비용은 보존한다. 도구·검색 등 별도 비용은 토큰 추정액의 범위 밖이다.

캐시 정보가 없으면 일반 입력으로 계산하고 가정을 표시한다. 캐시 사용량이 있는데 단가가 없으면
추정액은 `null`이다. 여러 TTL·장문 단가 등 조건이 다른 기록에는 해당 조건의 별도 단가표가 필요하다.
usage 형식이 잘못되어도 유효한 제공 비용은 남기며, 잘못된 비용 필드는 토큰 usage와 따로 진단한다.

## 기록과 합계

이벤트에는 `run_id`, `agent_id`, `event_id`, `model`, `status`, `usage_scope`를 지정한다.
API는 `response`, subagent는 런타임 `usage`를 제공한다. 상태는 `completed/failed/incomplete`다.
실패한 후보·폐기한 답변도 호출 기록과 비용에서 제외하지 않는다.

- `usage_scope: exclusive_delta`: 자기 호출/turn의 사용량만 받는다. 부모의 자식 포함 합계나 누적값을 섞지 않는다.
- 동일 이벤트는 한 번만 합산한다. 동일 ID에 다른 내용, 동일 API 응답 ID를 다른 이벤트로 재등록하면 거부한다.
- `reported_cost_usd`와 `estimated_token_cost_usd`를 분리한다. `accounted_cost_usd`는 보고 비용 우선이며 `accounting_basis`로 출처를 구분한다.
- 미확인 기록이 있으면 전체 합계는 `null`, 알려진 값은 `*_known_subtotal_usd`에 남긴다. 토큰도 전체·부분합·누락 수를 제공한다.
- `by_agent_id`와 `by_model`로 집계한다. API와 subagent는 별도 보고서로 비교한다.
- `budget_status`는 받은 기록에 대한 사후 비교다. 다음 호출 예약·동시 실행 잠금·계정 전체 한도 준수를 보장하지 않는다.

Codex JSONL은 단일 agent의 순서 있는 스트림을 받는다. 여러 thread, 다른 모델, 자식 agent 호출을
포함한 범위 불명 기록은 거부한다. 호출자가 고정 실행 설정에서 모델을 전달해야 한다.
종료되지 않은 turn이나 마지막 불완전한 JSONL 줄은 미확정 비용으로 남긴다. 완성된 줄이 손상되면 오류다.

## 오프라인 실행

Python 3.10 이상과 표준 라이브러리만 사용한다. 이 로컬 worktree에서는 명령 세션마다 중앙 경로를 설정한다.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/.worktrees/arena-usage-cost
python3.13 experiments/usage-cost/accounting.py --mode api \
  --input experiments/usage-cost/examples/observed-api-records.json \
  --prices experiments/usage-cost/examples/observed-prices.json
python3.13 experiments/usage-cost/accounting.py --mode subagent \
  --input experiments/usage-cost/examples/observed-subagent-records.json \
  --prices experiments/usage-cost/examples/observed-prices.json
```

`examples/prices.json`은 가상 테스트 단가다. `observed-prices.json`은 2026-10-28 검증 당시의
OpenRouter standard OpenAI 단가 스냅샷이며, 미래 호출의 최신 단가로 간주하지 않는다.
실제 검증 자료는 usage만 남겼고 API 응답 ID는 대체했으며 증명·대화 내용은 포함하지 않았다.

```sh
python3.13 experiments/usage-cost/accounting.py --mode subagent --format codex-jsonl \
  --input PATH/runtime.jsonl --run-id RUN --agent-id AGENT --model gpt-6.1-sol \
  --prices experiments/usage-cost/examples/observed-prices.json
python3.13 experiments/usage-cost/accounting.py --mode api --format harness-run \
  --input PATH/TO/HARNESS_RUN --run-id RUN --agent-id main \
  --prices experiments/usage-cost/examples/observed-prices.json \
  --output runs/usage-cost/RUN/report.json
```

하네스 importer는 지정된 `steps/*/request.json`과 `response.json`을 읽는다. 응답이 없는 요청도
미완료 호출로 포함하며, 후보 검증 결과와 무관하게 사용량을 보존한다. 입력 파일 해시를 기록하고
원본을 수정하거나 모델·Lean을 실행하지 않는다. 기존 보고서 파일은 덮어쓰지 않는다.

## 실제 API 확인

아래 `run`만 유료 모델을 호출한다. `OPENROUTER_API_KEY` 환경변수를 사용하거나 명시적으로
`--dotenv /absolute/path/.env`를 전달한다. dotenv의 `OPENROUTER`/`OPENROUTER_API_KEY` 값을
코드로 실행하거나 보간하지 않는다. 키·헤더·HTTP 예외 원문을 기록하지 않는다.

```sh
python3.13 experiments/usage-cost/live_check.py run --output runs/usage-cost/MY-CHECK
python3.13 experiments/usage-cost/live_check.py replay runs/usage-cost/MY-CHECK
# 이후 코드가 바뀌었다면 보관 코드를 사용한다.
python3.13 -B runs/usage-cost/MY-CHECK/code/live_check.py replay runs/usage-cost/MY-CHECK
```

`openai/gpt-6.1-sol`, standard `openai` provider를 고정하고 fallback·redirect·자동 retry를 끈다.
짧은 공개 JSON 응답 요청 한 건, 최대 출력 256토큰만 사용한다. 공개 endpoint 단가를 저장하고,
고정 입력의 보수적 토큰 여유와 장문 단가까지 고려한 사전 계산이 $0.05를 넘으면 호출하지 않는다.
이 값은 테스트 한 건의 로컬 보호 장치이며 제공자 청구나 다른 앱의 지출을 통제하는 계정 한도는 아니다.
호출 전에 요청·단가 해시와 attempt를 fsync한다. 응답 미수신·중단은 미확정으로 기록하고 재호출하지 않는다.

## 2026-10-28 검증 결과

| 자료 | 새 호출 | 보고 비용 | 토큰 환산액 |
| --- | ---: | ---: | ---: |
| 새 OpenRouter 소규모 확인: 입력 17 / 출력 12 | 1 | $0.000154 | $0.000154 |
| #28의 기존 API 5건 | 0 | $0.2009787 | $0.2009787 |
| #28의 기존 Codex CLI 3건 | 0 | 미확인 | $0.1259104 |

이번 작업에서 새로 발생한 API 보고 비용은 **$0.000154**다. 기존 API 기록에는 캐시 읽기·쓰기와
reasoning이 포함되어 있으며 각 건의 보고 비용과 환산액이 일치했다. 기존 subagent는 입력 61,181,
캐시 읽기 36,864, 출력 7,359토큰이다. 이 환산액은 구독 청구액이나 두 방식의 성능 비교 결과가 아니다.
원본 usage와 단가로 재계산하고, 보관 코드 replay가 외부 호출 없이 성공하는 것을 확인했다.

```sh
python3.13 -m unittest discover -s experiments/usage-cost -p 'test_*.py' -v
```

35개 검사는 네트워크 없이 실행한다. 사용량·가격·보고 비용·누락·실패·partial JSONL·중복 이벤트·
실제 usage projection·사전 가격 차단·timeout 무재시도·replay 변조 감지를 다룬다.
raw 응답·CLI 기록은 무시된 `runs/usage-cost/`에 보존한다. 별도 API 비교 작업의 파일은 수정하지 않았다.

## 공식 사용량 정의

- [Codex 비대화형 JSONL](https://learn.chatgpt.com/docs/non-interactive-mode): `turn.completed`의 런타임 usage.
- [OpenAI 토큰 계산](https://developers.openai.com/api/docs/guides/token-counting): 보이는 출력 문자열과 보고 usage의 차이.
- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting): 제공 비용·입출력·캐시·reasoning 필드.
- [OpenRouter prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching): 캐시 읽기·쓰기 비용 구분.
