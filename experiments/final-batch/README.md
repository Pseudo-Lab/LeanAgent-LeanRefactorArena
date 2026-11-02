# Final 60-problem OpenAI batch

User authorization: all 60 rows in the `d53690b057f9` dataset, with an actual
API-cost stopping threshold of USD 1 per problem. The final request
may cross the threshold; no further request for that problem may start once
its settled cumulative cost reaches USD 1. Nominal total USD 60 therefore is
not a strict total cap. All search decisions, repairs, discarded responses,
  reasoning tokens, and malformed outputs count toward the same problem ledger.

Before any paid request the user changed the provider to the direct OpenAI API.
OpenAI response token usage is converted to USD using frozen public list prices;
this is an auditable usage-based calculation, not a provider invoice or an
OpenRouter-reported charge. Cached reads and writes are accounted separately.

The run uses the experimental worktree, not `main`. Runtime, raw provider
receipts, candidates, measurement evidence, and per-problem progress belong
under `runs/final-batch/`; large files remain Git-ignored.

## Policy

- Start from the supplied reference for each final problem; preserve its exact
  statement and original source context.
- Use the existing `actions-v1` protocol, retained candidate ancestry, focused
  source retrieval, and error-specific repairs. Try reuse of existing evidence
  and remove repeated automation before adding elaborate scaffolding.
- Keep the tested model family using direct OpenAI `gpt-6.1-sol`, reasoning
  `high`, standard service tier, and JSON actions. No paid hosted tools,
  provider fallbacks, or server-managed subagents are enabled. Check model
  access and freeze current public prices before dispatch.
- Cache the unchanged system prompt at an explicit 30-minute text breakpoint.
  The changing user-state suffix has no cache-write breakpoint. Semantic prompt
  text remains unchanged; reported cache reads/writes determine the cost ledger.
- Use no separate paid planner or judge. Every model request is journaled
  before transmission. Unknown billing stops further dispatch until reconciled;
  requests with uncertain outcomes are never blindly retried.
- Archive invalid and worse candidates. Choose improvements using proof length
  and raw heartbeat ratios, and verify required version compatibility.
- Measure the original before inference, screen candidates in the primary pin,
  and repeat measurements plus all required version checks for final selection.
  Scores measured on this macOS arm64 machine are local estimates, not official
  worker results.

## Memory and concurrency

The user limits simultaneous subagents to fewer than four. This session uses
at most three subagents. The runtime allows at most two concurrent provider
requests, while every Lean compilation and measurement uses one global file
lock. Each compiler uses one thread and an explicit memory limit. There are
no parallel library builds.

`resources.py` records the system memory estimate before launching Lean.
Below 15% available memory it waits, up to five minutes, then stops the affected
evaluation rather than starting a compiler. Missing monitoring also stops the
launch. Existing user applications and unrelated processes are never killed.
The resource log records swap usage as well as memory availability; pre-existing
swap alone does not imply current memory pressure.

## Prepared dependencies

Run the preparation described in
[final-environment](../final-environment/README.md) first. That pins 8 Lean
versions, 17 source environments, and 127 problem/version combinations. It
does not replace the batch's baseline, heartbeat, axiom, and candidate checks.
The dataset snapshot, exact source pins, environment registry, input corpus,
  prompts, code hashes, and provider model metadata must be recorded with the
batch so that generation and evaluation can be audited separately.

## Commands

From the experimental repository root, use one batch directory throughout:

```sh
PYTHONPATH=src .venv/bin/python experiments/final-batch/driver.py prepare --root runs/final-batch/20261101-final60-usd1-r1
PYTHONPATH=src .venv/bin/python experiments/final-batch/driver.py reseal --root runs/final-batch/20261101-final60-usd1-r1
PYTHONPATH=src .venv/bin/python experiments/final-batch/driver.py run --root runs/final-batch/20261101-final60-usd1-r1 --workers 2 --ensure-preflight --key-file /ABSOLUTE/PATH/TO/.env
PYTHONPATH=src .venv/bin/python experiments/final-batch/driver.py status --root runs/final-batch/20261101-final60-usd1-r1
PYTHONPATH=src .venv/bin/python experiments/final-batch/report.py --root runs/final-batch/20261101-final60-usd1-r1 --require-complete --export
```

`prepare` bounds source-retrieval work to two concurrent jobs and seals all
inputs. The prelaunch-only `reseal` updates the request timeout to 900 seconds,
archives the previous seal and implementation, and refuses any batch with an
API attempt. It is never used after inference starts. This accommodates work
prepared while the provider transport was being finalized; no model identity,
prompt, budget, or source corpus is changed by this correction.

`--ensure-preflight` measures and checks each problem before its first model
call, reusing completed no-API reference checks. Independent subagent workers
use the same root, disjoint `--rows` sets, and `--workers 1`; the global API
slots and compiler lock still apply across those processes. The initial six
rows are 1, 11, 21, 31, 41, and 51, one from each source. Their spend is part of
the same 60-problem authorization, not an additional pilot budget.

An interrupted run resumes with the same `run` command. Original provider
responses are stored before evaluation and checked against normalized receipts
and ledger hashes on recovery. Pending requests without verifiable responses
stop dispatch; never delete their ledger records to force a retry. A resource
failure preserves the billed response so local evaluation can be retried
without another model request. `report.py` checks raw response hashes, token
costs, threshold ordering, source/log hashes, selected declarations, and all-pin
evidence before it writes the final local `submission.jsonl`. It does not
upload or submit anything externally.

Each compiler invocation is isolated by the prepared macOS read-only/no-network
sandbox. Launch from an outer execution environment that permits that native
sandbox; nesting it inside a conflicting sandbox fails before Lean starts.
The compiler receives no API credentials. Missing tools, hash changes, and
unknown accounting stop the affected work instead of weakening these checks.

The presence of this document is not evidence that any paid request was sent;
the durable ledger and provider responses establish that.

Official model and billing sources checked on 2026-11-01:
[model](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[pricing](https://developers.openai.com/api/docs/pricing),
[cache accounting](https://developers.openai.com/api/docs/guides/prompt-caching),
[Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
For standard requests below the long-context threshold, per-million-token rates
are USD 2 ordinary input, 0.10 cached reads, 2.50 cache writes with a 30-minute
lifetime, and 10 output (including reasoning). Cache writes replace the ordinary
input rate for those tokens; they are not added on top of it.
