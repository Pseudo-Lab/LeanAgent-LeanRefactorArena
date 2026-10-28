# Warm-up P02: subagent / OpenRouter 비교

이슈 [#28](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/28)의 첫 실제 모델 비교 실험이다.
`compare.py`는 현재 로컬 `src/lean_agent` 평가·선택 함수를 재사용한다. 공통 실행기 자체를 변경하지 않는다.


현재 공통 실행·입출력 사용량 집계·라이브러리 연결은 `src/lean_agent`로 통합했다.
[통합 사용법](../../docs/api-integration.md)을 기준으로 새 실행을 준비한다.
아래 수치와 기존 실행 설명은 통합 전 실험 기록이며, 과거 원문은 당시 보관 코드로 재생한다.

새 P02 실행은 다른 저장소의 고정 경로나 과거 P01 결과에 의존하지 않는다. 설치된 패키지를 사용하고,
원본 P02 packet과 준비된 라이브러리 manifest를 직접 지정한다. 모델·반복·계측 조건은
[`configs/p02-main-loop.json`](configs/p02-main-loop.json)에 분리했다.

```sh
python -m lean_agent freeze-environment \
  --library-path /ABSOLUTE/STRATA/BUILD/lib/lean \
  --library-path /ABSOLUTE/LEAN/lib/lean \
  --revision 451e5f047bafa010d178856db76c00029bfa4d7f \
  --sandbox macos-readonly --output configs/strata.local.json

python experiments/api-comparison/main_loop.py prepare --output runs/api-comparison/MY-LOOP \
  --common /ABSOLUTE/P02-ORIGINAL/common --prepared-environment configs/strata.local.json \
  --conditions experiments/api-comparison/configs/p02-main-loop.json
python experiments/api-comparison/main_loop.py check --output runs/api-comparison/MY-LOOP
python experiments/api-comparison/main_loop.py run --output runs/api-comparison/MY-LOOP
```

`--common`에는 `P02/metadata.json`, `P02/source.lean`, `packet.txt`가 있어야 한다.
해시와 대상 선언을 확인하고, 원본 앞부분을 문맥에 보존한다. `prepare`는 모델·Lean을 호출하지 않는다.
macOS 외 환경에서는 `--sandbox macos-readonly`를 사용할 수 없다. OS 격리는 별도로 준비한다.
원본 packet과 compiled library는 clone에 포함되지 않는 로컬 입력이며 절대 경로가 결과에 기록된다.
이 어댑터의 `.env` 읽기는 기존 동작을 유지한다. native CLI는 `--dotenv`를 명시해야 읽는다.

## main 공통 루프에 연결한 가벼운 실행

후속 `main_loop.py`는 최신 main의 **`lean_agent.harness.run()`을 직접 호출**한다.
별도 반복 루프를 만들지 않고 main의 상태 갱신·후보 검증·선택·피드백·최종 검증·replay를 사용한다.
한 실행에서 최대 3회 제안하며, 실행 전체 예산은 $2이다.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
ARENA_PY=/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/.venv/bin/python
$ARENA_PY -B experiments/api-comparison/main_loop.py prepare --output runs/api-comparison/MY-LOOP \
  --common /ABSOLUTE/P02-ORIGINAL/common --prepared-environment configs/strata.local.json
$ARENA_PY -B experiments/api-comparison/main_loop.py check --output runs/api-comparison/MY-LOOP
$ARENA_PY -B experiments/api-comparison/main_loop.py run --output runs/api-comparison/MY-LOOP
```

`prepare`의 기본 모델은 GPT-6.1 Sol·high다. 정리 직전까지의 원본 소스 91,086자와 필요한 import 정의를
시스템 입력에 넣는다. 이후 호출에는 main이 만든 최신 후보·검증 결과·진단이 user 입력으로 전달된다.
기존 `compare.py`의 단발 비교와 입력·반복 조건이 다르므로 같은 표에 합산하지 않는다.

준비된 Strata는 공통 `PreparedLeanEvaluator`와 `lean.prepared_environment` manifest로 연결한다. main의 네이티브 사전 점검을 유지하면서
고정된 LEAN_PATH·의존 artifact 해시와 읽기 전용 컴파일 프로세스를 추가한다. 자동 라이브러리 설치·빌드는 수행하지 않는다. 정리 이후 선언은 별도 전체 원본 모듈 컴파일로 확인한다.

`BudgetQuery`는 main이 기록한 요청을 그대로 전송한다. 매 호출 전 모델·provider 가격을 확인하고
최대 입력 byte·최대 출력의 비용을 예약한다. 이 경로는 검증 피드백을 위해 입력 예약 상한 200,000을
사용한다. 기존 단발 실행의 기본 상한 120,000은 유지한다. 예약이 불가능하면 전송 전에 실패하며
재시도하지 않는다. 과금 불명 응답은 main의 기존 중단·기록 절차를 따른다.

main 모델 설정에 선택적인 `reasoning_effort`, `max_price`를 추가했고 `temperature` 생략을 허용했다.
이 설정은 실제 요청 및 main의 replay에 함께 반영된다. 결과는 실행 폴더의 `report.json`, main 원문 기록은
`harness/`, 실제 전송·정산 기록은 `transport/`와 `budget.json`에 남는다.

2026-10-28 가벼운 실실행은 `20261028-main-loop-p02-light-v2`에 보관했다.
main 루프 한 번에서 모델을 3회 호출했고, **첫 후보 실패 → 오류 피드백 → 두 번째 후보 통과**를 확인했다.
세 번째 후보도 통과했으며 최종 선택은 두 번째 후보다. 원본 222 proof-token에서 104로 줄었고,
최종 raw heartbeat 중앙값은 2,695,001에서 1,459,084로 줄었다. 누적 입력 97,155토큰,
출력 4,418토큰, 실제 보고 비용 **$0.1394342**다. 전체 모듈 컴파일과 main replay도 통과했다.
[결과 요약](main-loop-results-20261028.json)에 조건과 단계별 사용량·판정을 보관한다.
상세 보고서는 해당 실행 폴더의 `report.md`다. 접미사 없는 앞선 light 폴더는 모델 호출 없는 사전 점검 기록이다.

## 누적 비용 도달 시 종료하는 실행

사용자가 승인한 threshold 모드에서는 마지막 응답으로 $2.50에 도달하거나 넘으면 종료한다.
마지막 한 호출의 초과분을 허용하는 기준이며, 엄격한 $2.50 상한과 다르다.

```sh
$ARENA_PY -B experiments/api-comparison/main_loop.py prepare \
  --output runs/api-comparison/MY-THRESHOLD --cost-stop-usd 2.50 \
  --common /ABSOLUTE/P02-ORIGINAL/common --prepared-environment configs/strata.local.json
$ARENA_PY -B experiments/api-comparison/main_loop.py run --output runs/api-comparison/MY-THRESHOLD
```

main 설정은 `limits.max_calls: null`, `limits.cost_stop_usd: "2.50"`이다.
호출 전 누적 사용액을 확인하고, 마지막 응답에서 기준에 도달하면 `cost_limit`으로 끝난다.
OpenRouter의 실측 비용이 없는 무제한 설정은 허용하지 않는다. 과금 불명·환경 실패·문맥 한도에 대한
기존 중단 정책은 유지한다. 성공·개선 정체·동일 후보 재등장으로는 조기 종료하지 않는다.
각 요청의 비용 예약과 원문 응답을 보존하고, 어댑터에서도 기준 도달 이후의 직접 호출을 막는다.

다음 명령은 실행 중인 기록을 읽기만 한다. 누적 비용, 검증 완료 수, 중복 소스, 마지막 최선 갱신을 표시한다.

```sh
$ARENA_PY -B experiments/api-comparison/trajectory.py --output runs/api-comparison/MY-THRESHOLD
```

종료 후 같은 명령에 `--save`를 붙이면 main replay와 마지막 한 호출에서의 기준 도달 여부를 확인하고
`trajectory.json`, `trajectory.csv`, `report.md`를 저장한다. `plot_trajectory.py --output ...`은
matplotlib이 설치된 Python에서 비용 대비 품질·후보 다양성 그래프를 만든다. 모두 모델을 재호출하지 않는다.

2026-10-28 threshold 실험은 **158회·$2.5019843**에서 `cost_limit`으로 종료했다.
마지막 호출 전 누적액은 $2.4934285였고, 초과분은 $0.0019843이다. 159번째 호출은 없었다.
실행 구간은 약 118.3분, HTTP 모델 요청 대기 합계는 약 47.0분이었다.

원본 **222 proof-token / raw HB 2,695,001 → 최종 120 / 499,239**, local score는 **0.362893**이다.
유효 후보는 84/158이며 고유 유효 소스는 26개, 동일 소스 재등장은 95회였다.
최종 개선의 80%는 6회차·$0.1760350에서 관측했고, 마지막 최선 소스 변경은 124회차·$2.1369096이었다.
그 뒤 $0.3650747을 더 사용하며 34회 호출했지만 최선은 바뀌지 않았다.
입력 5,089,921토큰 중 캐시 읽기는 4,800,588토큰이었다.

[threshold 결과 요약](threshold-results-20261028.json)에 조건·집계·개선 이력을 보존했다.
상세 보고서·CSV·그래프는 `runs/api-comparison/20261028-main-loop-p02-threshold-2p50/`에 있다.
main replay, 전체 원본 모듈 컴파일, 비용 합계·고유 generation ID·전송 본문 일치·비밀값 미기록 검사를 통과했다.
이 결과는 한 문제의 한 실행에 대한 관찰이며 다른 문제나 모델로 일반화하지 않는다.

완료된 실행의 JSON·그래프·최종 증명을 HTML 보고서로 묶을 수 있다. 모델을 재호출하지 않으며,
결과는 인터넷 연결 없이 열 수 있는 단일 `report.html`이다. 회차 필터·검색과 인쇄/PDF 버튼을 포함한다.
기존 HTML을 덮어쓰지 않는다.

```sh
$ARENA_PY -B experiments/api-comparison/render_html.py --output runs/api-comparison/MY-THRESHOLD
```

## 고정 조건

- 문제: Warm-up P02, `CallElimCorrect.extractedOldExprInVars`.
- Strata `451e5f047bafa010d178856db76c00029bfa4d7f`, Lean 4.26.0, 원본 모듈 전체 문맥.
- 기존 원본 metadata/source와 제한된 task packet을 사용한다. 이전 개선 증명은 생성 입력에 포함하지 않는다.
- subagent: 독립 Codex CLI 세션 3회, ChatGPT 로그인, `gpt-6.1-sol`, reasoning `high`.
- OpenRouter: `openai/gpt-6.1-sol`, OpenAI provider, reasoning `high`, 독립 5회.
- 실행당 후보 하나. 고정 초기 메시지를 매번 제공한다. 두 방식의 첫 3회가 비교 대상이고 API 4–5회는 추가 반복이다.
- 단일 부모가 후보를 검증한다. 원본·후보 계측은 3회씩이며, 선택된 증명도 따로 재검증한다.
- 최소 `0.5 × (후보 proof-token/원본 proof-token + 후보 raw-heartbeat/원본 raw-heartbeat)`를 선택한다.
  동률 처리와 proof-token 계산은 공통 하네스를 그대로 사용한다. 이 값은 공식 대회 점수가 아니다.

모델 호출 중 사용한 정확한 요청과 원시 응답, CLI runtime JSONL, 평가 코드 사본, 입력 해시,
컴파일러·라이브러리 artifact 해시, Lean 로그, 계측·선택·최종 검증 결과를 보관한다.

## 실행

모든 명령은 저장소 루트에서 실행한다. 프로젝트 Python 환경과 중앙 캐시를 사용한다.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
ARENA_PY=/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/.venv/bin/python
```

새 실험 폴더를 준비한다. 이 명령은 원본 Lean 검증과 공개 모델 metadata 조회만 수행한다.
기존 폴더는 재사용하지 않는다. 기본 경로의 기존 P02 원본 자료와 준비된 Strata 환경이 필요하다.

```sh
$ARENA_PY -B experiments/api-comparison/compare.py prepare --output runs/api-comparison/MY-RUN
```

`.env`의 `OPENROUTER` 또는 `OPENROUTER_API_KEY`를 사용한다. 값을 shell에서 실행하거나
문자열 보간하지 않으며 인증값을 산출물에 기록하지 않는다. CLI subagent에는 API 키 환경변수를 전달하지 않는다.

```sh
$ARENA_PY -B experiments/api-comparison/compare.py subagent --output runs/api-comparison/MY-RUN --trial 1
$ARENA_PY -B experiments/api-comparison/compare.py openrouter --output runs/api-comparison/MY-RUN --trial 1
```

동일하게 subagent 2–3, OpenRouter 2–5를 각각 한 번씩 실행한다. Lean 계측이 겹치지 않도록 직렬 실행한다.
CLI subagent의 작업 폴더는 중앙 프로젝트 캐시 아래의 새 빈 폴더다. 사용자 설정·이전 대화는 로드하지 않는다.
CLI의 기본 시스템·도구 정의는 raw API와 다르므로 전체 모델 입력이 같다는 뜻은 아니다.
실제 도구 실행이 있었다면 `runtime_tool_items`에 보존해 비교 해석에 반영한다.

수동 subagent 응답 파일도 `ingest --trial N --response FILE --agent-id ID`로 가져올 수 있다.
이 경우 runtime 토큰·시간은 미측정으로 남긴다. 기본 실험에서는 `subagent` 명령을 사용한다.

## 비용 제한

- 유료 실행당 최대 $2, 전체 $10, API 실행 최대 5개. 한 실행은 호출 한 번이다.
- 공개 endpoint 가격을 고정하고 실행 직전에 다시 확인한다. provider 고정, fallback·자동 retry를 끈다.
- 요청은 일반 텍스트 두 메시지로 제한한다. 도구·플러그인을 제공하지 않는다.
- 입력 비용 예약은 요청 UTF-8 byte 수 + framing 4,096토큰을 사용한다. OpenAI byte-level text tokenizer의
  보수적 상한으로 사용하며 120,000을 넘으면 실행하지 않는다. 표시용 proof-token 수와 다르다.
- 출력은 reasoning을 포함해 최대 16,384토큰. provider의 장문·cache-write 단가까지 확인하고
  입력 최대 $5/MTok, 출력 최대 $15/MTok으로 비용을 예약한다.
- 호출 전에 `budget.json`에 예약을 fsync/원자적으로 저장한다. 잠금 중 예약된 실행이 있으면 다른 호출을 막는다.
- 비용이 확인된 응답만 실제 비용으로 정산한다. 응답 전 실패·timeout·비용 누락·예약 초과는 이후 유료 실행을 막는다.
- HTTP redirect와 자동 재시도가 없다. 잘못된 JSON이나 Lean 실패 후보도 호출 기록과 비용에 포함한다.
- 예약은 로컬 코드의 사전 제한이다. 현재 inference key에는 관리 키 권한이 없어 OpenRouter 측 $2 전용 키를
  만들지는 않는다. provider가 공개 단가·출력 한도를 지키는 조건의 상한이며, 다른 앱의 동시 지출은 통제하지 않는다.

`usage.cost`는 OpenRouter 보고 비용이다. subagent의 실제 구독 청구액은 알 수 없으므로 `cost_usd: null`로 둔다.
대신 CLI의 개별 turn runtime usage와 고정 API 단가로 계산한 `estimated_token_cost_usd`를 제공한다.
캐시·reasoning 중복 계산은 기존 `experiments/usage-cost/accounting.py`를 재사용한다.
추정 가정·미측정도 함께 기록한다. `$2`를 모두 소진하는 실험이 아니다.

## 검사와 기록 재생

```sh
$ARENA_PY -B -m unittest discover -s experiments/api-comparison -p 'test_*.py' -v
$ARENA_PY -B experiments/api-comparison/compare.py report --output runs/api-comparison/MY-RUN
```

report는 모델이나 Lean을 호출하지 않는다. 보관 파일 해시, 고정 요청, 비용 정산과 선택 규칙을 다시 계산한다.
실험 자료는 `runs/api-comparison/`에 보관하고 Git에서는 제외한다. `.env`도 Git에서 제외한다.
이번 비교만으로 다른 문제의 성능이나 실행 방식의 일반 우열을 결론 내리지 않는다.

## 2026-10-28 실행 결과

전체 8회 실행과 기록 재생을 완료했다. [보관 가능한 결과 요약](results-20261028.json)에
호출별 사용량·비용·판정, 조건과 검증 결과를 남겼다.

| 첫 3회 비교 | 생성 후보 통과 | 개선 채택 | 입력 토큰 중앙값 | 출력 토큰 중앙값 | API 환산 비용 합계 |
|---|---:|---:|---:|---:|---:|
| Codex CLI subagent | 1/3 | 1/3 | 20,381 | 2,482 | $0.1259104 |
| OpenRouter | 0/3 | 0/3 | 2,306 | 4,223 | $0.1274061 |

OpenRouter 추가 2회도 후보 검증에 실패했다. 총 5회 보고 비용은 **$0.2009787**, 조회된 잔액은
**$9.7990213**이다. 실패한 후보를 포함해 모두 비용에 집계했다. subagent 환산액은 실제 구독 청구액이 아니다.
OpenRouter 최초 호출은 캐시 쓰기, 후속 호출은 캐시 읽기로 기록되어 캐시 조건도 동일하지 않다.

통과하지 못한 후보의 Lean 진단은 타입 불일치 또는 미해결 goal이었다. 원본을 유지하는 경우를 포함해
최종 선택 증명은 8/8 검증됐다. CLI subagent의 도구 실행은 0회였으며, 동일한 명시적 입력에서도
기본 시스템·도구 문맥 때문에 전체 사용량에 차이가 나타났다.

예산·집계 테스트 7개, 전체 기록 재생, 입력 해시, 비용 예약·정산, 비밀값 미기록 검사를 통과했다.
최종 소스 감사에서 공통 `diagnostics.py`의 끝 빈 줄만 달라진 것을 관찰했으며 AST와 평가·선택 코드는 같았다.
원본 사본과 관찰된 차이는 실행 폴더의 `validation.json` 및 `code-observed-after/`에 보존했다.

상세 표는 `runs/api-comparison/20261028-p02-sol-high-v2/comparison.md`, 원문 기록은 같은 폴더의
각 `subagent-NN/`, `openrouter-NN/` 아래에 있다. 앞선 `20261028-p02-sol-high/` 폴더는 모델 호출 없는 준비 기록이다.
