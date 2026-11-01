#!/usr/bin/env python3
"""auto_rewrite.py — automated proof-golf agent loop.

Generates deterministic rewrite candidates from a seed proof, screens them
via trial.py, adopts the best improving candidate, and repeats.

Usage:
  python3 auto_rewrite.py --problem-dir /tmp/la_work/putnam/P13 \
    --seed /path/to/seed.lean --output /path/to/rewrite/PXX \
    --t0 1769 --h0 115674000 --max-rounds 6 --workers 2
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
REPO = Path('/tmp/la_repos/LeanAgent-LeanRefactorArena')
TRIAL_PY = REPO / 'experiments' / 'proof-golf' / 'trial.py'
VERIFY_PY = REPO / 'experiments' / 'proof-golf' / 'verify.py'


# ═══════════════════════════════════════════════════════════════════════════
#  Rewrite rules
# ═══════════════════════════════════════════════════════════════════════════

def _find_balanced_paren(text: str, start: int) -> int | None:
    """Return index past the closing ')' for the '(' at *start*, or None."""
    if start >= len(text) or text[start] != '(':
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def rule_parens_to_dollar(proof: str) -> list[dict]:
    """Replace trailing `(f x)` with `f $ x` — saves 1 token per site."""
    trials = []
    # Find patterns where a space is followed by `(...)` at end-of-token-or-line
    for m in re.finditer(r' \(([A-Za-z_][\w.\']*(?:\s+[^\)]+)?)\)(?=\s|$)', proof):
        inner = m.group(1).strip()
        # Only do it when inner has at least one space (i.e. it's an application)
        if ' ' not in inner:
            continue
        old = m.group(0)  # includes leading space
        new = ' ' + inner.split(None, 1)[0] + ' $ ' + inner.split(None, 1)[1]
        # But we want ` (f x)` → ` f $ x` keeping the leading space
        new = ' $ '.join([' ' + inner.split(None, 1)[0], inner.split(None, 1)[1]])
        new = ' ' + new
        if old == new or proof.count(old) != 1:
            continue
        trials.append({
            'label': f'parens_to_dollar:{old.strip()[:40]}',
            'edits': [[old, new]],
        })
    return trials


def rule_remove_type_annotations(proof: str) -> list[dict]:
    """Try removing `: Type` from `(name : Type)` patterns."""
    trials = []
    for m in re.finditer(r'\((\w+)\s*:\s*([^)]+)\)', proof):
        old = m.group(0)
        name = m.group(1)
        if proof.count(old) != 1:
            continue
        trials.append({
            'label': f'remove_type_ann:{name}',
            'edits': [[old, name]],
        })
    return trials


def rule_inline_let(proof: str) -> list[dict]:
    """Inline `let f := expr\n` by substituting f everywhere after."""
    trials = []
    for m in re.finditer(r'let\s+(\w+)\s*:=\s*(.+)', proof):
        name = m.group(1)
        expr = m.group(2).strip()
        # Remove trailing semicolon if present
        if expr.endswith(';'):
            expr = expr[:-1].strip()
        let_line = m.group(0)
        # Find next newline after the let
        rest_start = m.end()
        rest = proof[rest_start:]
        # Check if name appears in rest
        pat = re.compile(r'(?<![.\w\'])' + re.escape(name) + r'(?![.\w\'])')
        if not pat.search(rest):
            continue
        # Wrap expr in parens if it contains spaces
        replacement = f'({expr})' if ' ' in expr else expr
        inlined_rest = pat.sub(replacement, rest)
        # Remove the let line (including the newline)
        new_full = proof[:m.start()] + inlined_rest
        # Clean up: remove blank line left by let removal
        new_full = re.sub(r'\n\s*\n', '\n', new_full)
        if new_full == proof:
            continue
        # Use full-text edit
        trials.append({
            'label': f'inline_let:{name}',
            'edits': [[proof, new_full]],
        })
    return trials


def rule_simp_only_to_simp(proof: str) -> list[dict]:
    """Try `simp` instead of `simp only [...]`."""
    trials = []
    for m in re.finditer(r'simp only \[[^\]]*\]', proof):
        old = m.group(0)
        if proof.count(old) != 1:
            continue
        trials.append({
            'label': f'simp_only_to_simp:{old[:40]}',
            'edits': [[old, 'simp']],
        })
    return trials


def rule_exact_have_inline(proof: str) -> list[dict]:
    """Convert `have h := expr\\n  exact h` → `exact expr`."""
    trials = []
    for m in re.finditer(
        r'have\s+(\w+)\s*:=\s*(.+)\n(\s*)exact\s+\1\b', proof
    ):
        old = m.group(0)
        expr = m.group(2).strip()
        indent = m.group(3)
        new = f'{indent}exact {expr}'
        if proof.count(old) != 1:
            continue
        trials.append({
            'label': f'exact_have_inline:{m.group(1)}',
            'edits': [[old, new]],
        })
    return trials


def rule_apply_to_exact(proof: str) -> list[dict]:
    """Try `exact` instead of `apply` where possible."""
    trials = []
    for m in re.finditer(r'\bapply\s+(\S+)', proof):
        old = m.group(0)
        new = 'exact ' + m.group(1)
        if proof.count(old) != 1:
            continue
        trials.append({
            'label': f'apply_to_exact:{m.group(1)[:30]}',
            'edits': [[old, new]],
        })
    return trials


def rule_congr_fun_dollar(proof: str) -> list[dict]:
    """Replace `congrArg X (congrFun Y Z)` → `congrArg X $ congrFun Y Z`."""
    trials = []
    pat = re.compile(r'(congrArg\s+\S+)\s+\((congrFun\s+\S+\s+\S+)\)')
    for m in pat.finditer(proof):
        old = m.group(0)
        new = m.group(1) + ' $ ' + m.group(2)
        if proof.count(old) != 1:
            continue
        trials.append({
            'label': f'congr_fun_dollar',
            'edits': [[old, new]],
        })
    return trials


def rule_by_omega_inline(proof: str) -> list[dict]:
    """Try removing `(by omega)` parenthetical — see if Lean can infer."""
    trials = []
    for m in re.finditer(r'\(by omega\)', proof):
        old = m.group(0)
        # Try dropping it entirely
        if proof.count(old) < 1:
            continue
        # Only replace the first occurrence each time
        idx = proof.index(old)
        new_proof = proof[:idx] + proof[idx + len(old):]
        # Clean up double spaces
        new_proof = re.sub(r'  +', ' ', new_proof)
        trials.append({
            'label': f'by_omega_drop:{idx}',
            'edits': [[proof, new_proof]],
        })
    return trials


def rule_semicolon_chain(proof: str) -> list[dict]:
    """Find consecutive identical tactic lines and merge with `<;>`."""
    trials = []
    lines = proof.split('\n')
    i = 0
    while i < len(lines) - 1:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        # Check for consecutive identical tactics
        j = i + 1
        while j < len(lines) and lines[j].strip() == stripped:
            j += 1
        count = j - i
        if count >= 2:
            # The lines from i..j-1 are identical; try merging with <;>
            indent = len(lines[i]) - len(lines[i].lstrip())
            old_block = '\n'.join(lines[i:j])
            new_block = ' ' * indent + f'all_goals {stripped}'
            if proof.count(old_block) == 1:
                trials.append({
                    'label': f'semicolon_chain:{stripped[:30]}',
                    'edits': [[old_block, new_block]],
                })
            # Also try <;> variant if there's a preceding tactic
            if i > 0 and lines[i - 1].strip():
                prev_stripped = lines[i - 1].strip()
                prev_indent = len(lines[i - 1]) - len(lines[i - 1].lstrip())
                combined_old = '\n'.join(lines[i - 1:j])
                combined_new = ' ' * prev_indent + prev_stripped + ' <;> ' + stripped
                if proof.count(combined_old) == 1:
                    trials.append({
                        'label': f'semicolon_chain_prev:{stripped[:30]}',
                        'edits': [[combined_old, combined_new]],
                    })
        i = j
    return trials


ALL_RULES = [
    rule_parens_to_dollar,
    rule_remove_type_annotations,
    rule_inline_let,
    rule_simp_only_to_simp,
    rule_exact_have_inline,
    rule_apply_to_exact,
    rule_congr_fun_dollar,
    rule_by_omega_inline,
    rule_semicolon_chain,
]


def generate_trials(proof: str) -> list[dict]:
    """Apply all rewrite rules and return a flat list of trial dicts."""
    trials = []
    seen_labels = set()
    for rule_fn in ALL_RULES:
        try:
            for t in rule_fn(proof):
                if t['label'] not in seen_labels:
                    seen_labels.add(t['label'])
                    trials.append(t)
        except Exception as exc:
            print(f'  [warn] rule {rule_fn.__name__} raised: {exc}', flush=True)
    return trials


# ═══════════════════════════════════════════════════════════════════════════
#  Agent loop
# ═══════════════════════════════════════════════════════════════════════════

def extract_proof_body(code: str) -> str:
    """Return everything after `:= by` (the tactic block)."""
    m = re.search(r':=\s*by\b', code)
    if not m:
        raise ValueError('No `:= by` found in seed proof')
    return code[m.end():]


def run_trial_py(
    problem_dir: Path,
    base_file: Path,
    trials: list[dict],
    output_dir: Path,
    t0: int,
    h0: int,
    workers: int,
) -> list[dict]:
    """Invoke trial.py and return parsed trial-log.jsonl rows."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write trials to a temp JSON file
    trials_path = output_dir / 'trials.json'
    trials_path.write_text(json.dumps(trials, ensure_ascii=False))

    cmd = [
        sys.executable, str(TRIAL_PY),
        '--problem-dir', str(problem_dir),
        '--base', str(base_file),
        '--trials', str(trials_path),
        '--output', str(output_dir),
        '--t0', str(t0),
        '--h0', str(h0),
        '--workers', str(workers),
    ]
    print(f'  → running trial.py with {len(trials)} trials ...', flush=True)
    result = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  [error] trial.py exited {result.returncode}', flush=True)
        if result.stderr:
            print(f'  stderr: {result.stderr[:500]}', flush=True)
    # Also show stdout for live feedback
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            print(f'  trial: {line}', flush=True)

    # Parse trial-log.jsonl
    log_path = output_dir / 'trial-log.jsonl'
    rows = []
    if log_path.exists():
        for line in log_path.read_text().strip().split('\n'):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def run_verify_py(
    problem_dir: Path,
    candidate_file: Path,
    output_dir: Path,
    t0: int,
    h0: int,
) -> dict | None:
    """Invoke verify.py and return the summary dict."""
    cmd = [
        sys.executable, str(VERIFY_PY),
        '--problem-dir', str(problem_dir),
        '--candidate', str(candidate_file),
        '--output', str(output_dir),
        '--t0', str(t0),
        '--h0', str(h0),
    ]
    print(f'  → running verify.py ...', flush=True)
    result = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  [error] verify.py exited {result.returncode}', flush=True)
        if result.stderr:
            print(f'  stderr: {result.stderr[:500]}', flush=True)
        return None

    summary_path = output_dir / 'summary.json'
    if summary_path.exists():
        return json.loads(summary_path.read_text())
    return None


def select_best(rows: list[dict], current_j: float | None) -> dict | None:
    """Pick the trial with the lowest valid J that improves over current_j."""
    best = None
    for row in rows:
        j = row.get('J')
        if j is None:
            continue
        if row.get('error'):
            continue
        if row.get('label') == 'base':
            continue  # skip the base entry
        if best is None or j < best['J']:
            best = row
    if best is None:
        return None
    if current_j is not None and best['J'] >= current_j:
        return None  # no improvement
    return best


def find_candidate_file(output_dir: Path, row: dict) -> Path | None:
    """Locate the candidate.lean file for a trial result row."""
    dir_name = row.get('dir')
    if not dir_name:
        return None
    candidate = output_dir / 'screen' / dir_name / 'candidate.lean'
    if candidate.exists():
        return candidate
    return None


def main():
    ap = argparse.ArgumentParser(
        description='Automated proof-golf agent loop for Lean Refactor Arena.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('--problem-dir', type=Path, required=True,
                    help='Folder with input.json/agent-input.json and environment.json')
    ap.add_argument('--seed', type=Path, required=True,
                    help='Initial valid candidate .lean file')
    ap.add_argument('--output', type=Path, required=True,
                    help='Output directory for results')
    ap.add_argument('--t0', type=int, required=True,
                    help='Original proof token count')
    ap.add_argument('--h0', type=int, required=True,
                    help='Original raw heartbeats')
    ap.add_argument('--max-rounds', type=int, default=6,
                    help='Maximum rewrite rounds (default: 6)')
    ap.add_argument('--workers', type=int, default=2,
                    help='Parallel workers for trial.py (default: 2)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Generate trials JSON without running them')
    args = ap.parse_args()

    # Resolve paths
    problem_dir = args.problem_dir.resolve()
    seed_path = args.seed.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rate = args.h0 / args.t0  # hb per token

    # Read seed
    seed_code = seed_path.read_text()
    print(f'Seed: {seed_path}', flush=True)
    print(f'T0={args.t0}  H0={args.h0}  rate={rate:.1f}  max_rounds={args.max_rounds}', flush=True)

    # Extract proof body for info
    proof_body = extract_proof_body(seed_code)
    print(f'Proof body length: {len(proof_body)} chars', flush=True)

    # ── dry-run mode ─────────────────────────────────────────────────────
    if args.dry_run:
        trials = generate_trials(seed_code)
        out_path = output_dir / 'trials_dry.json'
        out_path.write_text(json.dumps(trials, ensure_ascii=False, indent=2))
        print(f'\n[dry-run] Generated {len(trials)} trials → {out_path}')
        for t in trials:
            print(f'  • {t["label"]}')
        return

    # ── agent loop ───────────────────────────────────────────────────────
    current_file = output_dir / 'current.lean'
    shutil.copy2(seed_path, current_file)
    shutil.copy2(seed_path, output_dir / 'seed.lean')

    current_j: float | None = None
    no_improve_streak = 0
    lessons: list[str] = []

    lessons.append(f'# Auto-rewrite Log\n')
    lessons.append(f'- Seed: `{seed_path}`')
    lessons.append(f'- T0={args.t0}, H0={args.h0}, rate={rate:.1f}')
    lessons.append(f'- Max rounds: {args.max_rounds}\n')

    for rnd in range(1, args.max_rounds + 1):
        print(f'\n{"="*60}', flush=True)
        print(f'Round {rnd}/{args.max_rounds}', flush=True)
        print(f'{"="*60}', flush=True)

        current_code = current_file.read_text()

        # Generate trials from current code
        trials = generate_trials(current_code)
        print(f'  Generated {len(trials)} trial candidates', flush=True)

        if not trials:
            print('  No trials generated — stopping.', flush=True)
            lessons.append(f'\n## Round {rnd}\n- No trials generated. Stopping.')
            break

        # Unique output dir for this round
        ts = int(time.time())
        round_dir = output_dir / f'round_{rnd:02d}_{ts}'

        # Run trial.py
        rows = run_trial_py(
            problem_dir=problem_dir,
            base_file=current_file,
            trials=trials,
            output_dir=round_dir,
            t0=args.t0,
            h0=args.h0,
            workers=args.workers,
        )

        print(f'  Got {len(rows)} results', flush=True)

        # Find current base J from results
        base_rows = [r for r in rows if r.get('label') == 'base']
        if base_rows and base_rows[0].get('J') is not None:
            if current_j is None:
                current_j = base_rows[0]['J']
                print(f'  Base J={current_j:.2f}  T={base_rows[0].get("T")}  '
                      f'hb_k={base_rows[0].get("hb_k")}', flush=True)

        # Select best improving candidate
        best = select_best(rows, current_j)

        # Log round results
        valid_rows = [r for r in rows if r.get('J') is not None and r.get('label') != 'base']
        valid_rows.sort(key=lambda r: r['J'])

        round_log = f'\n## Round {rnd}\n'
        round_log += f'- Trials generated: {len(trials)}\n'
        round_log += f'- Valid results: {len(valid_rows)}\n'
        round_log += f'- Current J: {current_j}\n'

        if valid_rows:
            round_log += f'- Top 3 results:\n'
            for r in valid_rows[:3]:
                round_log += (f'  - {r["label"]}: J={r["J"]}  T={r.get("T")}  '
                              f'hb_k={r.get("hb_k")}\n')

        if best:
            no_improve_streak = 0
            print(f'  ✓ Improvement found: {best["label"]}  '
                  f'J={best["J"]:.2f} (was {current_j})', flush=True)

            # Find and adopt the candidate file
            candidate = find_candidate_file(round_dir, best)
            if candidate:
                shutil.copy2(candidate, current_file)
                current_j = best['J']
                round_log += (f'- **Adopted**: {best["label"]}  '
                              f'J={best["J"]}  T={best.get("T")}  '
                              f'hb_k={best.get("hb_k")}\n')
            else:
                print(f'  [warn] candidate file not found for {best["dir"]}', flush=True)
                no_improve_streak += 1
                round_log += f'- Candidate file not found\n'
        else:
            no_improve_streak += 1
            print(f'  ✗ No improvement (streak={no_improve_streak})', flush=True)
            round_log += f'- No improvement (streak={no_improve_streak})\n'

        lessons.append(round_log)

        # Early stop: 2 consecutive rounds with no improvement
        if no_improve_streak >= 2:
            print(f'\n  Stopping: {no_improve_streak} consecutive rounds without improvement.',
                  flush=True)
            lessons.append(f'\nStopped early: {no_improve_streak} consecutive rounds without improvement.\n')
            break

    # ── save best ────────────────────────────────────────────────────────
    best_path = output_dir / 'best.lean'
    shutil.copy2(current_file, best_path)
    print(f'\nBest candidate saved to {best_path}', flush=True)
    print(f'Final J={current_j}', flush=True)

    # ── final verify ─────────────────────────────────────────────────────
    verify_dir = output_dir / 'verify_best'
    if verify_dir.exists():
        # verify.py refuses existing dirs; use a unique name
        verify_dir = output_dir / f'verify_best_{int(time.time())}'
    summary = run_verify_py(
        problem_dir=problem_dir,
        candidate_file=best_path,
        output_dir=verify_dir,
        t0=args.t0,
        h0=args.h0,
    )
    if summary:
        print(f'\nVerification: {json.dumps(summary, indent=2)}', flush=True)
        lessons.append(f'\n## Verification\n')
        lessons.append(f'```json\n{json.dumps(summary, indent=2)}\n```\n')
    else:
        print('\n[warn] Verification failed or produced no summary.', flush=True)
        lessons.append(f'\n## Verification\n- Failed or no summary produced.\n')

    # ── write LESSONS.md ─────────────────────────────────────────────────
    lessons_path = output_dir / 'LESSONS.md'
    lessons_path.write_text('\n'.join(lessons) + '\n')
    print(f'Log saved to {lessons_path}', flush=True)


if __name__ == '__main__':
    main()
