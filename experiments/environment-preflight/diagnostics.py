"""Evidence-based failure diagnoses; never change evaluator validity or ranking.

The adapter is deliberately single-process. Its feedback hook must also be used
for record replay, since feedback is part of the frozen state/request history.
"""
from contextlib import contextmanager
from pathlib import Path
import re

from baseline import sha
from preflight import write


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
    observations, refs, excerpts = [], [], []
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
    return diagnosis(stage, kind, reason, evidence=refs, original_error=original,
                     excerpt="\n".join(excerpts))


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


@contextmanager
def feedback_adapter(harness, root, recorder=None):
    """Augment deterministic feedback only; all upstream state transitions remain."""
    original = harness.advance
    original_parse = harness.parse_proof
    original_canonical = harness.canonical
    root = Path(root)

    def canonical(value):
        # Preserve even an invalid Unicode response as lossless JSON escapes,
        # before parse_proof rejects it. Ordinary serialized bytes are unchanged.
        return original_canonical(value).encode("utf-8", errors="backslashreplace").decode("utf-8")

    def parse_proof(raw, problem, limit):
        content = harness.models.receipt(raw)["content"]
        if isinstance(content, str) and len(content) <= limit * 2:
            validate_response_text(content)
        try:
            code = original_parse(raw, problem, limit)
        except RecursionError as exc:
            raise ValueError("Model JSON exceeds parser nesting capacity") from exc
        try:
            code.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Proof contains invalid Unicode") from exc
        return code

    def advance(state, raw, code, result, rejection, baseline, config, run_directory):
        next_state = original(state, raw, code, result, rejection, baseline, config, run_directory)
        step = f"{next_state['step']:03}"
        folder = root / "harness/steps" / step
        report = response(raw, rejection, folder / "response.json", root)
        if report is None and result is not None:
            report = evaluation(result, folder / "evaluation", root, "candidate")
        if report and report["kind"]:
            # Keep the original status for the pinned main stopping/replay rules.
            # Full errors and logs stay in result.json and the sidecar diagnosis.
            feedback = next_state["latest"]["feedback"]
            feedback["diagnosis"] = {key: report[key] for key in ("kind", "reason", "stage")}
            excerpt = report["excerpt"].replace(run_directory, "<RUN>")
            limit = config["limits"]["max_feedback_characters"]
            guidance = report["guidance"]
            available = max(0, limit - len(guidance) - 1)
            feedback["details"] = (guidance + "\n" + (excerpt[-available:] if available else ""))[:limit]
            if recorder and report["stage"] == "model":
                recorder.save("model-" + step, report)
        return next_state

    harness.advance = advance
    harness.parse_proof = parse_proof
    harness.canonical = canonical
    try:
        yield
    finally:
        harness.advance = original
        harness.parse_proof = original_parse
        harness.canonical = original_canonical


def replay(harness, root):
    root = Path(root)
    if (root / "result.json").exists():
        result = harness.read(root / "result.json")
        if result["status"] not in ("completed", "stopped"):
            raise ValueError("Incomplete experiment: " + result["status"] + " at " + result.get("stage", "unknown"))
    with feedback_adapter(harness, root):
        return harness.replay(root / "harness")
