"""Bounded identifying descriptions; input text is never executed."""
import re
from pathlib import Path


def normalize(text):
    return ' '.join(text.split())


def strings(root):
    tables = {}
    for lang, folder in [('en', 'english'), ('ru', 'russian')]:
        table = {}
        for line, raw in enumerate((Path(root)/folder/'string.txt').read_text(encoding='utf-8-sig').splitlines(), 1):
            if not raw.strip() or raw.lstrip().startswith(('//', '#', ';')):
                continue
            match = re.fullmatch(r'"([^"\t]+)"\s*\t\s*"(.*)"\s*', raw)
            if not match:
                raise ValueError(f'invalid string record: {lang}:{line}')
            key, text = match.groups()
            if key in table:
                raise ValueError(f'duplicate string key: {lang}:{line}')
            table[key] = (text, line)
        tables[lang] = table
    return tables


def base(key):
    return key[:-5] if key.endswith('_name') else key


def select(row, name, tables, lore=None):
    if lore is None:
        lore = {normalize(text) for table in tables.values() for key, (text, _) in table.items() if key.endswith('_desc_lore') and normalize(text)}
    texts, evidence, statuses = {}, {}, []
    for lang in ['en', 'ru']:
        table = tables[lang]
        own = [row['defName']]
        keys = name.get('source_key_'+lang, []) if name else []
        # Derived names can reference a different product: never treat that as own text.
        if name and name['name_status'] in ('exact', 'own_field', 'prefixed'):
            own = [base(k) for k in keys] + own
        registry_key = row.get('nameKey', '')
        if registry_key and not registry_key.startswith('itemSubType_'):
            own.append(base(registry_key))
        candidates = [(k+'_short_desc', 'exact' if k == row['defName'] else (name or {}).get('name_status', 'own_field')) for k in dict.fromkeys(own)]
        categories = [k for k in [registry_key, *keys] if k.startswith('itemSubType_') and not k.endswith(('_desc', '_desc_lore'))]
        candidates += [(k+'_short_desc', 'category') for k in dict.fromkeys(categories)]
        candidates += [(k+'_desc', 'exact' if k == row['defName'] else (name or {}).get('name_status', 'own_field')) for k in dict.fromkeys(own)]
        candidates += [(k+'_desc', 'category') for k in dict.fromkeys(categories)]
        texts[lang] = ''
        evidence[lang] = {'key': '', 'line': None, 'status': 'none', 'rejected': []}
        for key, status in candidates:
            if '_desc_lore' in key or key not in table:
                continue
            text, line = table[key]
            text = normalize(text)
            if not text or len(text) > 200:
                evidence[lang]['rejected'].append({'key': key, 'line': line, 'reason': 'empty_or_long'})
                continue
            if text in lore:
                evidence[lang]['rejected'].append({'key': key, 'line': line, 'reason': 'duplicates_lore'})
                continue
            texts[lang] = text
            evidence[lang].update(key=key, line=line, status=status)
            statuses.append(status)
            break
    # A shared status is necessarily conservative when language fallback differs.
    order = ['none', 'exact', 'own_field', 'prefixed', 'derived', 'category']
    status = max(statuses, key=order.index) if statuses else 'none'
    placeholders = any(re.search(r'\$[^$]+\$', t) for t in texts.values())
    return texts, status, placeholders, evidence
