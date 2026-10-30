"""Run the existing profiler with the meta marker required by modular Lean."""
import importlib.util
import json
from pathlib import Path
import re
import sys

path = Path(__file__).with_name("profile.py")
spec = importlib.util.spec_from_file_location("hb_profile_original", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
environment = json.loads(Path(sys.argv[sys.argv.index("--env") + 1]).read_text())
if environment.get("lead"):
    loader = module.load_statement
    module.load_statement = lambda benchmark, name: environment["lead"] + loader(benchmark, name)
if re.search(r"(?m)^module\s*$", environment["template"]):
    module.PROFILER = (module.PROFILER
                      .replace("def seqItems", "public meta def seqItems")
                      .replace("partial def wrap", "public meta partial def wrap")
                      .replace("@[tactic hbProfileTac] def", "@[tactic hbProfileTac] public meta def"))
module.main()
