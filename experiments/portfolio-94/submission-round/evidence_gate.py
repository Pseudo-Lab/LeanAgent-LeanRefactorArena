"""Derive successful pins from the specific saved evidence used by this export.

Read-only: no Lean, subprocesses, imports of evaluators, or evidence promotion.
Archived embedded axiom checks retain their original evidence tier.
"""
import hashlib
import json
import re
from pathlib import Path


ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path, expected_hash=None):
    path = Path(path)
    if expected_hash is not None:
        assert _sha(path) == expected_hash, (str(path), "receipt changed")
    return json.loads(path.read_text())


def _pin(value):
    assert isinstance(value, str) and value, (value, "missing pin")
    return "v" + value.removeprefix("v")


def _candidate(row, expected):
    hashes = [row[k] for k in
              ("code_sha256", "candidate_sha256", "declaration_sha256") if k in row]
    assert hashes and all(h == expected for h in hashes), "candidate SHA mismatch"


def _receipt(path, expected, code, receipt_hash=None):
    """Fresh-style receipts: actual successful Check/Audit plus file integrity."""
    row = _read(path, receipt_hash)
    if "result" in row and "selected" in row:
        # P07's first checkpoint wraps the actual frozen receipt.
        assert _sha(row["selected"]) == expected
        row = row["result"]
    assert row.get("valid") is True, (str(path), "unsuccessful receipt")
    _candidate(row, expected)
    assert isinstance(row.get("axioms"), list)
    assert set(row["axioms"]) <= ALLOWED_AXIOMS
    stages = []
    for job in row["jobs"]:
        assert job["returncode"] == 0 and not job.get("timed_out", False)
        name = job.get("name", job.get("label"))
        assert name and name not in stages
        stages.append(name)
        source = Path(job["command"][-1])
        log = source.with_suffix(".log")
        assert _sha(source) == job.get("source_sha256", job.get("file_sha256"))
        assert _sha(log) == job["log_sha256"]
        if name == "Check" or name.startswith("Measure"):
            assert source.read_text().count(code.strip()) == 1, "proof not in saved source"
    assert "Check" in stages and "Audit" in stages
    return row


def _receipt_pin(row):
    direct = row.get("lean_pin") or row.get("pin")
    fingerprint = row.get("fingerprint", {})
    from_fingerprint = fingerprint.get("lean_pin") or fingerprint.get("pin")
    if direct or from_fingerprint:
        if direct and from_fingerprint:
            assert _pin(direct) == _pin(from_fingerprint)
        return _pin(direct or from_fingerprint)
    # Frozen search receipts point to run/evaluations/label via folder.
    environment = _read(Path(row["folder"]).parents[1] / "environment.json")
    assert environment["identity_sha256"] == row["environment_identity"]
    if "lean_pin" in environment:
        return _pin(environment["lean_pin"])
    # P12's older frozen fingerprint binds the restoration manifest by hash.
    restored = _read(environment["environment_manifest_path"],
                     environment["environment_manifest_sha256"])
    assert restored["status"] == "READY"
    assert restored["lean"] == environment["compiler_path"]
    return _pin(restored["lean_pin"])


def _pointer(value, pointer):
    for key in pointer.split("/")[1:]:
        key = key.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _historical_pin(row):
    match = re.search(r"Lean \(version ([^,\s]+)", row["fingerprint"]["version"])
    assert match, "missing archived compiler version"
    return _pin(match[1])


def _archival(n, archive, expected):
    entries = [r for r in archive["entries"] if r["id"] == n]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["proof_sha256"] == expected
    assert entry["all_required_versions_have_matching_success_evidence"] is True
    pins = []
    for p in entry["pins"]:
        for key in ("check_passed", "axioms_allowed", "candidate_sha256_matches", "tokens_match"):
            assert p[key] is True, (n, p["version"], key)
        # P03 explicitly records a null historical git fingerprint, not a failed revision check.
        assert p["source_revision_matches"] is True or (
            n == 3 and p["source_revision_matches"] is None and p.get("source_revision_evidence"))
        saved = _read(p["receipt"], p["receipt_sha256"])
        if n in (13, 15):
            version_record = _pointer(saved, p["json_pointer"].rsplit("/candidates/", 1)[0])
            assert _historical_pin(version_record) == _pin(p["version"])
            assert version_record["fingerprint"]["git"]["head"] == entry["required_revisions"][p["version"]]
            candidate = _pointer(saved, p["json_pointer"])
            assert candidate["sha256"] == expected
            assert candidate["result"]["valid"] is True
            for result in candidate["result"]["environments"].values():
                assert result["valid"] is True
                assert any(j["source"] == "check.lean" for j in result["runs"])
                for job in result["runs"]:
                    assert job["returncode"] == 0 and not job.get("timed_out", False)
                    if "measurement" in job:
                        assert set(job["measurement"]["axioms"]) <= ALLOWED_AXIOMS
        else:
            assert saved["valid"] is True
            _candidate(saved, expected)
            assert _historical_pin(saved) == _pin(p["version"])
            if n != 3:
                assert saved["fingerprint"]["git"]["head"] == entry["required_revisions"][p["version"]]
            if n == 14:
                plain = p["plain_check"]
                check = _read(plain["receipt"], plain["receipt_sha256"])
                assert check["returncode"] == 0 and not check.get("timed_out", False)
                assert _sha(check["source"]) == check["source_sha256"]
        pins.append(_pin(p["version"]))
    assert set(pins) == set(entry["required_versions"])
    return pins


def verified_pins(n, selected, expected_sha):
    """Return evidence-derived pins; never consult selected['verified_pins']."""
    assert 1 <= n <= 15
    assert _sha(selected["source"]) == expected_sha
    code = Path(selected["source"]).read_text()
    documents = [(Path(p), _read(p)) for p in selected.get("evidence", [])]
    if n == 9 and not documents:
        return []
    assert documents, (n, "no evidence")

    # Newly certified small-runner candidates supersede archival selections.
    if all("id" in row and "candidate_sha256" in row and "jobs" in row
           for _, row in documents):
        pins = []
        for path, row in documents:
            assert row["id"] == n
            checked = _receipt(path, expected_sha, code)
            pins.append(_receipt_pin(checked))
    elif n in (1, 2, 3, 13, 14, 15):
        assert len(documents) == 1 and "entries" in documents[0][1]
        pins = _archival(n, documents[0][1], expected_sha)
    elif n in (5, 6):
        assert len(documents) == 2
        results = [(p, r) for p, r in documents if "jobs" in r and "code_sha256" in r]
        audits = [r for _, r in documents if "receipt_sha256" in r and "passed" in r]
        assert len(results) == len(audits) == 1
        path, _ = results[0]
        audit = audits[0]
        assert audit["passed"] is True and audit["candidate_sha256"] == expected_sha
        assert Path(audit["receipt"]).resolve() == path.resolve()
        row = _receipt(path, expected_sha, code, audit["receipt_sha256"])
        assert row["environment_identity"] == audit["environment_identity"]
        pins = [_receipt_pin(row)]
    elif n in (7, 8):
        assert len(documents) == 1
        entry = documents[0][1][f"P{n:02}"]
        assert entry["sha256"] == expected_sha and entry["candidate_hash_ok"] is True
        pins = []
        for p in entry["pins"]:
            assert p["saved_integrity_ok"] is True
            row = _receipt(p["receipt"], expected_sha, code)
            if n == 7:
                assert _receipt_pin(row) == _pin(p["pin"])
                audit = _read(p["audit"])
                assert audit["passed"] is True and audit["environment_identity"] == row["environment_identity"]
            pins.append(_pin(p["pin"]))
    elif n in (9, 10, 11, 12):
        assert len(documents) == 1
        manifest = documents[0][1]
        _candidate(manifest, expected_sha)
        pins = []
        if n == 10:
            row = _receipt(manifest["primary_receipt"], expected_sha, code,
                           manifest["primary_receipt_sha256"])
            assert _receipt_pin(row) == _pin(manifest["primary_pin"])
            pins.append(_receipt_pin(row))
            for pin, p in manifest["additional_pin_compatibility"].items():
                assert p["valid"] is True
                row = _receipt(p["receipt"], expected_sha, code, p["receipt_sha256"])
                assert _receipt_pin(row) == _pin(pin)
                pins.append(_receipt_pin(row))
        elif n in (9, 11):
            for p in manifest["required_pin_evidence"]:
                assert p["candidate_sha256"] == expected_sha
                receipt_hash = p.get("receipt_sha256")
                if receipt_hash is None:
                    audit = manifest["selected_receipt_audit"]
                    assert audit["passed"] is True and audit["candidate_sha256"] == expected_sha
                    assert Path(audit["receipt"]).resolve() == Path(p["receipt"]).resolve()
                    receipt_hash = audit["receipt_sha256"]
                row = _receipt(p["receipt"], expected_sha, code, receipt_hash)
                assert _receipt_pin(row) == _pin(p["pin"])
                pins.append(_receipt_pin(row))
        else:
            assert manifest["status"] == "VERIFIED_ALL_3_REQUIRED_PINS"
            for p in manifest["pins"]:
                assert p["code_sha256"] == expected_sha
                row = _receipt(Path(p["evidence"]) / "result.json", expected_sha, code)
                assert _receipt_pin(row) == _pin(p["pin"])
                pins.append(_receipt_pin(row))
    else:
        raise AssertionError((n, "unsupported evidence format"))
    assert len(pins) == len(set(pins)), "duplicate pin evidence"
    return pins
