"""Evaluation adapter for golf and final selection, on top of the team FinalEvaluator.

One adapter serves one row of one final-batch-next run root (``<root>/problems/F0NN``).

* ``screen``: primary version, one sample, cached by content under ``golf/screen/<sha12>``.
  Default mode ``single-pass`` runs only the instrumented compile (the team's
  ``reference_single_pass`` job: wrapper + target + suffix, heartbeat counter and axiom
  collection), so a screen costs one Lean process instead of two. Mode ``check-measure``
  calls ``FinalEvaluator.evaluate(repetitions=1)`` exactly as exploration does. The mode is
  part of the cache identity. Screens are never submission evidence.
* ``validate``: all listed versions (``compatibility/<sha>``, the directory report.py reads)
  plus a fresh 3x primary measurement, both through ``driver.evaluate_cached`` with the same
  evaluator and evaluation cache as the driver, so report.py's reuse audit passes.
* ``probe``: one diagnostic compile of a modified declaration (``try?``, linter options), in
  the same sandbox and compiler pool, under ``golf/probe/<sha12>``. Never submitted.

Static rules (``rules.check_static``) run before any compile of a non-reference text.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
import uuid

from .contracts import EvalResult
from . import rules, scoring

REPO = Path(__file__).resolve().parents[3]
FINAL_BATCH = REPO / "experiments" / "final-batch-next"
SCREEN_MODES = {"single-pass": "single-pass-instrumented-v1", "check-measure": "evaluate-repetitions-1-v1"}
SCREEN_SCHEMA = "final60-golf-screen-v1"
PROBE_SCHEMA = "final60-golf-probe-v1"
MESSAGE_LIMIT = 4000


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def final_batch_module(name: str):
    """Import a final-batch-next module (driver, report, ...) from this repository."""
    path = str(FINAL_BATCH)
    if path not in sys.path:
        sys.path.insert(0, path)
    module = importlib.import_module(name)
    if Path(module.__file__).resolve() != (FINAL_BATCH / (name + ".py")).resolve():
        raise ImportError(f"{name} resolves outside {FINAL_BATCH}: {module.__file__}")
    return module


def driver():
    return final_batch_module("driver")


def _read(path):
    return json.loads(Path(path).read_text())


def _atomic(path, value):
    driver().atomic(path, value)


def _set_aside(folder: Path) -> None:
    if folder.exists():
        folder.rename(folder.with_name(folder.name + "-incomplete-" + str(time.time_ns())))


class EvalAdapter:
    def __init__(self, run_root: Path, row: int, *, evaluator=None, screen_mode: str | None = None,
                 problem: dict | None = None):
        self.d = driver()
        self.run_root = Path(run_root).resolve()
        self.row = int(row)
        self.folder = self.d.folder(self.run_root, self.row)
        self.problem = problem if problem is not None else _read(self.folder / "input/problem.json")
        self.statement = self.problem["statement"]
        self.reference = self.problem["reference"]
        self.environments = list(self.problem["environments"])
        self.primary = self.environments[0]
        self.golf_dir = self.folder / "golf"
        mode = screen_mode or os.environ.get("FINAL60_GOLF_SCREEN_MODE", "single-pass")
        if mode not in SCREEN_MODES:
            raise ValueError("Unknown golf screen mode: " + str(mode))
        self.screen_mode = mode
        self.ev = evaluator if evaluator is not None else self.d.evaluator(self.run_root)
        self.compiles = 0          # Lean processes started by this adapter (cache hits excluded)
        self._baseline = None

    # ---- reference numbers ---------------------------------------------------------------
    def baseline(self) -> tuple[int, int]:
        """(T0, HB0 raw primary median) frozen by preflight; state.json wins when present."""
        if self._baseline is None:
            state = self.folder / "state.json"
            if state.exists():
                base = _read(state)["baseline"]
                self._baseline = (int(base["tokens"]), int(base["raw_heartbeats"]))
            else:
                from lean_agent import harness as h
                measured = h.metrics(_read(self.folder / "baseline/result.json"))
                if measured is None:
                    raise ValueError("Original failed its baseline measurement")
                self._baseline = (int(measured["tokens"]), int(measured["raw_heartbeats"]))
        return self._baseline

    def tokens(self, code: str) -> int:
        return scoring.count_tokens(code, self.statement)

    def screen_score(self, result: EvalResult) -> float | None:
        if not result.valid or result.tokens is None or result.raw_heartbeats is None:
            return None
        t0, hb0 = self.baseline()
        return scoring.screen_score(result.tokens, result.raw_heartbeats, t0, hb0)

    # ---- result conversion ---------------------------------------------------------------
    def to_eval(self, result: dict, evidence_dir: Path, *, primary_from: dict | None = None) -> EvalResult:
        guarded = self.d.guard_compiler_signal(result) if result.get("environments") else result
        rows = guarded.get("environments", {})
        envs = {name: bool(value.get("valid")) for name, value in rows.items()}
        source = (primary_from or guarded).get("environments", {}).get(self.primary, {})
        samples = [run["measurement"]["raw"] for run in source.get("runs", []) if "measurement" in run]
        valid = bool(guarded.get("valid")) and bool(envs) and all(envs.values())
        error_kind, message = None, ""
        if not valid:
            failures = [value.get("error") or {} for value in rows.values() if not value.get("valid")]
            top = guarded.get("error") or {}
            kinds = [failure.get("kind") for failure in failures if failure.get("kind")]
            if top.get("kind") == "validation" or not rows:
                error_kind = "validation" if top.get("kind") in (None, "validation") else top.get("kind")
            elif any(kind in ("environment", "resource") for kind in kinds):
                error_kind = "environment"
            elif "timeout" in kinds:
                error_kind = "timeout"
            elif "axioms" in kinds:
                error_kind = "axioms"
            else:
                error_kind = "compile"
            text = next((failure.get("message") for failure in failures if failure.get("message")), None)
            message = (text or top.get("message") or "")[-MESSAGE_LIMIT:]
        return EvalResult(valid=valid, tokens=guarded.get("tokens"),
                          raw_heartbeats=int(statistics.median(samples)) if valid and samples else None,
                          envs=envs, error_kind=error_kind, message=message, evidence_dir=str(evidence_dir))

    def reference_result(self) -> EvalResult:
        """The preflight's 3x baseline evidence for the original (no compile)."""
        folder = self.folder / "baseline"
        return self.to_eval(_read(folder / "result.json"), folder)

    # ---- screening -----------------------------------------------------------------------
    def screen(self, code: str, label: str) -> EvalResult:
        """Primary version, one sample, cached by content; never compiles the same text twice."""
        if code == self.reference and (self.folder / "baseline/result.json").exists():
            return self.reference_result()
        digest = sha(code)
        folder = self.golf_dir / "screen" / digest[:12]
        expected = {"schema": SCREEN_SCHEMA, "candidate_sha256": digest, "problem_id": self.problem.get("id"),
                    "environment": self.primary, "mode": SCREEN_MODES[self.screen_mode]}
        receipt = folder / "screen-request.json"
        if (folder / "result.json").exists() and receipt.exists():
            if _read(receipt) != expected:
                raise ValueError("Golf screen directory belongs to a different candidate or mode: " + str(folder))
            return self.to_eval(_read(folder / "result.json"), folder)
        _set_aside(folder)
        issues = [] if code == self.reference else rules.check_static(code, self.statement)
        if issues:
            result = {"valid": False, "tokens": None, "environments": {},
                      "error": {"kind": "validation", "message": "; ".join(issues)}}
        elif self.screen_mode == "single-pass":
            result = self._single_pass(code, folder)
        else:
            started = self.compiles
            result = self.d.evaluate_cached(self.ev, code, self.problem, folder / "evaluation", repetitions=1)
            self.compiles = started + int(result.get("timing", {}).get("new_compiler_invocations", 0) or 0)
        result = {**result, "screen": {"mode": SCREEN_MODES[self.screen_mode], "label": label}}
        evaluated = self.to_eval(result, folder)
        if evaluated.valid or evaluated.error_kind in ("validation", "compile", "axioms"):
            _atomic(folder / "result.json", result)
            _atomic(receipt, expected)
        else:
            # Environment/timeout failures stay retryable: no receipt is published.
            folder.mkdir(parents=True, exist_ok=True)
            _atomic(folder / "unpublished-result.json", result)
        self._log("screen", {"label": label, "sha256": digest, "valid": evaluated.valid,
                             "tokens": evaluated.tokens, "raw_heartbeats": evaluated.raw_heartbeats,
                             "error_kind": evaluated.error_kind})
        return evaluated

    def _evaluator_module(self):
        module = sys.modules.get(type(self.ev).__module__)
        needed = ("pending_command_start", "target_is_private", "add_lean_import", "WRAPPER",
                  "PRIVATE_WRAPPER", "ALLOWED_AXIOMS", "proof_tokens")
        if module is None or not all(hasattr(module, name) for name in needed):
            raise AttributeError("Evaluator module lacks single-pass internals")
        return module

    def _single_pass(self, code: str, folder: Path) -> dict:
        """One instrumented compile on the primary version (wrapper, target, suffix)."""
        try:
            module = self._evaluator_module()
            for name in ("_compiler_lock", "_state", "_context", "_invoke"):
                getattr(self.ev, name)
        except AttributeError:
            started = self.compiles
            result = self.d.evaluate_cached(self.ev, code, self.problem, folder / "evaluation", repetitions=1)
            self.compiles = started + int(result.get("timing", {}).get("new_compiler_invocations", 0) or 0)
            return result
        result = {"valid": False, "tokens": None, "environments": {}, "error": None,
                  "reference_compile_mode": "instrumented-compile-and-axioms"}
        try:
            result["tokens"] = module.proof_tokens(code, self.statement)
        except ValueError as exc:
            result["error"] = {"kind": "validation", "message": str(exc)}
            return result
        row = {"valid": False, "runs": [], "median_heartbeats": None, "error": None}
        result["environments"][self.primary] = row
        env_folder = folder / self.primary
        try:
            with self.ev._compiler_lock():
                state = self.ev._state(self.primary)
                context = self.ev._context(self.problem, self.primary)
                env_folder.mkdir(parents=True, exist_ok=False)
                prefix, suffix = context["prefix"], context["suffix"]
                cut = module.pending_command_start(prefix)
                wrapper = (module.PRIVATE_WRAPPER if module.target_is_private(prefix, self.statement)
                           else module.WRAPPER)
                nonce = uuid.uuid4().hex
                source = (module.add_lean_import(prefix[:cut]) + "\n" + wrapper +
                          "\nset_option Elab.async false in\n#refactor_eval " + json.dumps(nonce) + " " +
                          json.dumps(self.problem["name"], ensure_ascii=False) + "\n" + prefix[cut:] + code + suffix)
                record, log = self.ev._invoke(source, state, context, env_folder, "measure-1")
                self.compiles += 1
                row["runs"].append(record)
                if record["returncode"] or record["timed_out"]:
                    lowered = log.lower()
                    host = any(marker in lowered for marker in ("sandbox-exec:", "sandbox_apply:", "operation not permitted",
                                                                "permission denied", "input/output error"))
                    kind = "environment" if host else "timeout" if record["timed_out"] else "compile"
                    row["error"] = {"kind": kind, "message": log[-8000:]}
                else:
                    import re
                    matches = re.findall(r"REFACTOR_EVAL " + nonce + r" (\{[^\n]*\})", log)
                    if len(matches) != 1:
                        raise ValueError("Expected exactly one fresh target measurement")
                    report = json.loads(matches[0])
                    if (report["target"] != self.problem["name"] or type(report["raw"]) is not int
                            or report["raw"] < 0 or report["scaled"] != report["raw"] // 1000):
                        raise ValueError("Invalid measurement counter or target")
                    record["measurement"] = report
                    if not set(report["axioms"]) <= module.ALLOWED_AXIOMS:
                        audit, resolved, error = self.ev._audit_frontier(report["axioms"], state, context,
                                                                         env_folder, "axiom-audit-measure-1")
                        self.compiles += 1
                        row["runs"].append(audit)
                        record["resolved_axioms"] = resolved
                        if error:
                            row["error"] = error
                    if row["error"] is None:
                        row.update(valid=True, median_heartbeats=report["raw"] // 1000,
                                   median_raw_heartbeats=report["raw"])
        except (OSError, ValueError, RuntimeError) as exc:
            row.update(valid=False, error={"kind": "environment", "message": str(exc)})
        env_folder.mkdir(parents=True, exist_ok=True)
        self.d.atomic(env_folder / "result.json", row)
        result["valid"] = row["valid"]
        if not row["valid"]:
            result["error"] = {"kind": "lean", "message": "One or more required environments failed"}
        return result

    def diagnostics(self, result: EvalResult) -> list[tuple[str, str]]:
        """(log, compiled source) pairs saved for the primary version of an evaluation."""
        pairs = []
        root = Path(result.evidence_dir)
        for folder in (root / self.primary, root / "evaluation" / self.primary):
            for stem in ("check", "measure-1"):
                log, source = folder / (stem + ".log"), folder / (stem + ".lean")
                if log.is_file() and source.is_file():
                    pairs.append((log.read_text(errors="replace"), source.read_text(errors="replace")))
        return pairs

    # ---- final validation ----------------------------------------------------------------
    def _fresh_options(self, code: str) -> dict:
        return {"repetitions": 3, "trusted_reference": code == self.reference, "fresh": True}

    def _fresh_dir(self, code: str, *, as_final: bool) -> Path:
        final = self.folder / "final"
        expected = {"candidate_sha256": sha(code), "problem": self.problem, "options": self._fresh_options(code)}
        receipt = final / "evaluation-request.json"
        if (final / "result.json").exists() and receipt.exists() and _read(receipt) == expected:
            return final
        if as_final:
            if final.exists():
                old = _read(receipt).get("candidate_sha256", "unknown") if receipt.exists() else "unknown"
                final.rename(final.with_name(f"final-prev-{old[:12]}-{time.time_ns()}"))
            return final
        return self.golf_dir / "validate" / sha(code)[:12] / "final"

    def validate(self, code: str, label: str, *, as_final: bool = False) -> EvalResult:
        """All listed versions plus a fresh 3x primary measurement (report.py layout)."""
        trusted = code == self.reference
        if not trusted:
            issues = rules.check_static(code, self.statement)
            if issues:
                return EvalResult(False, None, None, {}, "validation", "; ".join(issues)[-MESSAGE_LIMIT:], "")
        digest = sha(code)
        compat_dir = self.folder / "compatibility" / digest
        existed = (compat_dir / "result.json").exists()
        compat = self.d.guard_compiler_signal(self.d.evaluate_cached(
            self.ev, code, self.problem, compat_dir, repetitions=1, all_versions=True, trusted_reference=trusted))
        if not existed:
            self.compiles += int(compat.get("timing", {}).get("new_compiler_invocations", 0) or 0)
        checked = self.to_eval(compat, compat_dir)
        if (not checked.valid or set(compat.get("environments", {})) != set(self.environments)):
            self._log("validate", {"label": label, "sha256": digest, "valid": False, "stage": "compatibility",
                                   "error_kind": checked.error_kind})
            return EvalResult(False, checked.tokens, None, checked.envs, checked.error_kind or "compile",
                              checked.message, str(compat_dir))
        fresh_dir = self._fresh_dir(code, as_final=as_final)
        existed = (fresh_dir / "result.json").exists()
        fresh = self.d.guard_compiler_signal(self.d.evaluate_cached(
            self.ev, code, self.problem, fresh_dir, **self._fresh_options(code)))
        if not existed:
            self.compiles += int(fresh.get("timing", {}).get("new_compiler_invocations", 0) or 0)
        measured = self.to_eval(fresh, fresh_dir)
        samples = [run["measurement"]["raw"] for value in fresh.get("environments", {}).values()
                   for run in value.get("runs", []) if "measurement" in run]
        valid = measured.valid and len(samples) == 3 and set(fresh.get("environments", {})) == {self.primary}
        result = EvalResult(valid=valid, tokens=fresh.get("tokens"),
                            raw_heartbeats=measured.raw_heartbeats if valid else None,
                            envs=checked.envs, error_kind=None if valid else (measured.error_kind or "compile"),
                            message="" if valid else measured.message, evidence_dir=str(fresh_dir))
        self._log("validate", {"label": label, "sha256": digest, "valid": valid, "tokens": result.tokens,
                               "raw_heartbeats": result.raw_heartbeats, "evidence": str(fresh_dir)})
        return result

    def verify_environments(self) -> dict | None:
        """Full library-byte verification, as the driver records next to final/."""
        verify = getattr(self.ev, "verify_environments", None)
        return verify(self.problem, full=True) if verify else None

    # ---- diagnostic probes ---------------------------------------------------------------
    def probe(self, probe_code: str, label: str, *, timeout_s: int = 300, options=()) -> tuple[int, str]:
        """Compile a diagnostic declaration on the primary version: (returncode, log).

        ``options`` are inserted as ``set_option <opt> in`` lines before the declaration's
        pending modifiers. Timeouts return -1. Results are cached by content.
        """
        options = [str(option) for option in options]
        digest = sha(json.dumps({"code": probe_code, "options": options}, ensure_ascii=False, sort_keys=True))
        folder = self.golf_dir / "probe" / digest[:12]
        receipt = folder / "probe.json"
        if receipt.exists() and (folder / "probe.log").exists():
            saved = _read(receipt)
            if saved.get("probe_sha256") != digest:
                raise ValueError("Golf probe directory belongs to a different probe: " + str(folder))
            return saved["returncode"], (folder / "probe.log").read_text(errors="replace")
        _set_aside(folder)
        module = self._evaluator_module()
        with self.ev._compiler_lock():
            state = self.ev._state(self.primary)
            context = self.ev._context(self.problem, self.primary)
            folder.mkdir(parents=True, exist_ok=False)
            prefix, suffix = context["prefix"], context["suffix"]
            head = prefix
            if options:
                cut = module.pending_command_start(prefix)
                head = prefix[:cut] + "\n" + "\n".join(f"set_option {option} in" for option in options) + prefix[cut:]
            record, log = self.ev._invoke(head + probe_code + suffix, state, context, folder, "probe",
                                          timeout_seconds=timeout_s)
            self.compiles += 1
        returncode = -1 if record.get("timed_out") else int(record["returncode"])
        _atomic(receipt, {"schema": PROBE_SCHEMA, "probe_sha256": digest, "label": label, "options": options,
                          "returncode": returncode, "timed_out": bool(record.get("timed_out")),
                          "declaration_start_line": head.count("\n") + 1, "seconds": record.get("seconds")})
        self._log("probe", {"label": label, "sha256": digest, "returncode": returncode})
        return returncode, log

    def probe_start_line(self, probe_code: str, options=()) -> int | None:
        options = [str(option) for option in options]
        digest = sha(json.dumps({"code": probe_code, "options": options}, ensure_ascii=False, sort_keys=True))
        receipt = self.golf_dir / "probe" / digest[:12] / "probe.json"
        return _read(receipt)["declaration_start_line"] if receipt.exists() else None

    # ---- evidence log ----------------------------------------------------------------------
    def _log(self, kind: str, value: dict) -> None:
        try:
            self.golf_dir.mkdir(parents=True, exist_ok=True)
            with (self.golf_dir / "events.jsonl").open("a") as stream:
                stream.write(json.dumps({"kind": kind, "at": time.time(), **value}, ensure_ascii=False) + "\n")
        except OSError:
            pass
