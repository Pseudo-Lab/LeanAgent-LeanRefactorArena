# LeanAgent — Lean Refactor Arena

가짜연구소 LeanAgent 팀의 Lean Refactor Arena 참가 코드입니다.
기존 Lean 증명을 리팩터링해 증명 길이와 검증 비용을 줄이고, 지정된 Lean 버전에서의 호환성을 검증합니다.

팀 실험 결과 대시보드: [lean-arena-dashboard.pages.dev](https://lean-arena-dashboard.pages.dev)

## Reproduction (final60)

The final submission is produced by the final60 harness, `python -m lean_agent.final60`, at tag
`final60-rc2` (`01f8c703ae8ac9ab94a352ecf15705283bf63c9c`). This section was added on top of that tag
in a commit that changes only this README and the file mode of `scripts/final60_supervise.sh`.
Commands and flags: [docs/final60/RUNBOOK.md](docs/final60/RUNBOOK.md).
Order of operations, deadline actions and uploads: [docs/final-run.md](docs/final-run.md).

### Requirements

- **OS and sandbox:** Linux x86_64 with bubblewrap, or macOS with `sandbox-exec`. On Linux the
  evaluator takes `bwrap` from `PATH`, then `$ARENA_BWRAP`, then `sources/final/bin/bwrap`, and
  refuses to compile without one.
- **Run machine (measured):** Windows 11 host, WSL2 Ubuntu 24.04.2 LTS, x86_64, 28 hardware threads,
  45 GiB `MemTotal` (WSL2 memory limit 46 GB).
- **Python 3.12, standard library only.** `pyproject.toml` declares `requires-python >= 3.10` and no
  dependencies; the run machine uses Python 3.12.3 for the run and the test suites, and the
  environment preparation README asks for 3.12 or newer. Git and zstd are also needed.
- **Disk:** about 100 GB for the prepared environments (`sources/final` measured 97,183 MiB on the
  run machine), plus about 1-2 GB per run directory (estimate).
- **Memory:** 32 GiB or more (estimate; the run machine has 45 GiB). Each Lean compile runs with
  `-M16384` for the Mathlib-based sources (ArkLib, CSLib, LeanPool, PhysLib, PutnamBench) and
  `-M4096` for Strata (`--lean-memory-mib` overrides both). The supervisor sizes the shared compile
  pool to `min(--compiler-slots, (MemTotal - --mem-reserve-gib) / --gib-per-compile)`, within 2..8,
  and admits each compile only while free memory allows it.
- **Money:** an OpenRouter key with credit. At most US$2.99 is spent per problem, so at most
  US$179.40 for the 60 problems.

### Pinned inputs (untracked; put them in place before `plan`)

| Input | Path | Pin |
| --- | --- | --- |
| Final dataset (the organizers' file: 60 rows, 502,056 bytes) | `benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl` | SHA-256 `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682` (measured); the harness refuses other bytes |
| Prepared environments | `sources/` (`sources/final/checkouts`, `toolchains`, `environments`, caches) | `configs/final-environments.lock.json` |
| Local environment registry | `configs/final-environments.local.json` | written by the environment preparation |

- `configs/final-environments.lock.json` pins 17 source/toolchain environments (exact Git
  revisions) for the 6 sources ArkLib, CSLib, LeanPool, PhysLib, PutnamBench and Strata, covering
  127 problem-version pairs, on the toolchains v4.26.0, v4.27.0, v4.30.0, v4.31.0, v4.33.1, v4.34.0,
  v4.34.1 and v4.35.0-rc3. Preparation steps:
  [experiments/final-environment/README.md](experiments/final-environment/README.md).
- The lock was produced on macOS arm64 (`"platform": "darwin_aarch64"`), and the tracked toolchain
  downloaders (`experiments/final-environment/toolchains.py`, `scripts/download_final_toolchain.py`)
  fetch the `darwin_aarch64` archives. On Linux, install the official x86_64 Linux release of each
  version under `sources/final/toolchains/<version>/`; the run machine has the
  `x86_64-unknown-linux-gnu` builds of all eight there (measured with `lean --version`).

### Model, provider and budget (pinned in code)

- One model for every role (each row seals `role_models: {}`): `openai/gpt-6.1-sol` through
  OpenRouter (`src/lean_agent/final60/catalog.py`, entry `gen_primary`) with
  `provider.only` = `provider.order` = `["openai"]`, `allow_fallbacks: false`,
  `require_parameters: true`, `max_price` US$2 per million prompt tokens and US$10 per million
  completion tokens, `reasoning.effort: "high"`, `seed: 42`, `max_tokens: 8192`, a 900 s timeout,
  non-streaming JSON mode (`response_format: {"type": "json_object"}`). `transport.validate_body`
  refuses any other request body. The catalog entries `gen_alt`, `gen_alt2` and `cheap` are off by
  default.
- **Hard cap US$2.99 per problem** (`contracts.CAP_USD`; `--cap` accepts only values in (0, 2.99]).
  Every request is reserved at its worst-case bound in the row's `ledger.json` before it is sent
  (`spent + open reservations + bound <= 2.99 - declared prior spend`), and every billed call
  counts, including retries and lost responses (unbilled 4xx refusals cost US$0).
- Debit per call: max(OpenRouter `usage.cost`, list price of the returned token usage), at the list
  prices frozen on 2026-11-04 02:57 KST (US$2/M input, US$10/M output, US$0.10/M cache read,
  US$2.50/M cache write). A lost response is charged its generation cost if known, else its bound.
- A fixed seed does not make sampling deterministic, so a rerun gives different candidates. The run
  directory keeps every request, response and charge: `rows/F0NN/problems/F0NN/steps/NNNN/`, each
  row's `ledger.json`, and the SQLite mirror `final60.sqlite`.

### Key

A dotenv file with one line `OPENROUTER_API_KEY=sk-or-...` (the loader also reads `OPENROUTER=`, and
accepts only `sk-or-` keys). Only the transport reads it, through `--key-file`. Keep it outside the
repository and never print it.

### Commands

From the repository root. `PY` is the Python 3.12 interpreter, `RUN` a new run directory outside the
checkout, `KEY` the dotenv file and `DEADLINE` an ISO 8601 time with a UTC offset (the competition run:
`2026-11-04T20:59:59+09:00`).

```bash
export PYTHONPATH=src FINAL60_PYTHON="$PY"
# Tests (no API). At final60-rc2 the three suites hold 215, 167 and 568 test cases.
export PROJECT_CACHE_DIR="$(mktemp -d)"
"$PY" -B -m unittest discover -s tests -p 'test_final60_*.py'
"$PY" -B -m unittest discover -s experiments/final-batch-next -p 'test_*.py'
"$PY" -B -m unittest discover -s tests
# 1. plan: environment coverage, routes and an all-original submission.jsonl (no API, no Lean)
"$PY" -B -m lean_agent.final60 plan --run-dir "$RUN"
# 2. Free OpenRouter checks (no spend)
"$PY" -B experiments/final-batch-next/openrouter_transport.py key-status --key-file "$KEY"
"$PY" -B experiments/final-batch-next/openrouter_transport.py endpoint-check
# 3. run, through the watchdog (it restarts the supervisor every 30 s until it exits 0)
nohup bash scripts/final60_supervise.sh "$RUN" --key-file "$KEY" --rows 1-60 --deadline "$DEADLINE" \
    > "$RUN.watchdog.out" 2>&1 < /dev/null &
# 4. status: frozen-code check first, then per-row state and spend (JSON)
"$PY" -B -m lean_agent.final60 status --run-dir "$RUN"
# 5. Final assembly by hand (the supervisor also runs it near the deadline)
"$PY" -B -m lean_agent.final60 assemble --run-dir "$RUN" --final
# 6. Code ZIP of the tracked files (needs a git checkout)
"$PY" -B -m lean_agent.final60 package --out "$RUN/code.zip" --repo . --name LeanAgent-LeanRefactorArena
```

- Start the watchdog with `bash`: the code ZIP stores every file with mode 0644, so
  `scripts/final60_supervise.sh` is not executable after unpacking.
- `--deadline` defaults to the competition deadline, `2026-11-04T20:59:59+09:00`. A later rerun must
  pass a future time, or the supervisor stops at once. Relative to the deadline: no new paid requests
  from `--soft-stop-min` (100) minutes before it, no new rows and a final assembly every 10 min from
  60 min before it, the last assembly and `SUBMIT-READY.txt` 20 min before it.
- `run` defaults: `--max-rows 8` (1..14), `--compiler-slots 6` (2..8), `--exploration-minutes 75`,
  `--mem-start-gib 10`, `--mem-reserve-gib 6`, `--gib-per-compile 3.5`, `--transport openrouter`
  (the only submittable transport; `--dry-run` uses the `mock` transport: no network, no spend,
  never submitted). The options of a run are saved in `$RUN/run-options.json`; restarting with the
  same `--run-dir` resumes every row from disk. Stop gracefully with `touch "$RUN/supervisor/STOP"`.
- `FINAL60_WARNING_GATE=reject|demote|off` (default `reject`) decides whether a Strata candidate with
  warnings may be kept.
- `--non-openrouter PATH` (repeatable) adds proofs produced outside OpenRouter, such as development
  runs, to the set the provenance checker refuses; the tracked result folders are built in.
- `plan` reads environment readiness from this checkout's `configs/` and `sources/`; pass
  `--prepared-repo` to read them from another checkout.

### Outputs

`$RUN/submission.jsonl` always has 60 rows. A row uses its new proof only when its root is a real
(not dry-run) OpenRouter root, its audit passed, its recorded spend is at most US$2.99, and the rules
(PR #64), provenance (PR #70) and Space intake-filter checks accept it; every other row keeps the
dataset original. Also written: `report.json` and `report.md` (per-row origin, local score estimate,
calls, spend, served providers), `checks/rules.json`, `checks/provenance.json`, `checks/official.json`
and, from the final assembly, `SUBMIT-READY.txt`. Scores in the reports are local estimates, not
official scores.

## 목표

원래 명제와 필요한 문맥을 유지하면서 증명 길이와 검증 비용을 줄이고, 지정된 Lean 버전에서
같은 후보가 동작하는지 확인합니다. 짧은 증명이 항상 적은 비용으로 검증되는 것은 아니므로
여러 지표를 함께 비교합니다.

| 확인할 항목 | 의미 |
| --- | --- |
| 증명 정확성 | 원래 명제를 보존하고 Lean 컴파일·공리 검사를 통과하는가 |
| 증명 길이 | 증명 소스의 토큰 수가 원본보다 줄었는가 |
| 검증 비용 | 동일 환경에서 측정한 Lean heartbeat가 줄었는가 |
| 버전 호환성 | 같은 후보가 문제에 지정된 Lean 버전과 의존성에서 검증되는가 |
| 재현성 | 후보 코드, 실행 환경, 검증 로그와 선택 근거를 다시 확인할 수 있는가 |

증명 소스의 토큰 수와 모델 API의 사용 토큰·비용은 별도로 기록합니다.
로컬 측정값과 후보 선택 점수는 공식 Arena 평가 결과와 구분하며,
대회 규칙과 제출 요건은 [공식 Arena](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena)를 기준으로 확인합니다.

## 개발 범위

첫 실행 하네스는 `src/lean_agent/`에 있습니다. 고정 응답과 실제 Lean 검증으로 실행 흐름을
확인하고, 저장된 기록으로 후보 선택을 재생할 수 있습니다.
[설치·실행·테스트와 현재 지원 범위](docs/first-harness.md)를 참고하세요.

[공통하네스 구축](docs/common-harness/README.md)에 행동 선택·후보 계보,
피드백 연구, 최종 60문제 환경·배치·검증 캐시의 통합 범위와 실행 방법을 정리했습니다.
공통 오프라인 검사는 `python3 -B scripts/check_common_harness.py`로 실행합니다.

| 영역 | 주요 작업 |
| --- | --- |
| 문제·실행 환경 | 원본 증명과 문맥 준비, Lean 버전·라이브러리 commit·의존성 고정 |
| 에이전트·리팩터링 전략 | 문맥 탐색과 도구 선택, 후보 생성, 증명 구조와 tactic 선택 전략 탐색 |
| 실행 하네스 | 모델·도구 호출, 실행 상태·문맥·예산 관리, 기록과 중단·재개 |
| 검증·수리 | 컴파일 오류와 검증 결과 전달, 수정 범위·재시도·종료 조건 설계 |
| 평가·후보 선택 | 원본과 후보의 지표 측정, 중간 기록, 최종 재검증과 후보 선택 |
| 실험 분석·제출 | 문제별 결과 비교, 스코어보드, 제출 산출물과 실행 근거 정리 |

전체적으로 연결할 실행 흐름은 다음과 같습니다.

```text
문제와 지정 환경 준비 → 원본 검증·기준값 측정
  → 에이전트가 다음 행동 결정 → 도구 실행 → 결과 기록·문맥 갱신 ↺
  → 탐색 종료 → 최종 후보 재검증·선택 → 제출 산출물 준비
```

에이전트는 소스·관련 정리 검색, 후보 작성, 검증 요청과 오류 수리 등 다음 행동을 결정합니다.
하네스는 이 반복 실행을 관리하고, 모델·도구 호출 결과와 비용을 기록합니다.
Lean 실행 환경은 문제에 고정된 버전과 의존성으로 후보를 실행하며,
평가기는 검증 결과와 측정값을 바탕으로 후보의 유효성과 개선 정도를 판단합니다.

초기 구현은 단일 에이전트의 도구 호출 루프를 기준으로 검토합니다.
계획형·다중 에이전트 전략은 같은 실행 기반에서 실험할 수 있도록 구성합니다.

## 폴더 구조 (초안)

아래는 전체 구조 초안입니다. 현재 첫 하네스의 실제 파일 구성은
[첫 하네스 문서](docs/first-harness.md)에 정리했습니다. 수집 데이터와 기존 실험은 아래 구분을 따릅니다.

```text
LeanAgent-LeanRefactorArena/
├── README.md
├── LICENSE
├── pyproject.toml
├── src/                 # 에이전트와 실행 하네스의 공통 코드
│   └── lean_agent/      # 패키지 이름은 가칭
│       ├── agents/      # 다음 행동 결정, 탐색·수리 전략
│       ├── harness/     # 실행 루프, 상태, 예산, 기록·재개
│       ├── models/      # 모델 API 연결과 사용량 수집
│       ├── tools/       # 에이전트가 호출하는 도구
│       ├── context/     # 문제 문맥·검색 결과·실행 이력 구성
│       ├── lean/        # 문제별 환경과 Lean 실행
│       ├── evaluation/  # 검증 결과 판정, 지표와 후보 선택
│       ├── prompts/     # 에이전트 지침과 전략별 프롬프트
│       └── cli.py       # 실행 진입점
├── configs/             # 모델·전략·실행 예산 설정
├── data/                # 출처·revision별 압축 코퍼스, catalog, 원본 보관본
├── benchmarks/          # 공식 Arena 스냅샷·출처 명세
├── experiments/         # 실험별 코드·설정·분석
├── runs/                # 실행별 후보·측정값·로그
├── submissions/         # 최종 제출 증명·결과·재현 설정
├── tests/               # 코드와 통합 동작 검증
├── scripts/             # 데이터 준비·실행·결과 집계
├── dashboard/           # 문제별 결과 확인 화면
└── docs/                # 설계·실험 방법·사용법
```

`experiments/`에는 새로운 전략이나 기능을 시험하는 작업을 실험별로 모읍니다.
공통 하네스와 Lean 검증·평가 기능을 사용하면서 전략·프롬프트·도구 조합을 바꿔 비교합니다.
각 실험의 목적·방법·실행법·결론은 README에 기록하고, 필요한 코드와 설정을 함께 둡니다.
공통으로 사용할 기능은 검증 후 `src/`로 옮깁니다.

증명 단축 작업(예산 제한 API 탐색 → 로컬 golf → 지정 버전 전체 검증)을 에이전트가 따라 할 수 있도록
[lean-proof-shortening skill](skills/lean-proof-shortening/SKILL.md)에 절차와 알려진 실패 원인을 정리했습니다.

공식 JSONL에서 여러 출처의 작업을 준비할 때는
[lean-arena-harness skill](skills/lean-arena-harness/SKILL.md)을 사용합니다. 에이전트에 해당
`SKILL.md`를 읽도록 요청하면 입력에서 지정 환경 목록을 만들고, 현재 증명 구조에 맞는 편집과
기존 단축·검증 도구로 이어갑니다. 외부 플러그인 설치는 필요하지 않습니다.

```sh
python3 skills/lean-arena-harness/scripts/plan.py \
  --benchmark /path/to/benchmark_data_final.jsonl \
  --source physlib --source cslib --output runs/manual/arena-plan/plan.json
```

이 명령은 실행 계획만 만들며 Lean·모델을 호출하지 않습니다. 개발 자료가 있으면
`--development /path/to/development.jsonl`로 선언 중복을 검사할 수 있습니다.

```text
experiments/
└── <실험명>/
    ├── README.md        # 목적·방법·실행법·결론
    ├── configs/         # 실험 설정
    └── ...              # 실험 코드와 분석
```

실행에서 생성된 후보·측정값·로그는 `runs/`에 저장하고,
최종 제출할 산출물은 `submissions/`에 모읍니다. 실행 기록의 세부 폴더 구성은 추후 확정합니다.

## 수집 데이터 사용

수집 코퍼스는 `data/corpora/<source>/<revision>/`에 압축 보관하고,
`scripts/corpus.py`로 목록 확인·무결성 검사·문제별 추출을 수행합니다.
과거 실험 코드는 Git 이력에 남기고, 실행 결과는 `runs/`에 보존합니다.
현재 데이터 사용법과 과거 코드 확인 방법은 `data/README.md`에 있습니다.

압축 데이터와 대형 결과는 로컬에 보관하며 Git clone에는 포함되지 않습니다.
에이전트에는 선택한 원본 문제와 허용 문맥을 별도로 전달합니다.

## 평가 하네스

현재 설치 패키지는 `src/lean_agent/`이며 `lean-agent` 또는 `python -m lean_agent`로 실행합니다.
검증한 환경 사전 점검·오류 피드백·실행 상태 조회(기능 1–3)를 공통 실행기에 통합했습니다.
설치·실행·조회·재생 방법은 [공통 하네스 사용법](docs/first-harness.md)을 참고합니다.
실제 문제를 위한 준비된 외부 라이브러리 연결, 누적 API 비용 종료, API/subagent 사용량 집계도
공통 패키지에서 제공합니다. [실제 문제·API 통합 사용법](docs/api-integration.md)에 설정과 검증 범위를 정리했습니다.

`refactor_eval/`과 [평가 하네스 사용법](docs/evaluation-harness.md)은 이전 평가 실험의 참조 자료입니다.
현재 패키지에는 포함하지 않으며, 기존 실험 코드와 기록은 그대로 보존합니다.

이 모듈은 로컬 평가 기반입니다. P02 실험의 호출 전 비용 예약은 실험 어댑터에 있으며,
공통 하네스의 누적 비용 종료는 마지막 호출의 초과분을 허용합니다. 제출 운영과 범용 OS 격리는
`docs/architecture.md`의 설계에 따라 별도로 연결해야 합니다.

## 라이선스

이 저장소는 [MIT License](LICENSE)를 따릅니다. 외부 benchmark와 라이브러리는 각 원출처의 라이선스를 확인합니다.
