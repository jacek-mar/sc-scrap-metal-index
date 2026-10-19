import re

PAIR = re.compile(r'^\s*"((?:\\.|[^"\\])*)"\s+"((?:\\.|[^"\\])*)"\s*$')


def unescape(value):
    return re.sub(r'\\([\\"nrt])', lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), value)


def read_strings(path):
    values, duplicates, invalid = {}, [], []
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    for line, text in enumerate(lines, 1):
        match = PAIR.fullmatch(text)
        if not match:
            invalid.append(line)
            continue
        key, value = map(unescape, match.groups())
        if key in values:
            duplicates.append({'key': key, 'line': line})
        values[key] = value
    return values, dict(lines=len(lines), pairs=len(lines)-len(invalid), keys=len(values), duplicates=duplicates, invalid=invalid)
