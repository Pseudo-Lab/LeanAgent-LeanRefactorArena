#!/usr/bin/env python3
"""Tactic-level heartbeat profiler for one declaration in a prepared environment.

Reads an `environment.json` written by the warm-up verifier (command, template,
project) and a file holding one declaration (statement + proof). Rewrites the
first `:= by` into `:= by hb_profile "<nonce>:0"` and compiles once with the
profiler commands injected, once without. Prints a per-tactic table and writes
`profile.json`. Model/network are never used.

    python3 experiments/hb-profile/profile.py \
        --env runs/warmup-team-results/20261022-verify-01/P05/v4.32.0/environment.json \
        --decl runs/warmup-team-results/20261022-verify-01/P05/v4.32.0/baseline.lean \
        --output runs/hb-profile/P05-baseline

Heartbeats are reported in the official unit (raw // 1000). Per-item numbers
are measured around `evalTactic` of that item only; the residual
(total − Σ depth-0 items) is the cost of elaborating the declaration header,
instantiating the final term and the kernel check. Nested `by` blocks and
bullets are profiled recursively (depth ≥ 1); their numbers are included in
the parent's.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from lean_agent.evaluator.lean import WRAPPER, MARKERS, sha256  # noqa: E402

PROFILER = r'''
open Lean Elab Tactic in
syntax (name := hbProfileTac) "hb_profile " str tacticSeq : tactic

namespace HbProfile
open Lean Elab Tactic

def seqItems (seq : Syntax) : Array Syntax :=
  let inner := seq[0]
  if inner.isOfKind ``Lean.Parser.Tactic.tacticSeqBracketed then inner[1].getSepArgs
  else inner[0].getSepArgs

/-- Replace every nested `tacticSeq` with a one-item sequence `hb_profile tag <seq>`.
The sequence itself is left intact, so the inner items are profiled when it runs. -/
partial def wrap (tag : Syntax) (stx : Syntax) : Syntax :=
  if stx.isOfKind ``Lean.Parser.Tactic.tacticSeq then
    let tac := Syntax.node .none ``hbProfileTac #[mkAtom "hb_profile", tag, stx]
    let sep := Syntax.node .none nullKind #[tac]
    let indented := Syntax.node .none ``Lean.Parser.Tactic.tacticSeq1Indented #[sep]
    Syntax.node .none ``Lean.Parser.Tactic.tacticSeq #[indented]
  else
    match stx with
    | .node info kind args => .node info kind (args.map (wrap tag))
    | other => other

@[tactic hbProfileTac] def evalHbProfile : Tactic := fun stx => do
  let tagStr := (stx[1].isStrLit?).getD "?:0"
  let (nonce, depth) :=
    match tagStr.splitOn ":" with
    | [n, d] => (n, d.toNat?.getD 0)
    | _ => (tagStr, 0)
  let childTag := Syntax.mkStrLit s!"{nonce}:{depth + 1}"
  let fm ← getFileMap
  for item in seqItems stx[2] do
    let goalsBefore := (← getGoals).length
    let start ← IO.getNumHeartbeats
    evalTactic (wrap childTag item)
    let stop ← IO.getNumHeartbeats
    let goalsAfter := (← getGoals).length
    let (line, col, endLine) :=
      match item.getPos?, item.getTailPos? with
      | some p, some q =>
        let a := fm.toPosition p
        let b := fm.toPosition q
        (a.line, a.column, b.line)
      | some p, none =>
        let a := fm.toPosition p
        (a.line, a.column, a.line)
      | _, _ => (0, 0, 0)
    let report := Json.mkObj [
      ("depth", toJson depth), ("line", toJson line), ("col", toJson col),
      ("endLine", toJson endLine), ("hb", toJson (stop - start)),
      ("goalsBefore", toJson goalsBefore), ("goalsAfter", toJson goalsAfter),
      ("kind", toJson item.getKind.toString)]
    logInfo m!"HB_PROFILE {nonce} {report.compress}"

end HbProfile
'''

BY_PATTERN = re.compile(r":=\s*by\b")


def render(template: str, code: str, name: str, nonce: str, *, profile: bool) -> str:
    module = bool(re.search(r"(?m)^module\s*$", template))
    commands = WRAPPER + (PROFILER if profile else "")
    target = ("set_option Elab.async false in\n"
              f"#refactor_eval {json.dumps(nonce)} {json.dumps(name, ensure_ascii=False)}\n{code}")
    values = (("public import Lean" if module else "import Lean"), commands, target)
    replacements = dict(zip(MARKERS, values))
    return re.sub("|".join(map(re.escape, MARKERS)), lambda m: replacements[m[0]], template)


def instrument(code: str, nonce: str, statement: str | None) -> str:
    offset = 0
    if statement and code.startswith(statement):
        offset = len(statement)  # skip `by` inside the fixed statement (e.g. `(h := by omega)`)
    match = BY_PATTERN.search(code, offset)
    if not match:
        raise SystemExit("Declaration has no `:= by`; term-mode proofs are not profiled.")
    return code[:match.end()] + f' hb_profile "{nonce}:0"' + code[match.end():]


def load_statement(benchmark: Path | None, name: str) -> str | None:
    if benchmark is None:
        return None
    for line in (benchmark / "benchmark_data_warmup.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["name"] == name:
                return row["statement"]
    return None


def declaration_name(code: str) -> str:
    match = re.search(r"(?m)^(?:[^\n]*\b)?(?:theorem|lemma)\s+([^\s:({\[]+)", code)
    if not match:
        raise SystemExit("Could not find `theorem`/`lemma` name; pass --name.")
    return match.group(1)


def run_lean(env: dict, source: str, folder: Path, label: str) -> dict:
    path = (folder / f"{label}.lean").resolve()
    path.write_text(source, encoding="utf-8")
    command = [*env["command"], "--root=" + str(folder.resolve()), str(path)]
    started = time.monotonic()
    proc = subprocess.run(command, cwd=env["project"], capture_output=True, text=True,
                          timeout=env.get("timeout_seconds", 120) * 3,
                          env={k: v for k, v in os.environ.items()
                               if k in {"PATH", "HOME", "ELAN_HOME", "TMPDIR"}})
    log = proc.stdout + proc.stderr
    (folder / f"{label}.log").write_text(log, encoding="utf-8")
    return {"returncode": proc.returncode, "seconds": round(time.monotonic() - started, 3),
            "log": log, "source_sha256": sha256(source)}


def parse_total(log: str, nonce: str) -> dict | None:
    found = re.findall(r"REFACTOR_EVAL " + nonce + r" (\{[^\n]*\})", log)
    return json.loads(found[0]) if len(found) == 1 else None


def parse_items(log: str, nonce: str, source: str) -> list[dict]:
    items = [json.loads(m) for m in re.findall(r"HB_PROFILE " + nonce + r" (\{[^\n]*\})", log)]
    lines = source.splitlines()
    for r in items:
        text = lines[r["line"] - 1][r["col"]:] if 0 < r["line"] <= len(lines) else ""
        r["head"] = text.strip()[:120]
    # Lean reports a nested item before its parent finishes; sort by source order.
    return sorted(items, key=lambda r: (r["line"], r["col"], r["depth"]))


def table(items: list[dict], total_scaled: int, line_offset: int) -> str:
    rows = ["  hb(k)   %tot  depth  lines        tactic"]
    for r in items:
        hb = r["hb"] // 1000
        pct = 100.0 * r["hb"] / (total_scaled * 1000) if total_scaled else 0.0
        l1, l2 = r["line"] - line_offset, r["endLine"] - line_offset
        span = f"{l1}" if l1 == l2 else f"{l1}-{l2}"
        indent = "  " * r["depth"]
        rows.append(f"{hb:7d} {pct:6.1f}  {r['depth']:5d}  {span:12} {indent}{r['head']}")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True, type=Path, help="environment.json from the verifier")
    ap.add_argument("--decl", required=True, type=Path, help="file holding the declaration to profile")
    ap.add_argument("--name", help="declaration name (default: parsed from --decl)")
    ap.add_argument("--output", required=True, type=Path, help="new folder for sources, logs, profile.json")
    ap.add_argument("--no-plain", action="store_true", help="skip the unprofiled control compile")
    ap.add_argument("--benchmark", type=Path, help="benchmarks/arena/<revision>; locates the proof body via the fixed statement")
    args = ap.parse_args()

    env = json.loads(args.env.read_text(encoding="utf-8"))
    code = args.decl.read_text(encoding="utf-8")
    if not code.endswith("\n"):
        code += "\n"
    name = args.name or declaration_name(code)
    args.output.mkdir(parents=True, exist_ok=False)

    nonce = uuid.uuid4().hex
    statement = load_statement(args.benchmark, name)
    profiled_src = render(env["template"], instrument(code, nonce, statement), name, nonce, profile=True)
    # Line of the declaration inside the rendered file, so the table shows proof-relative lines.
    decl_line = profiled_src.count("\n", 0, profiled_src.index(f"#refactor_eval {json.dumps(nonce)}")) + 2

    profiled = run_lean(env, profiled_src, args.output, "profiled")
    total = parse_total(profiled["log"], nonce)
    items = parse_items(profiled["log"], nonce, profiled_src)
    result = {"name": name, "environment": str(args.env), "declaration": str(args.decl),
              "declaration_sha256": sha256(code), "nonce": nonce,
              "profiled": {k: v for k, v in profiled.items() if k != "log"},
              "total_profiled": total, "items": items}

    if profiled["returncode"] or total is None:
        print(profiled["log"][-4000:])
        (args.output / "profile.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        raise SystemExit("Profiled compile failed; see log above.")

    plain_total = None
    if not args.no_plain:
        plain_nonce = uuid.uuid4().hex
        plain_src = render(env["template"], code, name, plain_nonce, profile=False)
        plain = run_lean(env, plain_src, args.output, "plain")
        plain_total = parse_total(plain["log"], plain_nonce)
        result["plain"] = {k: v for k, v in plain.items() if k != "log"}
        result["total_plain"] = plain_total

    scaled = total["scaled"]
    top = [r for r in items if r["depth"] == 0]
    attributed = sum(r["hb"] for r in top) // 1000
    result["summary"] = {
        "total_scaled_profiled": scaled,
        "total_scaled_plain": plain_total["scaled"] if plain_total else None,
        "instrumentation_overhead_scaled": (scaled - plain_total["scaled"]) if plain_total else None,
        "attributed_depth0_scaled": attributed,
        "residual_scaled": scaled - attributed,
        "items": len(items),
    }
    (args.output / "profile.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"declaration: {name}")
    print(f"total (profiled run): {scaled}k heartbeats"
          + (f"   plain run: {plain_total['scaled']}k   overhead: {scaled - plain_total['scaled']:+d}k"
             if plain_total else ""))
    print(f"attributed to depth-0 tactics: {attributed}k   residual (header+term+kernel): {scaled - attributed}k")
    print()
    print(table(items, scaled, decl_line - 1))
    print(f"\nwritten: {args.output / 'profile.json'}")


if __name__ == "__main__":
    main()
