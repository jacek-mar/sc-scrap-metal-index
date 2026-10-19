"""Static input loading and public location mapping (CC0-1.0)."""
import json
import re
from pathlib import Path, PurePosixPath

STATUSES = ['exact', 'own_field', 'prefixed', 'category', 'derived', 'none']
COLUMNS = ('defName kind name_en name_ru label_en label_ru name_status '
           'short_desc_en short_desc_ru desc_status desc_has_placeholders '
           'race rank tier storeItemId storeId atlasId storeItemId_shared '
           'account_scope defined_in db_fields flags race_en race_ru').split()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def index(rows):
    result = {}
    for row in rows:
        key = row['kind'], row['defName']
        if key in result:
            raise ValueError(f'duplicate identity: {key}')
        result[key] = row
    return result


def load(r013, r016):
    registry = index(read_json(Path(r013) / 'results/items.json'))
    names = index(read_json(Path(r016) / 'results/names.json'))
    accounts = {k for k, r in registry.items() if r['account_scope'] == 'account'}
    if accounts != names.keys():
        raise ValueError(f'account join mismatch: missing={len(accounts-names.keys())}, extra={len(names.keys()-accounts)}')
    if any(n['name_status'] not in STATUSES for n in names.values()):
        raise ValueError('invalid name status')
    return registry, names


def game_location(file, line):
    file = file.replace('\\', '/')
    p = PurePosixPath(file)
    if not file or p.is_absolute() or '..' in p.parts or ':' in file:
        raise ValueError('game location must be relative')
    if not isinstance(line, int) or line < 1:
        raise ValueError('invalid source line')
    return 'star conflict\\' + file.replace('/', '\\') + ':' + str(line)


def database(name):
    allowed = {'cosmosim', 'stats_cosmosim', 'games', 'delivered', 'achievements', 'logs'}
    if name == 'atlas_ids':
        return name
    if name.endswith('_node') and name[:-5] in allowed:
        return name[:-5] + '_<WinUser>'
    raise ValueError('unknown database location')


def db_reference(ref):
    db, collection = ref['location'].split('/')
    if not re.fullmatch(r'[A-Za-z_]+', collection):
        raise ValueError('invalid collection')
    # Numeric attachment indices are sample structure, not stable item locations.
    field = re.sub(r'(?<=\.)\d+(?=\.|$)', '<>', ref['field'])
    return database(db) + '.' + collection + '.' + field
