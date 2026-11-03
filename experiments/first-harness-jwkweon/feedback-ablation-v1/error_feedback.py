"""Experiment-local feedback policy; extraction uses only archived compiler logs."""
from pathlib import Path
import re

import harness as h


MODES = ('legacy', 'structured_v1')
DIAGNOSTIC = re.compile(
    r'^(?:(?P<path>.+?):(?P<line>\d+):(?P<column>\d+):\s*)?'
    r'(?P<severity>error|warning|information|info)'
    r'(?:\((?P<code>[^()\r\n]+)\))?:\s*(?P<message>.*)$')
CASE = re.compile(r'^\s*case\s+(.+?)\s*$')
LOCAL = re.compile(r'^\s*[^\s:]+(?:\s+[^\s:]+)*\s*:\s*')


def validate_mode(mode):
    if mode not in MODES:
        raise ValueError('error_feedback_mode must be legacy or structured_v1')
    return mode


def _normalize(text, run_directory):
    return text.replace(run_directory, '<RUN>')


def _extract(log, run_directory):
    lines = log.splitlines()
    diagnostics = [(i, DIAGNOSTIC.match(line)) for i, line in enumerate(lines)]
    diagnostics = [(i, match) for i, match in diagnostics if match]
    first = next(((i, match) for i, match in diagnostics
                  if match['severity'] == 'error'), None)
    if first is None:
        # A failed compiler may print an unlocated/nonstandard fatal message.
        # Preserve it as evidence instead of inventing a Lean diagnostic.
        return {'location': None, 'message': _normalize(log.strip(), run_directory),
                'case': None, 'goal': None, 'local_context': '', 'truncated': False}
    start, match = first
    end = next((i for i, _ in diagnostics if i > start), len(lines))
    # Keep a tagged diagnostic's code in the existing message field, without
    # changing the schema or allocating a separate field from the same cap.
    message = (f"{match['severity']}({match['code']}): {match['message']}"
               if match['code'] is not None else match['message'])
    block = [message, *lines[start + 1:end]]
    goal_at = next((i for i, line in enumerate(block) if line.lstrip().startswith('⊢')), None)
    case_at = next((i for i, line in enumerate(block) if CASE.match(line)), None)
    # Never borrow the context or case of a later goal in the same diagnostic.
    if goal_at is not None:
        cases = [i for i in range(goal_at) if CASE.match(block[i])]
        case_at = cases[-1] if cases else None
        context_start = case_at + 1 if case_at is not None else next(
            (i for i in range(1, goal_at) if LOCAL.match(block[i])), goal_at)
        message_end = case_at if case_at is not None else context_start
        context_lines = block[context_start:goal_at]
        goal_end = next((i for i in range(goal_at + 1, len(block))
                         if CASE.match(block[i]) or block[i].lstrip().startswith('⊢')
                         or not block[i].strip()), len(block))
        goal = '\n'.join(block[goal_at:goal_end]).strip()
        context = '\n'.join(context_lines[-12:]).strip()
        context_truncated = len(context_lines) > 12
    else:
        message_end = case_at if case_at is not None else len(block)
        goal, context, context_truncated = None, '', False
    path = match['path']
    location = (f"{_normalize(path, run_directory)}:{int(match['line'])}:{int(match['column'])}"
                if path is not None else None)
    return {'location': location,
            'message': _normalize('\n'.join(block[:message_end]).strip(), run_directory),
            'case': CASE.match(block[case_at])[1] if case_at is not None else None,
            'goal': _normalize(goal, run_directory) if goal is not None else None,
            'local_context': _normalize(context, run_directory), 'truncated': context_truncated}


def _bounded_details(value, limit):
    """Clip values, never serialized JSON; retain the message before verbose locals."""
    def encoded():
        return h.canonical(value)

    caps = {'message': 1100, 'location': 220, 'case': 120, 'goal': 500, 'local_context': 650}
    for key, cap in caps.items():
        if value[key] is not None and len(value[key]) > cap:
            value[key] = value[key][:cap]
            value['truncated'] = True
    if len(encoded()) <= limit:
        return encoded()
    value['truncated'] = True
    for key in ('local_context', 'goal', 'case', 'location', 'message'):
        original = value[key]
        if not original:
            continue
        value[key] = ''
        if len(encoded()) > limit:
            continue
        low, high = 0, len(original)
        while low < high:
            middle = (low + high + 1) // 2
            value[key] = original[:middle]
            if len(encoded()) <= limit:
                low = middle
            else:
                high = middle - 1
        value[key] = original[:low]
        return encoded()
    raise ValueError('Feedback limit cannot contain the structured diagnostic envelope')


def _failed_log(result, evaluation):
    for environment, row in result.get('environments', {}).items():
        if row.get('valid') or (row.get('error') or {}).get('kind') != 'compile':
            continue
        for run in row.get('runs', []):
            if run.get('returncode') and not run.get('timed_out'):
                folder = (Path(evaluation) / environment).resolve()
                path = (folder / run['log']).resolve()
                if not path.is_relative_to(folder):
                    raise ValueError('Compiler log path escapes evaluation environment')
                return path.read_text(encoding='utf-8')
        raise ValueError('Failed compile result has no archived failing run')
    return None


def format_feedback(result, rejection, limit, run_directory, evaluation, mode='legacy'):
    validate_mode(mode)
    feedback = h.feedback(result, rejection, limit, run_directory)
    if mode == 'legacy' or rejection or result['valid'] or h.environment_failed(result):
        return feedback
    log = _failed_log(result, evaluation)
    if log is not None:
        feedback['details'] = _bounded_details(_extract(log, run_directory), limit)
    return feedback
