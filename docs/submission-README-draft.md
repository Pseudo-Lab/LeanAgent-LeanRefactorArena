# PseudoLab-LA — Lean Refactor Arena, Closed-source LLM track

This archive reproduces our submitted proof JSONL for the 60-problem final benchmark with the
final60 harness (`python -m lean_agent.final60`, PR #75 branch `final60/integrated-harness-20261104`, rc5).

- Every model call goes through OpenRouter (`--transport openrouter`, the only submittable transport).
- Hard cap US$2.99 per problem. Each request is reserved at its worst-case cost before it is sent,
  and every billed call counts, including retries, failed and discarded candidates.
- No previously found proofs are used: rows start cold (no warm start, no seeds, no carried proofs),
  and proofs produced outside OpenRouter are refused by the provenance check.
- Warm-up bank hints are off from rc5 (`route_rules.json` `hints.bank_cards: 0`). Rows started before rc5 are listed under Per-problem settings.

## Contact
<!-- 필수: 연락처 -->

Questions about reproduction: **TODO: 대표 연락처 이름과 이메일을 적으면 될 것 같습니다.**

| Name | GitHub | Email |
| --- | --- | --- |
| **TODO: 팀원 이름** | **TODO: GitHub ID** | **TODO: 이메일** |

<!-- 팀원 표는 선택입니다. 필요 없으면 표를 지우면 될 것 같습니다. -->

## Requirements

- Linux x86_64 with bubblewrap (`bwrap`), Python 3.12 (standard library only), Git, zstd
- Lean toolchains v4.26.0, v4.27.0, v4.30.0, v4.31.0, v4.33.1, v4.34.0, v4.34.1, v4.35.0-rc3
  (x86_64 Linux builds under `sources/final/toolchains/<version>/`)
- About 100 GB of disk for the prepared environments, 32 GiB or more of memory
- Tested on: Windows 11, WSL2 Ubuntu 24.04.2, x86_64, 28 threads, 45 GiB memory

## Pinned inputs
<!-- 필수: 고정된 Lean toolchain과 의존성 revision -->

| Input | Path | Pin |
| --- | --- | --- |
| Final dataset | `benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl` | SHA-256 `d53690b0…fadbd682` (the harness refuses other bytes) |
| Lean environments | `sources/final/` | `configs/final-environments.lock.json`: 17 environments, exact Git revisions, 6 sources, 127 problem-version pairs |

Environment preparation: `experiments/final-environment/README.md`.
**TODO: Lean 환경(`sources/final`, 약 97 GB)을 zip에 넣는지, 준비 스크립트로 만드는지 정해서 한두 줄로 적으면 좋을 것 같습니다. 스크립트라면 실행 명령도 함께 적으면 좋을 것 같습니다.**

## 1. OpenRouter API key
<!-- 필수: OpenRouter 키 설정 방법 -->

Use a regular OpenRouter API key (not a management key). Put it in a dotenv file outside the
repository; only the transport reads it, through `--key-file`.

```
OPENROUTER_API_KEY=sk-or-...
```

Model: `openai/gpt-6.1-sol` via OpenRouter (provider `openai` only, no fallbacks), reasoning effort
`high`, `max_tokens` 8192, seed 42, timeout 900 s, JSON mode. One model for every role.
Cost per call: max(OpenRouter `usage.cost`, list price of the returned token usage).

## 2. Run
<!-- 필수: 제출 JSONL을 다시 만드는 정확한 명령, 실행 방법 -->

`PY` = Python 3.12, `RUN` = a new directory outside the checkout, `KEY` = the dotenv file,
`DEADLINE` = an ISO 8601 time in the future with a UTC offset.

```bash
export PYTHONPATH=src FINAL60_PYTHON="$PY"
# 1. plan: environment coverage and routes (no API, no Lean)
"$PY" -B -m lean_agent.final60 plan --run-dir "$RUN"
# 2. free OpenRouter checks (no spend)
"$PY" -B experiments/final-batch-next/openrouter_transport.py key-status --key-file "$KEY"
"$PY" -B experiments/final-batch-next/openrouter_transport.py endpoint-check
# 3. run all 60 problems
bash scripts/final60_supervise.sh "$RUN" --key-file "$KEY" --rows 1-60 --deadline "$DEADLINE" --lean-memory-mib 16384
# 4. assemble submission.jsonl
"$PY" -B -m lean_agent.final60 assemble --run-dir "$RUN" --final
```

Output: `$RUN/submission.jsonl` (60 rows) and `report.json` / `report.md` (per-row origin, calls,
spend). A row uses its new proof only if it passed the rules check, the provenance check and the
all-version compatibility check; otherwise it keeps the original proof.
A fixed seed does not make sampling deterministic, so a rerun gives different candidates.
Full flags: `docs/final60/RUNBOOK.md`.

## Per-problem settings
<!-- 필수: 문제별로 설정이 다르면 기록 -->

All rows run the same command. Routing assigns settings by problem type (from the statement,
the original proof and its source), not by row, except:

| Setting | Rows | Effect |
| --- | --- | --- |
| `route_rules.json` `priority.weak_rows` | 2, 6, 14, 15, 35, 39, 40, 45, 48 | start earlier in the schedule (chosen from earlier team results); prompts unchanged |
| warm-up bank hint (`bank_cards: 1`, before rc5) | **TODO: 서버의 rows/F0NN/input/route.json에서 warmup-bank:이 있는 행 번호** | one generic strategy card from the warm-up bank in the prompt; turned off in rc5 |
| **TODO: 위 외에 문제별로 다르게 쓴 설정(재실행, regolf 등)이 있으면 추가하고, 없으면 이 줄을 지우면 될 것 같습니다.** | | |
