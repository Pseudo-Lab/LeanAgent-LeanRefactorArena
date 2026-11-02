"""Resolve canonical benchmark statements in each immutable source revision."""
from pathlib import Path
import json
import re
from bootstrap import REPO, ROOT, plan, dataset, command, write, digest


def resolve(env, rows):
    project = REPO / env["project"]
    if env["source"] == "putnambench":
        return [{"row": i, "name": rows[i-1]["name"], "kind": "standalone_header", "module": None}
                for i in env["problem_rows"]]
    files = command(["git", "-C", project, "ls-files", "*.lean"]).splitlines()
    texts = {}
    resolved = []
    for index in env["problem_rows"]:
        row = rows[index-1]
        statement = row["statement"]
        pattern = re.compile(r"\s+".join(re.escape(word) for word in statement.strip().split()))
        proof_pattern = re.compile(r"\s+".join(re.escape(word) for word in row["src"].strip().split()))
        preferred = row["file_path"]
        candidates = []
        order = ([preferred] if preferred in files else []) + [f for f in files if f != preferred]
        for name in order:
            if name not in texts:
                texts[name] = (project / name).read_text()
            text = texts[name]
            if row["src"] in text:
                start = text.index(row["src"])
                stop = start + len(row["src"])
                kind = "exact_src"
            elif (proof_match := proof_pattern.search(text)) is not None:
                start, stop = proof_match.span()
                kind = "whitespace_src"
            elif statement in text:
                start = text.index(statement)
                stop = None
                kind = "exact_statement"
            else:
                match = pattern.search(text)
                if not match:
                    continue
                start = match.start()
                stop = None
                kind = "whitespace_statement"
            candidates.append({"row": index, "name": row["name"], "file_path": name,
                               "module": name.removesuffix(".lean").replace("/", "."),
                               "kind": kind, "statement_start_char": start, "declaration_end_char": stop,
                               "source_sha256": digest(project / name)})
            if name == preferred:
                break
        if len(candidates) != 1:
            raise ValueError(f"Cannot uniquely resolve {env['id']} row {index}: {candidates}")
        resolved.append(candidates[0])
    return resolved


def main():
    rows = dataset()
    results = {}
    failures = []
    for env in plan()["environments"]:
        try:
            results[env["id"]] = resolve(env, rows)
            print("RESOLVED", env["id"], len(results[env["id"]]), flush=True)
        except Exception as error:
            failures.append({"id": env["id"], "error": str(error)})
            print("UNRESOLVED", env["id"], str(error)[:500], flush=True)
    write(ROOT / "locations.json", {"environments": results, "failures": failures})
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
