"""Pinned full-context evaluation for the final 60 problems.

No network or library builds. A machine-wide advisory lock serializes compilers.
Trusted references skip only candidate intake policy, never Lean or axiom checks.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from lean_agent.evaluator.lean import ALLOWED_AXIOMS, WRAPPER as SHARED_WRAPPER
from lean_agent.evaluator.tokens import proof_body, without_comments
from fast_prepared import FastPreparedLeanEvaluator as PreparedLeanEvaluator
from evaluation_cache import EvaluationCache

WRAPPER = SHARED_WRAPPER.replace("map Name.toString", "map _root_.Lean.Name.toString")
PRIVATE_WRAPPER = WRAPPER.replace(
    '    let name := target.getString.toName\n'
    '    if (← getEnv).contains name then\n',
    '    let semanticName := target.getString.toName\n'
    '    let findTargets (env : Environment) : Array _root_.Lean.Name :=\n'
    '      env.checked.get.constants.fold (fun names name _ =>\n'
    '        if name == semanticName || privateToUserName? name == some semanticName then\n'
    '          names.push name\n'
    '        else names) #[]\n'
    '    unless (findTargets (← getEnv)).isEmpty do\n'
).replace(
    '    unless env.contains name do\n'
    '      throwError "candidate did not define evaluation target"\n',
    '    let targets := findTargets env\n'
    '    unless targets.size == 1 do\n'
    '      throwError "candidate did not uniquely define private evaluation target"\n'
    '    let name := targets[0]!\n'
).replace(
    '      ("target", toJson target.getString),\n',
    '      ("target", toJson target.getString),\n'
    '      ("actual_target", toJson name.toString),\n'
)

_token_spec = importlib.util.spec_from_file_location("final_proof_tokens", REPO / "experiments/proof-analyze/proof_tokens.py")
_token_module = importlib.util.module_from_spec(_token_spec)
_token_spec.loader.exec_module(_token_module)
proof_tokens = _token_module.proof_length
TOKENIZER_ID = "arena-paper-compatible-v1"


def digest(value):
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _comment_mask(text, *, module_docs_are_commands=False):
    """Mask comments without moving any source boundary (nested comments work)."""
    chars, i = list(text), 0
    while i < len(text):
        if text[i] in ('"', '«'):
            end = '"' if text[i] == '"' else '»'
            i += 1
            while i < len(text):
                if end == '"' and text[i] == "\\":
                    i += 2
                elif text[i] == end:
                    i += 1
                    break
                else:
                    i += 1
        elif text.startswith("--", i):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            chars[i:end] = " " * (end-i)
            i = end
        elif text.startswith("/-", i):
            begin, depth = i, 1
            module_doc = text.startswith("/-!", i)
            i += 2
            while i < len(text) and depth:
                if text.startswith("/-", i):
                    depth += 1
                    i += 2
                elif text.startswith("-/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise ValueError("Unterminated context comment")
            for j in range(begin, i):
                if chars[j] != "\n":
                    chars[j] = " "
            if module_doc and module_docs_are_commands:
                # A module doc is a standalone command, unlike an attached
                # /-- declaration doc. Preserve its end as a command boundary.
                chars[i-1] = "§"
        else:
            i += 1
    return "".join(chars)


def pending_command_start(prefix):
    """Include doc comments and existing `open/omit/set_option ... in` wrappers.

    Final source declarations were audited to have single-line outer directives.
    Keeping these inside the measured command preserves their scope and prevents
    attaching an upstream doc comment to the instrumentation declaration.
    """
    masked = _comment_mask(prefix, module_docs_are_commands=True)
    end = len(masked.rstrip())
    while end:
        start = masked.rfind("\n", 0, end) + 1
        line = masked[start:end]
        if (re.fullmatch(r"\s*(?:open|omit|include|set_option|attribute)\b.*\bin\s*", line) or
                re.fullmatch(r"\s*(?:(?:private|protected|noncomputable|unsafe|partial|public|meta)\s*)+", line)):
            end = len(masked[:start].rstrip())
        else:
            break
    return end


def target_is_private(prefix, statement):
    """Respect explicit modifiers and inherited module/public-section visibility.

    A module's regular declarations are private unless a surrounding public
    section exports them. Namespace and section nesting restore the previous
    visibility when they end. Final-dataset headers use these ordinary forms;
    declaration attributes such as @[expose] may precede public section.
    """
    clean = _comment_mask(prefix)
    public = not bool(re.search(r"(?m)^module\s*$", clean))
    scopes = []
    for original_line in clean.splitlines():
        line = re.sub(r"^(?:@\[[^\]]*\]\s*)+", "", original_line.strip())
        opening = re.fullmatch(
            r"(?:(public|private)\s+)?(?:noncomputable\s+)?"
            r"(section|namespace)(?:\s+([\w.']+))?", line)
        if opening:
            scopes.append((opening[3], public))
            if opening[1]:
                public = opening[1] == "public"
            continue
        closing = re.fullmatch(r"end(?:\s+([\w.']+))?", line)
        if closing and scopes:
            name, previous = scopes.pop()
            public = previous
            if closing[1]:
                while name != closing[1] and scopes:
                    name, public = scopes.pop()
    pending = _comment_mask(prefix[pending_command_start(prefix):] + statement)
    declaration = re.search(
        r"(?m)^\s*((?:(?:private|public|protected|noncomputable|unsafe|partial|meta)\s+)*)"
        r"(?:theorem|lemma|def|abbrev|opaque|instance)\b", pending)
    if declaration:
        modifiers = declaration[1].split()
        if "private" in modifiers:
            return True
        if "public" in modifiers:
            return False
    return not public


def add_lean_import(prefix):
    module = re.search(r"(?m)^module\s*$", prefix)
    if module:
        pos = module.end()
        return prefix[:pos] + "\npublic import Lean\n" + prefix[pos:]
    return "import Lean\n" + prefix


class FinalEvaluator:
    def __init__(self, repo_root=None, global_lock_path=None, cache_root=None):
        self.repo = Path(repo_root or REPO).resolve()
        self.root = self.repo / "sources/final"
        self.registry = json.loads((self.repo / "configs/final-environments.local.json").read_text())
        self.lock_path = Path(global_lock_path or self.root / "final-batch-compiler.lock")
        self._prepared = {}
        self._states = {}
        self._contexts = {}
        self.cache = EvaluationCache(cache_root) if cache_root is not None else None
        self.timing_records = []

    def _cache_identity(self, code, problem, state, context, repetitions, trusted_reference):
        """Bind reuse to exact input, full context, toolchain and evaluator policy."""
        environment_file = self.root / "environments" / state["id"] / "environment.json"
        if json.loads(environment_file.read_text()) != state:
            raise ValueError("Environment metadata changed during evaluation")
        manifest = self.repo / state["prepared_environment"]
        if digest(manifest.read_bytes()) != state["prepared_manifest_sha256"]:
            raise ValueError("Prepared manifest identity changed")
        project = self.repo / state["project"]
        if digest((project / "lake-manifest.json").read_bytes()) != state["manifest_sha256"]:
            raise ValueError("Dependency manifest changed")
        if context["location"].get("file_path"):
            if digest((project / context["location"]["file_path"]).read_bytes()) != context["source_sha256"]:
                raise ValueError("Original full-context source changed")
        setup = None
        if context["module"]:
            path = project / ".lake/build/ir" / (context["module"].replace(".", "/") + ".setup.json")
            setup = digest(path.read_bytes())
            if context.setdefault("setup_sha256", setup) != setup:
                raise ValueError("Pinned Lake compiler setup changed")
        implementation = [Path(__file__), Path(__file__).with_name("evaluation_cache.py"),
                          Path(__file__).with_name("policy.py"), Path(__file__).with_name("fast_prepared.py"), Path(_token_spec.origin),
                          self.repo / "src/lean_agent/prepared.py",
                          self.repo / "src/lean_agent/evaluator/lean.py"]
        compiler = self.root / "toolchains" / state["version"] / "bin/lean"
        return {"candidate_sha256": digest(code), "problem": problem,
                "environment": state, "source_sha256": context["source_sha256"],
                "prepared_layout_sha256": getattr(getattr(self, "_prepared", {}).get(state["id"]), "layout_sha256", None),
                "setup_sha256": setup, "compiler_sha256": digest(compiler.read_bytes()),
                "implementation": {str(path): digest(path.read_bytes()) for path in implementation},
                "repetitions": repetitions, "trusted_reference": trusted_reference,
                "platform": platform.platform(), "machine": platform.machine()}

    def _cached_result(self, code, problem, state, context, folder, repetitions, trusted_reference):
        identity = self._cache_identity(code, problem, state, context, repetitions, trusted_reference)
        if not self.cache.contains(identity):
            return identity, None, 0
        started = time.monotonic()
        self._prepared[state["id"]].verify(full=False)
        verified_seconds = time.monotonic() - started
        return identity, self.cache.load(identity, folder), verified_seconds

    def load_problem(self, problem_id):
        if isinstance(problem_id, dict):
            return problem_id
        if isinstance(problem_id, str):
            match = re.search(r"(?:F)?(\d{1,3})$", problem_id)
            if not match:
                raise ValueError("Expected final problem row or FNNN ID")
            problem_id = int(match[1])
        if not 1 <= problem_id <= 60:
            raise ValueError("Final problem row outside 1..60")
        result = json.loads((self.root / "problems" / f"F{problem_id:03d}.json").read_text())
        if result["dataset_sha256"] != self.registry["dataset_sha256"]:
            raise ValueError("Final dataset identity mismatch")
        return result

    def _state(self, environment_id):
        if environment_id not in self._states:
            state = json.loads((self.root / "environments" / environment_id / "environment.json").read_text())
            if state["status"] != "ready":
                raise ValueError("Environment is not prepared: " + environment_id)
            project = self.repo / state["project"]
            actual = subprocess.check_output([shutil.which("git"), "rev-parse", "HEAD"], cwd=project, text=True).strip()
            if actual != state["revision"]:
                raise ValueError("Source revision changed: " + environment_id)
            if digest((project / "lake-manifest.json").read_bytes()) != state["manifest_sha256"]:
                raise ValueError("Dependency manifest changed")
            manifest = self.repo / state["prepared_environment"]
            if digest(manifest.read_bytes()) != state["prepared_manifest_sha256"]:
                raise ValueError("Prepared manifest identity changed")
            prepared = PreparedLeanEvaluator(manifest)
            prepared.verify()
            self._prepared[environment_id] = prepared
            self._states[environment_id] = state
        return self._states[environment_id]

    def _context(self, problem, environment_id):
        key = (problem["row"], environment_id)
        if key not in self._contexts:
            state = self._state(environment_id)
            location = next(loc for loc in state["locations"] if loc["row"] == problem["row"])
            if location["kind"] == "standalone_header":
                prefix, suffix, module = problem["header"], "\n", None
                source_hash = digest(prefix + problem["reference"])
            else:
                file = self.repo / state["project"] / location["file_path"]
                original = file.read_text()
                if digest(original) != location["source_sha256"]:
                    raise ValueError("Pinned source bytes changed")
                start, stop = location["statement_start_char"], location["declaration_end_char"]
                if stop is None or location["kind"] not in {"exact_src", "whitespace_src"}:
                    raise ValueError("Target declaration extent not proven")
                prefix, suffix, module = original[:start], original[stop:], location["module"]
                source_hash = location["source_sha256"]
            self._contexts[key] = {"prefix": prefix, "suffix": suffix, "module": module,
                                   "source_sha256": source_hash, "location": location}
        return self._contexts[key]

    @contextmanager
    def _compiler_lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as stream:
            waiting = time.monotonic()
            fcntl.flock(stream, fcntl.LOCK_EX)
            acquired = time.monotonic()
            try:
                yield
            finally:
                released = time.monotonic()
                self.timing_records.append({"compiler_lock_wait_seconds": acquired - waiting,
                                            "lock_held_seconds": released - acquired})
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _invoke(self, source, state, context, folder, label):
        project = self.repo / state["project"]
        # Reuse Lake's exact compiler setup without invoking Lake's resolver:
        # the latter may try to rewrite normalized, shared dependency links.
        # Setup retains package/private-import context, options and native plugins.
        saved = (folder / (label + ".lean")).resolve()
        saved.write_text(source)
        compiler = self.root / "toolchains" / state["version"] / "bin"
        command = [str(compiler / "lean"), str(saved), "-j1", "-M4096"]
        setup = None
        if context["module"]:
            setup = project / ".lake/build/ir" / (context["module"].replace(".", "/") + ".setup.json")
            if not setup.is_file():
                raise ValueError("Pinned Lake compiler setup missing: " + str(setup))
            setup_hash = digest(setup.read_bytes())
            known = context.setdefault("setup_sha256", setup_hash)
            if setup_hash != known:
                raise ValueError("Pinned Lake compiler setup changed")
            command.extend(["--setup", str(setup)])
        if sys.platform == "linux":
            sandbox = shutil.which("bwrap")
            if not sandbox:
                raise ValueError("Linux readonly compiler sandbox unavailable")
            mounts = [part for original, frozen in state.get("library_mounts", {}).items()
                      for part in ("--ro-bind", frozen, original)]
            command = [sandbox, "--die-with-parent", "--unshare-all", "--ro-bind", "/", "/",
                       "--dev", "/dev", "--proc", "/proc", *mounts, "--", *command]
        else:
            sandbox = shutil.which("sandbox-exec")
            if not sandbox:
                raise ValueError("macOS readonly compiler sandbox unavailable")
            command = [sandbox, "-p", "(version 1) (allow default) (deny network*) (deny file-write*)", *command]
        child = {"PATH": str(compiler) + ":" + str(Path(shutil.which("git")).parent) + ":/opt/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                 "HOME": str(Path.home()), "TMPDIR": "/tmp", "LANG": "C.UTF-8" if sys.platform == "linux" else "en_US.UTF-8",
                 "LEAN_NUM_THREADS": "1", "MATHLIB_NO_CACHE_ON_UPDATE": "1",
                 "LEAN_PATH": os.pathsep.join(self._prepared[state["id"]].settings["library_paths"])}
        started = time.monotonic()
        record = {"command": command, "cwd": str(project), "source": saved.name,
                  "source_sha256": digest(source)}
        if setup:
            record.update(compiler_setup=str(setup), compiler_setup_sha256=setup_hash)
        try:
            from resources import wait_for_memory, memory_snapshot
            wait_for_memory(log_path=folder / (label + ".memory.json"))
            after_memory = time.monotonic()
            self._prepared[state["id"]].verify(full=False)
            after_verification = time.monotonic()
            process = subprocess.Popen(command, cwd=project, env=child, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            timed_out = False
            try:
                output, _ = process.communicate(timeout=1200)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate()
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise
            after_compiler = time.monotonic()
            record["timing"] = {"memory_gate_seconds": after_memory - started,
                                "environment_verify_seconds": after_verification - after_memory,
                                "compiler_seconds": after_compiler - after_verification}
            text = output.decode(errors="replace")
            log = folder / (label + ".log")
            log.write_text(text)
            record.update(returncode=process.returncode, timed_out=timed_out,
                          seconds=round(time.monotonic()-started, 6), log=log.name,
                          log_sha256=digest(text), memory_after=memory_snapshot())
            return record, text
        finally:
            pass

    def _audit_frontier(self, names, state, context, folder, label):
        """Resolve opaque imported theorem placeholders using their real bodies.

        Lean 4.27's module collector reports exported imported theorems as
        axioms. Its returned names are the dependency frontier of the *actual*
        measured target proof. A separate non-module/private-body environment
        checks precisely those constants; the candidate is never re-elaborated
        with extra imports or a different elaboration context.
        """
        clean = _comment_mask(context["prefix"])
        modules = ["Init", "Lean"]
        for line in clean.splitlines():
            match = re.match(r"\s*(?:(?:public|private|meta)\s+)*import\s+(?:all\s+)?(.*)", line)
            if match:
                modules.extend(word for word in match[1].split() if re.fullmatch(r"[\w.']+", word))
        nonce = uuid.uuid4().hex
        source = ("".join("import " + module + "\n" for module in dict.fromkeys(modules)) +
                  '\nopen Lean Elab Command in\nrun_elab do\n'
                  '  if (← getEnv).header.isModule then\n'
                  '    throwError "Axiom audit requires full private non-module imports"\n'
                  '  let names : List String := ' + json.dumps(names, ensure_ascii=False) + '\n'
                  '  let mut result : Array Json := #[]\n'
                  '  for name in names do\n'
                  '    unless ((← getEnv).checked.get.find? name.toName).isSome do\n'
                  '      throwError m!"Missing audit dependency {name}"\n'
                  '    let axioms ← Lean.collectAxioms name.toName\n'
                  '    result := result.push <| Json.mkObj [("name", toJson name),\n'
                  '      ("axioms", toJson (axioms.toList.map Name.toString))]\n'
                  '  logInfo m!"AXIOM_FRONTIER ' + nonce + ' {(Json.arr result).compress}"\n')
        record, log = self._invoke(source, state, {"module": None}, folder, label)
        record["phase"] = "axiom-frontier-audit"
        if record["returncode"] or record["timed_out"]:
            return record, None, {"kind": "environment", "message": "Private-body axiom audit failed:\n" + log[-6000:]}
        matches = re.findall(r"AXIOM_FRONTIER " + nonce + r" (\[[^\n]*\])", log)
        if len(matches) != 1:
            raise ValueError("Expected exactly one private-body frontier report")
        reports = json.loads(matches[0])
        if (len(reports) != len(names) or [row.get("name") for row in reports] != names or
                any(not isinstance(row.get("axioms"), list) or
                    any(not isinstance(name, str) for name in row["axioms"]) for row in reports)):
            raise ValueError("Axiom frontier dependency coverage mismatch")
        resolved = sorted({name for report in reports for name in report["axioms"]})
        record.update(frontier_names=names, frontier_resolution=reports, resolved_axioms=resolved,
                      candidate_reelaborated=False, imports_visibility="private/non-module")
        error = None if set(resolved) <= ALLOWED_AXIOMS else {"kind": "axioms", "message": str(resolved)}
        return record, resolved, error

    def evaluate(self, code, problem, output_folder, *, repetitions=1, all_versions=False,
                 trusted_reference=False, fresh=False):
        if type(repetitions) is not int or repetitions < 1:
            raise ValueError("Expected a positive measurement count")
        evaluation_started = time.monotonic()
        first_timing = len(getattr(self, "timing_records", []))
        problem = self.load_problem(problem)
        output = Path(output_folder)
        output.mkdir(parents=True, exist_ok=False)
        result = {"valid": False, "tokens": None, "environments": {}, "error": None}
        try:
            result["tokens"] = proof_tokens(code, problem["statement"])
            result["tokenizer"] = {"id": TOKENIZER_ID, "source_sha256": digest(Path(_token_spec.origin).read_bytes())}
            proof_body(code, problem["statement"])
            if trusted_reference:
                if code != problem["reference"]:
                    raise ValueError("Only exact frozen reference may bypass candidate policy")
            else:
                from policy import validate_declaration
                validate_declaration(code, problem["statement"])
        except ValueError as error:
            result["error"] = {"kind": "validation", "message": str(error)}
            write(output / "result.json", result)
            return result
        ids = problem["environments"] if all_versions else problem["environments"][:1]
        cache_verification_seconds = 0
        for environment_id in ids:
            row = {"valid": False, "runs": [], "median_heartbeats": None, "error": None}
            result["environments"][environment_id] = row
            folder = output / environment_id
            folder.mkdir()
            cache_identity = None
            try:
                # Published cache evidence is immutable. A warm evaluator can
                # verify its library inventory and reuse it without waiting for
                # another worker's compiler. Cold initialization and misses keep
                # the existing global serial lock and memory guard.
                context_key = (problem.get("row"), environment_id)
                if (self.cache is not None and not fresh
                        and environment_id in getattr(self, "_states", {})
                        and context_key in getattr(self, "_contexts", {})):
                    state = self._states[environment_id]
                    context = self._contexts[context_key]
                    _, cached, seconds = self._cached_result(
                        code, problem, state, context, folder, repetitions, trusted_reference)
                    cache_verification_seconds += seconds
                    if cached is not None:
                        result["environments"][environment_id] = cached
                        continue
                with self._compiler_lock():
                    state = self._state(environment_id)
                    context = self._context(problem, environment_id)
                    if self.cache is not None and not fresh:
                        cache_identity, cached, seconds = self._cached_result(
                            code, problem, state, context, folder, repetitions, trusted_reference)
                        cache_verification_seconds += seconds
                        if cached is not None:
                            result["environments"][environment_id] = cached
                            continue
                    prefix, suffix = context["prefix"], context["suffix"]
                    jobs = [("check", None)] + [(f"measure-{i+1}", uuid.uuid4().hex) for i in range(repetitions)]
                    raw = []
                    for label, nonce in jobs:
                        if nonce is None:
                            source = prefix + code + suffix
                        else:
                            cut = pending_command_start(prefix)
                            private_target = target_is_private(prefix, problem["statement"])
                            wrapper = PRIVATE_WRAPPER if private_target else WRAPPER
                            source = (add_lean_import(prefix[:cut]) + "\n" + wrapper +
                                      "\nset_option Elab.async false in\n#refactor_eval " +
                                      json.dumps(nonce) + " " + json.dumps(problem["name"], ensure_ascii=False) +
                                      "\n" + prefix[cut:] + code + suffix)
                        record, log = self._invoke(source, state, context, folder, label)
                        row["runs"].append(record)
                        if record["returncode"] or record["timed_out"]:
                            host_failure = any(marker in log.lower() for marker in
                                ("sandbox-exec:", "sandbox_apply:", "operation not permitted", "permission denied", "input/output error"))
                            kind = "environment" if host_failure else "timeout" if record["timed_out"] else "compile"
                            row["error"] = {"kind": kind, "message": log[-8000:]}
                            break
                        if nonce:
                            matches = re.findall(r"REFACTOR_EVAL " + nonce + r" (\{[^\n]*\})", log)
                            if len(matches) != 1:
                                raise ValueError("Expected exactly one fresh target measurement")
                            report = json.loads(matches[0])
                            if (report["target"] != problem["name"] or type(report["raw"]) is not int or
                                    report["raw"] < 0 or report["scaled"] != report["raw"] // 1000):
                                raise ValueError("Invalid measurement counter or target")
                            record["measurement"] = report
                            if not set(report["axioms"]) <= ALLOWED_AXIOMS:
                                audit, resolved, error = self._audit_frontier(report["axioms"], state, context,
                                                                              folder, "axiom-audit-" + label)
                                row["runs"].append(audit)
                                record["resolved_axioms"] = resolved
                                if error:
                                    row["error"] = error
                                    break
                            raw.append(report["raw"])
                    else:
                        row.update(valid=True, median_heartbeats=statistics.median([v // 1000 for v in raw]) if raw else None,
                                   median_raw_heartbeats=statistics.median(raw) if raw else None)
                    write(folder / "result.json", row)
                    if cache_identity is not None:
                        self.cache.publish(cache_identity, folder, row)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                row.update(valid=False, error={"kind": "environment", "message": str(error)})
            write(folder / "result.json", row)
        result["valid"] = bool(result["environments"]) and all(row["valid"] for row in result["environments"].values())
        if not result["valid"]:
            result["error"] = {"kind": "lean", "message": "One or more required environments failed"}
        records = getattr(self, "timing_records", [])[first_timing:]
        actual = [r for value in result["environments"].values() if not value.get("cache", {}).get("hit")
                  for r in value["runs"]]
        result["timing"] = {"wall_seconds": time.monotonic() - evaluation_started,
            "compiler_lock_wait_seconds": sum(r["compiler_lock_wait_seconds"] for r in records),
            "lock_held_seconds": sum(r["lock_held_seconds"] for r in records),
            "new_compiler_invocations": len(actual),
            "cache_hits": sum(bool(v.get("cache", {}).get("hit")) for v in result["environments"].values()),
            "environment_verify_seconds": cache_verification_seconds + sum(r.get("timing", {}).get("environment_verify_seconds", 0) for r in actual),
            "compiler_seconds": sum(r.get("timing", {}).get("compiler_seconds", 0) for r in actual)}
        write(output / "result.json", result)
        return result

    def preflight(self, problem_id, output_folder):
        problem = self.load_problem(problem_id)
        output = Path(output_folder)
        output.mkdir(parents=True, exist_ok=True)
        baseline = self.evaluate(problem["reference"], problem, output / "baseline", repetitions=3,
                                 trusted_reference=True)
        compatibility = self.evaluate(problem["reference"], problem, output / "compatibility", repetitions=1,
                                      all_versions=True, trusted_reference=True) if baseline["valid"] else None
        result = {"problem": problem["id"], "valid": baseline["valid"] and bool(compatibility and compatibility["valid"]),
                  "baseline": baseline, "compatibility": compatibility}
        write(output / "preflight.json", result)
        return result

    def verify_environments(self, problem, *, full=True):
        """Recheck frozen library bytes at an experiment boundary."""
        problem = self.load_problem(problem)
        verified = {}
        with self._compiler_lock():
            for environment_id in problem["environments"]:
                already_initialized = environment_id in self._states
                state = self._state(environment_id)
                # A newly initialized state just performed synchronous full-byte
                # verification. Recheck stamps without reading those bytes twice.
                # Existing states (including every final boundary) still receive
                # the requested fresh full verification.
                verified[environment_id] = self._prepared[environment_id].verify(full=full and already_initialized)
                context = self._context(problem, environment_id)
                if context["location"].get("file_path"):
                    file = self.repo / state["project"] / context["location"]["file_path"]
                    if digest(file.read_bytes()) != context["source_sha256"]:
                        raise ValueError("Original full-context source changed")
        return verified

    def source_context(self, problem):
        problem = self.load_problem(problem)
        with self._compiler_lock():
            environment_id = problem["environments"][0]
            state = self._state(environment_id)
            context = self._context(problem, environment_id)
        prefix = context["prefix"]
        # Original target and downstream declarations are never retrieval entries.
        lines = prefix.splitlines()
        entries = []
        for start in range(0, len(lines), 60):
            text = "\n".join(lines[start:start+60])
            if not text:
                continue
            entries.append({"name": f"context-lines-{start+1}-{min(start+60,len(lines))}",
                            "source": context["location"].get("file_path", "dataset-header"), "text": text})
        from retrieval import build_import_corpus
        from lean_agent.artifacts import canonical
        prefix_bytes = len(canonical({"schema_version": 1, "entries": entries}))
        imported = build_import_corpus(problem, prefix, state, self.repo, target_module=context["module"],
                                      max_bytes=min(4_500_000, 5_000_000-prefix_bytes-1024))
        entries.extend(imported["entries"])
        from lean_agent.actions import validate_corpus
        corpus = {"schema_version": 1, "entries": entries}
        validate_corpus(corpus)
        # These source excerpts are mandatory, independently of lexical ranking.
        # Scope commands are shown in original source order (including closed
        # namespaces), not represented as a typechecked live-environment index.
        masked_lines = _comment_mask(prefix).splitlines()
        import_lines = [lines[i] for i, line in enumerate(masked_lines)
                        if re.match(r"\s*(?:(?:public|private|meta)\s+)*import\b|\s*module\s*$", line)]
        scope_indices = {i for i, line in enumerate(masked_lines)
                         if re.match(r"\s*(?:namespace|section|end)\b", line)}
        nearby = [i for i, line in enumerate(masked_lines)
                  if re.match(r"\s*(?:open|variable|universe|include|omit|set_option)\b", line)]
        for i in nearby[-60:]:
            scope_indices.update(range(i, min(i+3, len(lines))))
        scope_text = "\n".join(f"L{i+1}: {lines[i]}" for i in sorted(scope_indices))
        if len(scope_text) > 8000:
            scope_text = scope_text[:3500] + "\n-- Context-command excerpt truncated; full prefix is searchable.\n" + scope_text[-4400:]
        mandatory = ("[Original imports/header]\n" + ("\n".join(import_lines) or problem["header"]) +
                     "\n\n[Original prefix scope-command excerpts in source order]\n" + scope_text +
                     "\n\n[Original prefix immediately before target]\n" + "\n".join(lines[-60:]))
        identifiers = set(re.findall(r"[A-Za-z_][A-Za-z_0-9'.]*", problem["statement"] + problem["reference"]))
        ranked = sorted(enumerate(entries), key=lambda pair: (-len(set(re.findall(r"[A-Za-z_][A-Za-z_0-9'.]*", pair[1]["text"])) & identifiers), pair[0]))
        chosen, size = [], len(mandatory)
        for index, entry in ranked:
            if size + len(entry["text"]) + len(entry["name"]) + 10 <= 22000:
                chosen.append((index, entry))
                size += len(entry["text"]) + len(entry["name"]) + 10
        prompt = mandatory + "\n\n" + "\n\n".join(f"[{entry['name']}]\n{entry['text']}" for _, entry in sorted(chosen))
        return {"corpus": corpus, "prompt_context": prompt,
                "metadata": {"source_sha256": context["source_sha256"], "primary_environment": problem["environments"][0],
                             "context_scope": "Original target prefix plus pinned legal import closure; no target module or downstream declaration.",
                             "prefix_characters": len(prefix), "corpus_entries": len(entries),
                             "corpus_bytes": len(canonical(corpus)), "import_retrieval": imported["metadata"]}}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(FinalEvaluator().preflight(args.problem, args.output), ensure_ascii=False))
