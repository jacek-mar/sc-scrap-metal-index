"""Static localization gates; no execution of interface or game inputs (CC0)."""
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def tables(path):
    source = path.read_text(encoding='utf-8')
    return {lang: json.loads(re.search(r'const '+lang+r' = (\{.*?\});', source, re.S)[1])
            for lang in ('en', 'ru')}


def interface_errors(site):
    errors = []
    text = tables(site/'i18n.js')
    if text['en'].keys() != text['ru'].keys():
        errors.append('translation key mismatch')
    for key in text['en'].keys() | text['ru'].keys():
        values = [text[lang].get(key, '') for lang in ('en', 'ru')]
        if not all(isinstance(v, str) and v.strip() for v in values):
            errors.append('empty translation: '+key)
        if set(re.findall(r'\{(\w+)\}', values[0])) != set(re.findall(r'\{(\w+)\}', values[1])):
            errors.append('translation placeholder mismatch: '+key)
    html = (site/'index.html').read_text(encoding='utf-8')
    for key in re.findall(r'data-i18n(?:-placeholder|-aria-label)?="([^"]+)"', html):
        if key not in text['en']:
            errors.append('unknown HTML translation: '+key)
    return errors


def document_errors(dist):
    errors = []
    required = ['ru/README.md', 'docs/ru/using-the-search.md',
                'docs/ru/data-dictionary.md', 'ru/NOTICE.md']
    for name in required:
        path = dist/name
        if not path.is_file():
            errors.append('missing Russian document: '+name)
            continue
        source = path.read_text(encoding='utf-8')
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', source):
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (path.parent/unquote(url.path)).resolve()
            if not target.is_relative_to(dist.resolve()) or not target.exists():
                errors.append('invalid Russian document link: '+name)
    notice = dist/'ru/NOTICE.md'
    if notice.exists():
        english = (dist/'NOTICE.md').read_text(encoding='utf-8').split('\n\n')[1]
        if english not in notice.read_text(encoding='utf-8'):
            errors.append('English D3 notice not preserved')
    return errors
