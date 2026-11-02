"""Run a command in one explicitly pinned final-benchmark environment."""
import argparse
import json
import os
from bootstrap import REPO, ROOT, plan, command
from prepare import process_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", nargs="?")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    environments = {env["id"]: env for env in plan()["environments"]}
    if not args.environment:
        for name, env in environments.items():
            path = ROOT / "environments" / name / "environment.json"
            state = json.loads(path.read_text()) if path.exists() else {}
            print(name, state.get("status", "not-built"), state.get("stage", ""))
        return
    env = environments.get(args.environment)
    if env is None:
        parser.error("Unknown pinned environment")
    argv = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not argv:
        parser.error("Supply a command after --, e.g. lake lean File.lean")
    project = REPO / env["project"]
    head = command(["git", "-C", project, "rev-parse", "HEAD"]).strip()
    if head != env["revision"]:
        raise ValueError("Source checkout differs from the benchmark pin")
    compiler = ROOT / "toolchains" / env["version"] / "bin/lean"
    actual = command([compiler, "--version"]).strip()
    if not actual.startswith("Lean (version " + env["version"][1:] + ","):
        raise ValueError("Compiler version differs from the benchmark pin")
    os.chdir(project)
    os.execvpe(argv[0], argv, process_env(env["version"]))


if __name__ == "__main__":
    main()
