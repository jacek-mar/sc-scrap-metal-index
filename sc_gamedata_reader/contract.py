"""Versioned consumer helpers. CC0-1.0."""
FORMAT_VERSION = 2
CALL_FORMAT_VERSION = 1


def iter_assignments(document, scope=None):
    """Yield assignments in source order; None includes every scope."""
    if document.get('format_version') != FORMAT_VERSION:
        raise ValueError('Unsupported reader format_version')
    for assignment in document['assignments']:
        if scope is None or assignment['scope'] == scope:
            yield assignment


class ParseResult(dict):
    """JSON-serializable dictionary with an assignment iterator."""
    def iter_assignments(self, scope=None):
        return iter_assignments(self, scope)

    def iter_calls(self, scope=None, callee=None):
        return iter_calls(self, scope, callee)


def iter_calls(document, scope=None, callee=None):
    """Yield lexical call records; older exports must be regenerated."""
    if document.get('format_version') != FORMAT_VERSION or document.get('call_format_version') != CALL_FORMAT_VERSION:
        raise ValueError('Unsupported or missing structured-call format')
    for call in document['calls']:
        if (scope is None or call['scope'] == scope) and (callee is None or call['callee'] == callee):
            yield call


def table_get(value, key, default=None):
    """Look up a Lua key without executing or resolving it; last duplicate wins."""
    if isinstance(value, list):
        if type(key) in (int, float) and 1 <= key <= len(value) and key % 1 == 0:
            return value[int(key)-1]
        return default
    if not isinstance(value, dict):
        return default
    if '$table' in value:
        for entry in reversed(value['$table']):
            stored = entry['key']
            numeric = type(stored) in (int, float) and type(key) in (int, float)
            if (type(stored) is type(key) or numeric) and stored == key:
                return entry['value']
        return default
    if any(k.startswith('$') for k in value):
        return default
    return value.get(key, default) if isinstance(key, str) else default
