"""Conservative static account catalogue contract, not a grant API."""
import re
from collections import defaultdict
from .joins import xml_records, documents


def context(gamedir, db):
    typed, observed, related = defaultdict(list), defaultdict(list), defaultdict(list)
    for filename in ('store.xml', 'vessel_presets.xml', 'vessel_tree.xml'):
        path = gamedir / 'cloud/data' / filename
        if not path.exists():
            continue
        for tag, attrs, line in xml_records(path):
            location = f'cloud/data/{filename}:{line}'
            if filename == 'store.xml' and attrs.get('defName'):
                typed[attrs['defName']].append((tag, location))
                if tag == 'Module' and attrs.get('type') == '16' and attrs.get('itemSubtype') == '5000':
                    typed[attrs['defName']].append(('SeedChipBaseTemplate(type=16,itemSubtype=5000)', location))
            for field, name in attrs.items():
                if filename != 'store.xml' or field == 'preset':
                    related[name].append(f'{location} {tag}.{field}')
    path = db / 'cosmosim_node/accounts.json'
    if path.exists():
        for line, doc in enumerate(documents(path), 1):
            for slot in ('vessels', 'items', 'auras', 'autogenItems'):
                for item in doc.get(slot, []):
                    if isinstance(item, dict) and item.get('defName'):
                        observed[item['defName']].append((slot + '[].defName', f'<DB_SAMPLE>/cosmosim_node/accounts.json:{line}'))
            for name in doc.get('craftResources', {}):
                observed[name].append(('craftResources.<defName>', f'<DB_SAMPLE>/cosmosim_node/accounts.json:{line}'))
            for vessel in doc.get('vessels', []):
                for item in vessel.get('customElements', []):
                    if item.get('defName'):
                        observed[item['defName']].append(('vessels[].customElements[].defName', f'<DB_SAMPLE>/cosmosim_node/accounts.json:{line}'))
    return typed, observed, related


def classify(row, gen, ctx, fields=None):
    typed, observed, related = ctx
    name, file = row['defName'], row['defFile']
    evidence = [f'{file}:{row["defLine"]} source definition']
    evidence += [f'{loc} typed {tag}' for tag, loc in typed[name]]
    evidence += related[name]
    scope, slot, rule = 'unknown', '', 'insufficient account evidence'
    uncertainty = 'Grantability and current availability unverified; sample absence proves nothing.'
    tags = {tag for tag, _ in typed[name]}
    fields = fields or {}
    if gen and gen['file'].endswith('/autogen.xml'):
        scope, rule = 'npc_or_internal', 'autogen configuration subrecord: ' + gen.get('context', gen['tag'])
    elif any(token in file for token in ('pve_entities', 'openworld_entities', 'clanship_entities', 'gameplay_', 'special_gameplay_objects', 'adventure_objects', 'ships4brawl', 'preset')):
        scope, rule = 'npc_or_internal', 'NPC/gameplay/component/preset source family'
    elif row['kind'] == 'ship':
        if file == 'data/gamedata/def/ex/ship.lua':
            scope, slot, rule = 'account', 'vessels[].defName', 'player ship definition in def/ex/ship.lua'
        elif 'Vessel' in tags and row.get('name_en') and (row.get('subkind', '').startswith('Ship_') or fields.get('item_subtype') == {'$ref': 'ItemSubtype.Ship'} or any(' base class Ship_' in e for e in fields.get('_base_evidence', []))) and not any(t in file.lower() for t in ('pve', 'npc', 'preset')) and 'Preset' not in name:
            scope, slot = 'account', 'vessels[].defName'
            match = re.fullmatch(r'(.+)_Rank(\d+)(?:_.*)?', name)
            base = name
            if match:
                family = [(int(m.group(1)), n) for n in typed
                          if (m := re.fullmatch(re.escape(match.group(1)) + r'_Rank(\d+)', n))
                          and any(tag == 'Vessel' for tag, _ in typed[n])]
                base = min(family)[1]
            rule = ('rank variant of ' + base if base != name else 'base rank ' + base)
            rule += '; typed store Vessel, EN string name and ship base class; no NPC/gameplay/preset source family'
            evidence += fields.get('_base_evidence', [])
            evidence += [f'base class {row["subkind"]}', f'<STRINGS_DIR>/english/string.txt key {row.get("nameKey", "")}']
        elif 'pve' in file or 'npc' in file or 'preset' in file or 'Preset' in name:
            scope, rule = 'npc_or_internal', 'NPC/preset source or explicit preset name'
        else:
            rule = 'insufficient combined ship evidence: requires typed Vessel, EN name and ship base class outside NPC/gameplay/preset families; ownership unverified'
    elif gen and row['kind'] in ('account_aura', 'custom_element'):
        scope = 'account'
        slot = 'auras[].defName' if row['kind'] == 'account_aura' else 'vessels[].customElements[].defName'
        rule = 'typed generated account catalogue'
    elif 'SeedChipBaseTemplate(type=16,itemSubtype=5000)' in tags:
        slot, rule = 'autogenItems (member schema unverified)', 'typed seed-chip base template; instance ownership unestablished'
    elif tags & {'Module', 'Ammo', 'Blueprint', 'Resource', 'Junk', 'Drug'} and '/def/ex/' in file:
        scope, slot, rule = 'account', 'items[].defName', 'typed inventory catalogue plus explicit def/ex definition'
        if row['kind'] == 'autogen':
            slot = 'autogenItems (member schema unverified)'
    elif row['kind'] in ('title', 'avatar', 'bundle', 'other'):
        rule = 'catalogue/cosmetic/reward record; persistent account slot unestablished'
    if row['kind'] == 'ship' and fields.get('fake') is True:
        evidence.append('literal/inherited fake=true (not scope evidence)')
        uncertainty += ' Meaning of fake=true unverified; no engine interpretation asserted.'
    observations = observed[name]
    if row['kind'] == 'title':
        observations = []  # A same-named custom element does not prove title ownership.
    elif row['kind'] == 'custom_element':
        observations = [(s, loc) for s, loc in observations if 'customElements' in s]
    if observations:
        scope, rule = 'account', 'sample presence proves presence only'
        slot = ';'.join(sorted({s for s, _ in observations}))
        evidence += [f'{loc} observed {s}' for s, loc in observations]
    return dict(account_scope=scope, account_slot=slot, account_rule=rule,
                account_evidence=sorted(set(evidence)), account_uncertainty=uncertainty)


def account_rows(rows):
    return [r for r in rows if r['account_scope'] == 'account']
