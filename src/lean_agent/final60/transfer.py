"""Transfer repair: deprecated-alias renames between a row's listed toolchains (no API call).

Finding (rehearsal 2026-11-04, partial-compat analysis): a candidate that compiles on the
first-listed (newest) toolchain can fail an older listed toolchain only because the pinned
library renamed a lemma and kept ``@[deprecated] alias OLD := NEW`` for the old name. The
old name exists on every listed toolchain, so swapping NEW for OLD is token-neutral and
compiles everywhere (one deprecation warning on the newest toolchain).

* ``alias_map``: NEW -> OLD for the row's environment set, read from the first-listed
  toolchain's prepared library sources (project plus its ``.lake/packages``), keeping only
  pairs whose OLD is declared in every other listed toolchain's sources and whose NEW is not
  declared in at least one of them. Built once per environment set and cached as JSON
  (``alias-maps/`` under the run dir, next to ``rows/``; ``FINAL60_ALIAS_MAP_DIR`` overrides).
* ``unknown_names`` / ``plan``: the trigger. Every unknown-identifier/unknown-constant error
  in the failing toolchain's saved check log must name a key of the map; the primary
  toolchain must have passed.
* ``substitute``: identifier-level replacement in the proof body only (never inside comments
  or strings; the statement stays byte-identical), with an edit list for provenance.
* ``repair``: builds the candidate (``repair:<parent label>``, origin ``golf``, parent sha),
  runs the static rules and the official intake check, validates it exactly like any other
  finalist (every listed toolchain, then the fresh 3x primary measurement) and persists it
  like a golf winner (``golf/winners.json``, ``golf/winners/<sha12>.lean``).

Rows whose primary checkout sets ``warningAsError`` (Strata) and rows under a warning gate
(``select.warning_gate_mode`` != ``off``) are never repaired: the deprecation warning would
break their build.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time

from .contracts import Candidate, EvalResult
from . import rewrites as rw, rules

MAP_SCHEMA = "final60-alias-map-v1"
MAX_REPAIRS = 2            # repair validations per selection call
MAX_REPAIRS_POSTHOC = 3    # repair validations per row in ``regolf --transfer-repair``
REGISTRY = "configs/final-environments.local.json"
PACKAGES = ".lake/packages"

_KEYWORDS = "theorem|lemma|def|abbrev|instance|alias|structure|class|inductive|opaque|axiom"
_MODS = r"(?:(?:private|protected|noncomputable|nonrec|unsafe|partial|scoped|public|irreducible)\s+)*"
_DECL = re.compile(r"^\s*(?:@\[(?P<attr>[^\]]*)\]\s*)?(?P<mods>" + _MODS + r")(?P<kw>" + _KEYWORDS +
                   r")\s+(?P<name>[^\s:(\[{⟨]+)(?P<rest>.*)$")
_ATTR_ONLY = re.compile(r"^\s*@\[(?P<attr>[^\]]*)\]\s*$")
_ALIAS_IFF = re.compile(r"^\s*alias\s*⟨\s*(?P<a>[^,\s]+)\s*,\s*(?P<b>[^⟩\s]+)\s*⟩")
_ALIAS_TARGET = re.compile(r"^\s*:=\s*(?P<target>[^\s]+)\s*$")
_DEPRECATED = re.compile(r"(?:^|,)\s*deprecated\b\s*(?P<target>[^\s,(\]\"]+)?")
_NAMESPACE = re.compile(r"^\s*namespace\s+(?P<name>[^\s]+)\s*$")
_SECTION = re.compile(r"^\s*(?:noncomputable\s+)?section\b(?:\s+(?P<name>[^\s]+))?\s*$")
_END = re.compile(r"^\s*end\b(?:\s+(?P<name>[^\s]+))?\s*$")
_IDENT = re.compile(r"^(?:[^\W\d]|_)[\w'!?]*(?:\.(?:[^\W\d]|_)[\w'!?]*)*$")
_UNKNOWN = re.compile(r"(?i)\bunknown\s+(?:identifier|constant)\s*[`'‘]?(?P<name>[^`'’\s,:]+)")
_TOKEN = re.compile(r"(?<![\w.'!?])(?:[^\W\d]|_)[\w'!?]*(?:\.(?:[^\W\d]|_)[\w'!?]*)*")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---- library sources ----------------------------------------------------------------------------
def registry(repo: Path) -> dict:
    path = Path(repo) / REGISTRY
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get("environments", {})


def project_dir(repo: Path, env: str) -> Path | None:
    entry = registry(repo).get(env)
    if not entry or not entry.get("project"):
        return None
    return (Path(repo) / entry["project"]).resolve()


def library_roots(project: Path) -> list[Path]:
    """The project checkout plus each of its lake packages (symlinks resolved, deduplicated)."""
    roots, seen = [], set()
    packages = project / PACKAGES
    for path in [project] + (sorted(packages.iterdir()) if packages.is_dir() else []):
        try:
            real = path.resolve()
        except OSError:
            continue
        if real.is_dir() and str(real) not in seen:
            seen.add(str(real))
            roots.append(real)
    return roots


def lean_files(project: Path):
    for root in library_roots(project):
        for folder, names, files in os.walk(root):
            names[:] = sorted(name for name in names if name != ".lake" and not name.startswith("."))
            for name in sorted(files):
                if name.endswith(".lean"):
                    yield Path(folder) / name


def warning_as_error(repo: Path, env: str) -> bool:
    """Whether the environment's checkout sets ``warningAsError`` (lakefile.toml/lakefile.lean)."""
    project = project_dir(repo, env)
    if project is None:
        return False
    for name in ("lakefile.toml", "lakefile.lean"):
        path = project / name
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if re.search(r"(?mi)^\s*warningAsError\s*=\s*true|warningAsError\s*,\s*true|`warningAsError\s*,\s*true", text):
            return True
    return False


# ---- declaration scanning -----------------------------------------------------------------------
def qualify(namespace: str, name: str) -> str:
    if name.startswith("_root_."):
        return name[len("_root_."):]
    return namespace + "." + name if namespace else name


def candidates(namespace: str, name: str) -> list[str]:
    """Full names a term-level reference may resolve to, most specific namespace first."""
    if name.startswith("_root_."):
        return [name[len("_root_."):]]
    chain = namespace.split(".") if namespace else []
    return [".".join(chain[:i]) + "." + name for i in range(len(chain), 0, -1)] + [name]


def scan_file(text: str):
    """Yield (namespace, attr, keyword, name, rest) for each declaration of one Lean file."""
    stack, depth, pending = [], 0, []
    for raw in text.splitlines():
        line = raw
        if depth > 0:
            # Inside a block comment: only the text after the closing ``-/`` (if any) counts.
            depth = max(0, depth + line.count("/-") - line.count("-/"))
            if depth > 0:
                continue
            line = line[line.rfind("-/") + 2:]
            if not line.strip():
                continue
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        cut = line.find("--")
        if cut >= 0 and "/-" not in line[:cut]:
            line = line[:cut]
        opened, closed = line.count("/-"), line.count("-/")
        if opened > closed:
            depth = opened - closed
            line = line[:line.find("/-")]
            if not line.strip():
                continue
        namespace = ".".join(item for item in stack if item)
        match = _NAMESPACE.match(line)
        if match:
            stack.append(match["name"])
            pending = []
            continue
        if _SECTION.match(line):
            stack.append("")
            pending = []
            continue
        if _END.match(line):
            if stack:
                stack.pop()
            pending = []
            continue
        match = _ATTR_ONLY.match(line)
        if match:
            pending.append(match["attr"])
            continue
        match = _ALIAS_IFF.match(line)
        if match:
            for name in (match["a"], match["b"]):
                yield namespace, "", "alias", name, ""
            pending = []
            continue
        match = _DECL.match(line)
        if match:
            attrs = ", ".join(pending + ([match["attr"]] if match["attr"] else []))
            yield namespace, attrs, match["kw"], match["name"], match["rest"]
        if line.strip():
            pending = []


def deprecated_pair(namespace: str, attr: str, keyword: str, name: str, rest: str):
    """(OLD full name, NEW candidates) for a deprecated alias/declaration, else None."""
    match = _DEPRECATED.search(attr or "")
    if not match:
        return None
    old = qualify(namespace, name)
    target = match["target"]
    if keyword == "alias":
        value = _ALIAS_TARGET.match(rest or "")
        if value and _IDENT.match(value["target"]):
            return old, candidates(namespace, value["target"])
        return None
    if target and _IDENT.match(target) and keyword in ("theorem", "lemma", "def", "abbrev"):
        return old, candidates(namespace, target)
    return None


def scan_project(project: Path) -> tuple[set[str], list[tuple[str, list[str], str]]]:
    """(declared full names, deprecated pairs) over the project's library sources."""
    declared, pairs = set(), []
    for path in lean_files(project):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for namespace, attr, keyword, name, rest in scan_file(text):
            declared.add(qualify(namespace, name))
            pair = deprecated_pair(namespace, attr, keyword, name, rest)
            if pair:
                pairs.append((pair[0], pair[1], str(path)))
    return declared, pairs


# ---- the alias map ------------------------------------------------------------------------------
def map_identity(repo: Path, environments: list[str]) -> str:
    items = []
    for env in environments:
        entry = registry(repo).get(env) or {}
        items.append([env, entry.get("project"), entry.get("revision")])
    return sha(json.dumps([MAP_SCHEMA, items], sort_keys=True))[:16]


def cache_dir_for(run_root: Path) -> Path:
    override = os.environ.get("FINAL60_ALIAS_MAP_DIR")
    if override:
        return Path(override)
    root = Path(run_root).resolve()
    if root.parent.name == "rows":
        return root.parent.parent / "alias-maps"
    return root / "alias-maps"


def build_alias_map(repo: Path, environments: list[str]) -> dict:
    """NEW -> OLD for ``environments`` (first-listed = newest), with per-pair counts."""
    repo = Path(repo)
    environments = list(environments)
    started = time.time()
    primary = environments[0]
    value = {"schema": MAP_SCHEMA, "environments": environments, "primary": primary, "identity": map_identity(repo, environments),
             "sources": {}, "counts": {"deprecated_pairs": 0, "kept": 0, "per_pair": {}}, "map": {}, "evidence": {}}
    project = project_dir(repo, primary)
    if project is None or len(environments) < 2:
        value.update(built_at=time.time(), seconds=round(time.time() - started, 3), reason="no primary sources or single toolchain")
        return value
    value["sources"][primary] = str(project)
    declared_new, pairs = scan_project(project)
    value["counts"]["deprecated_pairs"] = len(pairs)
    others = {}
    for env in environments[1:]:
        other = project_dir(repo, env)
        if other is None:
            value.update(built_at=time.time(), seconds=round(time.time() - started, 3), reason="missing sources for " + env)
            return value
        value["sources"][env] = str(other)
        others[env], _ = scan_project(other)
    per_pair = {env: {"old_exists": 0, "new_missing": 0, "kept": 0} for env in others}
    for old, news, path in pairs:
        new = next((name for name in news if name in declared_new), None)
        if new is None or new == old or new in value["map"]:
            continue
        old_everywhere = all(old in index for index in others.values())
        missing = [env for env, index in others.items() if not any(name in index for name in news)]
        for env, index in others.items():
            if old in index:
                per_pair[env]["old_exists"] += 1
            if env in missing:
                per_pair[env]["new_missing"] += 1
            if old in index and env in missing:
                per_pair[env]["kept"] += 1
        if old_everywhere and missing:
            value["map"][new] = old
            value["evidence"][new] = {"source": path, "missing_in": missing}
    value["counts"]["kept"] = len(value["map"])
    value["counts"]["per_pair"] = per_pair
    value.update(built_at=time.time(), seconds=round(time.time() - started, 3))
    return value


def load_or_build(repo: Path, environments: list[str], cache_dir: Path | None) -> dict:
    """The cached map for this environment set, built (and cached) on first use."""
    identity = map_identity(repo, environments)
    path = Path(cache_dir) / f"alias-map-{identity}.json" if cache_dir else None
    if path is not None and path.exists():
        try:
            cached = json.loads(path.read_text())
            if cached.get("schema") == MAP_SCHEMA and cached.get("identity") == identity and isinstance(cached.get("map"), dict):
                return cached
        except (OSError, ValueError):
            pass
    value = build_alias_map(repo, environments)
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + f".tmp-{os.getpid()}-{time.time_ns()}")
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
            os.replace(temporary, path)
        except OSError:
            pass
    return value


def alias_map_for(adapter, problem: dict | None = None) -> dict:
    """NEW -> OLD for the adapter's row (memoised on the adapter; ``adapter.alias_map`` overrides)."""
    given = getattr(adapter, "alias_map", None)
    if isinstance(given, dict):
        return given
    cached = getattr(adapter, "_final60_alias_map", None)
    if isinstance(cached, dict):
        return cached
    environments = list(getattr(adapter, "environments", None) or (problem or {}).get("environments") or [])
    try:
        repo = Path(getattr(adapter.d, "REPO"))
        run_root = Path(adapter.run_root)
    except AttributeError:
        return {}
    try:
        value = load_or_build(repo, environments, cache_dir_for(run_root)).get("map", {})
    except Exception:   # the map is only a proposal generator; never fail a selection over it
        value = {}
    try:
        adapter._final60_alias_map = value
    except Exception:
        pass
    return value


# ---- trigger ------------------------------------------------------------------------------------
def unknown_names(log: str) -> list[str]:
    """Names of every unknown-identifier/unknown-constant error, in order, deduplicated."""
    out = []
    for message in rw.parse_messages(log):
        if message.severity != "error":
            continue
        match = _UNKNOWN.search(message.text)
        if match:
            name = match["name"].strip("`'‘’")
            if name and name not in out:
                out.append(name)
    return out


def plan(result: EvalResult, primary: str, logs: dict, alias_map: dict) -> dict | None:
    """The repair plan for a finalist that passed the primary toolchain but failed another one.

    ``logs`` is ``adapter.version_logs(code)``: env -> (log, source). Every failing listed
    toolchain needs a saved log whose unknown-identifier/unknown-constant errors all name
    keys of ``alias_map`` (and at least one such error); otherwise None.
    """
    if result is None or result.valid or not alias_map:
        return None
    envs = dict(result.envs or {})
    if not envs.get(primary):
        return None
    failing = [env for env, ok in envs.items() if env != primary and not ok]
    if not failing:
        return None
    mapping, per_env = {}, {}
    for env in failing:
        pair = logs.get(env)
        if not pair:
            return None
        names = unknown_names(pair[0])
        if not names or any(name not in alias_map for name in names):
            return None
        per_env[env] = names
        for name in names:
            mapping[name] = alias_map[name]
    return {"envs": failing, "names": per_env, "mapping": mapping}


# ---- substitution -------------------------------------------------------------------------------
def substitute(code: str, statement: str, mapping: dict) -> tuple[str, list[dict]]:
    """Replace identifiers in the proof body (not in comments or strings); the statement is kept."""
    if not code.startswith(statement):
        raise ValueError("The theorem statement must be preserved byte-for-byte")
    body = code[len(statement):]
    masked = rw.mask_strings(rw.mask_comments(body))
    edits = []
    for match in _TOKEN.finditer(masked):
        token = match.group()
        replacement = _replacement(token, mapping)
        if replacement is None or replacement == token:
            continue
        edits.append({"start": len(statement) + match.start(), "end": len(statement) + match.end(),
                      "from": token, "to": replacement})
    if not edits:
        return code, []
    out, cursor = [], 0
    for edit in edits:
        out.append(code[cursor:edit["start"]])
        out.append(edit["to"])
        cursor = edit["end"]
    out.append(code[cursor:])
    return "".join(out), edits


def _replacement(token: str, mapping: dict) -> str | None:
    if token in mapping:
        return mapping[token]
    parts = token.split(".")
    for new, old in mapping.items():
        new_parts, old_parts = new.split("."), old.split(".")
        count = len(parts)
        if count < len(new_parts) and new_parts[-count:] == parts:
            # A suffix written under an open namespace keeps its depth when both names share the prefix.
            if len(old_parts) >= count and new_parts[:-count] == old_parts[:-count]:
                return ".".join(old_parts[-count:])
            return old
        if count > 1 and parts[-1] == new_parts[-1] and new_parts[:-1] == old_parts[:-1] and len(new_parts) > 1:
            # Dot notation on a term (``s.card_univ_sdiff``): only the last component can change.
            return ".".join(parts[:-1] + [old_parts[-1]])
    return None


# ---- repair candidates --------------------------------------------------------------------------
def repair_text(candidate: Candidate, statement: str, mapping: dict) -> tuple[str | None, list[dict], str | None]:
    """(repaired text, edits, rejection) for ``candidate``; the text is None when rejected."""
    try:
        fixed, edits = substitute(candidate.code, statement, mapping)
    except ValueError as exc:
        return None, [], str(exc)
    if not edits or fixed == candidate.code:
        return None, [], "no identifier to replace"
    rejection = rules.official_rejection(fixed)
    if rejection:
        return None, edits, "official: " + rejection
    issues = rules.check_static(fixed, statement)
    if issues:
        return None, edits, "; ".join(issues)[:300]
    return fixed, edits, None


def repair_candidate(candidate: Candidate, fixed: str) -> Candidate:
    return Candidate(fixed, sha(fixed), "golf", candidate.sha256, "repair:" + candidate.label, None)


def gate_blocks(adapter, problem: dict) -> str | None:
    """Why this row must not be repaired (warning gate on, or warningAsError in the primary checkout)."""
    from .select import warning_gate_mode
    try:
        mode = warning_gate_mode(problem)
    except ValueError:
        mode = "reject"
    if mode != "off":
        return f"warning gate {mode} ({problem.get('source')})"
    try:
        repo, primary = Path(adapter.d.REPO), adapter.environments[0]
    except (AttributeError, IndexError):
        return None
    if warning_as_error(repo, primary):
        return "primary checkout sets warningAsError"
    return None


WINNERS_SCHEMA = "final60-golf-winners-v1"


def persist(adapter, candidate: Candidate, result: EvalResult, edits: list[dict], plan_info: dict | None) -> None:
    """Record a validated repair like a golf winner (``golf/winners.json`` + code file)."""
    try:
        folder = Path(adapter.golf_dir)
        index_path = folder / "winners.json"
        index = json.loads(index_path.read_text()) if index_path.exists() else {"schema": WINNERS_SCHEMA, "winners": []}
        if any(item.get("sha256") == candidate.sha256 for item in index["winners"]):
            return
        path = folder / "winners" / (candidate.sha256[:12] + ".lean")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(candidate.code)
        accepted = sorted({f"repair:{edit['from']}->{edit['to']}" for edit in edits})
        index["winners"].append({"sha256": candidate.sha256, "label": candidate.label, "parent_sha256": candidate.parent_sha256,
                                 "tokens": result.tokens, "raw_heartbeats": result.raw_heartbeats, "envs": result.envs,
                                 "evidence_dir": result.evidence_dir, "accepted": accepted, "code_path": path.name,
                                 "at": time.time(),
                                 "repair": {"kind": "deprecated-alias", "edits": edits, "envs": (plan_info or {}).get("envs"),
                                            "names": (plan_info or {}).get("names")}})
        temporary = index_path.with_name(index_path.name + f".tmp-{time.time_ns()}")
        temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(index_path)
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass


def compat_status(folder: Path, digest: str) -> str:
    """``valid`` / ``invalid`` / ``unknown`` from the row's saved all-version check of a text."""
    base = Path(folder) / "compatibility" / digest
    path = base / "result.json"
    if not path.exists():
        return "invalid" if (base / "skipped.json").exists() else "unknown"
    try:
        result = json.loads(path.read_text())
    except (OSError, ValueError):
        return "unknown"
    if result.get("valid"):
        return "valid"
    kinds = {str((value.get("error") or {}).get("kind")) for value in (result.get("environments") or {}).values()
             if not value.get("valid")}
    if kinds & {"environment", "resource", "timeout"} or not result.get("environments"):
        return "unknown"
    return "invalid"


def saved_result(adapter, code: str) -> EvalResult | None:
    """The saved all-version check of ``code`` as an EvalResult (no compile), if any."""
    path = Path(adapter.folder) / "compatibility" / sha(code) / "result.json"
    if not path.exists():
        return None
    try:
        return adapter.to_eval(json.loads(path.read_text()), path.parent)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def repair_known(adapter, problem: dict, candidate: Candidate, *, blocked=frozenset(), alias_map: dict | None = None):
    """Validate the alias repair of a candidate whose saved all-version check failed.

    Returns (repaired candidate, validated result, record) or (None, None, record).
    """
    from .select import provenance_sha
    record = {"label": candidate.label, "parent_sha256": candidate.sha256}
    why = gate_blocks(adapter, problem)
    if why:
        record["skipped"] = why
        return None, None, record
    result = saved_result(adapter, candidate.code)
    if result is None:
        record["skipped"] = "no saved all-version check"
        return None, None, record
    alias_map = alias_map if alias_map is not None else alias_map_for(adapter, problem)
    primary = problem["environments"][0]
    try:
        logs = adapter.version_logs(candidate.code)
    except Exception:
        logs = {}
    plan_info = plan(result, primary, logs, alias_map)
    if plan_info is None:
        record["skipped"] = "not an alias-repairable failure"
        return None, None, record
    fixed, edits, rejection = repair_text(candidate, problem["statement"], plan_info["mapping"])
    record.update(mapping=plan_info["mapping"], edits=edits)
    if fixed is None:
        record["skipped"] = rejection
        return None, None, record
    if provenance_sha(fixed) in {str(value) for value in blocked}:
        record["skipped"] = "equals-non-openrouter-proof"
        return None, None, record
    repaired = repair_candidate(candidate, fixed)
    record.update(label=repaired.label, sha256=repaired.sha256)
    try:
        validated = adapter.validate(fixed, repaired.label, as_final=False)
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"[:500]
        return None, None, record
    record.update(valid=validated.valid, envs=validated.envs, error_kind=validated.error_kind)
    if not validated.valid:
        record["message"] = (validated.message or "")[-300:]
        return None, None, record
    persist(adapter, repaired, validated, edits, plan_info)
    screen = EvalResult(True, validated.tokens, validated.raw_heartbeats, {primary: True}, None, "", validated.evidence_dir)
    return Candidate(repaired.code, repaired.sha256, repaired.origin, repaired.parent_sha256, repaired.label, screen), validated, record
