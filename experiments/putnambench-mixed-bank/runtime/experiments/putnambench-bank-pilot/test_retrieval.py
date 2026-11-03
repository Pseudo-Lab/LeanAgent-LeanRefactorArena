"""Legal-scope and bounded-memory retrieval regressions; no compiler or API."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from retrieval import build_import_corpus, imports_from_text


class RetrievalTests(unittest.TestCase):
    def test_import_comments_and_modifiers(self):
        self.assertEqual(imports_from_text("prelude\n/- import Bad -/\npublic meta import Good.One\nimport all Good.Two -- import Bad\n"),
                         ["Good.One", "Good.Two"])

    def test_only_import_closure_and_no_target_or_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".lake/build/lib/lean").mkdir(parents=True)
            sources = {
                "Root": "import Good\nimport Downstream\ntheorem rootRarething : True := by trivial\n",
                "Good": "import Dependency\ntheorem rarethingUseful : True := by trivial\n",
                "Dependency": "prelude\ntheorem rarethingDependency : True := by trivial\n",
                "Downstream": "import Target\ntheorem rarethingCircular : True := by trivial\n",
                "Unrelated": "prelude\ntheorem rarethingNotImported : True := by trivial\n",
            }
            for module, source in sources.items():
                (root / (module + ".lean")).write_text(source)
            # The forbidden module cannot even be decoded, proving it is not opened.
            (root / "Target.lean").write_bytes(b"\xff\xfe")
            state = {"id": "fixture", "revision": "fixture-sha", "project": ".",
                     "lean_path": str(root / ".lake/build/lib/lean")}
            problem = {"name": "target", "statement": "theorem target : rarething", "reference": "theorem target : rarething := by trivial"}
            result = build_import_corpus(problem, "import Root\n", state, root,
                                         target_module="Target", max_bytes=10000)
            text = "\n".join(entry["text"] for entry in result["entries"])
            self.assertIn("rarethingUseful", text)
            self.assertIn("rarethingDependency", text)
            self.assertNotIn("rarethingCircular", text)
            self.assertNotIn("rootRarething", text)
            self.assertNotIn("rarethingNotImported", text)
            self.assertEqual(result["metadata"]["blocked_modules"], ["Downstream", "Root", "Target"])
            for record in result["metadata"]["included_sources"]:
                self.assertEqual(record["sha256"], hashlib.sha256(Path(record["source"]).read_bytes()).hexdigest())

    def test_detected_target_definition_blocks_importers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".lake/build/lib/lean").mkdir(parents=True)
            (root / "Parent.lean").write_text("import Answer\ntheorem rarethingParent : True := by trivial\n")
            (root / "Answer.lean").write_text("prelude\ntheorem target : True := by trivial\n")
            state = {"id": "fixture", "revision": "fixture-sha", "project": ".",
                     "lean_path": str(root / ".lake/build/lib/lean")}
            problem = {"name": "target", "statement": "theorem target : rarething", "reference": "theorem target : rarething := by trivial"}
            result = build_import_corpus(problem, "import Parent\n", state, root, max_bytes=10000)
            self.assertEqual(result["entries"], [])
            self.assertEqual(result["metadata"]["blocked_modules"], ["Answer", "Parent"])

    def test_budget_and_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".lake/build/lib/lean").mkdir(parents=True)
            (root / "Good.lean").write_text("prelude\n" + "\n".join(f"theorem rarething_{i} : True := by trivial" for i in range(1000)))
            state = {"id": "fixture", "revision": "fixture-sha", "project": ".",
                     "lean_path": str(root / ".lake/build/lib/lean")}
            problem = {"name": "target", "statement": "theorem target : rarething", "reference": "theorem target : rarething := by trivial"}
            one = build_import_corpus(problem, "import Good\n", state, root, max_bytes=10000)
            two = build_import_corpus(problem, "import Good\n", state, root, max_bytes=10000)
            self.assertEqual(one, two)
            self.assertGreater(len(one["entries"]), 0)
            self.assertLessEqual(one["metadata"]["corpus_utf8_bytes"], 10000)
            self.assertLessEqual(len(json.dumps(one["entries"], ensure_ascii=False).encode()), 10000)


if __name__ == "__main__":
    unittest.main()
