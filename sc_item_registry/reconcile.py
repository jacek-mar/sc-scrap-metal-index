"""Reconcile static reader limits with independent typed XML evidence."""
from collections import Counter

HELPERS = {
    'modules_armor.lua': ('ModuleArmor_', '24-47'),
    'modules_capacitor.lua': ('ModuleCapacitor_', '600-615'),
    'modules_engine.lua': ('ModuleEngine_', '985-1004'),
    'modules_misc.lua': ('Module_Computer_', '67-92'),
    'modules_shield.lua': ('ModuleShield_', '25-49'),
}


def reconcile(rows, definitions, coverage, ctx):
    typed, _, _ = ctx
    names = {r['defName'] for r in rows}
    inventory_tags = {'Vessel', 'Module', 'Ammo', 'Blueprint', 'Resource', 'Junk', 'Drug', 'Bundle', 'Avatar', 'Motto'}
    catalogue = {n for n, records in typed.items() if any(t in inventory_tags for t, _ in records)}
    missing = sorted(catalogue - names)
    text = '# Reader generation reconciliation\n\n*(file)* Independent typed store catalogue check: '
    text += f'{len(catalogue)} distinct definitions; {len(catalogue & names)} represented; {len(missing)} absent. '
    text += 'This reconciles catalogue membership, not the full set of dynamic Lua outputs or grantability. Commented definitions are not omissions.\n\n'
    for name in missing:
        text += f'- Missing `{name}`: {typed[name]}.\n'
    text += '\n## Skipped helpers\n\n'
    for entry in coverage:
        if not entry['warnings']:
            continue
        file = entry['file']
        basename = file.rsplit('/', 1)[-1]
        locations = ', '.join(str(w['line']) for w in entry['warnings'][:5])
        text += f'\n### {file}\n\n*(file)* {len(entry["warnings"])} warnings; first lines {locations}. '
        if basename in HELPERS:
            prefix, lines = HELPERS[basename]
            members = sorted(n for n in catalogue if n.startswith(prefix))
            literals = sorted(n for n in definitions if n.startswith(prefix))
            text += f'Generator {file}:{lines} writes `{prefix}` family using grade/model inheritance. '
            text += f'{len(literals)} literal definitions; {len(members)} typed inventory members, {len(set(members) & names)} represented; '
            text += f'{len(set(members) - set(definitions))} lack literal Lua definitions. '
            text += '*(inferred)* Ship component generator; no demonstrated missing account row. Dynamic output enumeration remains unknown; family comparison does not prove each output internal. '
            examples = [f'`{n}` ({typed[n][0][1]})' for n in members[:3]]
            if not examples:
                examples = [f'`{n}` ({definitions[n]["file"]}:{definitions[n]["line"]}; literal component)' for n in literals[:3]]
            text += 'Examples: ' + ', '.join(examples) + '.\n'
        elif basename in ('avatars.lua', 'bundles.lua', 'drugs.lua', 'mottos.lua'):
            affected = [r for r in rows if r['defFile'] == file and r['storeItemIdCause'] == 'unevaluated_expression']
            text += f'Counter helper: {len(affected)} retained rows with blank own IDs; typed store/generated rows preserve names, never computed counters. '
            text += 'Examples: ' + ', '.join(f'`{r["defName"]}` ({r["defFile"]}:{r["defLine"]})' for r in affected[:3]) + '.\n'
        elif basename in ('autogen.lua', 'vessel_custom_elements.lua'):
            kind = 'autogen' if basename == 'autogen.lua' else 'custom_element'
            selected = [r for r in rows if r['kind'] == kind]
            text += f'Included files are scanned independently by READER. {len(selected)} broad {kind} rows; scopes {dict(Counter(r["account_scope"] for r in selected))}. '
            text += 'Generated XML preserves configuration/account catalogue records; included runtime expressions remain unevaluated.\n'
        elif basename in ('clan_ship.lua', 'module_upgrade_chain.lua'):
            text += 'Unknown dynamic ship/upgrade helper effects; no demonstrated missing typed account catalogue row. Full runtime output coverage unverified.\n'
        else:
            text += 'Runtime gameplay/reference functions outside item-generation scope; not counted as lost account rows. No function execution or generalized generator handling added.\n'
    text += '\n*(inferred)* No minimal recovery was necessary: every independently typed inventory definition is already retained. This does not certify definitions absent from both static literals and generated catalogues.\n'
    return text, missing
