import os
import re
import sys
from pathlib import Path


def reader():
    root = Path(os.environ.get('READER', Path(__file__).resolve().parents[2] / '001-sc-gamedata-reader'))
    sys.path.insert(0, str(root))
    from sc_gamedata_reader import parse_file
    return parse_file


def scalar(value):
    if isinstance(value, dict):
        return value.get('$ref', '')
    return value if isinstance(value, (str, int, float, bool)) else ''


def walk(gamedir):
    parse = reader()
    definitions, coverage, assignments = {}, [], []
    root = gamedir / 'data/gamedata'
    for folder in ('def/objects', 'def/ex', 'shared'):
        for path in sorted((root / folder).glob('*.lua')):
            relative = path.relative_to(gamedir).as_posix()
            document = parse(path)
            used = 0
            for a in document['assignments']:
                assignments.append((relative, a))
                if a['scope'] is not None or a['conditional']:
                    continue
                match = re.fullmatch(r'Def\.([A-Za-z_0-9]+)(?:\.([A-Za-z_0-9]+))?', a['target'])
                if not match:
                    continue
                name, field = match.groups()
                entry = definitions.setdefault(name, {'fields': {}, 'file': relative, 'line': a['line']})
                if field:
                    entry['fields'][field] = a['value']
                    if field == 'storeItemId':
                        entry.update(file=relative, line=a['line'])
                elif isinstance(a['value'], dict) and not any(k.startswith('$') for k in a['value']):
                    entry['fields'].update(a['value'])
                used += 1
            coverage.append(dict(file=relative, assignments=len(document['assignments']), used=used,
                                 reason='Def literals' if used else 'No unconditional Def literals; reference scan only', warnings=document['warnings']))
    return definitions, coverage, assignments


def inherited(name, definitions, seen=None):
    seen = set() if seen is None else seen
    if name in seen or name not in definitions:
        return {}
    seen.add(name)
    fields = definitions[name]['fields']
    parent = fields.get('inherit')
    result = inherited(parent, definitions, seen) if isinstance(parent, str) else {}
    return {**result, **fields}


def kind(name, fields, filename):
    if filename in ('craft', 'prices_tradegoods', 'junk'): return 'craft_part' if 'part' in name.lower() else 'resource'
    if name.startswith(('WeaponMod_', 'SpaceMissile_', 'SpaceMine_', 'Missile_')) or filename in ('weapon_mod', 'rockets', 'minefield'): return 'munition'
    if name.startswith('Ship_') and ('ship' in filename or fields.get('item_subtype') == {'$ref': 'ItemSubtype.Ship'}): return 'ship'
    if name.startswith(('AG_', 'Autogen')) or 'autogen' in filename: return 'autogen'
    if name.startswith('Avatar') or 'avatars' in filename: return 'avatar'
    if 'bundle' in filename or name.startswith('Bundle'): return 'bundle'
    if name.startswith('Weapon') or filename in ('laser', 'railgun', 'plasma', 'deathray'): return 'weapon'
    if name.startswith(('Ammo', 'Missile', 'Rocket', 'Mine', 'Torpedo')): return 'munition'
    if name.startswith(('Module', 'Green_')) or '_mod' in filename or filename in ('active', 'passive'): return 'module'
    if filename in ('craft', 'prices_tradegoods', 'junk'): return 'craft_part' if 'part' in name.lower() else 'resource'
    return 'other'
