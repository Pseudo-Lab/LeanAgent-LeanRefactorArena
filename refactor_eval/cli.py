from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .lean import execute, read_text
from .session import Session, json_text, run_search
from .tokens import proof_tokens


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Lean refactoring evaluation and final selection")
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="Freeze problem/policy and measure the original proof")
    init.add_argument("--problem", required=True, type=Path)
    init.add_argument("--run-dir", required=True, type=Path)
    checkpoint = commands.add_parser("checkpoint", help="Snapshot, verify and measure one candidate")
    checkpoint.add_argument("--run-dir", required=True, type=Path)
    checkpoint.add_argument("--candidate", required=True, type=Path)
    checkpoint.add_argument("--parent-id")
    checkpoint.add_argument("--note", default="")
    for action in ("status", "feedback", "recover", "finalize"):
        command = commands.add_parser(action)
        command.add_argument("--run-dir", required=True, type=Path)
    tokens = commands.add_parser("tokens", help="Count proof source tokens without compiling")
    tokens.add_argument("--statement", required=True, type=Path)
    tokens.add_argument("--candidate", required=True, type=Path)
    run = commands.add_parser("run", help="Drive a JSON-stdio agent, measuring every returned candidate")
    run.add_argument("--problem", required=True, type=Path)
    run.add_argument("--run-dir", required=True, type=Path)
    run.add_argument("--max-attempts", type=int, default=5)
    run.add_argument("--agent-timeout", type=float, default=300)
    run.add_argument("agent_command", nargs=argparse.REMAINDER, help="-- python path/to/adapter.py")
    args = parser.parse_args(argv)
    try:
        if args.action == "tokens":
            result = {"tokens": proof_tokens(read_text(args.candidate), read_text(args.statement).rstrip("\n"))}
        else:
            session = Session(args.run_dir)
            if args.action == "init":
                result = session.initialize(args.problem)
            elif args.action == "checkpoint":
                result = session.checkpoint(read_text(args.candidate), parent_id=args.parent_id, note=args.note)
            elif args.action == "run":
                from .session import positive_number
                positive_number(args.max_attempts, "max_attempts", integer=True)
                positive_number(args.agent_timeout, "agent_timeout")
                command = args.agent_command
                if command and command[0] == "--":
                    command = command[1:]
                if not command:
                    raise ValueError("run requires an agent command after --")
                session.initialize(args.problem)
                def propose(feedback):
                    # Separate protocol stdout from diagnostic stderr. No shell.
                    result = execute(command, Path.cwd(), args.agent_timeout,
                                     input_text=json_text(feedback), separate_stderr=True)
                    if result["returncode"] or result["timed_out"]:
                        raise ValueError("Agent failed: " + result.get("stderr", "")[-4000:])
                    return json.loads(result["output"])
                result = run_search(session, propose, max_attempts=args.max_attempts)
            else:
                result = getattr(session, args.action)()
        print(json_text(result), end="")
        if args.action == "checkpoint" and not result["result"]["valid"]:
            return 2  # Expected failed candidate: saved and available for repair.
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json_text({"error": str(error)}), file=sys.stderr, end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
