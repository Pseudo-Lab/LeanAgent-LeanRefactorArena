# 로컬 정리 검색

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

선언 이름 AND검색을 signature/source FTS5와 rank fusion으로 보완한다.

## 확인된 결과와 해석

162,417외부모듈 색인. P11 유용 정리 순위4/2/4/3,P01은1위. API0,선정된 진단 query이며 proof 점수·성공률 개선은 입증하지 않았다.

## 코드·Lean 보존 결정

색인은 중앙 캐시에서 재생성. 검색된 외부 정리의 현재 환경 적용 가능성을 별도 검증한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/theorem-retrieval-20261101/README.md` | `로컬 작업본` | `1bedc430981bac9173397e5873e6ea2d94f0b038d4cb3863d0c98d94056d6802` |

## 원문: `experiments/theorem-retrieval-20261101/README.md`

### Local theorem retrieval experiment

This experiment addresses a concrete failure of the frozen v10 lookup: all
query words must occur in a declaration's name. Goal terms such as binder names,
specialized arguments and result-type operators therefore produce no matches
even when a useful preceding lemma is available.

The experiment does not modify the harness, archived runs, imports, or scoring.
It uses no generation or embedding API.

#### Implemented

- Index all 162,417 `lean/OAI` source modules from `openai/math` commit
  `4eaee87548250b2682affda7d05d947c05554bae`. Keep source SHA, path, toolchain,
  and Comparator solution mappings. Challenge files containing target stubs
  are not indexed as proof examples. An external result is source material,
  not a claim that its theorem has been verified or is available in Arena.
- Index preceding declarations using existing compiler syntax byte ranges.
  Remove proof bodies while retaining assignments inside result-type `let`
  expressions. Resolve names against the original native name index; skip
  ambiguous source names. Check prefix, environment command/project and
  native-index hashes before building.
- Search normalized identifiers and source/signature text using SQLite FTS5
  BM25. Fuse name, signature and source rankings with equal-weight reciprocal
  rank fusion, constant 60. Query words are alternatives, not an all-words name
  constraint. The response size does not restrict the searchable corpus.
- Follow one lexical OAI import hop and identify exact dotted source mentions
  that also occur in the original environment's name index. These are hints;
  they are not elaborated dependency edges or application checks.
- Verify selected candidates' actual types and axioms with the existing native
  Lean inspection tool in the original environment.

Derived SQLite indexes are under
`$PROJECT_CACHE_DIR/theorem-retrieval-20261101/`, not the repository.
The full external index occupies about 710 MB; building it took 171 seconds.

#### Diagnostics

Results and provenance: `runs/theorem-retrieval-20261101/report.json`.

| Diagnostic | Old name AND search | New result |
| --- | --- | --- |
| Four P11 goal-term queries | 0 matches each | Known useful one-level lemma ranks 4, 2, 4, 3 |
| P01 `normalizeOldExpr getVars Subset` | 0 matches | `normalizeOldExprInVars` ranks 1 |
| P10 `Set ncard range prod` | 0 matches | Preceding declarations are insufficient |
| P14 same representation query | 0 matches | No preceding declarations to index |

These queries were selected for diagnosis, not sampled as a held-out benchmark.
No proof-score, success-rate or leaderboard improvement is established.

External queries over the full corpus took roughly 0.5–2.3 seconds in this run.
For example, `Set ncard range prod` retrieved
`OAI.NumberTheory.EgyptianFractions.FiniteBox` at rank 2, whose proof uses
`Set.encard_pi_eq_prod_encard`. Other broad matches were less useful. This
illustrates both the opportunity for finding a representation and the noise
of lexical matching. The query's rank-1 result is not automatically applicable.

The checked P11 lemmas are present in the original Lean 4.31 environment and
have only `propext`, `Classical.choice` and `Quot.sound` among their axioms.
Full type responses and execution records are retained in the run directory.
Three Mathlib references found in external proofs were also checked in the
original P10 environment: `Set.encard_pi_eq_prod_encard`,
`Finset.card_image_of_injective`, and `Finset.card_image_of_injOn`. All three
are present with the same three standard axioms. Their applicability to the
actual P10 goal has not been tested by this retrieval experiment.

#### Reproduce

From the Arena checkout, first source the mandatory central environment config:

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
python3 -B -m unittest discover -s experiments/theorem-retrieval-20261101 -v
```

Build into a new index path; the builder refuses to overwrite an existing one:

```sh
python3 -B experiments/theorem-retrieval-20261101/retrieval.py build-corpus \
  --corpus sources/openai-math \
  --db "$PROJECT_CACHE_DIR/theorem-retrieval-20261101/openai-math-v1.sqlite"
```

`build-local --context PATH --environment PATH --db PATH` builds a separate
prefix-scoped index. `search --db PATH --kind local|external --scope SHA
--query TEXT --limit N` queries it. Local scope is `prefix_sha256`; external
scope is the pinned corpus commit. No compatibility with an unpinned Lean
version is assumed. `evaluate.py` replays the documented diagnostics using
the prepared indexes and saved native type checks.

#### Next harness design

Use the same policy for every problem; the examples above are evaluation
fixtures, not problem-specific instructions.

1. Extract the goal, hypotheses, operators and specialized arguments. Search
   preceding signatures before reconstructing a long proof.
2. Search imported declarations by type pattern in the original toolchain.
   This prototype still lacks a full imported-type index. Loogle-style
   structural matching is the complementary missing component, especially
   for cases such as P14.
3. Search external proof examples for alternate representations and short
   proof chains. Follow helper imports; intersect discovered references with
   the original environment. Keep unavailable OAI declarations as analogies.
4. For each candidate, record result shape, substitutions and remaining
   premises. Test an actual `exact`, `simpa`, `apply` or rewrite in Lean.
   Feed failed type matches back into the query. A checked type alone does
   not establish that the candidate solves the goal.
5. Compare proof structures and then golf the validated candidate. Evaluate
   retrieval recall, successful applications, score, wall time and cost
   separately on held-out problems.

Semantic embeddings/reranking and elaborated dependency graphs can improve
recall later. Neither is implemented by this lexical prototype. The external
corpus uses Lean 4.34.1 and has not been built as a whole.
