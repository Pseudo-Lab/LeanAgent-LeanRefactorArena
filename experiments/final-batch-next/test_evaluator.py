"""Contract checks against the actual frozen final dataset; no API or Lean jobs."""
import json
import os
import tempfile
import re
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import nullcontext

from evaluator import FinalEvaluator, REPO, pending_command_start, proof_tokens, _comment_mask, target_is_private
from evaluator import DEFAULT_LEAN_MEMORY_MIB, lean_memory_mib


class LeanMemoryBoundTests(unittest.TestCase):
    def test_default_is_frozen_bound_and_override_is_explicit(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ARENA_LEAN_MEMORY_MIB", None)
            self.assertEqual(lean_memory_mib(), DEFAULT_LEAN_MEMORY_MIB)
            self.assertEqual(DEFAULT_LEAN_MEMORY_MIB, 4096)
        with patch.dict(os.environ, {"ARENA_LEAN_MEMORY_MIB": "16384"}):
            self.assertEqual(lean_memory_mib(), 16384)
        for bad in ("", "16G", "-1", "512", "999999999"):
            with patch.dict(os.environ, {"ARENA_LEAN_MEMORY_MIB": bad}):
                with self.assertRaises(ValueError):
                    lean_memory_mib()

    def test_compiler_command_uses_the_configured_bound(self):
        # The evaluator's own compiles take the bound; an explicit caller value (AutoSolver) wins.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repo = Path(temporary.name)
        (repo / "configs").mkdir()
        (repo / "configs/final-environments.local.json").write_text(json.dumps({"dataset_sha256": "fixture"}))
        evaluator = FinalEvaluator(repo_root=repo)
        evaluator._prepared["env"] = SimpleNamespace(settings={"library_paths": []}, verify=lambda full=False: None)
        state, folder = {"id": "env", "project": "project", "version": "v0"}, repo / "out"
        (repo / "project").mkdir()
        folder.mkdir()
        commands = []

        class Done:
            pid, returncode = 0, 0

            def __init__(self, command, **_):
                commands.append(command)

            def communicate(self, timeout=None):
                return b"", b""

        with patch("evaluator.subprocess.Popen", Done), patch("evaluator.shutil.which", return_value="/bin/true"), \
                patch("resources.wait_for_memory"), patch("resources.memory_snapshot", return_value={}):
            for env, explicit, expected in ((None, None, "-M4096"), ("16384", None, "-M16384"), ("16384", 2048, "-M2048")):
                with patch.dict(os.environ, {} if env is None else {"ARENA_LEAN_MEMORY_MIB": env}):
                    if env is None:
                        os.environ.pop("ARENA_LEAN_MEMORY_MIB", None)
                    kwargs = {} if explicit is None else {"memory_mib": explicit}
                    evaluator._invoke("-- source", state, {"module": None}, folder, f"run-{len(commands)}", **kwargs)
                    self.assertIn(expected, commands[-1])
                    self.assertEqual(sum(part.startswith("-M") for part in commands[-1]), 1)


class FinalEvaluatorContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture_repo = Path(temporary.name)
        (self.fixture_repo / "configs").mkdir()
        (self.fixture_repo / "configs/final-environments.local.json").write_text(
            json.dumps({"dataset_sha256": "fixture"}))
        folder = self.fixture_repo / "sources/final/problems"
        folder.mkdir(parents=True)
        (folder / "F001.json").write_text(json.dumps({
            "id": "F001", "row": 1, "dataset_sha256": "fixture", "name": "sample",
            "statement": "theorem sample : True", "reference": "theorem sample : True := by trivial",
            "header": "", "environments": ["fixture-env"]}))

    def test_linux_setup_accepts_only_pinned_mounted_artifacts(self):
        evaluator = FinalEvaluator(repo_root=self.fixture_repo)
        checkout = self.fixture_repo / 'checkout/lib'
        artifact = checkout / 'Qq/Typ.olean'
        frozen = self.fixture_repo / 'frozen'
        mounted = frozen / 'Qq/Typ.olean'
        setup = self.fixture_repo / 'project/.lake/build/ir/Test.setup.json'
        setup.parent.mkdir(parents=True)
        setup.write_text(json.dumps({'importArts': [str(artifact)]}))
        state = {'id': 'fixture-env', 'project': 'project',
                 'library_mounts': {str(checkout): str(frozen)}}
        evaluator._prepared['fixture-env'] = SimpleNamespace(settings={'files': {str(mounted): 'pinned'}})
        with patch('evaluator.sys.platform', 'linux'):
            self.assertEqual(evaluator._compiler_setup(state, {'module': 'Test'})[0], setup)
            evaluator._prepared['fixture-env'].settings['files'].clear()
            with self.assertRaisesRegex(ValueError, 'unpinned artifact'):
                evaluator._compiler_setup(state, {'module': 'Test'})

    def test_module_visibility_and_explicit_modifiers(self):
        cases = [
            ("", "theorem target : True", False),
            ("module\n", "theorem target : True", True),
            ("module\n@[expose] public section\n", "theorem target : True", False),
            ("module\npublic section\nprivate\n", "theorem target : True", True),
            ("module\n", "public theorem target : True", False),
            ("module\npublic section\nnamespace N\nsection S\nend S\nend N\n", "theorem target : True", False),
            ("module\npublic section\nnamespace N\nend N\nend\n", "theorem target : True", True),
            ("module\n/- public section -/\n", "theorem target : True", True),
            ("", 'theorem target : ("private" = "private")', False),
        ]
        for prefix, statement, expected in cases:
            with self.subTest(prefix=prefix, statement=statement):
                self.assertEqual(target_is_private(prefix, statement), expected)

    @unittest.skipUnless(os.environ.get("ARENA_FINAL_INTEGRATION") == "1",
                         "Set ARENA_FINAL_INTEGRATION=1 after preparing all final environments")
    def test_final_context_visibility_recovery_only_changes_implicit_private_targets(self):
        root = REPO / "sources/final"
        changed = []
        checked = 0
        for state_file in sorted((root / 'environments').glob('*/environment.json')):
            state = json.loads(state_file.read_text())
            for location in state['locations']:
                packet = json.loads((root / 'problems' / f"F{location['row']:03d}.json").read_text())
                if location['kind'] == 'standalone_header':
                    prefix = packet['header']
                else:
                    source = REPO / state['project'] / location['file_path']
                    prefix = source.read_text()[:location['statement_start_char']]
                pending = _comment_mask(prefix[pending_command_start(prefix):] + packet['statement'])
                old_private = bool(re.search(r'\bprivate\b', pending))
                new_private = target_is_private(prefix, packet['statement'])
                checked += 1
                if old_private != new_private:
                    self.assertTrue(new_private)
                    changed.append((location['row'], state['id']))
        self.assertEqual(checked, 127)
        self.assertEqual(set(changed), {(row, 'strata-' + version)
                                       for row in (2, 3, 5, 6, 8, 9, 10)
                                       for version in ('v4.27.0', 'v4.31.0')})

    def test_boundary_verifies_bytes_once_on_load_and_again_on_final(self):
        evaluator = FinalEvaluator(repo_root=self.fixture_repo)
        calls = []

        class Prepared:
            def verify(self, *, full=True):
                calls.append(full)
                return 'verified-manifest-hash'

        def load_state(environment_id):
            if environment_id not in evaluator._states:
                prepared = Prepared()
                prepared.verify(full=True)
                evaluator._prepared[environment_id] = prepared
                evaluator._states[environment_id] = {}
            return evaluator._states[environment_id]

        problem = {'environments': ['test-environment']}
        with patch.object(evaluator, 'load_problem', return_value=problem), \
             patch.object(evaluator, '_state', side_effect=load_state), \
             patch.object(evaluator, '_context', return_value={'location': {}}), \
             patch.object(evaluator, '_compiler_lock', side_effect=lambda: nullcontext()):
            evaluator.verify_environments(problem, full=True)
            self.assertEqual(calls, [True, False])
            evaluator.verify_environments(problem, full=True)
            self.assertEqual(calls, [True, False, True])

    def test_blank_final_prefix_page_is_not_an_empty_action_entry(self):
        evaluator = FinalEvaluator(repo_root=self.fixture_repo)
        problem = evaluator.load_problem(1)
        prefix = "import Lean\n" + "\n" * 60
        context = {"prefix": prefix, "suffix": "", "module": "Test.Context", "source_sha256": "test",
                   "location": {"file_path": "Test/Context.lean"}}
        with patch.object(evaluator, "_state", return_value={}), \
             patch.object(evaluator, "_context", return_value=context), \
             patch.object(evaluator, "_compiler_lock", return_value=nullcontext()), \
             patch("retrieval.build_import_corpus", return_value={"entries": [], "metadata": {}}):
            result = evaluator.source_context(problem)
        self.assertTrue(all(entry["text"] for entry in result["corpus"]["entries"]))
        self.assertIn("import Lean", result["prompt_context"])

    @unittest.skipUnless((REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl").is_file(),
                         "Install the frozen final dataset for this integration check")
    def test_dataset_length_metric_matches_all_sixty(self):
        path = REPO / "benchmarks/arena/final-d53690b057f9/benchmark_data_final.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(rows), 60)
        for index, row in enumerate(rows, 1):
            self.assertEqual(proof_tokens(row["src"], row["statement"]), row["proof_length"], f"F{index:03d}")

    def test_outer_scopes_and_doc_comments_stay_with_target(self):
        prefix = ('namespace N\n\ntheorem previous : True := by trivial\n\n'
                  'set_option maxHeartbeats 100000 in\nopen Nat in\n'
                  '/-- The target documentation, with /- nested comment -/. -/\n')
        cut = pending_command_start(prefix)
        self.assertEqual(prefix[:cut], 'namespace N\n\ntheorem previous : True := by trivial')
        self.assertIn('set_option maxHeartbeats', prefix[cut:])
        self.assertIn('/-- The target documentation', prefix[cut:])

    def test_module_doc_is_complete_command_and_private_modifier_stays_with_target(self):
        prefix = ('namespace N\n\ntheorem previous : True := by trivial\n\n'
                  '/-! A standalone module-doc command. -/\n'
                  'omit [Inhabited α] in\nprivate \n/-- Attached declaration doc. -/\n')
        cut = pending_command_start(prefix)
        self.assertTrue(prefix[:cut].endswith('/-! A standalone module-doc command. -/'))
        self.assertIn('omit [Inhabited α] in', prefix[cut:])
        self.assertIn('private', prefix[cut:])
        self.assertIn('/-- Attached declaration doc.', prefix[cut:])

    def test_comment_mask_preserves_all_source_offsets(self):
        original = 'def x := "/- not a comment -/"\n/- a /- nested -/\ncomment -/\n-- tail\n'
        masked = _comment_mask(original)
        self.assertEqual(len(masked), len(original))
        self.assertEqual([i for i,c in enumerate(masked) if c == '\n'],
                         [i for i,c in enumerate(original) if c == '\n'])
        self.assertIn('"/- not a comment -/"', masked)
        self.assertNotIn('nested', masked)

    @unittest.skipUnless(os.environ.get("ARENA_FINAL_INTEGRATION") == "1",
                         "Set ARENA_FINAL_INTEGRATION=1 after preparing all final environments")
    def test_every_pinned_context_is_complete_and_compiler_setup_exists(self):
        count = 0
        root = REPO / "sources/final"
        for state_file in sorted((root / 'environments').glob('*/environment.json')):
            state = json.loads(state_file.read_text())
            for location in state['locations']:
                count += 1
                if location['kind'] == 'standalone_header':
                    continue
                self.assertIsInstance(location['declaration_end_char'], int)
                source = REPO / state['project'] / location['file_path']
                packet = json.loads((root / 'problems' / f"F{location['row']:03d}.json").read_text())
                start, stop = location['statement_start_char'], location['declaration_end_char']
                actual = source.read_text()[start:stop]
                prefix = source.read_text()[:start]
                pending = prefix[pending_command_start(prefix):]
                self.assertNotIn('§', _comment_mask(pending, module_docs_are_commands=True),
                                 f"Standalone module doc captured as target: {state['id']} F{location['row']:03d}")
                if location['row'] == 4 and state['id'] == 'strata-v4.27.0':
                    self.assertIn('private', _comment_mask(pending))
                if location['kind'] == 'exact_src':
                    self.assertEqual(actual, packet['reference'])
                else:
                    self.assertEqual(actual.split(), packet['reference'].split())
                setup = REPO / state['project'] / '.lake/build/ir' / (location['module'].replace('.', '/') + '.setup.json')
                self.assertTrue(setup.is_file(), setup)
        self.assertEqual(count, 127)


if __name__ == '__main__':
    unittest.main()
