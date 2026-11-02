"""Evidence-based diagnoses shared by execution and deterministic replay."""
from pathlib import Path
import re

from .artifacts import sha
from .artifacts import write


GUIDANCE = {
    "api": "No usable API response. Stop; do not automatically retry. Outcome and billing may be unknown.",
    "response": 'Return exactly one JSON object with a nonempty "proof" string containing a tactic proof.',
    "proof": "Correct the rejected proof using the Lean diagnostic below; preserve the theorem statement.",
    "measurement": "Inspect the measurement pipeline. This is not evidence that the proof is incorrect.",
    "environment": "Inspect the prepared compiler/import environment before generating another proof.",
    "timeout": "Local process protection fired; proof correctness and competition outcome are undetermined.",
    "unknown": "Cause is undetermined. Inspect the saved evidence before deciding what to change.",
}

# Bound parsing independently of the Python runtime's recursion limit. Brackets
# inside JSON strings (including escaped quotes) do not contribute to depth.
MAX_RESPONSE_JSON_DEPTH = 128


def validate_response_text(content):
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Model content contains invalid Unicode") from exc
    depth, quoted, escaped = 0, False, False
    for char in content:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_RESPONSE_JSON_DEPTH:
                raise ValueError("Model JSON exceeds maximum nesting depth")
        elif char in "]}":
            depth -= 1


def diagnosis(stage, kind, reason, *, evidence=(), original_error=None, excerpt=""):
    return {"schema_version": 1, "stage": stage, "kind": kind, "reason": reason,
            "evidence": list(evidence), "original_error": original_error,
            "excerpt": excerpt, "guidance": GUIDANCE.get(kind, ""),
            "automatic_retry": False}


def evidence(root, path):
    path, root = Path(path), Path(root).resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Diagnostic evidence escapes the run directory")
    path = path.resolve()
    return {"path": str(path.relative_to(root)), "sha256": sha(path.read_bytes())}


def import_failure(text):
    # Recognize a narrow compiler diagnostic, not arbitrary mentions of imports.
    return bool(re.search(r"(?m)(?:^|: )error: (?:unknown module prefix '[^'\n]+'|"
                          r"object file '[^'\n]+' of module [^\n]+ does not exist)", text))


def measuring_after_check(records):
    return bool(records and str(records[-1].get("source", "")).startswith("measure-")
                and any(r.get("source") == "check.lean" and r.get("returncode") == 0
                        and not r.get("timed_out") for r in records))


REPAIR_HINTS = {
    "unknown_tactic": "Replace the unavailable tactic using tactics known to work in the pinned imports; do not assume mathlib automation or add imports.",
    "no_goals": "A preceding tactic already closed this branch. Scope subsequent tactics to remaining goals with explicit cases or <;>; do not append unconditional intro/cases after a closing tactic.",
    "no_progress": "The simplifier made no progress. Inspect the remaining goal and use an explicit proof step; guard optional cleanup only when unchanged goals are handled elsewhere.",
    "type_mismatch": "Use the reported expected and actual types. For dependent applications, apply/refine can expose binders that a direct term application guessed incorrectly.",
    "unsolved_goals": "Solve the displayed remaining cases explicitly using their local hypotheses; do not assume the preceding automation closed them.",
}


def lean_issues(text, source="", code=""):
    """Parse compiler evidence; locate errors in the candidate, keeping warnings separate."""
    header = re.compile(r"(?m)^(.+?):(\d+):(\d+): (error|warning|info): ([^\n]*)")
    matches = list(header.finditer(text))
    start = source.find(code) if code and source.count(code) == 1 else -1
    first = source[:start].count("\n") + 1 if start >= 0 else None
    code_lines = code.splitlines()
    issues, warnings = [], 0
    for index, match in enumerate(matches):
        if match[4] != "error":
            warnings += match[4] == "warning"
            continue
        message = match[5]
        detail = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()
        line = int(match[2]) - first + 1 if first is not None else None
        if line is not None and not 1 <= line <= len(code_lines):
            line = None
        kind = ("unknown_tactic" if message.startswith("unknown tactic") else
                "no_goals" if "No goals to be solved" in message else
                "no_progress" if "made no progress" in message else
                "type_mismatch" if "type mismatch" in message.lower() else
                "unsolved_goals" if message.startswith("unsolved goals") else "lean_error")
        issues.append({"kind": kind, "message": message[:320], "detail": detail[-1200:],
            "source_line": int(match[2]), "column": int(match[3]), "candidate_line": line,
            "candidate_text": code_lines[line - 1][:240] if line is not None else None})
    unique = {}
    for issue in issues:
        key = (issue["source_line"], issue["column"], issue["kind"], issue["message"], issue["detail"])
        if key not in unique:
            unique[key] = {**issue, "occurrences": 0}
        unique[key]["occurrences"] += 1
    return list(unique.values()), warnings


def evaluation(result, folder, root, stage):
    """Classify only what the invocation order and recorded compiler evidence show."""
    rows = result.get("environments", {})
    original = {"error": result.get("error"),
                "environments": {key: row.get("error") for key, row in rows.items()}}
    if result.get("valid"):
        return diagnosis(stage, None, "verified")
    if (result.get("error") or {}).get("kind") == "validation":
        return diagnosis(stage, "response", "declaration_contract_rejected", original_error=original,
                         excerpt=result["error"].get("message", ""))
    observations, refs, excerpts, issues, warnings = [], [], [], [], 0
    for label, row in rows.items():
        if row.get("valid"):
            continue
        runs = row.get("runs", [])
        last = runs[-1] if runs else {}
        text = ""
        for record in runs:
            for key in ("source", "log"):
                if key not in record:
                    continue
                path = folder / label / record[key]
                ref = evidence(root, path)
                if ref["sha256"] != record.get(key + "_sha256"):
                    raise ValueError("Diagnostic evidence hash differs: " + ref["path"])
                refs.append(ref)
                if record is last and key == "log":
                    text = path.read_text(encoding="utf-8")
        error = row.get("error") or {}
        excerpts.append(text or error.get("message", ""))
        if last.get("source"):
            source = (folder / label / last["source"]).read_text()
            filename = "baseline.lean" if folder.name == "baseline" else "selected.lean" if folder.name == "final" else "candidate.lean"
            code_path = folder.parent / filename
            code = code_path.read_text() if code_path.is_file() else ""
            parsed, count = lean_issues(text, source, code)
            issues.extend(parsed)
            warnings += count
        if last.get("timed_out") or error.get("kind") == "timeout":
            item = ("timeout", "local_process_timeout")
        elif type(last.get("returncode")) is int and last["returncode"] < 0:
            item = ("unknown", "compiler_terminated_by_signal")
        elif import_failure(text):
            item = ("environment", "missing_import")
        elif error.get("kind") == "axioms":
            item = ("proof", "disallowed_axioms")
        elif measuring_after_check(runs):
            item = ("measurement", "measurement_failed_after_check")
        elif (last.get("source") == "check.lean" and last.get("returncode") == 1
              and re.search(r"(?m)(?:^|: )error:", text)):
            item = ("proof", "lean_check_rejected")
        else:
            item = ("unknown", "insufficient_compiler_evidence")
        observations.append(item)
    kind, reason = observations[0] if observations and len(set(observations)) == 1 else ("unknown", "ambiguous_failure")
    report = diagnosis(stage, kind, reason, evidence=refs, original_error=original, excerpt="\n".join(excerpts))
    if issues:
        report.update(issues=issues, warning_count=warnings)
    return report


def response(raw, rejection, response_path, root):
    raw = raw if isinstance(raw, dict) else {}
    transport, status = raw.get("transport_error"), raw.get("http_status")
    if transport or type(status) is int and status >= 400:
        # ValueError here means the adapter received an undecodable API envelope.
        kind = "response" if transport in ("ValueError", "JSONDecodeError") and status is None else "api"
        reason = ("http_error" if type(status) is int and status >= 400 else
                  "api_response_timeout" if transport in ("TimeoutError", "timeout") else
                  "invalid_api_envelope" if kind == "response" else "transport_error")
        result = diagnosis("model", kind, reason, original_error={"transport_error": transport, "http_status": status})
        result.update(response_received=True if status is not None or kind == "response" else None,
                      usable_model_response=False, call_outcome="unknown", billing="unknown")
    elif rejection:
        result = diagnosis("model", "response", "model_content_rejected", excerpt=rejection)
    else:
        return None
    result["evidence"] = [evidence(root, response_path)]
    return result


def preflight_diagnosis(report, root):
    error = report.get("error")
    if not error:
        return None
    refs, text = [], []
    for record in report["commands"]:
        ref = evidence(root, root / record["log"])
        if ref["sha256"] != record["log_sha256"]:
            raise ValueError("Preflight diagnostic log hash differs")
        refs.append(ref)
        if record["stage"] == report["stage"]:
            text.append((root / record["log"]).read_text())
    kind, reason = error["kind"], error["reason"]
    if kind == "unknown" and import_failure("\n".join(text)):
        kind, reason = "environment", "missing_import"
    return diagnosis(report["stage"], kind, reason, evidence=refs,
                     original_error=error, excerpt="\n".join(text))


class Recorder:
    def __init__(self, root):
        self.root = Path(root)
        self.records = []

    def save(self, name, value):
        path = self.root / "diagnostics" / (name + ".json")
        write(path, value)
        self.records.append({"path": str(path.relative_to(self.root)), "stage": value["stage"],
                             "kind": value["kind"], "reason": value["reason"]})

    def evaluated(self, result, folder):
        if folder.name in ("baseline", "final"):
            stage, name = folder.name, folder.name
        else:
            stage, name = "candidate", "candidate-" + folder.parent.name
        self.save(name, evaluation(result, folder, self.root, stage))


def step(raw, rejection, result, folder, root):
    report = response(raw, rejection, folder / "response.json", root)
    if report is None and result is not None:
        report = evaluation(result, folder / "evaluation", root, "candidate")
    return report


def enrich(feedback, report, limit, run_directory):
    if report and report["kind"]:
        feedback["diagnosis"] = {key: report[key] for key in ("kind", "reason", "stage")}
        excerpt = report["excerpt"].replace(run_directory, "<RUN>")
        guidance = report["guidance"]
        available = max(0, limit - len(guidance) - 1)
        feedback["details"] = (guidance + "\n" + (excerpt[-available:] if available else ""))[:limit]
        if report.get("issues"):
            # The complete compiler log stays in hashed evidence. Keep the first
            # error even when a long trailing goal state truncates the excerpt.
            feedback["issues"] = report["issues"][:8]
            feedback["issue_count"] = sum(row.get("occurrences", 1) for row in report["issues"])
            feedback["warning_count"] = report.get("warning_count", 0)
    return feedback
