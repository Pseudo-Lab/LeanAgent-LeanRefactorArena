"""REFACTOR_EVAL_LEAN_TESTS=1 python3 -m unittest discover -s tests -v

Requires the example's Lean 4.26.0 toolchain already installed. No model calls.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from refactor_eval.lean import LeanEvaluator, execute
from refactor_eval.session import Session, load_config, run_search, write_json

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/basic"


class ProcessTests(unittest.TestCase):
    def test_timeout_keeps_partial_diagnostics(self):
        command = [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(20)"]
        result = execute(command, Path.cwd(), 0.2)
        self.assertTrue(result["timed_out"])
        self.assertNotEqual(result["returncode"], 0)
        self.assertIn("started", result["output"])

    def test_agent_stderr_is_not_protocol_stdout(self):
        result = execute([sys.executable, "-c", "import sys; print(sys.stdin.read()); print('log', file=sys.stderr)"],
                         Path.cwd(), 5, input_text='{"code":"example"}', separate_stderr=True)
        self.assertEqual(json.loads(result["output"]), {"code": "example"})
        self.assertEqual(result["stderr"].strip(), "log")


@unittest.skipUnless(os.environ.get("REFACTOR_EVAL_LEAN_TESTS") == "1", "opt-in real Lean tests")
class LeanIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_real_repair_loop_final_selection_and_all_artifacts(self):
        session = Session(self.root / "run")
        session.initialize(EXAMPLE / "problem.json")
        codes = [(EXAMPLE / "broken.lean").read_text(), (EXAMPLE / "short.lean").read_text()]
        seen = []
        def propose(feedback):
            seen.append(feedback)
            if len(seen) == 2:
                self.assertFalse(feedback["latest_evaluation"]["result"]["valid"])
            return {"code": codes[len(seen) - 1]}
        selected = run_search(session, propose, max_attempts=2)
        self.assertEqual(selected["winner"]["candidate_id"], "candidate-0002")
        self.assertGreater(selected["winner"]["score"], 0)
        manifest = session.status()
        final = manifest["candidates"][2]["evaluations"][-1]["result"]
        self.assertEqual(final["tokens"], 2)
        runs = final["environments"]["lean-4-26"]["runs"]
        self.assertEqual(len(runs), 4)  # plain compilation + 3 measurements
        self.assertEqual(runs[1]["measurement"]["axioms"], [])
        self.assertTrue(list(session.directory.rglob("*.log")))

    def evaluate_template(self, template, name, statement, code):
        config, _ = load_config(EXAMPLE / "problem.json")
        config.update(name=name, statement=statement)
        env = copy.deepcopy(config["environments"][0])
        env["template"] = template
        if template.startswith("module\n"):
            env["command"].append("-Dexperimental.module=true")
        return LeanEvaluator().evaluate(code, config, [env], self.root / "evaluation", 1)

    def test_module_context_and_axiom_inspection(self):
        template = ("module\n{{HARNESS_IMPORT}}\npublic import Lean\n{{HARNESS_COMMANDS}}\n"
                    "public section\nnamespace Sample\n{{DECLARATION}}\nend Sample\n")
        statement = "theorem verified : True"
        result = self.evaluate_template(template, "Sample.verified", statement, statement + " := by\n  trivial\n")
        self.assertTrue(result["valid"], result)

    def test_imported_or_context_sorry_is_not_a_valid_candidate(self):
        template = ("{{HARNESS_IMPORT}}\nimport Lean\n{{HARNESS_COMMANDS}}\n"
                    "theorem untrusted : False := by sorry\n{{DECLARATION}}\n")
        statement = "theorem checked : False"
        result = self.evaluate_template(template, "checked", statement, statement + " := by\n  exact untrusted\n")
        self.assertFalse(result["valid"])
        self.assertEqual(result["environments"]["lean-4-26"]["error"]["kind"], "axioms")

    def test_measurement_import_does_not_make_plain_invalid_proof_valid(self):
        template = "{{HARNESS_IMPORT}}\n{{HARNESS_COMMANDS}}\n{{DECLARATION}}\n"
        statement = "theorem checked : Lean.Meta.Config = Lean.Meta.Config"
        # This type is provided by Lean imports, absent in the plain context.
        result = self.evaluate_template(template, "checked", statement, statement + " := by\n  rfl\n")
        self.assertFalse(result["valid"])
        self.assertEqual(result["environments"]["lean-4-26"]["error"]["kind"], "compile")


if __name__ == "__main__":
    unittest.main()
