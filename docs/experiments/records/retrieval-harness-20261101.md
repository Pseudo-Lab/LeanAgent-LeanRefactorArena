# v11 검색 통합 하네스

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

v10 위에 선언 검색·타입 구조 검색·외부 proof 예제 검색을 연결한다.

## 확인된 결과와 해석

P11 28호출·19평가·12유효·$1.8724256. post-golf368토큰/9,067,259raw HB. 외부 검색 도구를 호출하지 않았고4.31만 검증했다.

## 코드·Lean 보존 결정

검색의 효과를 입증한 결과로 취급하지 않는다. 공통 경로 통합은 후속 작업이다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/retrieval-harness-20261101/README.md` | `로컬 작업본` | `1ef18ebc4ec5a5e62a72fc43c41e2bf2b363a6c150c8f568cc379e7c88e676c9` |

## 원문: `experiments/retrieval-harness-20261101/README.md`

### Retrieval-enabled harness

This entrypoint extends the current parallel v10 harness with common premise
retrieval. Transactional request accounting, immutable inputs, the original
proof guard, three fresh measurements, and full golf are inherited unchanged.
Historical run implementations remain reproducible.

The same `instructions.txt` and tool schema apply to every problem:

| Tool | Searches or reads |
| --- | --- |
| `search`, `types` | Existing original-scope name lookup and canonical Lean types/axioms |
| `retrieve` | Names and complete preceding declaration signatures |
| `type_search` | All original-scope compiler types: used constants, conclusion constants/head, kind, binder count |
| `external` | All indexed OpenAI OAI source modules, with excerpts and available-reference hints |
| `external_source`, `external_refs` | Further original source lines or exact available-name references |

`type_search` is compiler-derived structural filtering, not type unification.
For example, `contains:Finset.sum head:Eq kind:theorem` finds equality theorems
whose types mention the exact resolved sum constant. `conclusion:Set.ncard`
restricts the occurrence to the final conclusion, rather than a hypothesis.
Canonical types and actual Lean application checks remain separate steps.

The type index must cover every name and original module in the native index;
incomplete exports are rejected. It does not read theorem proof values. Helper
imports cannot expand solver-visible scope. Fingerprints bind the index to the
compiler, project, original prefix and helper implementation. All derived data
is stored in the mandatory central cache.

External source is unverified reference material from a different toolchain.
The index contains 162,417 OAI source modules from OpenAI math commit
`4eaee87548250b2682affda7d05d947c05554bae`; target stubs from ComparatorChallenges
are excluded. Source hashes are checked before returning excerpts. External
references are lexical hints intersected with the original native index, not
verified dependencies or permission to add imports/axioms.
The local clone may omit the OAI working tree to save disk space. Every indexed
module remains searchable. A missing result file is recovered on demand with
`git show` from the index's exact 40-hex commit in the complete local Git object
store, with `GIT_NO_LAZY_FETCH=1` and no network operation. Only canonical paths
under the pinned clone's `lean/OAI` tree are accepted. The recovered bytes must
match the indexed SHA before atomic materialization; an existing changed file
is rejected and never overwritten. Namespace, index coverage and proof content
are unchanged by this storage policy. Preprint PDFs also remain in Git history.

Preparation can reuse same-case original-prefix compiler inventories from other
run input directories only when prefix, compiler/project fingerprint, helper
source, index SHA, and stripped source context all agree. Only `context.json`
and a hash-verified compiler reference are copied. Prior solver proofs, attempts,
scores and submissions are never read by this reuse path.

Every retrieved result is retained with its original observation IDs, content
hash and scope. Repeated and aliased observations preserve provenance without
discarding unique facts. Database and manifest hashes join the existing runtime
freeze; changed cached evidence is rejected. Pagination bounds individual
responses while keeping all results accessible.

From the Arena checkout:

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
python3 -B experiments/retrieval-harness-20261101/retrieval_runner.py prepare \
  --root runs/retrieval-v11-p11-20261101 --problems P11
python3 -B experiments/retrieval-harness-20261101/retrieval_runner.py run \
  --root runs/retrieval-v11-p11-20261101 --problems P11
```

Only `run` reads the existing API credential. Default policy remains GPT-6.1
Sol, high reasoning, a maximum $2.70 per problem, a target of 40 actual proof
evaluations, and full golf. The financial cap takes priority over the target;
inspection calls consume API budget and do not count as proof evaluations.

`trial.py prepare|run|status|audit --problem P11` wraps the same entrypoint with
timing telemetry. `analyze.py --root PATH` produces a read-only numerical report.
`audit_retrieval.py --root PATH --output PATH` independently checks receipts,
source/runtime fingerprints, request and observation provenance, state chains,
and fresh final compiler evidence without additional API or Lean executions.

Run unit/regression checks with:

```sh
python3 -B -m unittest discover -s experiments/retrieval-harness-20261101 -v
```

#### Completed P11 diagnostic

Run: `runs/retrieval-v11-p11-20261101`. Preparation took 66.63 seconds with
verified compiler-fact/type-index reuse. The paid run, including full golf,
took 9,676.94 seconds (2 h 41 m 17 s); golf accounted for 5,488.68 seconds.
All 28 API calls settled, with an estimated total cost of $1.8724256 under the
$2.70 cap. Search completed 19 proof evaluations, 12 valid. The target was 40;
the inherited conservative next-request reservation stopped search before the
remaining $0.8275744 could be spent. This was not a completed 40-trial run.
An independent read-only reconstruction confirmed the next request's bound:
179,796 input tokens (serialized UTF-8 byte count plus 4,096), $0.898980 input
reservation plus $0.043520 for minimum output/reserve and $0.005 margin, totaling
$0.947500. This exceeded the remaining budget by $0.1199256; actual API spend
had not exhausted the cap. The reservation bound is deliberately pessimistic
and is separate from reported usage-based cost.

The model used `retrieve` once (15 matches, 0.31 seconds) and `type_search` once
(7 matches, 1.18 seconds), in addition to the existing search/types tools.
It did not request external OpenAI source in this paid case. External lookup,
source recovery and reference filtering were exercised separately without API
calls. Whole-scope type-index coverage was 502,679 of 502,679 original constants.

| P11 result | Tokens | Heartbeats | Conditional score |
| --- | ---: | ---: | ---: |
| Historical common-harness final | 501 | 11,488,620 | 82.8282 |
| Retrieval search best | 385 | 9,083,437 | 86.6176 |
| Retrieval after full golf | 368 | 9,067,259 | 86.9267 |
| Existing reference88 submission's P11 | 248 | 6,215,475 | 91.1129 |

Scores use `100 - (100/3) * (T/1906 + H/45535629)`. Only Lean 4.31.0 was
verified; required-version compatibility with 4.30.0 and 4.29.0 is not established.
These are local conditional scores, not official leaderboard measurements.
One case and a historical comparator do not isolate retrieval's causal effect
or establish a general improvement. The one-level fiber lemma was already used
before the new retrieval call; its discovery cannot be attributed to that call.

Full golf screened 1,280 new variants without the old 40-screen cutoff. Final
fresh heartbeat samples were `[9067259, 9067201, 9067288]`. Independent financial,
runtime/source, observation-memory, state-chain and fresh-proof audit passed
(29 frozen sources; 185 workflow events). The new 19-test suite and 97 existing
v10 regression tests passed. Legacy canonical `types` inspection still showed
large latency, including one 180-second timeout; new structural search does not
remove that bottleneck or the full-golf cost.

Artifacts: `runs/retrieval-v11-p11-20261101/comparison.json`,
`runs/retrieval-v11-p11-20261101/final-audit.json`, and
`runs/retrieval-v11-p11-20261101/P11/golf-best.lean`.
