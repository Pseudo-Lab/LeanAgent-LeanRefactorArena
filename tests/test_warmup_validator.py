"""Static filter and publication regressions; never execute Lean or use the network."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import publish_warmup_verification as publisher
from scripts import verify_warmup_pins as verifier
from scripts import warmup_evaluator

ROOT = Path(__file__).resolve().parents[1]
STATEMENT = 'theorem fixture : True'


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.runtime = Path(temp.name)
        cls.metadata = warmup_evaluator.restore_evaluator(ROOT, cls.runtime)
        spec = importlib.util.spec_from_file_location(
            'patched_tokens', cls.runtime / 'refactor_eval/tokens.py')
        cls.validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validator)
        cls.original_source = subprocess.check_output(
            ['git', '-C', str(ROOT), 'show',
             f'{warmup_evaluator.EVALUATOR_REVISION}:refactor_eval/tokens.py'])
        cls.original = types.ModuleType('original_tokens')
        exec(compile(cls.original_source, 'original_tokens.py', 'exec'), cls.original.__dict__)

    def validate(self, body):
        self.validator.validate_declaration(STATEMENT + ' := by\n  ' + body, STATEMENT)

    def test_adjacent_cardinality_notations_are_allowed(self):
        for expression in ('#(filter p s)', '#{i | p i}', '#((s))'):
            with self.subTest(expression=expression):
                self.validate(f'have h := {expression}\n  trivial')

    def test_other_hash_forms_and_unknown_commands_stay_blocked(self):
        for expression in ('#eval 1', '#reduce 1', '#check Nat', '#print Nat',
                           '#exit', '#count_heartbeats trivial', '#unknown', '#',
                           '# (s)', '# {i | p i}', '#s', '##(s)'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.validate(expression)

    def test_existing_forbidden_constructs_stay_blocked(self):
        for expression in (
            'sorry', 'sorryAx', 'admit', 'axiom', 'unsafe', 'native_decide',
            'ofReduceBool', 'ofReduceNat', 'run_tac', 'run_elab', 'run_cmd',
            'initialize', 'builtin_initialize', 'implemented_by', 'extern',
            'set_option', 'macro', 'macro_rules', 'elab', 'elab_rules', 'syntax',
            'notation', 'attribute', 'import', 'namespace', 'section', 'end',
            'def', 'abbrev', 'instance', 'structure', 'inductive', 'class',
            'opaque', 'theorem', 'lemma', 'example', 'variable', 'universe',
            'export', 'IO.println "x"',
        ):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.validate(expression)

    def test_cardinality_does_not_hide_inner_or_appended_forbidden_code(self):
        for body in (
            'have h := #(by sorry)',
            'have h := #{i | by run_tac pure ()}',
            'have h := #(#eval 1)',
            'have h := #(s)\n  #unknown',
            'have h := #{i | p i}\n  theorem injected : True := by trivial',
            'have h := #(s)\n  native_decide',
            'have h := #(s)\n  IO.println "x"',
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.validate(body)

    def test_comment_handling_does_not_hide_executable_code(self):
        self.validate('/- outer /- #eval sorry -/ #unknown -/\n  trivial -- #exit')
        self.validate('have h := #(/- nested /- #eval -/ -/ s)\n  trivial')
        for body in ('#/- comment -/eval 1', '"--"; #eval 1',
                     '"/-"; #eval 1; "-/"', '/- unclosed'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.validate(body)

    def test_statement_and_tactic_proof_requirements_are_unchanged(self):
        with self.assertRaisesRegex(ValueError, 'statement'):
            self.validator.validate_declaration('theorem fixture : False := by trivial', STATEMENT)
        with self.assertRaisesRegex(ValueError, 'tactic proofs'):
            self.validator.validate_declaration(STATEMENT + ' := True.intro', STATEMENT)

    def test_real_originals_and_candidates_keep_token_counts_and_gate_outcomes(self):
        inputs = json.loads((ROOT / 'submissions/warmup/verification-inputs.json').read_text())
        snapshot = json.loads((ROOT / 'dashboard/public/data/warmup-team-results.json').read_text())
        self.assertEqual(self.original.TOKENIZER_ID, self.validator.TOKENIZER_ID)
        for row in snapshot['problems']:
            if str(row['id']) not in inputs['problems']:
                continue
            meta = inputs['problems'][str(row['id'])]
            declarations = [('original', meta['src'])]
            declarations.extend((c['id'], c['proof']) for c in row['teamResults'])
            for label, declaration in declarations:
                with self.subTest(problem=row['id'], source=label):
                    self.assertEqual(
                        self.original.proof_tokens(declaration, meta['statement']),
                        self.validator.proof_tokens(declaration, meta['statement']))
                    self.validator.validate_declaration(declaration, meta['statement'])
                    if row['id'] == 12 and label == 'original':
                        with self.assertRaisesRegex(ValueError, 'Forbidden'):
                            self.original.validate_declaration(declaration, meta['statement'])
                    else:
                        self.original.validate_declaration(declaration, meta['statement'])

    def test_restored_files_and_reported_hash_match_exact_patch(self):
        self.assertEqual(self.metadata, warmup_evaluator.evaluator_metadata())
        for file in (self.runtime / 'refactor_eval').glob('*.py'):
            original = subprocess.check_output(
                ['git', '-C', str(ROOT), 'show',
                 f'{warmup_evaluator.EVALUATOR_REVISION}:refactor_eval/{file.name}'])
            expected = (warmup_evaluator.patch_validator(original)
                        if file.name == 'tokens.py' else original)
            self.assertEqual(file.read_bytes(), expected, file.name)
        actual = (self.runtime / 'refactor_eval/tokens.py').read_bytes()
        self.assertEqual(hashlib.sha256(actual).hexdigest(), self.metadata['validatorSha256'])
        with self.assertRaisesRegex(ValueError, 'Frozen validator hash mismatch'):
            warmup_evaluator.patch_validator(self.original_source + b'\n')


class CslibRunnerTests(unittest.TestCase):
    def test_each_p07_pin_routes_through_cslib_preparation_and_evaluation(self):
        """Exercise the actual runner with synthetic preparation; no Lean or network."""
        inputs = json.loads((ROOT / 'submissions/warmup/verification-inputs.json').read_text())
        meta = inputs['problems']['7']
        snapshot = json.loads((ROOT / 'dashboard/public/data/warmup-team-results.json').read_text())
        row = next(p for p in snapshot['problems'] if p['id'] == 7)
        selected = next(c for c in row['teamResults'] if c['id'] == row['selectedCandidateId'])
        for pin in meta['version_info']:
            version, revision = next(iter(pin.items()))
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                folder = root / 'submissions/warmup'
                (folder / 'best').mkdir(parents=True)
                (folder / 'best/P07.lean').write_text(selected['proof'])
                (folder / 'verification-inputs.json').write_text(json.dumps({'problems': {'7': meta}}))
                published = root / 'dashboard/public/data/warmup-team-results.json'
                published.parent.mkdir(parents=True)
                published.write_text(json.dumps({'problems': [row]}))
                args = argparse.Namespace(source='cslib', version=version,
                                          work=root / 'work', output=root / 'output', memory_mb=6144)
                project = args.work / 'project'
                commands, evaluations = [], []

                def prepare(command, **kwargs):
                    commands.append(command)
                    if command == ['git', 'rev-parse', 'HEAD']:
                        kwargs['stdout'].write(revision + '\n')
                    if command[:2] == ['git', 'init']:
                        project.mkdir()
                        (project / 'lean-toolchain').write_text(f'leanprover/lean4:{version}\n')
                        (project / 'lake-manifest.json').write_text('{"packages": []}')
                        source = project / meta['file_path']
                        source.parent.mkdir(parents=True)
                        source.write_text(
                            'module\npublic import Cslib.Languages.LambdaCalculus.LocallyNameless.Fsub.Typing\n'
                            'namespace Cslib.LambdaCalculus.LocallyNameless.Fsub\n'
                            'set_option linter.tacticAnalysis.verifyGrindOnly false in\n'
                            '/-- Synthetic surrounding context. -/\n' + meta['src'] + '\nend\n')
                    return subprocess.CompletedProcess(command, 0)

                def checkout_head(command, **kwargs):
                    self.assertEqual(command, ['git', '-C', str(project), 'rev-parse', 'HEAD'])
                    return revision + '\n'

                class FakeEvaluator:
                    def fingerprint(self, env):
                        return {'command': env['command']}

                    def evaluate(self, code, config, environments, output, runs):
                        evaluations.append((code, config, runs))
                        return {'valid': True, 'environments': {}}

                lean = types.ModuleType('refactor_eval.lean')
                lean.LeanEvaluator = FakeEvaluator
                tokens = types.ModuleType('refactor_eval.tokens')
                tokens.TOKENIZER_ID = 'synthetic'
                with (patch.object(verifier, 'ROOT', root),
                      patch.object(verifier.platform, 'platform', return_value='synthetic'),
                      patch.object(verifier, 'restore_evaluator', return_value=warmup_evaluator.evaluator_metadata()),
                      patch.object(verifier.subprocess, 'run', side_effect=prepare),
                      patch.object(verifier.subprocess, 'check_output', side_effect=checkout_head),
                      patch.dict(sys.modules, {'refactor_eval.lean': lean, 'refactor_eval.tokens': tokens}),
                      patch.object(sys, 'path', sys.path.copy()),
                      patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}),
                      redirect_stdout(io.StringIO())):
                    verifier.main(args)
                self.assertIn(['git', 'remote', 'add', 'origin', 'https://github.com/leanprover/cslib.git'], commands)
                self.assertIn(['git', 'fetch', '--depth=1', 'origin', revision], commands)
                self.assertIn(['lake', 'build',
                               '+Cslib.Languages.LambdaCalculus.LocallyNameless.Fsub.Safety:olean'], commands)
                summary = json.loads((args.output / 'summary.json').read_text())
                self.assertEqual(summary['status'], 'completed')
                self.assertEqual(summary['source'], 'cslib')
                self.assertEqual(summary['revision'], revision)
                self.assertEqual([p['id'] for p in summary['problems']], [7])
                self.assertEqual(len(evaluations), 1 + len(row['teamResults']))
                self.assertTrue(all(runs == 3 for _, _, runs in evaluations))
                self.assertTrue(all(code.startswith(config['statement']) for code, config, _ in evaluations))


class PublicationTests(unittest.TestCase):
    """Synthetic successful measurements test metadata handling in an isolated tree."""

    source = 'arklib'
    problem_id = 12
    designated_versions = ('v4.29.0', 'v4.30.0', 'v4.31.0')

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / 'submissions/warmup'
        self.snapshot_path = self.root / 'dashboard/public/data/warmup-team-results.json'
        self.manifest_path = self.folder / 'manifest.json'
        proof = STATEMENT + ' := by trivial\n'
        digest = hashlib.sha256(proof.encode()).hexdigest()
        versions = [{'version': v, 'revision': chr(97 + i) * 40, 'status': 'pending'}
                    for i, v in enumerate(self.designated_versions)]
        candidate = {'id': 'fixture', 'proof': proof, 'candidateHash': digest,
                     'note': 'Synthetic fixture.', 'status': 'pending',
                     'baseline': None, 'candidate': None, 'versions': versions,
                     'environment': 'fixture'}
        row = {'id': self.problem_id, 'source': self.source, 'selectedCandidateId': 'fixture',
               'teamResults': [candidate]}
        self.write(self.snapshot_path, {'problems': [row]})
        self.write(self.manifest_path, {'problems': [{'id': self.problem_id, 'sha256': digest,
                                                     'allDesignatedVersionsVerified': False}]})
        self.write(self.folder / 'verification-inputs.json', {
            'problems': {str(self.problem_id): {'version_info': [{v['version']: v['revision']} for v in versions]}}})
        best = self.folder / f'best/P{self.problem_id:02}.lean'
        best.parent.mkdir(parents=True)
        best.write_text(proof)
        self.reports = []
        self.paths = []
        for index, version in enumerate(versions):
            def measured(tokens, heartbeats):
                return {'valid': True, 'tokens': tokens, 'environments': {
                    'fixture': {'runs': [{} for _ in range(4)], 'median_heartbeats': heartbeats}}}
            self.reports.append({
                **warmup_evaluator.evaluator_metadata(), 'status': 'completed', 'repetitions': 3,
                'source': self.source, 'version': version['version'], 'revision': version['revision'],
                'host': 'synthetic', 'commit': 'd' * 40, 'runId': 'fixture',
                'manifestSha256': 'e' * 64, 'dependencies': [],
                'finishedAt': '2026-10-26T00:00:00+00:00',
                'problems': [{'id': self.problem_id, 'baseline': measured(100 + index, 1000 + index * 100), 'candidates': {
                    'fixture': {'sha256': digest, 'result': measured(50 + index, 500 + index * 50)}}}],
            })
            self.paths.append(self.root / f'{version["version"]}.json')

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def publish(self, reports):
        for path, report in zip(self.paths, reports):
            self.write(path, report)
        with patch.object(publisher, 'ROOT', self.root):
            publisher.publish(self.paths)

    def test_current_identity_is_published_with_each_run(self):
        self.publish(self.reports)
        evidence = json.loads((self.folder / 'verification-results.json').read_text())
        self.assertEqual(evidence['schemaVersion'], 2)
        for key, value in warmup_evaluator.evaluator_metadata().items():
            self.assertEqual(evidence[key], value)
            self.assertTrue(all(run[key] == value for run in evidence['runs']))
        manifest = json.loads(self.manifest_path.read_text())
        snapshot = json.loads(self.snapshot_path.read_text())
        self.assertEqual(snapshot['problems'][0]['status'], 'measured')
        primary = next(r for r in self.reports if r['version'] == publisher.PRIMARY[self.source])
        original = primary['problems'][0]['baseline']
        candidate = primary['problems'][0]['candidates']['fixture']['result']
        self.assertEqual(snapshot['problems'][0]['baseline'], publisher.measurement(original))
        self.assertEqual(snapshot['problems'][0]['candidate'], publisher.measurement(candidate))
        self.assertTrue(all(v['status'] == 'pass' for v in snapshot['problems'][0]['versions']))
        self.assertIn(warmup_evaluator.VALIDATOR_VERSION, snapshot['provenance'])
        self.assertEqual(manifest['dashboardSnapshotSha256'],
                         hashlib.sha256(self.snapshot_path.read_bytes()).hexdigest())

    def test_legacy_mixed_or_changed_identities_cannot_write_published_files(self):
        for field in ('legacy', 'validatorVersion', 'validatorSha256', 'evaluatorRevision'):
            with self.subTest(field=field):
                reports = deepcopy(self.reports)
                if field == 'legacy':
                    reports[1].pop('validatorVersion')
                    reports[1].pop('validatorSha256')
                else:
                    reports[1][field] = 'changed'
                snapshot_before = self.snapshot_path.read_bytes()
                manifest_before = self.manifest_path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'incompatible verification'):
                    self.publish(reports)
                self.assertEqual(self.snapshot_path.read_bytes(), snapshot_before)
                self.assertEqual(self.manifest_path.read_bytes(), manifest_before)
                self.assertFalse((self.folder / 'verification-results.json').exists())

    def test_unregistered_problem_and_its_evidence_are_preserved(self):
        snapshot = json.loads(self.snapshot_path.read_text())
        untouched = {'id': 9, 'status': 'measured',
                     'evidence': ['submissions/warmup/best/P09.lean',
                                  'dashboard/public/research/p09/experiment.json']}
        snapshot['problems'].append(deepcopy(untouched))
        self.write(self.snapshot_path, snapshot)
        self.publish(self.reports)
        after = json.loads(self.snapshot_path.read_text())
        self.assertEqual(after['problems'][1], untouched)


class CslibPublicationTests(PublicationTests):
    source = 'cslib'
    problem_id = 7
    designated_versions = ('v4.33.0-rc2', 'v4.32.0', 'v4.31.0')

    def test_missing_cslib_version_cannot_write_published_files(self):
        for path, report in zip(self.paths, self.reports):
            self.write(path, report)
        snapshot_before = self.snapshot_path.read_bytes()
        manifest_before = self.manifest_path.read_bytes()
        with patch.object(publisher, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'Missing designated verification: P07 cslib v4.33.0-rc2'):
                publisher.publish(self.paths[1:])
        self.assertEqual(self.snapshot_path.read_bytes(), snapshot_before)
        self.assertEqual(self.manifest_path.read_bytes(), manifest_before)
        self.assertFalse((self.folder / 'verification-results.json').exists())


if __name__ == '__main__':
    unittest.main()
