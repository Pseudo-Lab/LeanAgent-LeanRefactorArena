"""Preflight and diagnose the pinned main fixture harness (features 1 and 2)."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import sys

import baseline
from baseline import artifact_hashes as files
import diagnostics
import preflight


@dataclass
class RunProgress:
    """In-memory context for exception records; not a persisted status journal."""
    stage: str = "setup"
    calls: int = 0
    failure_report: str | None = None

    def enter(self, stage):
        self.stage, self.failure_report = stage, None


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


def run_harness(harness, evaluator_module, config_path, environment, output, recorder, progress):
    """Adapt the pinned harness for this run; restore all hooks before replay."""
    expected = {k: v for k, v in environment.items() if k not in ("project", "git")}

    class CheckedEvaluator(evaluator_module.LeanEvaluator):
        def _evaluate_environment(self, code, problem, env, folder, row, runs):
            try:
                return super()._evaluate_environment(code, problem, env, folder, row, runs)
            except (KeyError, TypeError, RecursionError) as exc:
                records = row["runs"]
                last = records[-1] if records else {}
                if not (diagnostics.measuring_after_check(records) and last.get("returncode") == 0
                        and not last.get("timed_out") and "measurement" not in last):
                    raise
                # Match main's malformed-report stop policy without inventing a counter.
                row.update(valid=False, error={"kind": "environment",
                    "message": "Malformed measurement report: " + str(exc),
                    "exception_type": type(exc).__name__})

        def fingerprint(self, env):
            progress.enter("environment")
            value = super().fingerprint(env)
            if {k: v for k, v in value.items() if k not in ("project", "git")} != expected:
                raise ValueError("Harness environment differs from the preflight snapshot")
            return value

        def evaluate(self, code, problem, environments, folder, repetitions):
            progress.enter(folder.name if folder.name in ("baseline", "final") else "candidate")
            value = super().evaluate(code, problem, environments, folder, repetitions)
            recorder.evaluated(value, folder)
            if recorder.records[-1]["kind"]:
                progress.failure_report = recorder.records[-1]["path"]
            return value

    original_query = harness.models.query

    def counted_query(*args, **kwargs):
        progress.enter("model")
        progress.calls += 1
        return original_query(*args, **kwargs)

    harness.models.query = counted_query
    try:
        with diagnostics.feedback_adapter(harness, output, recorder):
            return harness.run(config_path, output / "harness", evaluator=CheckedEvaluator())
    finally:
        harness.models.query = original_query


def execute(config_path, output, *, continue_run=False, cache=None):
    """Single-process experiment; preflight failures stop before any model request."""
    output, config_path = Path(output), Path(config_path).resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Refusing to reuse an existing output: " + str(output))
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve()
    harness = None
    progress = RunProgress()
    recorder = diagnostics.Recorder(output)
    summary = {"schema_version": 1, "status": "failed", "model_requests": 0, "api_calls": 0}
    try:
        implementation_snapshot(output)
        harness, evaluator_module, source_root = baseline.load(cache)
        # Freeze the baseline implementation even for a failed preflight run.
        for relative in harness.CODE_FILES:
            dest = output / "code/lean_agent" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / "src/lean_agent" / relative, dest)
        progress.enter("config")
        config, paths = harness.load_config(config_path)
        if config["model"]["backend"] != "fixture":
            raise ValueError("This experiment only accepts fixture mode; no live API calls")
        environment = snapshot_inputs(config_path, config, paths, output)
        lock(output, harness, config_path)
        progress.enter("preflight")
        checked = preflight.check(environment, output, evaluator_module)
        diagnosed = diagnostics.preflight_diagnosis(checked, output)
        if diagnosed:
            recorder.save("preflight", diagnosed)
        summary.update(preflight_status=checked["status"], stage=checked["stage"],
                       preflight_report="preflight.json", error=checked["error"])
        if checked["status"] == "passed":
            summary.update(status="ready", stage="preflight", error=None)
            if continue_run:
                progress.enter("harness")
                summary.update(status="incomplete", stage=progress.stage)
                path = launch_config(config, checked["effective_command"], output)
                result = run_harness(harness, evaluator_module, path, checked["environment"], output, recorder, progress)
                progress.enter("replay")
                replay = diagnostics.replay(harness, output)
                summary.update(status=result["status"], stage="harness", harness_summary="harness/summary.json",
                               selected_sha256=result["state"]["best"]["sha256"], replay=replay)
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        interrupted = isinstance(exc, (KeyboardInterrupt, SystemExit))
        diagnostic = output / "diagnostic.log"
        diagnostic.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        summary.update(status="interrupted" if interrupted else "failed", stage=progress.stage, diagnostic_log=diagnostic.name,
                       error={"kind": "configuration" if progress.stage == "config" else "unknown",
                              "exception_type": type(exc).__name__, "message": str(exc)})
        if progress.failure_report:
            summary["failure_diagnosis"] = progress.failure_report
        else:
            recorder.save("failure", diagnostics.diagnosis(
                progress.stage, summary["error"]["kind"], "execution_interrupted" if interrupted else "execution_exception",
                evidence=[diagnostics.evidence(output, diagnostic)], original_error=summary["error"]))
            summary["failure_diagnosis"] = "diagnostics/failure.json"
        if interrupted:
            raise  # Persist in finally while retaining Ctrl-C/SystemExit behavior.
    finally:
        if not (output / "run-lock.json").exists():
            lock(output, harness, config_path)
        summary["model_requests"] = progress.calls
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
