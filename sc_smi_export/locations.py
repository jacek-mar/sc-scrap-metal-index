"""Revision 1 (v0.2): race names, grouped file locations, database by kind (CC0-1.0)."""
import re

from .core import game_location


def race_names(code, tables):
    """Game wording for an `ai.Race.X` code from the string tables (key race_X)."""
    match = re.fullmatch(r'ai\.Race\.([A-Z_]+)', code or '')
    if not match:
        return '', ''
    key = 'race_' + match[1]
    return tuple(tables[lang].get(key, (code, 0))[0] for lang in ('en', 'ru'))


# cloud/data files and what they mean for an editor
# (research docs: store-zones-rules-semantics section 1, data-files).
GENERATED = {'store.xml', 'quests.xml', 'zones.xml', 'ship_quests.xml', 'vessel_presets.xml', 'battle_pass.xml',
             'achievements.xml', 'titles.xml', 'account_auras.xml', 'autogen.xml', 'special_values.xml',
             'tournaments.xml', 'starter_pack.xml', 'vessel_custom_elements.xml'}
SERVER_RULES = {'store_rules.xml', 'aux_limits.xml'}
INERT = {'defmod_rules.xml', 'defmod_rules_new.xml'}
GROUPS = ['edit_here', 'generated', 'server_rules', 'inert', 'used_by']
GROUP_TITLES = {
    'edit_here': 'Edit here (source definition)',
    'generated': 'Generated server copy - do not edit (rebuilt by prepare_shared)',
    'server_rules': 'Server rule or limit file (hand-maintained)',
    'inert': 'Not read by any service',
    'used_by': 'Used by (other items and tables pointing to it)',
}

# Member of a referring definition -> plain-language role (first match wins).
ROLES = [
    (r'^default_modules', 'fitted by default on'),
    (r'^required_ship$', 'required ship of'),
    (r'^(inherit|parent_prototype)$', 'base definition of'),
    (r'^craft_result$', 'produced by blueprint'),
    (r'^craftable_reagents', 'crafting ingredient of'),
    (r'^upgrade_cost_negator$', 'upgrade-cost item of'),
    (r'^default_rocket_munition$', 'default missiles of'),
    (r'^(ship_def|ship_name)$', 'ship of'),
    (r'^(prev|next)$', 'progression neighbour of'),
    (r'^fixed_contents', 'contained in bundle'),
    (r'^default_custom_elements', 'default paint or decal of'),
    (r'^uiName$', 'name source for'),
    (r'^(modules|munition)', 'in module preset'),
    (r'^resources', 'progression cost of'),
    (r'^ship_variants$', 'variant list of'),
    (r'^depends_on', 'ship tree link of'),
    (r'^blueprint$', 'blueprint of'),
    (r'^reward_def$', 'zone reward of'),
]
TABLE_ROLES = {'LootTable': 'drops from loot table', 'ModulePresets': 'in module preset',
               'VesselProgress': 'progression of', 'VesselTree': 'ship tree entry',
               'AccountAura': 'account aura', 'SpaceZone': 'zone', 'Def': 'referenced by'}
OTHER_ROLES = {'Quests': 'quest', 'Achievements': 'achievement', 'Adventures': 'adventure',
               'LeaguePermittedDefs': 'league permitted list'}


def classify(def_name, ref):
    """One file reference of an item -> dict(group, location, role, referrer)."""
    file, _, line = ref['location'].rpartition(':')
    field = ref['field']
    name = file.rsplit('/', 1)[-1]
    location = game_location(file, int(line))
    if file.startswith('cloud/'):
        group = ('generated' if name in GENERATED else 'inert' if name in INERT else 'server_rules')
        role = {'generated': 'server copy', 'server_rules': 'server rule or limit',
                'inert': 'not read by any service'}[group]
        if field == 'definition':
            role = 'definition in server data'
        return dict(group=group, location=location, role=role, referrer='')
    if field in ('definition', 'name', 'defName'):
        return dict(group='edit_here', location=location,
                    role='definition' if field == 'definition' else 'own entry', referrer='')
    match = re.match(r'^([A-Za-z]+)\.([A-Za-z0-9_]+)(?:\.(.+))?$', field)
    if match:
        table, owner, member = match[1], match[2], match[3] or ''
        if owner == def_name:
            return dict(group='edit_here', location=location,
                        role=('own field ' + member) if member else 'own entry', referrer='')
        for pattern, role in ROLES:
            if member and re.search(pattern, member):
                return dict(group='used_by', location=location, role=role, referrer=owner)
        role = 'contained in bundle' if owner.startswith('Bundle_') else TABLE_ROLES.get(table, 'referenced by')
        return dict(group='used_by', location=location, role=role, referrer=owner)
    table = re.match(r'^([A-Za-z]+)', field)
    role = OTHER_ROLES.get(table[1] if table else '', 'referenced by')
    return dict(group='used_by', location=location, role=role, referrer=field)


def locations(registry):
    """All file locations, one row each, sorted; duplicates (same group/location/role/referrer) removed."""
    rows = set()
    for (kind, def_name), row in registry.items():
        seen = {}
        for ref in row['references']:
            if ref['source'] == 'file':
                c = classify(def_name, ref)
                key = (c['group'], c['location'], c['referrer'])
                # One row per place: a definition role wins over a generic one at the same line.
                if key not in seen or c['role'].startswith('definition'):
                    seen[key] = c['role']
        for (group, location, referrer), role in seen.items():
            rows.add((kind, def_name, GROUPS.index(group), location, role, referrer))
    return [dict(kind=k, defName=d, group=GROUPS[g], location=l, role=r, referrer=f)
            for k, d, g, l, r, f in sorted(rows)]


LOCATION_COLUMNS = ['kind', 'defName', 'group', 'location', 'role', 'referrer']

# Where an item of each kind can appear in the game database
# (DB_FIELDS_BY_KIND.md, Claude 2026-10-19). Evidence: S seen in the sample,
# D documented schema, B field name in Shard.exe, M mail attachment type,
# L observed after a lab grant (admin task, 2026-10-19).
DB_BY_KIND = [
    ('ship', 'accounts', 'vessels[].defName', 'defName; each ship also gets vessels[].vid (instance id from counters)', 'S,D', ''),
    ('module', 'accounts', 'items[].defName', 'defName; plus items[].iid (instance id), amount', 'S,D', 'mail type 5 LAT_ITEM: content.defName'),
    ('module', 'accounts', 'vessels[].equipped[]', 'the iid of an items[] entry when fitted, not the defName', 'D', ''),
    ('weapon', 'accounts', 'items[].defName', 'defName; plus items[].iid (instance id), amount', 'S,D', 'mail type 5 LAT_ITEM: content.defName'),
    ('weapon', 'accounts', 'vessels[].equipped[]', 'the iid of an items[] entry when fitted, not the defName', 'D', ''),
    ('munition', 'accounts', 'vessels[].munition[].def', 'defName (the field is named def), amount', 'S,D', 'mail type 5 LAT_ITEM (untested for munitions)'),
    ('munition', 'accounts', 'items[].defName', 'in storage: defName, iid, amount; a second grant adds to the same entry', 'D,L', ''),
    ('craft_part', 'accounts', 'craftResources.<defName>', 'the defName is the key; the value is the amount (CraftResource_Base parts)', 'S,D,L', 'mail type 5 LAT_ITEM (untested)'),
    ('resource', 'accounts', 'craftResources.<defName>', 'the defName is the key; the value is the amount (CraftResource_Base and craft resources, also blueprints)', 'D,L', 'mail type 5 LAT_ITEM (untested)'),
    ('resource', 'accounts', 'items[].defName', 'unverified: junk (Junk_Base) resources; the give task refuses them', 'D', ''),
    ('account_aura', 'accounts', 'auras[].defName', 'defName, cntrLeft', 'S,D', 'mail type 14 LAT_ACCOUNT_AURA: content.defName'),
    ('custom_element', 'accounts', 'vessels[].customElements[].defName', 'defName, till', 'D', 'mail type 16 LAT_CUSTOM_ELEMENT: content.customElement'),
    ('custom_element', 'accounts', 'freeVesselCustomElements.<name>', 'not fitted to a ship: the element name is the key; the value is a count', 'B,L', ''),
    ('autogen', 'accounts', 'autogenItems[]', 'an instance: iid (from counters), upgradeLevel, rollData (number array), exp', 'D,B,L', 'mail type 15 LAT_AUTOGEN: content.autogenItem'),
    ('title', 'accounts', 'acquiredTitles[].id', 'the numeric title id from cloud/data/titles.xml, not a defName; the active title is the number in title (0 = none)', 'B,L', 'mail type 11 LAT_TITLE: content.tid'),
    ('avatar', 'accounts', 'acquiredAvatars.<defName>', 'the defName is the key (value 1); the active avatar is the defName in avatar', 'B,L', 'mail type 17 LAT_AVATAR: content.avatar'),
    ('bundle', '', '', 'not stored on the account; opened into its contents', '', 'bundles flagged can_be_sent_by_mail can be mailed'),
]
DB_COLUMNS = ['kind', 'database', 'collection', 'field_path', 'value_written', 'evidence', 'mail', 'value_written_ru', 'mail_ru']


def db_by_kind():
    return [dict(kind=k, database='cosmosim_<WinUser>' if c else '', collection=c, field_path=f,
                 value_written=v, evidence=e, mail=m, value_written_ru=DB_RU[i][0], mail_ru=DB_RU[i][1])
            for i, (k, c, f, v, e, m) in enumerate(DB_BY_KIND)]


# Russian prose aligned one-to-one with the reviewed English rows; identifiers stay raw.
DB_RU = [
    ('defName; каждый корабль также получает vessels[].vid (ID экземпляра из counters)', ''),
    ('defName; также items[].iid (ID экземпляра), amount', 'почтовый тип 5 LAT_ITEM: content.defName'),
    ('iid записи items[] при установке, а не defName', ''),
    ('defName; также items[].iid (ID экземпляра), amount', 'почтовый тип 5 LAT_ITEM: content.defName'),
    ('iid записи items[] при установке, а не defName', ''),
    ('defName (поле называется def), amount', 'почтовый тип 5 LAT_ITEM (для боеприпасов не проверен)'),
    ('на складе: defName, iid, amount; повторная выдача увеличивает ту же запись', ''),
    ('defName — ключ; значение — количество (компоненты CraftResource_Base)', 'почтовый тип 5 LAT_ITEM (не проверен)'),
    ('defName — ключ; значение — количество (CraftResource_Base и ресурсы изготовления, включая чертежи)', 'почтовый тип 5 LAT_ITEM (не проверен)'),
    ('не проверено: мусорные ресурсы (Junk_Base); задача give отказывается их выдавать', ''),
    ('defName, cntrLeft', 'почтовый тип 14 LAT_ACCOUNT_AURA: content.defName'),
    ('defName, till', 'почтовый тип 16 LAT_CUSTOM_ELEMENT: content.customElement'),
    ('не установлен на корабль: имя элемента — ключ; значение — количество', ''),
    ('экземпляр: iid (из counters), upgradeLevel, rollData (массив чисел), exp', 'почтовый тип 15 LAT_AUTOGEN: content.autogenItem'),
    ('числовой ID титула из cloud/data/titles.xml, а не defName; активный титул — число в title (0 = нет)', 'почтовый тип 11 LAT_TITLE: content.tid'),
    ('defName — ключ (значение 1); активный аватар — defName в avatar', 'почтовый тип 17 LAT_AVATAR: content.avatar'),
    ('не хранится в учётной записи; раскрывается в содержимое', 'наборы с признаком can_be_sent_by_mail можно отправлять по почте'),
]
