"""Small, portable result tables (no raw game content). CC0-1.0."""
from collections import Counter, defaultdict
import csv


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def warning_cause(warning):
    if warning['code'] != 'unsupported':
        return warning['code']
    return {
        'Expected =': 'missing_assignment_operator',
        'Unsupported value': 'unsupported_value',
        'Unsupported statement': 'return_break_or_unsupported_statement',
        'Local function skipped': 'local_function',
        'Nested function skipped': 'nested_function',
        'Unsupported assignment suffix': 'assignment_suffix',
        'Expected assignment': 'non_assignment_token',
    }.get(warning['message'], 'malformed_or_unsupported_syntax')


def group_warnings(warnings, key):
    counts, examples = Counter(), defaultdict(list)
    for warning in warnings:
        group = key(warning)
        counts[group] += 1
        example = f"{warning['file']}:{warning['line']}"
        if len(examples[group]) < 3 and example not in examples[group]:
            examples[group].append(example)
    return [dict(cause=group, count=counts[group], examples='; '.join(examples[group]))
            for group in sorted(counts)]


def write_warning_audit(directory, warnings):
    current = {r['cause']: r for r in group_warnings(warnings, warning_cause)}
    baseline_path = directory / 'warnings_before_audit.csv'
    baseline = {}
    if baseline_path.exists():
        with baseline_path.open(encoding='utf-8', newline='') as stream:
            baseline = {r['cause']: r for r in csv.DictReader(stream)}
    rows = []
    for cause in sorted(current.keys() | baseline.keys()):
        prior = baseline.get(cause, {})
        row = dict(current.get(cause, dict(cause=cause, count=0, examples=prior.get('examples', ''))))
        row['baseline_count'] = int(prior.get('count', 0))
        row['fixed'] = 'yes' if row['baseline_count'] and not row['count'] else 'no'
        rows.append(row)
    write_csv(directory / 'warnings_by_cause.csv',
              ['cause', 'count', 'examples', 'fixed', 'baseline_count'], rows)
