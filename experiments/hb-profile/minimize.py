#!/usr/bin/env python3
"""LLM-free post-optimizer for one verified declaration (Phase A + part of B).

Objective (lower is better, same shape as the harness selection rule):
    score = tokens / tokens₀ + heartbeats / heartbeats₀
tokens₀ / heartbeats₀ are the official reference values from the benchmark
snapshot. A candidate is accepted only if it compiles on *every* environment
given with --env and lowers the score by more than --min-gain.

Passes, each repeated until no change:
  1. list-min    : for `simp/simp_all/simpa/apply_rules/grind … only [a, b, c]`
                   remove entries one at a time (greedy delta-debugging).
  2. have-drop   : delete whole `have`/`let`/`obtain` blocks.
  3. try-this    : `simp`/`simpa`/`simp_all`/`aesop` without `only` → run the
                   `?` variant, parse "Try this:", substitute the script.
  4. arg-subst   : `(by decide)`, `(by simp)`, `(by omega)`, `(by norm_num)`
                   → cheaper closers from a fixed list.

Everything is deterministic and uses only local Lean compiles; no model calls.

    python3 experiments/hb-profile/minimize.py \
        --env runs/warmup-team-results/20261022-verify-01/P05/v4.32.0/environment.json \
        --decl submissions/warmup/best/P05.lean --name <benchmark name> \
        --benchmark benchmarks/arena/56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c \
        --output runs/hb-profile/P05-min
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from lean_agent.evaluator.lean import WRAPPER, MARKERS, sha256  # noqa: E402
from lean_agent.evaluator.tokens import proof_tokens, without_comments  # noqa: E402

OPEN, CLOSE = "([{⟨", ")]}⟩"
LIST_HEAD = re.compile(r"\b(simp_all|simpa|simp|apply_rules|grind|dsimp|simp_rw|norm_num|field_simp)\b"
                       r"((?:\s+[+\-]\w+|\s+\([^()]*\))*)\s+only\s*\[")
PLAIN_HEAD = re.compile(r"\b(simp_all|simpa|simp|aesop)\b(?!\?)(?![\w'])"
                        r"(?!(?:\s+[+\-]\w+|\s+\([^()]*\))*\s+only\b)")
ARG_BY = re.compile(r"\(by (decide|simp|omega|norm_num|positivity|linarith|trivial|rfl)\)")
ARG_ALTS = ["le_rfl", "le_top", "trivial", "rfl", "ENat.LEInfty.out", "bot_le", "zero_le _",
            "(by decide +kernel)", "(by rfl)", "(by exact le_rfl)", "(by omega)", "(by decide)",
            "(by simp)", "(by norm_num)"]
BLOCK_HEAD = re.compile(r"^(\s*)(have|let|obtain|haveI|letI)\b")


# ───────────────────────── Lean execution ─────────────────────────

def render(template: str, code: str, name: str, nonce: str) -> str:
    module = bool(re.search(r"(?m)^module\s*$", template))
    target = ("set_option Elab.async false in\n"
              f"#refactor_eval {json.dumps(nonce)} {json.dumps(name, ensure_ascii=False)}\n{code}")
    values = (("public import Lean" if module else "import Lean"), WRAPPER, target)
    repl = dict(zip(MARKERS, values))
    return re.sub("|".join(map(re.escape, MARKERS)), lambda m: repl[m[0]], template)


class Runner:
    def __init__(self, envs: list[dict], name: str, workdir: Path):
        self.envs, self.name, self.workdir = envs, name, workdir
        self.compiles = 0
        self.cache: dict[str, dict] = {}
        workdir.mkdir(parents=True, exist_ok=True)

    def _run(self, env: dict, source: str, label: str) -> str:
        path = (self.workdir / f"{label}.lean").resolve()
        path.write_text(source, encoding="utf-8")
        cmd = [*env["command"], "--root=" + str(self.workdir.resolve()), str(path)]
        self.compiles += 1
        try:
            proc = subprocess.run(cmd, cwd=env["project"], capture_output=True, text=True,
                                  timeout=env.get("timeout_seconds", 120) * 3,
                                  env={k: v for k, v in os.environ.items()
                                       if k in {"PATH", "HOME", "ELAN_HOME", "TMPDIR"}})
            log = proc.stdout + proc.stderr
            if proc.returncode:
                log += f"\n[exit {proc.returncode}]"
        except subprocess.TimeoutExpired:
            log = "[timeout]"
        (self.workdir / f"{label}.log").write_text(log, encoding="utf-8")
        return log

    def measure(self, code: str, runs: int = 1) -> dict:
        """valid on all envs; heartbeats (scaled) = median over `runs` on the first env."""
        key = sha256(code) + f":{runs}"
        if key in self.cache:
            return self.cache[key]
        result = {"valid": True, "hb": None, "logs": []}
        hbs = []
        for idx, env in enumerate(self.envs):
            for r in range(runs if idx == 0 else 1):
                nonce = uuid.uuid4().hex
                log = self._run(env, render(env["template"], code, self.name, nonce),
                                f"m{self.compiles:04d}")
                found = re.findall(r"REFACTOR_EVAL " + nonce + r" (\{[^\n]*\})", log)
                if "[exit" in log or "[timeout]" in log or len(found) != 1 or re.search(r"(?m)^[^\n]*: error:", log):
                    result["valid"] = False
                    result["logs"].append(log[-1500:])
                    self.cache[key] = result
                    return result
                rep = json.loads(found[0])
                if not set(rep["axioms"]) <= {"propext", "Classical.choice", "Quot.sound"}:
                    result["valid"] = False
                    result["logs"].append("axioms: " + str(rep["axioms"]))
                    self.cache[key] = result
                    return result
                if idx == 0:
                    hbs.append(rep["scaled"])
        result["hb"] = int(statistics.median(hbs))
        self.cache[key] = result
        return result

    def try_this(self, code: str) -> list[str]:
        """Compile `code` (which contains `?` tactics) and return all Try-this suggestions."""
        env = self.envs[0]
        nonce = uuid.uuid4().hex
        log = self._run(env, render(env["template"], code, self.name, nonce), f"t{self.compiles:04d}")
        out, cur = [], None
        for line in log.splitlines():
            if re.match(r"^[^\s:]+:\d+:\d+: ", line):
                if cur is not None:
                    out.append(cur.strip())
                    cur = None
                m = re.search(r"Try this: (.*)$", line)
                if m:
                    cur = m.group(1)
            elif cur is not None:
                cur += "\n" + line
        if cur is not None:
            out.append(cur.strip())
        return out


# ───────────────────────── text surgery ─────────────────────────

def match_bracket(text: str, i: int) -> int:
    """index of the bracket closing text[i]; -1 if none."""
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def split_items(inner: str) -> list[str]:
    items, depth, cur = [], 0, ""
    for c in inner:
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        if c == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += c
    if cur.strip():
        items.append(cur)
    return items


def lemma_lists(code: str) -> list[tuple[int, int]]:
    """(start, end) spans of the bracket contents of every `… only [ … ]`."""
    spans = []
    for m in LIST_HEAD.finditer(code):
        open_i = m.end() - 1
        close_i = match_bracket(code, open_i)
        if close_i > open_i:
            spans.append((open_i + 1, close_i))
    return spans


def proof_blocks(code: str) -> list[tuple[int, int]]:
    """(start, end) char spans of `have/let/obtain …` tactic blocks (header + more-indented lines)."""
    lines = code.splitlines(keepends=True)
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln))
    blocks = []
    i = 0
    while i < len(lines):
        m = BLOCK_HEAD.match(lines[i])
        if m:
            indent = len(m.group(1))
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent):
                j += 1
            blocks.append((offsets[i], offsets[j]))
            i = j
        else:
            i += 1
    return blocks


# ───────────────────────── optimizer ─────────────────────────

def body_start(code: str, statement: str) -> int:
    """Offset of the proof body (after `:=`), using the fixed statement when it matches."""
    if code.startswith(statement):
        m = re.match(r"\s*:=", code[len(statement):])
        if m:
            return len(statement) + m.end()
    m = re.search(r":=\s*by\b", code)
    if not m:
        raise SystemExit("Cannot locate the proof body")
    return m.start() + 2


def tactic_end(text: str, start: int) -> int:
    """End of the tactic call starting at `start`: a depth-0 newline, `,`, `;`, `<;>` or unmatched closer."""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if depth == 0:
            if c in "\n,;":
                return i
            if text.startswith("<;>", i):
                return i
            if c in CLOSE:
                return i
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        i += 1
    return len(text)


class Optimizer:
    def __init__(self, runner: Runner, statement: str, tok0: int, hb0: int, min_gain: float, log):
        self.r, self.statement, self.tok0, self.hb0, self.min_gain, self.log = runner, statement, tok0, hb0, min_gain, log
        self.history = []
        self.head = ""  # statement part, never edited

    def split(self, code: str) -> str:
        b = body_start(code, self.statement)
        self.head, body = code[:b], code[b:]
        return body

    def join(self, body: str) -> str:
        return self.head + body

    def tokens(self, code: str) -> int:
        try:
            return proof_tokens(code, self.statement)
        except ValueError:
            return proof_tokens("x :=" + code[body_start(code, self.statement):], "x")

    def score(self, code: str, runs: int = 1):
        m = self.r.measure(code, runs)
        if not m["valid"]:
            return None, None, None
        tok = self.tokens(code)
        return tok / self.tok0 + m["hb"] / self.hb0, tok, m["hb"]

    def attempt(self, label: str, cur: str, cur_score: float, cand: str):
        if cand == cur:
            return None
        s, tok, hb = self.score(cand)
        if s is None:
            self.log(f"    ✗ {label}: does not compile")
            return None
        gain = cur_score - s
        if gain > self.min_gain:
            self.log(f"    ✓ {label}: score {cur_score:.4f} → {s:.4f}  (tok {tok}, hb {hb}k)")
            self.history.append({"pass": label, "score": s, "tokens": tok, "hb": hb})
            return cand, s
        self.log(f"    · {label}: no gain ({cur_score:.4f} → {s:.4f})")
        return None

    def pass_list_min(self, cur, cur_score):
        changed = True
        while changed:
            changed = False
            body = self.split(cur)
            for start, end in lemma_lists(body):
                items = split_items(body[start:end])
                if len(items) == 0:
                    continue
                for k in range(len(items)):
                    kept = items[:k] + items[k + 1:]
                    inner = ",".join(kept).strip()
                    cand = self.join(body[:start] + inner + body[end:])
                    res = self.attempt(f"list-min drop `{items[k].strip()[:40]}`", cur, cur_score, cand)
                    if res:
                        cur, cur_score = res
                        changed = True
                        break
                if changed:
                    break
        return cur, cur_score

    def pass_have_drop(self, cur, cur_score):
        changed = True
        while changed:
            changed = False
            body = self.split(cur)
            for start, end in proof_blocks(body):
                head = body[start:end].strip().splitlines()[0][:50]
                res = self.attempt(f"have-drop `{head}`", cur, cur_score, self.join(body[:start] + body[end:]))
                if res:
                    cur, cur_score = res
                    changed = True
                    break
        return cur, cur_score

    def pass_try_this(self, cur, cur_score):
        body = self.split(cur)
        for m in list(PLAIN_HEAD.finditer(body)):
            if m.start() > 0 and body[m.start() - 1] in "_'.":
                continue
            probe = self.join(body[:m.end()] + "?" + body[m.end():])
            suggestions = self.r.try_this(probe)
            if not suggestions:
                self.log(f"    · try-this `{m.group(1)}` @{m.start()}: no suggestion")
                continue
            end = tactic_end(body, m.start())
            col = m.start() - (body.rfind("\n", 0, m.start()) + 1)
            for sug in suggestions:
                lines = sug.splitlines()
                sug = "\n".join([lines[0]] + [" " * col + ln for ln in lines[1:]]) if len(lines) > 1 else sug
                cand = self.join(body[:m.start()] + sug + body[end:])
                res = self.attempt(f"try-this `{m.group(1)}` → `{lines[0][:60]}`", cur, cur_score, cand)
                if res:
                    return res[0], res[1], True
        return cur, cur_score, False

    def pass_arg_subst(self, cur, cur_score):
        changed = True
        while changed:
            changed = False
            body = self.split(cur)
            for m in list(ARG_BY.finditer(body)):
                for alt in ARG_ALTS:
                    if alt == m.group(0):
                        continue
                    cand = self.join(body[:m.start()] + alt + body[m.end():])
                    res = self.attempt(f"arg-subst `{m.group(0)}` → `{alt}`", cur, cur_score, cand)
                    if res:
                        cur, cur_score = res
                        changed = True
                        break
                if changed:
                    break
        return cur, cur_score

    def run(self, code: str):
        s, tok, hb = self.score(code, runs=1)
        if s is None:
            raise SystemExit("Input declaration does not compile in the given environments:\n"
                             + "\n".join(self.r.measure(code)["logs"]))
        self.log(f"start: score {s:.4f}  tokens {tok} (ref {self.tok0})  hb {hb}k (ref {self.hb0}k)")
        cur, cur_score = code, s
        for rnd in range(4):
            before = cur_score
            self.log(f"[round {rnd + 1}] list-min")
            cur, cur_score = self.pass_list_min(cur, cur_score)
            self.log(f"[round {rnd + 1}] have-drop")
            cur, cur_score = self.pass_have_drop(cur, cur_score)
            self.log(f"[round {rnd + 1}] try-this")
            cur, cur_score, _ = self.pass_try_this(cur, cur_score)
            self.log(f"[round {rnd + 1}] arg-subst")
            cur, cur_score = self.pass_arg_subst(cur, cur_score)
            if before - cur_score <= self.min_gain:
                break
        return cur, cur_score


def load_reference(benchmark: Path, name: str) -> tuple[str, int, int]:
    statement = tok0 = hb0 = None
    for line in (benchmark / "benchmark_data_warmup.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["name"] == name:
                statement, tok0 = row["statement"], int(row["proof_length"])
    for line in (benchmark / "benchmark_heartbeats.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["name"] == name:
                hb0 = int(row["heartbeat"])
    if statement is None or hb0 is None:
        raise SystemExit(f"{name} not found in benchmark snapshot")
    return statement, tok0, hb0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True, type=Path, action="append",
                    help="environment.json; repeat for every toolchain the candidate must pass")
    ap.add_argument("--decl", required=True, type=Path)
    ap.add_argument("--name", required=True, help="benchmark name")
    ap.add_argument("--benchmark", required=True, type=Path, help="benchmarks/arena/<revision>")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--min-gain", type=float, default=0.0005, help="minimum score decrease to accept")
    ap.add_argument("--final-runs", type=int, default=3)
    args = ap.parse_args()

    envs = [json.loads(p.read_text(encoding="utf-8")) for p in args.env]
    code = args.decl.read_text(encoding="utf-8")
    if not code.endswith("\n"):
        code += "\n"
    statement, tok0, hb0 = load_reference(args.benchmark, args.name)
    args.output.mkdir(parents=True, exist_ok=False)
    logf = open(args.output / "log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    runner = Runner(envs, args.name, args.output / "work")
    opt = Optimizer(runner, statement, tok0, hb0, args.min_gain, log)
    best, best_score = opt.run(code)

    final = runner.measure(best, runs=args.final_runs)
    tok = opt.tokens(best)
    (args.output / "best.lean").write_text(best, encoding="utf-8")
    summary = {
        "name": args.name, "input": str(args.decl), "input_sha256": sha256(code),
        "best_sha256": sha256(best), "changed": best != code,
        "reference": {"tokens": tok0, "heartbeats": hb0},
        "input_metrics": {"tokens": opt.tokens(code), "heartbeats": runner.measure(code)["hb"]},
        "best_metrics": {"tokens": tok, "heartbeats_median": final["hb"], "valid_all_envs": final["valid"]},
        "score_input": opt.score(code)[0], "score_best": best_score,
        "problem_score_estimate": {
            "input": round((100 * (1 - opt.tokens(code) / tok0) + 100 * (1 - runner.measure(code)["hb"] / hb0) + 100) / 3, 2),
            "best": round((100 * (1 - tok / tok0) + 100 * (1 - final["hb"] / hb0) + 100) / 3, 2) if final["valid"] else None,
        },
        "history": opt.history, "compiles": runner.compiles,
        "environments": [str(p) for p in args.env],
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    log(json.dumps(summary["problem_score_estimate"]) + f"  compiles={runner.compiles}")
    log(f"written: {args.output / 'best.lean'}")


if __name__ == "__main__":
    main()
