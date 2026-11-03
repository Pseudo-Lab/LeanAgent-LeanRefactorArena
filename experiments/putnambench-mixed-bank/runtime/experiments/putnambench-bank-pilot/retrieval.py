"""Bounded lexical retrieval from the exact pinned import closure, without Lean.

Only source roots derived from the supplied compiler search path are searched.
The target module is never opened. Imports are followed from the original
prefix/header, not by scanning every package directory. A hit is a source
excerpt, not a claim about exports, namespace accessibility or applicability.
"""
from __future__ import annotations

from collections import Counter, deque
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import re

RETRIEVAL_ID = "pinned-import-closure-lexical-v1"
_MODULE = re.compile(r"^[\w][\w'.]*(?:\.[\w][\w']*)*$", re.UNICODE)
_IMPORT = re.compile(r"^(?:(?:public|private|meta)\s+)*import\s+(?:all\s+)?(.+)$")
_IDENTIFIER = re.compile(r"[^\W\d][\w']*(?:\.[^\W\d][\w']*)*", re.UNICODE)
_DECLARATION = re.compile(
    r"^\s*(?:(?:private|protected|noncomputable|unsafe|partial|public)\s+)*"
    r"(?:theorem|lemma|def|abbrev|opaque|instance)\s+([^\s(:{\[]+)"
)
_STOP = set("""theorem lemma by have show from using exact apply intro intros
  cases case next with simp only simp_all simpa rw erw rfl refine constructor
  obtain rcases rintro calc fun forall exists true false let set suffices
  sorry classical clear revert change specialize first all_goals any_goals
  this that then else match return type prop nat int fin real aesop grind omega
  linarith nlinarith positivity norm_num ring field_simp tauto assumption decide
  induction subst repeat unfold dsimp ext congr simp_rw nth_rewrite use trivial
  for at in and or not as if end namespace section import open include omit
  exact_mod_cast norm_cast push_cast by_cases by_contra generalize rename_i
""".split())


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _components(text):
    result = []
    for identifier in _IDENTIFIER.findall(text):
        words = [identifier, *re.split(r"[._']+", identifier)]
        for word in tuple(words):
            words.extend(re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", word).split())
        for word in words:
            word = word.lower()
            if (len(word) >= 3 and word not in _STOP and not re.fullmatch(r"[a-z]\d*", word)
                    and not re.fullmatch(r"h\w*\d+", word)):
                result.append(word)
    return result


def query_terms(problem):
    """A bounded, deterministic query; statement terms receive extra weight."""
    terms = Counter(_components(problem["reference"]))
    for term in _components(problem["statement"]):
        terms[term] += 8
    return dict(sorted(terms.items(), key=lambda pair: (-pair[1], -len(pair[0]), pair[0]))[:180])


def _mask_line(line, depth):
    """Strip nested comments for import/declaration discovery, preserving strings."""
    if not depth and "--" not in line and "/-" not in line:
        return line, 0
    out, i, quoted = [], 0, False
    while i < len(line):
        if depth:
            if line.startswith("/-", i):
                depth += 1
                i += 2
            elif line.startswith("-/", i):
                depth -= 1
                i += 2
            else:
                i += 1
        elif quoted:
            out.append(line[i])
            if line[i] == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
            else:
                quoted = line[i] != '"'
                i += 1
        elif line.startswith("--", i):
            break
        elif line.startswith("/-", i):
            out.append(" ")
            depth += 1
            i += 2
        else:
            quoted = line[i] == '"'
            out.append(line[i])
            i += 1
    return "".join(out), depth


def imports_from_text(text):
    modules, depth = [], 0
    for line in text.splitlines():
        clean, depth = _mask_line(line, depth)
        match = _IMPORT.match(clean.strip())
        if match:
            modules.extend(token for token in match[1].split() if _MODULE.fullmatch(token))
    # Every ordinary Lean module implicitly imports Init.
    if not re.search(r"(?m)^\s*prelude\s*$", text):
        modules.insert(0, "Init")
    return list(dict.fromkeys(modules))


def source_roots(state, repo_root):
    roots = []
    for item in state.get("lean_path", "").split(os.pathsep):
        if not item:
            continue
        compiled = Path(item)
        if tuple(compiled.parts[-4:]) == (".lake", "build", "lib", "lean"):
            roots.append(compiled.parents[3])
        elif tuple(compiled.parts[-2:]) == ("lib", "lean"):
            roots.append(compiled.parents[1] / "src/lean")
            roots.append(compiled.parents[1] / "src/lean/lake")
    project = Path(repo_root) / state["project"]
    # A package with a nondefault srcDir can have source beside its Lean root;
    # the exact module-relative resolver below records unresolved cases.
    roots.append(project)
    return list(dict.fromkeys(root.resolve() for root in roots if root.is_dir()))


def _resolve(module, roots):
    if not _MODULE.fullmatch(module) or ".." in module or module.startswith("."):
        return None
    relative = Path(*module.split(".")).with_suffix(".lean")
    for root in roots:
        candidate = root / relative
        if candidate.is_file():
            resolved = candidate.resolve()
            if resolved.is_relative_to(root):
                return resolved
    return None


def _header(path, cap=2_000_000):
    lines, size, depth, truncated = [], 0, 0, False
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            size += len(line.encode())
            if size > cap:
                truncated = True
                break
            clean, depth = _mask_line(line, depth)
            clean = clean.strip()
            if clean and not (clean in {"module", "prelude"} or _IMPORT.match(clean)):
                break
            lines.append(line)
    text = "".join(lines)
    return imports_from_text(text), _sha(text.encode()), truncated


def _blocked_modules(graph, seeds):
    blocked = set(seeds)
    parents = {}
    for module, node in graph.items():
        for imported in node["imports"]:
            parents.setdefault(imported, []).append(module)
    queue = deque(blocked)
    while queue:
        for parent in parents.get(queue.popleft(), ()):
            if parent not in blocked:
                blocked.add(parent)
                queue.append(parent)
    return blocked


def build_import_corpus(problem, prefix, state, repo_root, target_module=None,
                        max_bytes=4_500_000, max_modules=30_000):
    """Return bounded action entries plus a reproducible retrieval inventory.

    Memory holds the module graph and at most max_bytes of selected excerpts;
    files are streamed one at a time. No source library or cache is modified.
    The source inventory is separate from the action corpus byte allowance.
    """
    if not 1000 <= max_bytes <= 4_500_000:
        raise ValueError("Import corpus byte allowance must be 1,000..4,500,000")
    repo = Path(repo_root).resolve()
    roots = source_roots(state, repo)
    seeds = imports_from_text(prefix)
    graph, unresolved, excluded, capped_headers = {}, set(), set(), []
    if target_module:
        excluded.add(target_module)
    queue, seen = deque(seeds), set()
    while queue and len(seen) < max_modules:
        module = queue.popleft()
        if module in seen:
            continue
        seen.add(module)
        if module in excluded:
            continue
        path = _resolve(module, roots)
        if path is None:
            unresolved.add(module)
            continue
        imports, header_sha, truncated = _header(path)
        graph[module] = {"path": path, "imports": imports, "header_sha256": header_sha}
        if truncated:
            capped_headers.append(module)
        queue.extend(imports)
    module_cap_reached = bool(queue)
    terms = query_terms(problem)
    module_df = Counter()
    for module in graph:
        module_df.update(set(_components(module)))
    weights = {term: (1 + math.log1p(weight)) * math.log(2 + (len(graph) + 1) / (module_df[term] + 1))
               for term, weight in terms.items()}
    heap, used, sequence, scanned_chunks, scanned_bytes = [], 0, 0, 0, 0
    source_hashes, too_large, target_definitions = {}, [], []
    target_names = {problem["name"], problem["name"].split(".")[-1]}

    def offer(module, node, text, start, stop):
        nonlocal used, sequence, scanned_chunks
        scanned_chunks += 1
        matches = set(_components(text)) & weights.keys()
        if not matches:
            return
        path_matches = set(_components(module)) & weights.keys()
        score = sum(weights[word] for word in matches) + .35 * sum(weights[word] for word in path_matches)
        if len(text) > 12000:
            text = text[:12000] + "\n-- Excerpt truncated after an unusually long source line."
        entry = {"name": f"import-{module[:140]}-{_sha(module.encode())[:8]}-L{start}-{stop}",
                 "source": str(node["path"]),
                 "text": f"-- Lexical source excerpt: module {module}, lines {start}-{stop}.\n" + text}
        cost = len(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()) + 2
        if cost > max_bytes - 100:
            return
        sequence += 1
        heapq.heappush(heap, (score, -sequence, cost, module, start, entry))
        used += cost
        while used > max_bytes - 100:
            used -= heapq.heappop(heap)[2]

    initially_blocked = _blocked_modules(graph, excluded)
    # One streamed pass through reachable source, with a bounded retained heap.
    for module, node in sorted(graph.items()):
        if module in initially_blocked:
            continue
        path = node["path"]
        if path.stat().st_size > 4_000_000:
            too_large.append(module)
            continue
        digest, lines, start, depth, line_no, forbidden_target = hashlib.sha256(), [], 1, 0, 0, False
        chars = 0
        with path.open("rb") as stream:
            for raw in stream:
                digest.update(raw)
                scanned_bytes += len(raw)
                line = raw.decode("utf-8")
                line_no += 1
                clean, depth = _mask_line(line, depth)
                declaration = _DECLARATION.match(clean)
                if declaration and declaration[1].strip("«»") in target_names:
                    forbidden_target = True
                    excluded.add(module)
                    target_definitions.append({"module": module, "line": line_no,
                                               "name": declaration[1], "source": str(path)})
                    break
                lines.append(line)
                chars += len(line)
                if chars >= 2800 or len(lines) >= 65:
                    offer(module, node, "".join(lines), start, line_no)
                    overlap = lines[-4:]
                    start, lines = line_no - len(overlap) + 1, overlap
                    chars = sum(map(len, lines))
            if not forbidden_target:
                if lines:
                    offer(module, node, "".join(lines), start, line_no)
                source_hashes[module] = digest.hexdigest()

    blocked = _blocked_modules(graph, excluded)
    retained = [item for item in heap if item[3] not in blocked]
    retained.sort(key=lambda item: (-item[0], item[3], item[4]))
    entries = [item[5] for item in retained]
    included = sorted({item[3] for item in retained})
    graph_inventory = [{"module": module, "imports": node["imports"],
                        "header_sha256": node["header_sha256"], "source": str(node["path"])}
                       for module, node in sorted(graph.items())]
    metadata = {
        "retrieval_id": RETRIEVAL_ID,
        "scope": "Lexically ranked source excerpts from original imports and their transitive imports; not a Lean export/type index.",
        "environment": state["id"], "revision": state["revision"],
        "source_roots": [str(root) for root in roots], "seed_imports": seeds,
        "target_module_excluded": target_module,
        "import_graph_sha256": _sha(json.dumps(graph_inventory, sort_keys=True, ensure_ascii=False).encode()),
        "reachable_source_modules": len(graph), "unresolved_modules": sorted(unresolved),
        "module_cap_reached": module_cap_reached, "header_limit_modules": capped_headers,
        "source_size_limit_modules": too_large, "target_definition_modules_excluded": target_definitions,
        "blocked_modules": sorted(blocked), "source_bytes_scanned": scanned_bytes,
        "chunks_scanned": scanned_chunks, "entries": len(entries),
        "corpus_utf8_bytes": len(json.dumps({"schema_version": 1, "entries": entries}, ensure_ascii=False).encode()),
        "max_excerpt_bytes": max_bytes, "query_terms": terms,
        "included_sources": [{"module": module, "source": str(graph[module]["path"]),
                              "sha256": source_hashes[module], "imports": graph[module]["imports"]}
                             for module in included],
    }
    return {"entries": entries, "metadata": metadata}
