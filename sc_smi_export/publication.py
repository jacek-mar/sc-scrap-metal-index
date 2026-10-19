"""Bounded public-output audit; reports filenames/rules, never matched data."""
import csv
import json
import os
import re
from html.parser import HTMLParser

from .descriptions import normalize

SITE_URLS = {
    'https://github.com/jacek-mar/sc-server-under-the-hood',
    'https://github.com/jacek-mar/sc-scrap-metal-index',
}


class SiteHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []
        self.errors = []
        self.csp = ''

    def handle_data(self, data):
        self.values.append(data)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.values.extend(attrs.values())
        if tag == 'meta' and attrs.get('http-equiv', '').lower() == 'content-security-policy':
            self.csp = attrs.get('content', '')
        for key, value in attrs.items():
            if key.startswith('on') or key == 'style':
                self.errors.append('inline executable/style attribute')
            if key in {'src', 'href', 'action', 'srcset'} and value:
                if re.match(r'(?i)^(?:[a-z][a-z0-9+.-]*:|//)', value) and value not in SITE_URLS:
                    self.errors.append('external site URL')
                if key == 'src' and (value in SITE_URLS or value.startswith('//')):
                    self.errors.append('external site resource')
        if tag == 'script' and not attrs.get('src'):
            self.errors.append('inline script')


def site_rules(path, text):
    errors = []
    if re.search(r'\b(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write)\b', text):
        errors.append('HTML insertion API')
    if re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\s*\(', text):
        errors.append('network API')
    for url in re.findall(r'https?://[^\s\'"<>`)]+', text):
        if url not in SITE_URLS:
            errors.append('external site URL')
    if re.search(r'(?i)(?:url\s*\(|@import)', text) and path.suffix == '.css':
        errors.append('CSS external resource mechanism')
    if path.suffix == '.html':
        parser = SiteHTML(); parser.feed(text)
        errors.extend(parser.errors)
        directives = {part.split()[0]: part.split()[1:] for part in parser.csp.split(';') if part.strip()}
        for name, expected in {'default-src': ["'none'"], 'script-src': ["'self'"], 'style-src': ["'self'"], 'connect-src': ["'none'"]}.items():
            if directives.get(name) != expected:
                errors.append('missing/restricted site CSP')
        return errors, parser.values
    return errors, text.splitlines()


def values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from values(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from values(item)


def scan(dist, tables):
    lore = {normalize(text) for table in tables.values() for key, (text, _) in table.items() if key.endswith('_desc_lore') and normalize(text)}
    patterns = {
        'local path': r'(?i)(?:(?<![a-z0-9])[a-z]:[\\/]|\\\\[^\\\s]+\\|/(?:home|Users|mnt|tmp)/|<GAME_DIR>|<STRINGS_DIR>|<DOCS_DIR>|sc-playground|_inputs)',
        # Lab database suffix (cosmosim_node); not stock file names such as green_nodes_price.lua.
        'lab identifier': r'(?i)_node(?![a-z])',
        'sample account': r'(?i)test_user_',
        'sample address': r'192\.0\.2\.',
        'lore key': r'_desc_lore',
        'asset path': r'(?i)\.(?:dds|png|jpe?g|tga|ogg|wav|mp3|mdl|model)(?:\b|$)',
    }
    username = os.environ.get('USERNAME') or os.environ.get('USER')
    if username and len(username) > 2:
        patterns['local username'] = r'(?i)(?<![\w-])'+re.escape(username)+r'(?![\w-])'
    patterns = {rule: re.compile(pattern) for rule, pattern in patterns.items()}
    errors = []
    for path in sorted(dist.rglob('*')):
        if not path.is_file():
            continue
        label = str(path.relative_to(dist))
        if path.suffix not in {'.json', '.csv', '.md', '.js', '.html', '.css'}:
            errors.append(label+': non-text file type')
            continue
        try:
            text = path.read_bytes().decode('utf-8')
        except UnicodeDecodeError:
            errors.append(label+': invalid UTF-8/binary')
            continue
        if any(ord(c) < 32 and c not in '\t\r\n' for c in text) or text.startswith('\ufeff'):
            errors.append(label+': control bytes/BOM')
        try:
            site_data = path.suffix == '.js' and path.parent.name == 'data'
            if site_data:
                from .site import read_script
                parsed = read_script(path)
                scalar = set(values(parsed))
                if path.name in {'items.js', 'items_all.js'}:
                    if any(len(row) != 11 or any(len(row[i]) > 200 for i in [2, 3]) for row in parsed):
                        errors.append(label+': D1 index text length/shape')
                elif path.name.startswith('details-'):
                    if any(len(row.get(k, '')) > 200 for row in parsed.values() for k in ['short_desc_en', 'short_desc_ru']):
                        errors.append(label+': D1 detail text length')
            elif path.suffix == '.json':
                parsed = json.loads(text)
                scalar = set(values(parsed))
            elif path.suffix == '.csv':
                with path.open(encoding='utf-8', newline='') as f:
                    parsed = list(csv.DictReader(f))
                scalar = set(values(parsed))
            else:
                scalar = text.splitlines()
            if 'site' in path.relative_to(dist).parts:
                issues, extra = site_rules(path, text)
                errors.extend(label+': '+issue for issue in sorted(set(issues)))
                if not site_data:
                    scalar = set(scalar) | {s for s in extra if s is not None}
            for rule, pattern in patterns.items():
                if any(pattern.search(value) for value in scalar):
                    errors.append(label+': '+rule)
            if any(normalize(value) in lore for value in scalar):
                errors.append(label+': lore value')
            if path.name in {'items.csv', 'items.json', 'items_all.csv', 'items_all.json'}:
                for row in parsed:
                    if any(len(row.get(k, '')) > 200 for k in ['short_desc_en', 'short_desc_ru', 'name_en', 'name_ru']):
                        errors.append(label+': D1 text length')
                        break
        except (ValueError, TypeError, AttributeError):
            errors.append(label+': invalid structured text')
    return errors
