"""Preflight and diagnose the pinned main fixture harness (features 1 and 2)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import baseline
import diagnostics
import preflight


def files(root):
    return {str(p.relative_to(root)): baseline.sha(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts
            and p != root / "artifacts.json"}


def implementation_snapshot(root):
    for name in ("baseline.py", "preflight.py", "diagnostics.py", "replay.py", "run.py"):
        dest = root / "code" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(baseline.HERE / name, dest)
    for name in ("design.json", "baseline.lock.json"):
        dest = root / "planning" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(baseline.HERE / name, dest)


def snapshot_inputs(config_path, config, paths, root):
    directory = root / "input"
    directory.mkdir()
    shutil.copyfile(config_path, directory / "config.original.json")
    for key, name in {"problem": "problem.json", "template": "context.lean.in", "prompt": "prompt.txt",
                      "responses": "responses.json"}.items():
        shutil.copyfile(paths[key], directory / name)
    project = directory / "project"
    project.mkdir()
    for name in ("lean-toolchain", "lakefile.toml", "lakefile.lean", "lake-manifest.json"):
        if (paths["project"] / name).is_file():
            shutil.copyfile(paths["project"] / name, project / name)
    return {"id": "fixed", "project": str(project),
            "template": (directory / "context.lean.in").read_bytes().decode("utf-8"),
            **{key: config["lean"][key] for key in ("toolchain", "command", "timeout_seconds")}}


def lock(root, harness, config_path):
    compiler = Path(sys.executable).resolve()
    preflight.write(root / "run-lock.json", {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "implementation_git": harness.git_metadata(baseline.HERE) if harness else None,
        "python": {"executable": str(compiler), "sha256": baseline.sha(compiler.read_bytes()), "version": sys.version},
        "host": platform.platform(), "original_config_path": str(config_path),
        "files_before_compiler_execution": files(root),
        "prepared_compiler_evidence": "compiler-before-check.json and environment.json, when available",
        "model_backend": "fixture", "paid_api_calls_allowed": False,
    })


def launch_config(config, command, root):
    value = json.loads(json.dumps(config))
    for key, name in {"problem": "problem.json", "template": "context.lean.in", "prompt": "prompt.txt",
                      "project": "project"}.items():
        value[key] = "../input/" + name
    value["model"]["responses"] = "../input/responses.json"
    value["lean"]["command"] = command
    path = root / "launch/config.json"
    preflight.write(path, value)
    return path


def execute(config_path, output, *, continue_run=False, cache=None):
    """Single-process experiment. Failure paths persist a result without any model call."""
    output, config_path = Path(output), Path(config_path).resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Refusing to reuse an existing output: " + str(output))
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve()
    harness = None
    calls = 0
    recorder = diagnostics.Recorder(output)
    stage = "setup"
    failure_report = None
    summary = {"schema_version": 1, "status": "failed", "model_requests": 0, "api_calls": 0}
    try:
        implementation_snapshot(output)
        harness, evaluator_module, source_root = baseline.load(cache)
        # Freeze the baseline implementation even for a failed preflight run.
        for relative in harness.CODE_FILES:
            dest = output / "code/lean_agent" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / "src/lean_agent" / relative, dest)
        stage = "config"
        config, paths = harness.load_config(config_path)
        if config["model"]["backend"] != "fixture":
            raise ValueError("This experiment only accepts fixture mode; no live API calls")
        environment = snapshot_inputs(config_path, config, paths, output)
        lock(output, harness, config_path)
        stage = "preflight"
        checked = preflight.check(environment, output, evaluator_module)
        diagnosed = diagnostics.preflight_diagnosis(checked, output)
        if diagnosed:
            recorder.save("preflight", diagnosed)
        summary.update(preflight_status=checked["status"], stage=checked["stage"],
                       preflight_report="preflight.json", error=checked["error"])
        if checked["status"] == "passed":
            summary.update(status="ready", stage="preflight", error=None)
            if continue_run:
                stage = "harness"
                path = launch_config(config, checked["effective_command"], output)
                expected = {k: v for k, v in checked["environment"].items() if k not in ("project", "git")}

                class CheckedEvaluator(evaluator_module.LeanEvaluator):
                    def fingerprint(self, env):
                        nonlocal stage, failure_report
                        stage, failure_report = "environment", None
                        value = super().fingerprint(env)
                        if {k: v for k, v in value.items() if k not in ("project", "git")} != expected:
                            raise ValueError("Harness environment differs from the preflight snapshot")
                        return value

                    def evaluate(self, code, problem, environments, folder, repetitions):
                        nonlocal stage, failure_report
                        stage = folder.name if folder.name in ("baseline", "final") else "candidate"
                        failure_report = None
                        value = super().evaluate(code, problem, environments, folder, repetitions)
                        recorder.evaluated(value, folder)
                        if recorder.records[-1]["kind"]:
                            failure_report = recorder.records[-1]["path"]
                        return value

                original_query = harness.models.query

                def counted_query(*args, **kwargs):
                    nonlocal calls, stage, failure_report
                    stage, failure_report = "model", None
                    calls += 1
                    return original_query(*args, **kwargs)

                harness.models.query = counted_query
                try:
                    with diagnostics.feedback_adapter(harness, output, recorder):
                        result = harness.run(path, output / "harness", evaluator=CheckedEvaluator())
                finally:
                    harness.models.query = original_query
                stage, failure_report = "replay", None
                replay = diagnostics.replay(harness, output)
                summary.update(status=result["status"], stage="harness", harness_summary="harness/summary.json",
                               selected_sha256=result["state"]["best"]["sha256"], replay=replay)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        diagnostic = output / "diagnostic.log"
        diagnostic.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        summary.update(status="failed", stage=stage, diagnostic_log=diagnostic.name,
                       error={"kind": "configuration" if stage == "config" else "unknown",
                              "exception_type": type(exc).__name__, "message": str(exc)})
        if failure_report:
            summary["failure_diagnosis"] = failure_report
        else:
            recorder.save("failure", diagnostics.diagnosis(
                stage, summary["error"]["kind"], "execution_exception",
                evidence=[diagnostics.evidence(output, diagnostic)], original_error=summary["error"]))
            summary["failure_diagnosis"] = "diagnostics/failure.json"
    finally:
        if not (output / "run-lock.json").exists():
            lock(output, harness, config_path)
        summary["model_requests"] = calls
        summary["diagnostics"] = recorder.records
        preflight.write(output / "result.json", summary)
        preflight.write(output / "artifacts.json", files(output))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "run"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, help="Defaults to PROJECT_CACHE_DIR")
    args = parser.parse_args(argv)
    try:
        result = execute(args.config, args.output, continue_run=args.action == "run", cache=args.cache)
    except (OSError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("ready", "completed") else 1


if __name__ == "__main__":
    sys.exit(main())
