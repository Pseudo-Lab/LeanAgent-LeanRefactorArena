# v9 컴파일러 사실·변경 기억

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

전체 정리 타입 복원·원래 import 범위 조회·실행 중 검증한 변경의 재사용을 시도한다.

## 확인된 결과와 해석

P01/P10/P14 유료 실행은 11/2/24평가, 합계$6.5364999, 비용76.74%가 inspection. 문맥 회귀·반복 조회·파서 본문 유실을 확인했다.

## 코드·Lean 보존 결정

부정 결과와 진단을 보존. 성능이 개선된 기본 전략으로 채택하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/research-harness-20261031/README.md` | `로컬 작업본` | `53b1c997ab722d8ca27bb93039fc19b497818f2a259f2f697bd2ae843069452e` |

## 원문: `experiments/research-harness-20261031/README.md`

### V9: compiler facts and reusable within-run changes

The earlier P10 fast pilot reduced compilation and golf work. Its conditional
score fell from 79.84 to 78.09, and its historical wall comparison included shared
queueing. It is not evidence of equal-quality acceleration. V9 addresses missing
information and poor reuse rather than imposing another search cutoff.

Every problem gets the same instructions (`experiments/research-harness-20261031/instructions.txt`, 원래 실행 자료). The solver can:

1. Search declarations from the original imports and preceding context, then ask
   Lean for exact types and axioms. Search results are paginated; every match is
   reachable. Inspection never returns constant proof values or future declarations.
2. Submit a new proof or retrieve any own earlier proof, diagnostic, observation
   or recorded source patch. Complete Pareto proofs remain in the repeated context.
3. Compose observed, validated parent-to-child edits onto a validated own proof.
   Character alignment rejects overlapping changes. The result is an unverified
   candidate and receives the same unchanged-context check and three heartbeat/
   axiom measurements as any other candidate.

The experience graph retains every completed observation, including regressions,
repairs, measured costs, the incumbent curve and raw measurement ranges. Ranges
are descriptive observations, not confidence intervals. Historical median-only
records explicitly have one observed sample. An observed patch is not a general
semantic rewrite theorem; composition can fail.

There is no two-failure quarantine, six-step strategy switch, 0.5% improvement
threshold, top-eight frontier/failure truncation, tactic-family ordering, or new
40-screen/180-second golf cap. The original full golf algorithm and all three
intermediate measurements are retained. Forty evaluations and $2.70/case remain
the user-specified target and cap; inspections consume API money without claiming
an evaluation. Conservative API reservations and input/output transport bounds
remain. Their limits are not claims of an exhaustive proof search.

The former source parser cut theorem headers at their first `:=`, including lets
inside the conclusion. The native parser now removes actual declaration-body
syntax spans, preserving complete types and embedded proof terms in those types.
A synthetic parser-only declaration completes trailing modifiers such as
`omit ... in`; it is never elaborated or exposed as an API. Module-system helpers
are marked `meta` when required. Import closure checks exclude APIs available
solely through the injected inspection import; omitted private/meta module
dependencies contribute no visible index entries. Private compiler logs stay
private. Compiler/project, context and index fingerprints are checked on reuse.

Quotes of own proof source are now accepted. A literal quote mismatch produces an
explicit unverified-citation warning; it does not establish a fact and does not
discard an otherwise checkable proof. Unknown evidence sources remain rejected.
All route claims remain hypotheses until a complete Lean proof succeeds.

#### Running

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
python -B experiments/research-harness-20261031/runner.py prepare --problems P01
python -B experiments/research-harness-20261031/runner.py status
python -B experiments/research-harness-20261031/runner.py audit
# This command spends API money; it has NOT been run in the v9 validation:
python -B experiments/research-harness-20261031/runner.py run
```

Default output: `runs/research-openai-v9-20261031/`. `--root` selects a fresh
direct child of `runs/`. Omitting `--problems` during preparation selects all 15;
the selected set is then frozen. Native preparation has CPU cost but no API cost.
Only `run` loads credentials. `pause`, `resume` and `reconcile` retain v7 semantics.

Calls commit through reserved → dispatching → responded → received, then either
observed (inspection) or staged → evaluating → evaluated (candidate/composition).
Invalid responses finish rejected and remain charged. Unknown network responses
block and retain their reservation; they are never automatically resent.
An interrupted local inspection can rerun without repeating its paid model call.
Observation IDs/results and own proof hashes are checked against the ledgers.

The controller, workflow, evaluator orchestration and adapter are explicit new
forks of v6/v7. Completed v6/v7/v8 code and paid artifacts are unchanged. Keeping
the forks local makes this experimental policy reviewable without invalidating
frozen historical protocols. Shared source transformations live in
`src/lean_agent/proof_experience.py`. Derived API indexes and compressed native
inventory logs use the required central project cache, not a new repo cache.

#### Validation and limits

```sh
python -B -m unittest discover -s experiments/research-harness-20261031 -p 'test_*.py'
python -B experiments/research-harness-20261031/validate.py contexts
python -B experiments/research-harness-20261031/validate.py types
python -B experiments/research-harness-20261031/validate.py replay
python -B experiments/research-harness-20261031/native_smoke.py
```

Validation covers 51 tests including budget/receipt integrity, crash boundaries,
inspection accounting/recovery, citation/source boundaries, patch conflicts,
Unicode byte ranges, pagination, frontier retention and measurement uncertainty.
The unchanged v7 recovery suite also passes its 28 tests.

All 15 original source contexts were extracted with the pinned compilers
(4.26, 4.31 and 4.32). Native type/axiom queries passed on P11, P14 and P07. In
particular, P11's previously truncated `x = free_coeff_term + y_lifted` conclusion
is present in both source context and the compiler's complete type.
The 636 archived evaluations were replayed for format/retention validation only;
none of their proof sources was supplied to a fresh benchmark solver.

The separate synthetic native smoke run uses real Lean for three candidates,
including composing two independent branch edits, independent final verification,
and original full golf. It uses synthetic model responses, no credentials or API.
Latest evidence is under `runs/research-v9-native-smoke-v2-20261031/` and
`runs/research-v9-validation-20261031/`. Earlier smoke artifacts are superseded
development snapshots, not frozen paid experiment results.

A paid P01/P10/P14 trial has completed, with its source/prompt frozen before
dispatch. API search has closed at 11/2/24 evaluations rather than 40 each;
251 calls cost $6.5364999, with 76.74% spent on inspection. P01 and P14 have
completed full golf, as has P10, which screened all 1,965 new variants at the
user's explicit request. None of the three cases adopted a golf change.
The selected-three mean is 69.21297, versus 87.15826 for the same v6 cases and
91.40537 for the corresponding 88-line snapshot, all on common normalizers and
conditional on full required-version compatibility. P01/P10/P14 execution times
were 35m58s / 3h27m40s / 38m18s, excluding their separately recorded preparation.
See `runs/research-v9-threecase-20261031/comparison.md` and `diagnosis.md`.
Actual request replay reproduced a working-context regression: full failed-parent
source and previously retrieved native types are not retained together. Unit and
native feature tests did not establish effective closed-loop search performance.
This experimental version is not a demonstrated score or speed improvement.
An additional native diagnostic confirmed a second defect in the frozen legacy
golf parser: rebuilding P10 without any intended edit changes 1,463 proof tokens
to 554 and fails Lean. Line joining loses code through comments and layout.
These failures concern model working context and source-preserving transformations;
they do not establish that case-specific prompts are necessary or that general
golf strategies cannot help. Exported proofs passed their configured native checks.
