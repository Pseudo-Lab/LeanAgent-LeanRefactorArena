#!/usr/bin/env python3
"""No-API baseline/compatibility cache before freezing paid-batch inputs."""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

from driver import REPO, atomic, evaluator, folder, require_policy
from lean_agent import artifacts as a


def measurement_core(path):
    tree = ast.parse(Path(path).read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "FinalEvaluator":
            node.body = [child for child in node.body if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                         or child.name not in {"source_context", "verify_environments", "preflight"}]
    return a.sha(ast.dump(tree, include_attributes=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rows", type=int, nargs="+", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    require_policy(root)
    rows = args.rows
    root.mkdir(parents=True, exist_ok=True)
    files = [Path(__file__).with_name("evaluator.py"), Path(__file__).with_name("policy.py"),
             Path(__file__).with_name("evaluation_cache.py"),
             REPO / "experiments/proof-analyze/proof_tokens.py", REPO / "src/lean_agent/evaluator/lean.py"]
    hashes = {str(path): a.sha(path.read_bytes()) for path in files if path.exists()}
    initial_core = measurement_core(files[0])
    code = root / "offline-cache-code"
    code.mkdir(exist_ok=True)
    for path, digest in hashes.items():
        destination = code / (Path(path).stem + "-" + digest + ".py")
        if not destination.exists():
            shutil.copyfile(path, destination)
    manifest_path = root / f"offline-cache-manifest-{min(rows):03}-{max(rows):03}.json"
    manifest = a.read(manifest_path) if manifest_path.exists() else {"model_api_calls": 0, "rows": {},
                "created_at": datetime.now(timezone.utc).isoformat()}
    manifest.setdefault("cohorts", []).append({"code_sha256": hashes, "measurement_core_sha256": initial_core,
                                               "started_at": datetime.now(timezone.utc).isoformat()})
    manifest["code_sha256"] = hashes
    ev = evaluator(root)
    for row in rows:
        actual_hashes = {str(path): a.sha(path.read_bytes()) for path in files if path.exists()}
        if measurement_core(files[0]) != initial_core or any(actual_hashes[path] != digest for path, digest in hashes.items()
                                                            if path != str(files[0])):
            raise ValueError("Measurement core/policy/tokenizer changed during cached baseline cohort")
        for path, digest in actual_hashes.items():
            destination = code / (Path(path).stem + "-" + digest + ".py")
            if not destination.exists():
                shutil.copyfile(path, destination)
        started = time.monotonic()
        problem = ev.load_problem(row)
        output = folder(root, row)
        try:
            results = {}
            for name, runs, all_versions in (("baseline", 3, False), ("reference-compatibility", 1, True)):
                destination = output / name
                result_path = destination / "result.json"
                if result_path.exists():
                    result = a.read(result_path)
                else:
                    if destination.exists():
                        archived = destination.with_name(destination.name + "-incomplete-" + str(time.time_ns()))
                        destination.rename(archived)
                    result = ev.evaluate(problem["reference"], problem, destination,
                                         repetitions=runs, all_versions=all_versions, trusted_reference=True)
                results[name] = {"valid": result["valid"], "result_sha256": a.sha(result_path.read_bytes()),
                                 "path": str(result_path)}
                if not result["valid"]:
                    errors = {key: value.get("error") for key, value in result.get("environments", {}).items() if not value.get("valid")}
                    print(json.dumps({"row": row, "stage": name, "valid": False, "errors": errors}, ensure_ascii=False), flush=True)
                    break
            ready = len(results) == 2 and all(value["valid"] for value in results.values())
            manifest["rows"][str(row)] = {"ready": ready, "results": results, "seconds": time.monotonic() - started}
        except Exception as exc:
            manifest["rows"][str(row)] = {"ready": False, "exception_type": type(exc).__name__, "message": str(exc)[:2000]}
        manifest["rows"][str(row)].update(loaded_code_sha256=hashes, filesystem_code_sha256=actual_hashes,
                                           measurement_core_sha256=initial_core)
        atomic(manifest_path, manifest)
        print(json.dumps({"row": row, **manifest["rows"][str(row)]}, ensure_ascii=False), flush=True)
    failed = [row for row, value in manifest["rows"].items() if not value["ready"]]
    print(json.dumps({"offline_cache_finished": True, "rows": rows, "failed": failed, "model_api_calls": 0}), flush=True)


if __name__ == "__main__":
    main()
