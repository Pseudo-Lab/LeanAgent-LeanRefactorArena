"""Absolute Lake setup aliases must resolve into the verified file inventory."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments/final-batch-next'))
from evaluator import FinalEvaluator, digest


class CompilerSetupScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('PROJECT_CACHE_DIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'checkout'
        self.build = self.root / 'verified-build'
        self.artifact = self.build / 'lib/lean/Dep.olean'
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_bytes(b'pinned dependency')
        (self.build / 'ir').mkdir()
        (self.project / '.lake').mkdir(parents=True)
        self.link = self.project / '.lake/build'
        self.link.symlink_to(self.build, target_is_directory=True)
        self.setup = self.link / 'ir/Target.setup.json'
        self.data = {'importArts': {'Dep': [[str(self.link / 'lib/lean/Dep.olean')]]}, 'plugins': [], 'dynlibs': []}
        self.setup.write_text(json.dumps(self.data))
        self.evaluator = object.__new__(FinalEvaluator)
        self.evaluator.repo = self.root
        self.evaluator._prepared = {'env': SimpleNamespace(settings={'files': {str(self.artifact): digest(self.artifact.read_bytes())}})}
        self.state = {'id': 'env', 'project': 'checkout'}

    def test_matching_checkout_alias_is_bound_to_the_prepared_file(self):
        path, checksum = self.evaluator._compiler_setup(self.state, {'module': 'Target'})
        self.assertEqual(path, self.setup)
        self.assertEqual(checksum, digest(self.setup.read_bytes()))

    def test_unchanged_setup_bytes_do_not_authorize_retargeting_a_build_link(self):
        context = {'module': 'Target'}
        self.evaluator._compiler_setup(self.state, context)
        other = self.root / 'unverified-build'
        (other / 'lib/lean').mkdir(parents=True)
        (other / 'ir').mkdir()
        (other / 'lib/lean/Dep.olean').write_bytes(self.artifact.read_bytes())
        (other / 'ir/Target.setup.json').write_bytes(self.setup.read_bytes())
        self.link.unlink()
        self.link.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unpinned artifact'):
            self.evaluator._compiler_setup(self.state, context)

    def test_unverified_native_plugin_is_rejected_before_compilation(self):
        plugin = self.root / 'foreign.dylib'
        plugin.write_bytes(b'plugin outside manifest')
        self.data['plugins'] = [str(plugin)]
        self.setup.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'unpinned artifact'):
            self.evaluator._compiler_setup(self.state, {'module': 'Target'})

    def test_relative_import_artifacts_are_resolved_from_the_pinned_project(self):
        self.data['importArts'] = {'Dep': [['.lake/build/lib/lean/Dep.olean']]}
        self.setup.write_text(json.dumps(self.data))
        self.evaluator._compiler_setup(self.state, {'module': 'Target'})
