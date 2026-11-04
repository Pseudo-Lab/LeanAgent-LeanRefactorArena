"""Bounded native tactic search; no model dispatch or independent evaluator.

Local patching/goal collection derives from repair PRs #41/#42. Only a completed
candidate is returned to the caller for ordinary full-proof verification.
"""
import math
from pathlib import Path
import time

from . import native
from .artifacts import canonical, read, sha, write

TACTICS = ('rfl', 'assumption', 'trivial', 'simp', 'omega', 'grind')
DEFAULTS = {'tactics': list(TACTICS), 'max_attempts': 6, 'max_sites': 3,
            'inspection_seconds': 30, 'search_seconds': 120, 'memory_mib': 4096}


def enabled(config):
    return 'autosolver' in config.get('agent', {})


def settings(config):
    return {**DEFAULTS, **config['agent']['autosolver']}


def validate(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('Expected bounded autosolver settings')
    merged = {**DEFAULTS, **value}
    tactics = merged['tactics']
    if (not isinstance(tactics, list) or not tactics or len(tactics) > len(TACTICS)
            or any(t not in TACTICS for t in tactics) or len(set(tactics)) != len(tactics)):
        raise ValueError('AutoSolver tactics must be distinct members of the fixed tactic set')
    for key, maximum in [('max_attempts', 32), ('max_sites', 8), ('memory_mib', 16384)]:
        if type(merged[key]) is not int or not 1 <= merged[key] <= maximum:
            raise ValueError('Invalid autosolver ' + key)
    for key, maximum in [('inspection_seconds', 120), ('search_seconds', 600)]:
        v = merged[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= maximum:
            raise ValueError('Invalid autosolver ' + key)


def eligible(config, raw, code, result):
    from .models import receipt
    if not enabled(config) or code is None or not result or result['valid'] or receipt(raw)['cost_usd'] is None:
        return False
    if (result.get('error') or {}).get('kind') == 'validation':
        return False
    rows = result.get('environments', {}).values()
    return bool(result.get('environments')) and not any(
        (row.get('error') or {}).get('kind') in ('environment', 'timeout')
        or any(run.get('timed_out') or run.get('returncode', 0) < 0 for run in row.get('runs', []))
        for row in rows)


def _search(options, original, observe):
    """Deterministic decisions over recorded native observations and durations."""
    spent, inspections, attempts, closed = 0.0, 0, [], 0
    initial, current = None, original
    seen = {sha(original)}

    def inspect(code):
        nonlocal spent, inspections
        remaining = options['search_seconds'] - spent
        if remaining <= 0:
            return None
        timeout = min(options['inspection_seconds'], remaining)
        report, seconds = observe(code, timeout, options['memory_mib'])
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('Invalid native duration')
        if report.get('source_sha256') != sha(code):
            raise ValueError('Native observation source differs')
        spent += seconds
        inspections += 1
        return report

    def finish(status, candidate=None):
        return {'status': status, 'original_sha256': sha(original), 'candidate_code': candidate,
                'candidate_sha256': sha(candidate) if candidate is not None else None,
                'attempts': attempts, 'inspections': inspections, 'native_seconds': spent,
                'sites_closed': closed, 'initial_site': initial}

    report = inspect(current)
    if report is None:
        return finish('time_limit')
    if report['kind'] != 'proof':
        return finish('timeout' if report['kind'] == 'timeout' else 'unavailable')
    initial = native.select_site(report, current)
    if initial is None:
        return finish('no_supported_goal')
    while report['errors']:
        if closed >= options['max_sites']:
            return finish('site_limit')
        site = native.select_site(report, current)
        if site is None:
            return finish('no_supported_goal')
        for tactic in options['tactics']:
            if len(attempts) >= options['max_attempts']:
                return finish('attempt_limit')
            proposal, region = native.patch_site(current, site, 'by ' + tactic)
            item = {'tactic': tactic, 'parent_sha256': sha(current), 'candidate_sha256': sha(proposal), 'solved': False}
            attempts.append(item)
            if sha(proposal) in seen:
                item['status'] = 'duplicate'
                continue
            seen.add(sha(proposal))
            observed = inspect(proposal)
            if observed is None:
                item['status'] = 'time_limit'
                return finish('time_limit')
            if observed['kind'] != 'proof':
                item['status'] = 'timeout' if observed['kind'] == 'timeout' else 'unavailable'
                return finish(item['status'])
            item['solved'] = native.local_closed(observed, region)
            item['status'] = 'closed' if item['solved'] else 'unresolved'
            if item['solved']:
                current, report = proposal, observed
                closed += 1
                break
        else:
            return finish('exhausted')
    return finish('candidate', current)


def replay_search(config, code, record):
    if record.get('schema_version') != 1 or record.get('settings') != settings(config):
        raise ValueError('AutoSolver settings/record differ')
    observations = iter(record['observations'])
    def observe(source, timeout, memory):
        try:
            row = next(observations)
        except StopIteration as exc:
            raise ValueError('Missing native observation') from exc
        if (row['source_sha256'] != sha(source) or row['timeout'] != timeout or row['memory_mib'] != memory):
            raise ValueError('AutoSolver inspection differs from replay')
        return row['report'], row['elapsed_seconds']
    outcome = _search(settings(config), code, observe)
    if next(observations, None) is not None or outcome != record['outcome']:
        raise ValueError('AutoSolver search outcome differs from replay')
    return outcome


def search(config, code, folder, inspect):
    folder = Path(folder)
    saved = folder / 'search.json'
    if saved.exists():
        record = read(saved)
        replay_search(config, code, record)
        return record
    if folder.exists():
        folder.rename(folder.with_name(folder.name + '-incomplete-' + str(time.time_ns())))
    folder.mkdir(parents=True)
    observations = []
    def observe(source, timeout, memory):
        start = time.monotonic()
        report = inspect(source, folder / f'inspect-{len(observations)+1:03}', timeout, memory)
        seconds = time.monotonic() - start
        observations.append({'source_sha256': sha(source), 'timeout': timeout, 'memory_mib': memory,
                             'report': report, 'elapsed_seconds': seconds})
        return report, seconds
    outcome = _search(settings(config), code, observe)
    record = {'schema_version': 1, 'settings': settings(config), 'observations': observations, 'outcome': outcome}
    write(saved, record)
    return record


def summary(outcome, parent_id):
    site = outcome['initial_site']
    goal = None
    if site:
        goal = {'target': site['goal']['target'][:1200], 'source_candidate_id': parent_id,
                'scope': 'first unresolved native state; not all proof obligations',
                'local_context': [{key: (row.get(key) or '')[:600] for key in ('name', 'type', 'value')}
                                  for row in site['goal']['local_context'] if not row.get('implementation_detail')][-12:]}
    return {'status': outcome['status'], 'attempts': len(outcome['attempts']), 'inspections': outcome['inspections'],
            'native_seconds': outcome['native_seconds'], 'sites_closed': outcome['sites_closed'],
            'source_candidate_id': parent_id, 'native_goal': goal, 'model_calls': 0}
