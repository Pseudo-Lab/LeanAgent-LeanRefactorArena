"""Recorded model compression of the same first diagnostic used by structured_v1.

Only submit waits for a fresh summarizer. Replay reads the archived response and
never launches a model, waits, or invokes Lean. Invalid/missing responses use the
prespecified structured fallback and remain visible as treatment failures.
"""
import json
from pathlib import Path
import time

import harness as h
import legacy_error_feedback as legacy

MODES = ('structured_v1', 'semantic_v1')
KEYS = {'location', 'message', 'case', 'goal', 'local_context', 'truncated'}


def validate_mode(mode):
    if mode not in MODES:
        raise ValueError('Expected structured_v1 or semantic_v1')
    return mode


def validate_summary(value, diagnostic, limit):
    if not isinstance(value, dict) or set(value) != KEYS:
        raise ValueError('Summary must use the exact diagnostic schema')
    if type(value['truncated']) is not bool:
        raise ValueError('truncated must be boolean')
    for key in ('location', 'case'):
        if value[key] != diagnostic[key]:
            raise ValueError(key + ' must match the source verbatim')
    for key in ('message', 'local_context'):
        if not isinstance(value[key], str):
            raise ValueError(key + ' must be a string')
    if not value['message'].strip():
        raise ValueError('Empty error explanation')
    goal = diagnostic['goal']
    if goal is None:
        if value['goal'] is not None:
            raise ValueError('Invented goal')
    else:
        if (not isinstance(value['goal'], str) or not value['goal']
                or value['goal'] not in goal):
            raise ValueError('Goal must be a contiguous verbatim source span')
        # Reserve 200 chars for an explanation. A goal that fits this envelope
        # must be copied whole, not rewritten or selectively shortened.
        envelope = {**diagnostic, 'message': '', 'local_context': '', 'truncated': True}
        if len(h.canonical(envelope)) + 200 <= limit and value['goal'] != goal:
            raise ValueError('The full goal fits and must be preserved')
    original_lines = diagnostic['local_context'].splitlines()
    cursor = 0
    for line in value['local_context'].splitlines():
        try:
            cursor = original_lines.index(line, cursor) + 1
        except ValueError as error:
            raise ValueError('Context must select whole original lines in order') from error
    if (diagnostic['truncated'] or any(value[k] != diagnostic[k]
            for k in ('message', 'goal', 'local_context'))) and not value['truncated']:
        raise ValueError('Omission or compression must be marked truncated')
    encoded = h.canonical(value)
    if len(encoded) > limit:
        raise ValueError(f'Summary is {len(encoded)} characters; limit is {limit}')
    return encoded


def format_feedback(result, rejection, limit, run_directory, evaluation,
                    mode='structured_v1', *, replay=False):
    validate_mode(mode)
    feedback = legacy.format_feedback(result, rejection, limit, run_directory,
                                      evaluation, 'structured_v1')
    if mode == 'structured_v1' or rejection or result['valid'] or h.environment_failed(result):
        return feedback
    log = legacy._failed_log(result, evaluation)
    if log is None:
        return feedback
    diagnostic = legacy._extract(log, run_directory)
    folder = Path(evaluation).parent / 'summary'
    request_path, response_path = folder / 'request.json', folder / 'response.json'
    request = {'schema_version': 1, 'details_character_limit': limit,
               'diagnostic': diagnostic,
               'source_log_sha256': h.digest(log),
               'summarizer_prompt_sha256': h.digest(
                   (Path(run_directory) / 'input/summarizer-prompt.txt').read_bytes())}
    if replay:
        if h.read(request_path) != request:
            raise ValueError('Summary request does not match the archived compiler log')
        receipt = h.read(folder / 'receipt.json')
        if receipt['status'] == 'accepted':
            if receipt['fallback'] is not None:
                raise ValueError('Accepted summary cannot use fallback')
            encoded = validate_summary(h.read(response_path), diagnostic, limit)
            if h.digest(response_path.read_bytes()) != receipt['response_sha256']:
                raise ValueError('Summary response hash mismatch')
            feedback['details'] = encoded
        elif receipt['status'] == 'invalid':
            if (receipt['fallback'] != 'structured_v1'
                    or h.digest(response_path.read_bytes()) != receipt['response_sha256']):
                raise ValueError('Invalid summary receipt mismatch')
            try:
                validate_summary(h.read(response_path), diagnostic, limit)
            except (ValueError, TypeError, KeyError):
                pass
            else:
                raise ValueError('An archived invalid summary is now valid')
        elif receipt['status'] == 'timeout':
            if (response_path.exists() or receipt['response_sha256'] is not None
                    or receipt['fallback'] != 'structured_v1'):
                raise ValueError('Timeout summary receipt mismatch')
        else:
            raise ValueError('Unknown summary receipt status')
        return feedback
    h.write(request_path, request)
    started = time.monotonic()
    # Separate from the fixed Lean invocation timeout. This is orchestration
    # latency only; no compiler work occurs while awaiting the summarizer.
    while not response_path.exists() and time.monotonic() - started < 1800:
        time.sleep(0.5)
    receipt = {'wait_seconds': round(time.monotonic() - started, 6),
               'status': 'timeout', 'response_sha256': None,
               'fallback': 'structured_v1', 'model_internal_calls': None,
               'cost_usd': None}
    if response_path.exists():
        receipt['response_sha256'] = h.digest(response_path.read_bytes())
        try:
            feedback['details'] = validate_summary(h.read(response_path), diagnostic, limit)
            receipt.update(status='accepted', fallback=None)
        except (ValueError, TypeError, KeyError) as error:
            receipt.update(status='invalid', validation_error=str(error))
    h.write(folder / 'receipt.json', receipt)
    return feedback
