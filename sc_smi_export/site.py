"""Offline site data, generated only from the public JSON contract."""
import json
import re
import shutil
from pathlib import Path

INDEX_COLUMNS = 'kind defName name_en name_ru label_en label_ru name_status storeItemId storeId atlasId account_scope'.split()
ASSETS = Path(__file__).resolve().parent.parent / 'site'
LIMIT = 4_000_000


def script(path, target, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(target + ' = ' + json.dumps(value, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8', newline='\n')


def generate(dist):
    dest = dist / 'site'
    data = dest / 'data'
    data.mkdir(parents=True, exist_ok=True)
    for old in data.glob('*.js'):
        old.unlink()
    groups = {}
    for stem, target in [('items', 'SMI_INDEX'), ('items_all', 'SMI_ALL')]:
        rows = json.loads((dist / 'data' / (stem + '.json')).read_text(encoding='utf-8'))
        script(data / (stem + '.js'), 'window.' + target, [[r[k] for k in INDEX_COLUMNS] for r in rows])
        groups[stem] = rows
    shared = {}
    for row in groups['items_all']:
        if row['storeItemId_shared']:
            shared.setdefault(str(row['storeItemId']), []).append([row['kind'], row['defName']])
    script(data / 'shared.js', 'window.SMI_SHARED', shared)
    for kind in sorted({r['kind'] for r in groups['items_all']}):
        if not re.fullmatch(r'[a-z][a-z0-9_]*', kind):
            raise ValueError('invalid site kind')
        details = {r['defName']: {k: v for k, v in r.items() if k not in INDEX_COLUMNS}
                   for r in groups['items_all'] if r['kind'] == kind}
        # Each kind has its own global; no executable initialization is needed.
        script(data / ('details-' + kind + '.js'), 'window.SMI_DETAILS_' + kind, details)
    # Revision 1: grouped file locations per kind (loaded on demand) and database fields by kind.
    # Optional inputs: synthetic test folders may omit them; the real export always writes both.
    loc_file, db_file = dist / 'data' / 'locations.json', dist / 'data' / 'db_by_kind.json'
    places = json.loads(loc_file.read_text(encoding='utf-8')) if loc_file.is_file() else []
    by_kind = {}
    for r in places:
        by_kind.setdefault(r['kind'], {}).setdefault(r['defName'], []).append(
            [r['group'], r['location'], r['role'], r['referrer']])
    for kind, value in sorted(by_kind.items()):
        if not re.fullmatch(r'[a-z][a-z0-9_]*', kind):
            raise ValueError('invalid site kind')
        script(data / ('locations-' + kind + '.js'), 'window.SMI_LOC_' + kind, value)
    if db_file.is_file():
        script(data / 'db.js', 'window.SMI_DB', json.loads(db_file.read_text(encoding='utf-8')))
    if ASSETS.is_dir():
        for p in sorted(ASSETS.iterdir()):
            if p.is_file():
                shutil.copyfile(p, dest / p.name)


def read_script(path):
    text = path.read_text(encoding='utf-8')
    match = re.fullmatch(r'window\.(SMI_INDEX|SMI_ALL|SMI_SHARED|SMI_DB|SMI_DETAILS_[a-z][a-z0-9_]*|SMI_LOC_[a-z][a-z0-9_]*) =(.*);\n', text, re.DOTALL)
    if not match:
        raise ValueError('invalid site data assignment')
    return json.loads(match[2])


def check_data(dist):
    errors = []
    data = dist / 'site/data'
    if (data / 'items.js').stat().st_size > LIMIT:
        errors.append('account search index exceeds 4 MB')
    for stem in ['items', 'items_all']:
        expected = json.loads((dist / 'data' / (stem + '.json')).read_text(encoding='utf-8'))
        actual = read_script(data / (stem + '.js'))
        if actual != [[r[k] for k in INDEX_COLUMNS] for r in expected]:
            errors.append(stem + ' search index differs')
        details = {kind: read_script(data / ('details-' + kind + '.js')) for kind in {r['kind'] for r in expected}}
        for row, source in zip(actual, expected):
            rebuilt = dict(zip(INDEX_COLUMNS, row))
            rebuilt.update(details[row[0]][row[1]])
            if rebuilt != source:
                errors.append(stem + ' detail reconstruction differs')
                break
    if not (dist / 'data' / 'locations.json').is_file():
        return errors  # synthetic fixtures; the real gate requires the file via the manifest check
    places = json.loads((dist / 'data' / 'locations.json').read_text(encoding='utf-8'))
    rebuilt = []
    for p in sorted(data.glob('locations-*.js')):
        kind = p.stem[len('locations-'):]
        for def_name, rows in read_script(p).items():
            rebuilt.extend(dict(kind=kind, defName=def_name, group=g, location=l, role=r, referrer=f)
                           for g, l, r, f in rows)
    order = lambda r: (r['kind'], r['defName'], r['group'], r['location'], r['role'], r['referrer'])
    if sorted(rebuilt, key=order) != sorted(places, key=order):
        errors.append('site locations differ from locations.json')
    if read_script(data / 'db.js') != json.loads((dist / 'data' / 'db_by_kind.json').read_text(encoding='utf-8')):
        errors.append('site database table differs')
    return errors
