"""Repeat the final environment preparation from the checked dataset snapshot."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import venv

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
runtime = REPO / "sources/final"
logs = runtime / "logs"
logs.mkdir(parents=True, exist_ok=True)
python = REPO / ".venv/bin/python"
if not python.exists():
    venv.EnvBuilder(with_pip=True).create(REPO / ".venv")
with (logs / "python-install.log").open("w") as stream:
    subprocess.run([str(python), "-m", "pip", "--cache-dir", str(runtime / "cache/pip"),
                    "install", "--index-url", "https://pypi.org/simple", "--no-deps", "-e", str(REPO)],
                   cwd=REPO, stdout=stream, stderr=subprocess.STDOUT, check=True)
environment = dict(os.environ, PYTHONPATH=str(REPO / "src"))
for script, arguments in (("bootstrap.py", ["fetch"]), ("toolchains.py", []),
                          ("resolve.py", []), ("prepare.py", []), ("finalize.py", [])):
    log = logs / (script.removesuffix(".py") + ".log")
    print("PHASE", script, "LOG", log, flush=True)
    with log.open("w") as stream:
        result = subprocess.run([str(python), "-B", str(HERE / script), *arguments],
                                cwd=REPO, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(errors="replace")[-5000:], flush=True)
        raise SystemExit(result.returncode)
print("All final benchmark environments prepared and checked.")
