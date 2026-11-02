"""Conservative source edits; Lean, not this generator, decides validity."""
import re


def split_rules(text):
    """Split at top-level commas. Refuse strings/comments rather than misparse them."""
    if any(x in text for x in ['--', '/-', '"']):
        return None
    stack, cuts, begin = [], [], 0
    pairs = {')': '(', ']': '[', '}': '{', '⟩': '⟨'}
    for i, c in enumerate(text):
        if c in '([{⟨':
            stack.append(c)
        elif c in pairs:
            if not stack or stack.pop() != pairs[c]:
                return None
        elif c == ',' and not stack:
            cuts.append(text[begin:i].strip()); begin = i + 1
    if stack:
        return None
    cuts.append(text[begin:].strip())
    return cuts if all(cuts) else None


def variants(code, statement):
    if not code.startswith(statement):
        raise ValueError('Statement mismatch')
    body = code[len(statement):]
    # Do not edit comments or strings accidentally. Current pilot seeds have neither.
    if any(x in body for x in ['--', '/-', '"']):
        return []
    edits = []
    for match in re.finditer(r'\b(simp(?:_rw|_all)?|simpa|grind)(\s+only)?\s*\[', body):
        start, depth, end = match.end(), 1, match.end()
        while end < len(body) and depth:
            depth += (body[end] == '[') - (body[end] == ']')
            end += 1
        if depth:
            continue
        rules = split_rules(body[start:end - 1])
        if not rules:
            continue
        drops = [tuple(range(len(rules)))] + [(i,) for i in range(len(rules))]
        if len(rules) > 3:
            mid = len(rules) // 2
            drops += [tuple(range(mid)), tuple(range(mid, len(rules)))]
        for drop in drops:
            kept = ', '.join(r for i, r in enumerate(rules) if i not in drop)
            edits.append((f'rules:{match.start()}:drop:{drop}', start, end - 1, kept))
        if match.group(2):
            edits.append((f'only:{match.start()}:omit', match.start(2), match.end(2), ''))
        elif match.group(1) in ('simp', 'simpa', 'grind'):
            edits.append((f'only:{match.start()}:add', match.end(1), match.end(1), ' only'))
    # Simple named argument deletions only; compound expressions are left intact.
    for m in re.finditer(r'\s*\([\wεϑι]+\s*:=\s*[\wεϑι.]+\)', body):
        edits.append((f'argument:{m.start()}:omit', m.start(), m.end(), ''))
    # Isolated convenience wrappers, including no-op final rfl, are checked by Lean.
    for m in re.finditer(r'(?m)^([ \t]*)(classical|rfl)\s*\n', body):
        edits.append((f'line:{m.start()}:omit-{m.group(2)}', m.start(), m.end(), ''))
    seen, out = {code}, []
    for label, a, b, replacement in edits:
        candidate = statement + body[:a] + replacement + body[b:]
        if candidate not in seen:
            seen.add(candidate); out.append((label, candidate))
    return out
