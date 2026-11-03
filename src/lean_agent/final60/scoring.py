"""Official per-problem score (local estimate) and the arena proof tokenizer.

Score = mean(L, H, C) with L = 100(1 - T/T0) on proof-body tokens, H = 100(1 - HB/HB0)
on raw `#count_heartbeats` style counts and C = 100 * passed/total listed toolchains
(official Space app.py, "Scoring (multi-objective)"). Negative L and H are allowed;
a proof that compiles nowhere scores 0. The original proof scores exactly 100/3.

Heartbeat ratios use raw counts. The official file stores raw // 1000, which gives the
same ratio up to rounding. Which toolchain the official worker measures HB on is not
public; callers pass the primary (first listed) version's median raw count.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOKENIZER_PATH = REPO / "experiments/proof-analyze/proof_tokens.py"
ORIGINAL_SCORE = 100.0 / 3.0
EPSILON = 1e-9
_tokenizer = None


def _positive(name: str, value) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")


def length_reduction(tokens: int, base_tokens: int) -> float:
    _positive("base_tokens", base_tokens)
    return 100.0 * (1.0 - tokens / base_tokens)


def heartbeat_reduction(raw_hb: int, base_raw_hb: int) -> float:
    _positive("base_raw_hb", base_raw_hb)
    return 100.0 * (1.0 - raw_hb / base_raw_hb)


def problem_score(tokens: int, raw_hb: int, passed: int, total: int, base_tokens: int, base_raw_hb: int) -> float:
    """Official mean of the three axes; 0 when the proof compiles on no listed toolchain."""
    _positive("total", total)
    if type(passed) is not int or not 0 <= passed <= total:
        raise ValueError("passed must be an integer in 0..total")
    if passed == 0:
        return 0.0
    if type(tokens) is not int or tokens < 0 or type(raw_hb) is not int or raw_hb < 0:
        raise ValueError("tokens and raw heartbeats must be non-negative integers")
    transfer = 100.0 * passed / total
    return (length_reduction(tokens, base_tokens) + heartbeat_reduction(raw_hb, base_raw_hb) + transfer) / 3.0


def screen_score(tokens: int, raw_hb: int, base_tokens: int, base_raw_hb: int) -> float:
    """Primary-version screening estimate, assuming every listed version will accept it."""
    return problem_score(tokens, raw_hb, 1, 1, base_tokens, base_raw_hb)


def max_possible(tokens: int, base_tokens: int) -> float:
    """Upper bound for pruning: zero heartbeats and full version transfer."""
    return (length_reduction(tokens, base_tokens) + 100.0 + 100.0) / 3.0


def improves(new_score: float, old_score: float, *, epsilon: float = EPSILON) -> bool:
    """Strict improvement (Delta L + Delta H > 0) with a float tolerance."""
    return new_score > old_score + epsilon


def tokenizer():
    """The arena-compatible proof_length counter used by FinalEvaluator."""
    global _tokenizer
    if _tokenizer is None:
        spec = importlib.util.spec_from_file_location("final60_proof_tokens", TOKENIZER_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _tokenizer = module.proof_length
    return _tokenizer


def count_tokens(code: str, statement: str) -> int:
    return tokenizer()(code, statement)
