"""Contract, acceptance and repeatability gate."""
import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

from .core import COLUMNS, read_json
from .export import build, digest, dump, schema


def contract_errors(rows):
    errors = []
    props = schema()['items']['properties']
    previous = None
    for number, row in enumerate(rows, 1):
        key = row.get('kind'), row.get('defName')
        if previous is not None and key <= previous:
            errors.append(f'row {number}: duplicate or unsorted identity')
        previous = key
        if set(row) != set(COLUMNS):
            errors.append(f'row {number}: column mismatch')
            continue
        for field, value in row.items():
            definition = props[field]
            typ = definition['type']
            allowed = [typ] if isinstance(typ, str) else typ
            actual = 'boolean' if type(value) is bool else 'integer' if type(value) is int else 'array' if isinstance(value, list) else 'string' if isinstance(value, str) else 'invalid'
            if actual not in allowed or ('enum' in definition and value not in definition['enum']):
                errors.append(f'row {number}: invalid {field}')
            if actual == 'array' and (any(not isinstance(v, str) for v in value) or len(set(value)) != len(value)):
                errors.append(f'row {number}: invalid list {field}')
            if field.startswith('short_desc') and (len(value) > 200 or value != ' '.join(value.split())):
                errors.append(f'row {number}: description limit')
        placeholder = any(re.search(r'\$[^$]+\$', row[f'short_desc_{lang}']) for lang in ['en', 'ru'])
        if bool(placeholder) != row['desc_has_placeholders']:
            errors.append(f'row {number}: placeholder flag')
        if (not row['short_desc_en'] and not row['short_desc_ru']) != (row['desc_status'] == 'none'):
            errors.append(f'row {number}: description status')
    return errors


def snapshot():
    result = {}
    for p in sorted(Path('dist').rglob('*')):
        if p.is_file():
            if p.name == 'manifest.json':
                value = read_json(p); value.pop('generated_at', None)
                result[str(p)] = json.dumps(value, sort_keys=True).encode()
            else:
                result[str(p)] = p.read_bytes()
    return result


def validate(args, accounts, all_rows, tables):
    errors = contract_errors(all_rows)
    checks = {}
    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            errors.append('acceptance: '+name)
    source = read_json(Path(args.r013)/'results/items.json')
    check('account count and statuses', len(accounts) == sum(r['account_scope']=='account' for r in source) and all(r['name_status'] for r in accounts))
    by_name = {r['defName']: r for r in accounts}
    nebula = by_name.get('Ship_Race1_S_T4_Glass', {})
    check('Nebula name and physical location', nebula.get('name_en') == 'Nebula GS' and nebula.get('defined_in') == 'star conflict\\data\\gamedata\\def\\ex\\ship.lua:26711')
    coil = by_name.get('ModulePassive_AccelerationCoil_T1_Mk1', {})
    check('Acceleration Coils category placeholders', coil.get('short_desc_en') == 'Raises energy charger voltage, increasing projectile speed by $projectile_speed_mul$%.' and coil.get('desc_status') == 'category' and coil.get('desc_has_placeholders') is True)
    check('shared storeItemId 224', all(by_name.get(n, {}).get('storeItemId') == 224 and by_name.get(n, {}).get('storeItemId_shared') is True for n in ['Ship_Race3_L_T5_Mole', 'Ship_Race2_L_T5_Protozan']))
    # Revision 1 (v0.2): race names, grouped locations, database by kind.
    check('race names from string tables', nebula.get('race_en') == 'Empire' and nebula.get('race_ru') == 'Империя')
    places = read_json('dist/data/locations.json')
    mole = [r for r in places if r['kind'] == 'ship' and r['defName'] == 'Ship_Race3_L_T5_Mole']
    check('Mole locations grouped', any(r['group'] == 'edit_here' and r['location'].endswith('ship.lua:15649') and r['role'] == 'definition' for r in mole)
          and any(r['group'] == 'generated' and 'store.xml' in r['location'] for r in mole)
          and any(r['group'] == 'used_by' and r['role'] == 'required ship of' and r['referrer'] == 'Weapon_MoleGun_T5_Mk1' for r in mole))
    check('locations use standard paths and known groups', all(r['location'].startswith('star conflict\\') and r['group'] in
          ('edit_here', 'generated', 'server_rules', 'inert', 'used_by') for r in places))
    kinds = read_json('dist/data/db_by_kind.json')
    check('database location for ships', any(r['kind'] == 'ship' and r['field_path'] == 'vessels[].defName' and r['database'] == 'cosmosim_<WinUser>' for r in kinds))
    check('standard database fields', all('_node' not in f and ('<WinUser>' in f or f.startswith('atlas_ids.')) for r in all_rows for f in r['db_fields']))
    for stem, expected in [('items', accounts), ('items_all', all_rows)]:
        actual = read_json(Path('dist/data')/(stem+'.json'))
        check(stem+' JSON parity', actual == expected)
        with (Path('dist/data')/(stem+'.csv')).open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            check(stem+' CSV columns', reader.fieldnames == COLUMNS)
            csvrows = list(reader)
        check(stem+' CSV parity', csvrows == [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict, bool)) else str(v) for k,v in r.items()} for r in expected])
    manifest = read_json('dist/data/manifest.json')
    check('manifest hashes', all(digest(Path('dist/data')/name) == value for name, value in manifest['sha256'].items()) and set(manifest['sha256']) == {'items.csv','items.json','items_all.csv','items_all.json','db_fields.csv','schema.json','locations.csv','locations.json','db_by_kind.csv','db_by_kind.json'})
    from .site import check_data
    site_errors = check_data(Path('dist'))
    errors.extend(site_errors)
    check('site index size and complete reconstruction', not site_errors)
    from .localization import interface_errors, document_errors
    check('Russian interface completeness', not interface_errors(Path('dist/site')))
    check('Russian documents and links', not document_errors(Path('dist')))
    check('Russian database prose', all(r.get('value_written_ru') and
          (not r['mail'] or r.get('mail_ru')) for r in kinds))
    node = shutil.which('node')
    if node:
        result = subprocess.run([node, '--test', 'tests/search.test.cjs'], capture_output=True, text=True, encoding='utf-8')
        Path('out').mkdir(exist_ok=True)
        Path('out/javascript-tests.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
        check('Node search and site tests', result.returncode == 0)
    first = snapshot()
    build(args)
    check('byte repeatability except generation date', first == snapshot())
    # The publication module is added at the dedicated scan step.
    from .publication import scan
    publication = scan(Path('dist'), tables)
    errors.extend(publication)
    check('publication scan', not publication)
    dump(Path('out/checks.json'), {'checks': checks, 'errors': errors, 'account_rows': len(accounts), 'all_rows': len(all_rows)})
    return errors
