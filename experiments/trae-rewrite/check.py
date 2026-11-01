"""Check the published snapshot; does not execute Lean or a model API."""
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from lean_agent.evaluator.tokens import proof_tokens


def main():
    data = json.loads((Path(__file__).parent / "summary.json").read_text())
    archived = {}
    revision = data.get("evidence_archive_commit")
    if revision:
        blob = subprocess.check_output(
            ["git", "archive", revision, "runs/trae-rewrite-20261031"], cwd=ROOT
        )
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            for member in archive:
                if member.isfile():
                    archived[member.name] = archive.extractfile(member).read()

    def read(path):
        file = ROOT / path
        return file.read_bytes() if file.is_file() else archived[path]

    for file in data["files"]:
        content = read(file["path"])
        assert len(content) == file["bytes"], file["path"]
        assert hashlib.sha256(content).hexdigest() == file["sha256"], file["path"]

    assert len(data["problems"]) == 15
    assert len({row["name"] for row in data["problems"]}) == 15
    verified = 0
    allowed = {"propext", "Classical.choice", "Quot.sound"}
    for row in data["problems"]:
        code = read(row["candidate"]).decode()
        statement = read(f"runs/trae-rewrite-20261031/statements/{row['id']}.txt").decode()
        assert proof_tokens(code, statement) == row["candidate_tokens"], row["id"]
        summary = row["candidate_verification"]
        if not summary:
            assert not row["all_designated_versions_verified"]
            continue
        folder = str(Path(summary["path"]).parent)
        for version, result in summary["versions"].items():
            assert result["valid"]
            source = read(f"{folder}/{version}/check.lean").decode()
            assert code.strip() in source, row["id"]
            measurements = []
            for run in range(1, 4):
                log = read(f"{folder}/{version}/measure-{run}.log").decode()
                reports = re.findall(r"REFACTOR_EVAL \w+ (\{[^\n]*\})", log)
                assert len(reports) == 1, (row["id"], version, run)
                report = json.loads(reports[0])
                assert report["target"] == row["name"]
                assert set(report["axioms"]) <= allowed
                assert report["scaled"] == report["raw"] // 1000
                measurements.append(report["scaled"])
            assert statistics.median(measurements) == result["hb_k"]
        required = set(row["official_reference"]["required_versions"])
        assert row["all_designated_versions_verified"] == (required <= set(row["passed_versions"]))
        verified += 1
    print(f"OK: 15 candidate snapshots, {verified} historical final checks, {len(data['files'])} file hashes")


if __name__ == "__main__":
    main()
