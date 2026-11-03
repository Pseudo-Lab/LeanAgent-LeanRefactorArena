"""final60 routing: classification, routes, hint hygiene, leak filter, schedule.

No Lean, no model calls, no network. The 60-row case runs only when the final
problems or the benchmark JSONL are present locally (both are untracked).
"""
import dataclasses
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lean_agent import portfolio  # noqa: E402
from lean_agent.final60 import contracts, prompts, routing  # noqa: E402

BASELINES = ROOT / "docs/measurements/final60-baselines.json"
DATASET = Path(os.environ.get("FINAL60_DATASET",
                              ROOT / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"))
PROBLEMS = ROOT / "sources/final/problems"
PRIMARY = contracts.ModelSpec(key="gen_primary", model_id="openai/gpt-6.1-sol", provider="openai",
                              prompt_usd_per_mtok=Decimal("2"), completion_usd_per_mtok=Decimal("10"),
                              cache_read_usd_per_mtok=Decimal("0.10"), cache_write_usd_per_mtok=Decimal("2.50"),
                              max_tokens=8192, reasoning_effort="high")


def make(row, source, statement, body, *, environments=None, name=None):
    return {"row": row, "id": f"final-test-F{row:03}", "name": name or f"Test.P{row:03}", "source": source,
            "statement": statement, "reference": statement + " := by\n" + body, "header": "",
            "environments": environments or [f"{source}-v4.34.1", f"{source}-v4.34.0"]}


ALG_LINES = "".join(f"  have h{i} : a * {i} + b * {i} = (a + b) * {i} := by ring\n" for i in range(30))
TINY = make(11, "physlib", "lemma tiny : (I : Fin 3) → I.val < 3", "  decide +kernel")
SHORT = make(1, "strata", "theorem short (a b : Nat) (h : a = b) : b = a", "  subst h\n  simp_all")
STRUCT_BODY = "".join(
    f"  induction t{i} with\n  | nil => simp_all\n  | cons x xs ih =>\n    cases x\n"
    f"    · simp_all [step{i}, eval{i}, ih]\n    · simp_all [step{i}, eval{i}, ih]\n"
    for i in range(12))
STRUCT = make(21, "cslib", "lemma Typing.foo (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢ t'", STRUCT_BODY)
ALGEBRA = make(31, "arklib", "theorem alg (a b : ℚ) : (a + b) * 30 = a * 30 + b * 30", ALG_LINES + "  ring",
               environments=["arklib-v4.34.0", "arklib-v4.33.1", "arklib-v4.31.0", "arklib-v4.30.0"])
COMP = make(51, "putnambench", "theorem putnam_x (x : ℝ) (h : 0 < x) : 0 < x ^ 2 + x", "  positivity")
CASES_STMT = "theorem t (xs : List Nat) : f xs = g xs"
CASES = CASES_STMT + """ := by
  induction xs with
  | nil => simp [f, g]
  | cons x xs ih =>
    cases x
    · simp_all [f, g]
    · simp_all [f, g]
    cases xs
    · simp_all [f, g]
    · simp_all [f, g]
    simp_all
"""


def route(problem, **kwargs):
    kwargs.setdefault("non_openrouter_proofs", [])
    return routing.route(problem, None, **kwargs)


def longest_common(a, b):
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


class Classification(unittest.TestCase):
    def test_all_five_types(self):
        cases = {"kernel-decide-tiny": TINY, "short-tactic": SHORT, "structural-induction": STRUCT,
                 "algebra-analysis-long": ALGEBRA, "competition": COMP}
        for expected, problem in cases.items():
            with self.subTest(expected):
                self.assertEqual(routing.classify(problem, None), expected)
        self.assertEqual(set(cases), set(routing.TYPES))

    def test_order_competition_before_short(self):
        # The Putnam fixture is short (T0 < 300) but stays a competition row.
        self.assertLess(routing.features(COMP, None)["t0"], 300)
        self.assertEqual(routing.classify(COMP, None), "competition")

    def test_unknown_source_uses_density_and_statement_words(self):
        dense = dict(STRUCT, source="newlib", statement="theorem foo (xs : List Nat) : P xs",
                     reference="theorem foo (xs : List Nat) : P xs := by\n" + STRUCT_BODY)
        sparse = dict(ALGEBRA, source="newlib")
        self.assertEqual(routing.classify(dense, None), "structural-induction")
        self.assertEqual(routing.classify(sparse, None), "algebra-analysis-long")

    def test_tiny_needs_decide(self):
        no_decide = make(11, "physlib", "lemma tiny (h : p) : p", "  exact h")
        self.assertEqual(routing.classify(no_decide, None), "short-tactic")

    def test_baseline_entry_or_file(self):
        entry = {"id": "F031", "name": ALGEBRA["name"], "primary_environment": "arklib-v4.34.0",
                 "environments": {"arklib-v4.34.0": {"median_raw_heartbeats": 123456789}}}
        for baseline in (entry, {"problems": [entry]}):
            feat = routing.features(ALGEBRA, baseline)
            self.assertEqual(feat["hb0"], 123456789)
        with self.assertRaises(ValueError):
            routing.features(STRUCT, entry)  # an entry of another row is never used silently
        self.assertIsNone(routing.features(ALGEBRA, None)["hb0"])

    def test_raw_benchmark_row_format(self):
        raw = {"name": "x", "source": "strata", "statement": SHORT["statement"], "src": SHORT["reference"],
               "version_info": [{"v4.31.0": "a" * 40}, {"v4.27.0": "b" * 40}, {"v4.26.0": "c" * 40}], "row": 1}
        feat = routing.features(raw, None)
        self.assertEqual(feat["versions"], ["v4.31.0", "v4.27.0", "v4.26.0"])
        self.assertEqual(feat["environments"][0], "strata-v4.31.0")
        self.assertEqual(routing.classify(raw, None), "short-tactic")

    def test_features_are_deterministic_json(self):
        first = json.dumps(routing.features(STRUCT, None), sort_keys=True)
        self.assertEqual(first, json.dumps(routing.features(STRUCT, None), sort_keys=True))


class Routes(unittest.TestCase):
    def test_every_portfolio_validates(self):
        for problem in (TINY, SHORT, STRUCT, ALGEBRA, COMP):
            value = route(problem)
            portfolio.validate(value.portfolio)
            self.assertTrue(value.portfolio["hide_original_first_scout"])
            self.assertEqual(value.portfolio["progress_guard"], "bounded-v1")
        self.assertFalse(route(COMP).portfolio["merger_until_budget"])
        self.assertTrue(route(ALGEBRA).portfolio["merger_until_budget"])

    def test_kernel_decide_tiny_skips_llm(self):
        value = route(TINY)
        self.assertTrue(value.skip_llm)
        self.assertEqual(value.hints, ())
        self.assertEqual(routing.prompt_addendum(value), "")
        self.assertEqual(value.golf["passes"], ["G5", "G3"])
        self.assertEqual(value.role_models, {})
        self.assertEqual(routing.worst_case_calls(value, PRIMARY, 60000), 0)

    def test_golf_budget_follows_amendment_a7(self):
        short, long = route(SHORT), route(ALGEBRA)
        self.assertLessEqual(short.golf["original_compiles"], 4)
        self.assertEqual(short.golf["max_compiles_row"], 12)
        self.assertTrue(short.golf["ddmin"])
        self.assertIn("G4", short.golf["passes"])
        self.assertGreater(routing.features(ALGEBRA, None)["t0"], 600)
        self.assertFalse(long.golf["ddmin"])
        self.assertNotIn("G4", long.golf["passes"])
        self.assertEqual(long.golf["passes"][:2], ["G1", "G2"])
        self.assertEqual(long.wallclock_budget_s, 4500)

    def test_route_json_schema_and_determinism(self):
        first, second = route(STRUCT), route(STRUCT)
        self.assertEqual(first, second)
        data = routing.route_json(first)
        self.assertEqual(json.dumps(data, sort_keys=True), json.dumps(routing.route_json(second), sort_keys=True))
        self.assertEqual(list(data), sorted(data))
        for name in [field.name for field in dataclasses.fields(contracts.Route)]:
            self.assertIn(name, data)
        self.assertEqual(data["schema"], contracts.SCHEMA)
        self.assertEqual(data["cost_stop_usd"], "2.99")
        self.assertEqual(data["prior_cost_usd"], "0")
        self.assertEqual(data["prompt_addendum"], routing.prompt_addendum(first))
        self.assertEqual(data["prompt_addendum_sha256"],
                         hashlib.sha256(data["prompt_addendum"].encode()).hexdigest())
        self.assertEqual(routing.route_from_json(json.loads(json.dumps(data))), first)
        self.assertEqual(routing.route_json(first, prior_cost_usd="0.40")["prior_cost_usd"], "0.40")
        with self.assertRaises(ValueError):
            routing.route_json(first, prior_cost_usd="2.99")

    def test_route_from_json_rejects_tampering(self):
        data = routing.route_json(route(ALGEBRA))
        data["hints"] = data["hints"][:-1]
        data["hint_sources"] = data["hint_sources"][:-1]
        with self.assertRaises(ValueError):
            routing.route_from_json(data)
        with self.assertRaises(ValueError):
            routing.route_from_json({**routing.route_json(route(ALGEBRA)), "schema": "other"})

    def test_diversity_sets_scout_c_only(self):
        self.assertEqual(route(STRUCT, diversity=True).role_models, {"scout-c": "gen_alt"})
        self.assertEqual(route(STRUCT).role_models, {})
        self.assertEqual(route(TINY, diversity=True).role_models, {})

    def test_conditional_hints(self):
        sources = route(ALGEBRA).hint_sources
        self.assertIn("playbook:conditional:many_versions", sources)  # four listed versions
        heavy = {"id": "F031", "primary_environment": "arklib-v4.34.0",
                 "environments": {"arklib-v4.34.0": {"median_raw_heartbeats": 250_000_000}}}
        value = routing.route(ALGEBRA, heavy, non_openrouter_proofs=[])
        self.assertIn("playbook:conditional:hb_heavy", value.hint_sources)
        self.assertTrue(any("250 million" in hint for hint in value.hints))

    def test_default_route_is_full_loop_without_hints(self):
        for problem in (TINY, STRUCT, {"row": 7, "name": "odd", "source": "strata", "reference": "x"}):
            value = routing.default_route(problem)
            self.assertFalse(value.skip_llm)
            self.assertEqual((value.hints, value.hint_sources, value.role_models), ((), (), {}))
            self.assertTrue(value.portfolio["merger_until_budget"])
            portfolio.validate(value.portfolio)
        with self.assertRaises(ValueError):
            routing.default_route({"name": "no row", "reference": "x"})

    def test_route_needs_row(self):
        with self.assertRaises(ValueError):
            route({k: v for k, v in SHORT.items() if k not in ("row", "id")})


class Hints(unittest.TestCase):
    def test_limits(self):
        for problem in (SHORT, STRUCT, ALGEBRA, COMP):
            value = route(problem)
            addendum = routing.prompt_addendum(value)
            self.assertLessEqual(len(addendum), prompts.MAX_ADDENDUM_CHARS)
            self.assertLessEqual(len(value.hints), 6)
            self.assertGreaterEqual(len(value.hints), 3)
            for hint in value.hints:
                self.assertLessEqual(len(hint), 300)
                self.assertTrue(all(len(span) <= 39 for span in prompts.lean_spans(hint)))
                self.assertEqual(prompts.hint_problems(hint), [])

    def test_hint_rules(self):
        self.assertIn("Lean snippet longer than 39 characters", prompts.hint_problems("Use `" + "x" * 40 + "`."))
        self.assertEqual(prompts.hint_problems("Use `" + "x" * 39 + "`."), [])
        self.assertIn("Lean syntax outside backticks", prompts.hint_problems("Write have h := foo here."))
        self.assertIn("Lean syntax outside backticks", prompts.hint_problems("Then by simp closes it."))
        self.assertIn("unbalanced or fenced backticks", prompts.hint_problems("Use `simp."))
        self.assertIn("reserved prompt marker", " ".join(prompts.hint_problems("x </routing_notes> y")))
        self.assertIsNone(prompts.sanitize_hint("x" * 301))
        self.assertEqual(prompts.sanitize_hint("  Use\n `simp`  now. "), "Use `simp` now.")
        self.assertEqual(prompts.shorten("First part. " + "y" * 400), "First part.")

    def test_every_playbook_hint_is_valid(self):
        book = prompts.playbooks()
        texts = [hint for hints in book["types"].values() for hint in hints]
        texts.append(book["conditional"]["many_versions"].format(versions="v4.30.0, v4.31.0, v4.33.1, v4.34.0"))
        texts.append(book["conditional"]["hb_heavy"].format(hb_millions="3224"))
        for text in texts:
            self.assertEqual(prompts.hint_problems(prompts.flat(text)), [], text)
        for kind in routing.TYPES:
            self.assertIn(kind, book["types"])

    def test_insert_and_split_addendum(self):
        prompt = "Base prompt.\nNo extra imports or helper declarations.\n<original_context>\nctx\n</original_context>\n"
        addendum = routing.prompt_addendum(route(STRUCT))
        combined = routing.insert_addendum(prompt, addendum)
        self.assertTrue(combined.endswith("\n</original_context>\n"))
        self.assertEqual(combined.split("<original_context>\n", 1)[1], "ctx\n</original_context>\n")
        self.assertEqual(routing.split_addendum(combined), (prompt, addendum))
        self.assertEqual(routing.split_addendum(prompt), (prompt, ""))
        self.assertEqual(routing.insert_addendum(prompt, ""), prompt)
        with self.assertRaises(ValueError):
            routing.insert_addendum(combined, addendum)
        with self.assertRaises(ValueError):
            routing.insert_addendum("x" * 59000 + "\n<original_context>\nc\n</original_context>\n", addendum)

    def test_hints_never_contain_original_proof(self):
        for problem in (SHORT, STRUCT, ALGEBRA, COMP):
            value = route(problem)
            addendum = routing.prompt_addendum(value)
            self.assertNotIn(problem["reference"].strip(), addendum)
            portfolio.validate_shared_inputs({"agent": {"portfolio": value.portfolio}}, problem["reference"],
                                             addendum, {"entries": []})
            self.assertFalse(any(routing.LeakCorpus([problem["reference"]]).mask(value.hints)))

    def test_lesson_quoting_the_original_is_dropped(self):
        quote = prompts.flat(ALG_LINES)[:80]
        with tempfile.TemporaryDirectory() as tmp:
            bank = Path(tmp) / "lessons.jsonl"
            bank.write_text(json.dumps({"schema": routing.LESSON_SCHEMA, "row": 32, "name": "other",
                                        "source": "arklib", "problem_type": "algebra-analysis-long",
                                        "lessons": ["A winner kept " + quote + " intact."],
                                        "metrics": {"token_reduction_pct": 50}}) + "\n")
            value = route(ALGEBRA, bank_paths=[bank])
        self.assertNotIn("in-run-lesson:F032", value.hint_sources)
        self.assertFalse(any(quote in prompts.flat(hint) for hint in value.hints))

    def test_route_drops_hint_leaking_non_openrouter_proof(self):
        clean = route(STRUCT)
        leaked = clean.hints[1]
        outside = ["theorem other : True := by\n  -- " + leaked[:60] + "\n  trivial"]
        value = route(STRUCT, non_openrouter_proofs=outside)
        self.assertNotIn(leaked, value.hints)
        self.assertNotIn(clean.hint_sources[1], value.hint_sources)
        self.assertEqual(len(value.hints), len(value.hint_sources))
        self.assertIn(clean.hints[0], value.hints)


class LeakFilter(unittest.TestCase):
    PROOF = "theorem x : P := by\n  induction h <;> simp_all [foo_bar_baz, qux_lemma, another_one]\n  exact h"

    def test_drops_40_char_overlap_keeps_prose(self):
        piece = prompts.flat(self.PROOF)[20:60]
        self.assertEqual(len(piece), 40)
        texts = ["Plain prose about merging branches.", "Copy: " + piece + " end.",
                 "Short `simp_all [foo_bar_baz]` mention."]
        self.assertEqual(routing.leak_filter(texts, [self.PROOF]), [texts[0], texts[2]])

    def test_39_chars_is_not_a_leak(self):
        piece = prompts.flat(self.PROOF)[20:59]
        self.assertEqual(routing.leak_filter(["<" + piece + ">"], [self.PROOF]), ["<" + piece + ">"])

    def test_whitespace_is_flattened(self):
        piece = prompts.flat(self.PROOF)[15:70].replace(" ", "\n   ")
        self.assertEqual(routing.leak_filter(["see " + piece], [self.PROOF]), [])

    def test_matches_brute_force(self):
        rng = random.Random(7)
        alphabet = "ab cd"
        for _ in range(150):
            proof = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120)))
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120)))
            if rng.random() < 0.5 and len(proof) > 30:
                start = rng.randrange(len(proof) - 20)
                text = text[:20] + proof[start:start + rng.randint(5, 50)] + text[20:]
            for need in (6, 10, 40):
                expected = longest_common(prompts.flat(text), prompts.flat(proof)) >= need
                kept = routing.leak_filter([text], [proof], min_chars=need)
                self.assertEqual(kept == [], expected, (text, proof, need))

    def test_reusable_corpus_and_inputs(self):
        corpus = routing.LeakCorpus([self.PROOF, "short", 42])
        self.assertEqual(len(corpus), 1)
        self.assertEqual(routing.leak_filter(["ok"], corpus), ["ok"])
        self.assertEqual(routing.leak_filter(["ok"], []), ["ok"])
        with self.assertRaises(TypeError):
            routing.leak_filter(["ok"], "a proof string, not a list")
        with self.assertRaises(ValueError):
            routing.LeakCorpus([], min_chars=1)


class Banks(unittest.TestCase):
    def test_warmup_bank_is_pinned_warmup_copy(self):
        bank = routing.warmup_bank()
        self.assertIn("warm-up material only", bank["built_from"])
        for card in bank["strategies"]:
            self.assertEqual(card["evidence"]["source_set"], "warm-up")
        original = ROOT / routing.WARMUP_BANK_SOURCE
        if original.is_file():
            self.assertEqual((routing.DATA / "warmup_bank.json").read_bytes(), original.read_bytes())

    def test_warmup_selection_matches_pr50_on_fixture(self):
        problem = {"row": 3, "name": "t", "source": "strata", "statement": CASES_STMT, "reference": CASES}
        feat = routing.features(problem, None)
        self.assertIn("route_cue", feat["tags"])
        self.assertIn("case_main", feat["tags"])
        hints = routing.warmup_hints(feat, limit=1)
        self.assertEqual(hints[0][1], "warmup-bank:bank-v1:S01@760b59e")
        retriever_dir = ROOT / "experiments/strategy-retriever"
        if retriever_dir.is_dir():
            sys.path.insert(0, str(retriever_dir))
            try:
                import retriever
                expected = retriever.retrieve(CASES_STMT, CASES, retriever.load_bank(), k=1)
            finally:
                sys.path.remove(str(retriever_dir))
            self.assertEqual(expected["strategies"][0]["id"], "S01")

    def test_team_bank_is_opt_in_and_leave_one_out(self):
        def card(card_id, problem):
            return {"id": card_id, "title": f"Card {card_id}", "match": {"tactic_min": {"induction": 1}},
                    "guide": "Close the generated branches together.", "risks": "May raise heartbeats.",
                    "evidence": [{"problem": problem, "candidate_sha256": "0" * 64}]}
        bank = {"schema_version": 1, "version": "fixture-team", "scope": "final-adaptation",
                "strategies": [card("own", STRUCT["name"]), card("other", "Some.Other")]}
        self.assertFalse(any(s.startswith("team-bank") for s in route(STRUCT).hint_sources))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(json.dumps(bank))
            value = route(STRUCT, bank_paths=[path])
        self.assertIn("team-bank:fixture-team:other", value.hint_sources)
        self.assertNotIn("team-bank:fixture-team:own", value.hint_sources)

    def test_unknown_bank_format_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bank.json"
            path.write_text("[1, 2]")
            with self.assertRaises(ValueError):
                route(STRUCT, bank_paths=[path])


class Lessons(unittest.TestCase):
    WINNER = STRUCT["statement"] + " := by\n  induction t0 <;> grind"

    def test_lesson_is_prose_and_deterministic(self):
        lessons = routing.lessons_from_winner(STRUCT, self.WINNER, metrics={"hb_reduction_pct": 40})
        self.assertEqual(lessons, routing.lessons_from_winner(STRUCT, self.WINNER, metrics={"hb_reduction_pct": 40}))
        self.assertEqual(len(lessons), 1)
        self.assertIn("`grind`", lessons[0])
        self.assertIn("`<;>`", lessons[0])
        self.assertIn("heartbeats by 40%", lessons[0])
        self.assertEqual(prompts.hint_problems(lessons[0]), [])
        self.assertEqual(routing.lessons_from_winner(STRUCT, STRUCT["reference"]), [])  # no reduction

    def test_record_and_reuse_same_source_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            bank = Path(tmp) / "run" / "lessons.jsonl"
            saved = routing.record_lessons(bank, STRUCT, self.WINNER, run_root="rows/F021")
            self.assertEqual(len(saved), 1)
            routing.record_lessons(bank, STRUCT, self.WINNER, run_root="rows/F021")
            with bank.open("a") as stream:
                stream.write('{"torn": ')
            records = [line for line in bank.read_text().splitlines() if line.strip()]
            self.assertEqual(len(records), 2)  # one record plus the torn line, no duplicate
            self.assertEqual(json.loads(records[0])["metrics"]["token_reduction_pct"] > 0, True)
            sibling = dict(STRUCT, row=22, id="final-test-F022", name="Test.P022")
            used = route(sibling, bank_paths=[bank])
            self.assertIn("in-run-lesson:F021", used.hint_sources)
            self.assertNotIn("in-run-lesson:F021", route(STRUCT, bank_paths=[bank]).hint_sources)
            other_source = dict(ALGEBRA)
            self.assertFalse(any(s.startswith("in-run-lesson") for s in
                                 route(other_source, bank_paths=[bank]).hint_sources))

    def test_record_refuses_lessons_leaking_outside_proofs(self):
        lesson = routing.lessons_from_winner(STRUCT, self.WINNER)[0]
        with tempfile.TemporaryDirectory() as tmp:
            bank = Path(tmp) / "lessons.jsonl"
            self.assertEqual(routing.record_lessons(bank, STRUCT, self.WINNER, run_root="r",
                                                    non_openrouter_proofs=["-- " + lesson]), [])
            self.assertFalse(bank.exists())


class Schedule(unittest.TestCase):
    def test_priority_and_readiness(self):
        routes = [route(p) for p in (TINY, SHORT, STRUCT, ALGEBRA, COMP)]
        order = routing.schedule(routes, {1, 11, 21, 31, 51})
        self.assertEqual(order, [31, 21, 1, 51, 11])  # weak ArkLib, weak CSLib, Strata, Putnam, tiny
        self.assertEqual(routing.schedule(routes, {11, 51}), [51, 11])
        self.assertEqual(routing.schedule(routes, set()), [])
        self.assertEqual(routing.schedule(routes + routes, {31}), [31])

    def test_worst_case_calls(self):
        value = route(ALGEBRA)
        bound = routing.request_bound_usd(PRIMARY, 60000)
        self.assertEqual(bound, Decimal("0.24216"))
        self.assertEqual(routing.worst_case_calls(value, PRIMARY, 60000), 12)
        self.assertEqual(routing.worst_case_calls(value, PRIMARY, 240000), 0)
        self.assertGreater(routing.worst_case_calls(value, PRIMARY, 0), 30)
        with self.assertRaises(ValueError):
            routing.worst_case_calls(value, PRIMARY, -1)

    def test_budget_plan(self):
        plan = routing.budget_plan(route(ALGEBRA), PRIMARY, 60000)
        self.assertEqual((plan["cap_usd"], plan["bound_usd_per_call"], plan["worst_case_calls"]),
                         ("2.99", "0.24216", 12))
        self.assertEqual(plan["portfolio_evaluations"], 40)
        self.assertTrue(plan["merger_until_budget"])
        tiny = routing.budget_plan(route(TINY), PRIMARY, 60000)
        self.assertEqual((tiny["worst_case_calls"], tiny["portfolio_evaluations"]), (0, None))
        self.assertFalse(tiny["merger_until_budget"])


class Cli(unittest.TestCase):
    def test_preview_and_outside_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            problems = tmp / "problems"
            problems.mkdir()
            for problem in (TINY, STRUCT):
                (problems / f"F{problem['row']:03}.json").write_text(json.dumps(problem))
            outside = tmp / "outside"
            outside.mkdir()
            (outside / "a.lean").write_text("theorem a : True := trivial")
            (outside / "b.jsonl").write_text(json.dumps({"name": "b", "proof": "by simp"}) + "\n")
            (outside / "c.json").write_text(json.dumps([{"proof": "by omega"}, {"other": 1}]))
            self.assertEqual(sorted(routing.load_outside_proofs([outside])),
                             ["by omega", "by simp", "theorem a : True := trivial"])
            out = tmp / "routes.json"
            missing_lessons = tmp / "not-yet" / "lessons.jsonl"
            with open(os.devnull, "w") as sink:
                stdout, sys.stdout = sys.stdout, sink
                try:
                    code = routing.main(["--problems", str(problems), "--non-openrouter", str(outside),
                                         "--bank", str(missing_lessons), "--out", str(out)])
                finally:
                    sys.stdout = stdout
            self.assertEqual(code, 0)
            data = json.loads(out.read_text())
            self.assertEqual(sorted(data), ["F011", "F021"])
            self.assertEqual(routing.route_from_json(data["F021"]), route(STRUCT))


def sixty_problems():
    if PROBLEMS.is_dir() and len(list(PROBLEMS.glob("F0[0-9][0-9].json"))) == 60:
        return [json.loads((PROBLEMS / f"F{row:03}.json").read_text(encoding="utf-8")) for row in range(1, 61)]
    if DATASET.is_file():
        rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [dict(row, row=index) for index, row in enumerate(rows, 1)] if len(rows) == 60 else None
    return None


@unittest.skipUnless(sixty_problems(), "final problems or benchmark JSONL not present")
class SixtyRows(unittest.TestCase):
    def test_final_sixty(self):
        problems = sixty_problems()
        baselines = routing.load_baselines(BASELINES)
        routes = routing.route_all(problems, baselines, non_openrouter_proofs=[])
        types = {item.row: item.problem_type for item in routes}
        for row in (11, 12, 13):
            self.assertEqual(types[row], "kernel-decide-tiny")
        for row in range(51, 61):
            self.assertEqual(types[row], "competition")
        for item, problem in zip(routes, problems):
            routing.validate_route(item, problem)
            self.assertEqual(item.skip_llm, item.row in (11, 12, 13))
            self.assertLessEqual(len(routing.prompt_addendum(item)), prompts.MAX_ADDENDUM_CHARS)
        self.assertEqual(sorted(routing.schedule(routes, set(range(1, 61)))), list(range(1, 61)))
        again = routing.route_all(problems, baselines, non_openrouter_proofs=[])
        self.assertEqual([routing.route_json(r) for r in routes], [routing.route_json(r) for r in again])


if __name__ == "__main__":
    unittest.main()
