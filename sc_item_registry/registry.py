import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from .strings import read_strings
from .definitions import walk, inherited, scalar, kind
from .joins import joins
from .database import resolve, SCHEMA
from .scope import context, classify
from .consumer import collisions
from .id_causes import id_cause
from .reconcile import reconcile

COLUMNS = 'defName kind subkind race rank tier defFile defLine storeItemId storeId atlasId nameKey name_en name_ru nameSource flags'.split()


REQUIRED_SHIPS = (
    'Ship_ST_Rank5', 'Ship_Race5_S_RECON_Rank5', 'Ship_Race5_S_SCOUT_Rank5',
    'Ship_Race5_M_ATTACK_Rank5', 'Ship_Race5_M_COMMAND_Rank5',
    'Ship_Race5_L_ENGINEER_Rank5', 'Ship_Race5_L_GUARD_Rank5',
    'Ship_Race5_H_OVERSEER_Rank9', 'Ship_Race5_HUGE_SATURN_Rank9',
    'Ship_Helicon_L_SNIPER_Rank5', 'Ship_Salyut_S_ECM_Rank5', 'Ship_UFO_L_GUARD_Rank5')


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def csv_write(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, columns, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ';'.join(map(str, v)) if isinstance(v, list) else v for k, v in row.items() if k in columns})


def lookup(name, fields, tables):
    candidates = [(name, 'defName')]
    for field in ('ship_name', 'name', 'localized_name', 'default_icon'):
        val = scalar(fields.get(field))
        if isinstance(val, str) and val:
            candidates.extend([(val + '_name', 'field:' + field), (val, 'field:' + field)])
    subtype = scalar(fields.get('item_subtype'))
    if isinstance(subtype, str) and subtype.startswith('ItemSubtype.'):
        candidates.append(('itemSubType_' + subtype.split('.')[-1], 'field:item_subtype'))
    candidates.append((name + '_name', 'defName_name'))
    chosen = next(((k, source) for k, source in candidates if tables['en'].get(k)), None)
    if chosen is None: chosen = next(((k, source) for k, source in candidates if tables['ru'].get(k)), ('', 'none'))
    key, source = chosen
    return key, source, tables['en'].get(key, ''), tables['ru'].get(key, ''), list(dict.fromkeys(k for k, _ in candidates))


def build(args):
    results, out = Path('results'), Path('out')
    results.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    tables, stats = {}, {}
    for lang, folder in [('en', 'english'), ('ru', 'russian')]:
        tables[lang], stats[lang] = read_strings(args.strings / folder / 'string.txt')
    definitions, coverage, assignments = walk(args.gamedir)
    title_keys = {}
    for file, assignment in assignments:
        if file.endswith('/shared/titles.lua') and assignment['target'].startswith('Titles[PlayerTitleId.'):
            value = assignment['value']
            if isinstance(value, dict) and isinstance(value.get('name'), str):
                enum = assignment['target'].split('PlayerTitleId.', 1)[1].rstrip(']')
                title_keys[value['name']] = 'title_' + enum + '_name'
    xml_diagnostics = []
    store, generated, atlas, refs = joins(args.gamedir, args.db, xml_diagnostics)
    store_locations = {r[0]: r[2] for r in refs if r[2].startswith('cloud/data/store.xml:')}
    generated_names = {name for _, name in generated}
    names = set(store) | generated_names | {n for n, d in definitions.items() if 'storeItemId' in d['fields']}
    scope_context = context(args.gamedir, args.db)
    rows, full = [], []
    candidates = [(name, None) for name in sorted(names - generated_names)] + [(name, gen) for (_, name), gen in sorted(generated.items())]
    for name, gen in candidates:
        definition = definitions.get(name)
        if not definition and not gen:
            # Explicit store defName is sufficient static provenance.
            location = store_locations[name]
            file, line = location.rsplit(':', 1)
            definition = dict(fields={}, file=file, line=int(line))
        fields = inherited(name, definitions) if name in definitions else {}
        if gen and gen['kind'] == 'title' and name in title_keys:
            fields = {**fields, 'name': title_keys[name]}
        origin = definition or gen
        category = gen['kind'] if gen else kind(name, fields, Path(origin['file']).stem)
        ids = sorted(set(store.get(name, [])), key=int)
        key, source, en, ru, tried = lookup(name, fields, tables)
        flags = [flag for flag in ('premium', 'cant_be_bought', 'hidden', 'test', 'event', 'alien') if fields.get(flag) is True]
        if not ids: flags.append('no_store_entry')
        if not en or not ru: flags.append('no_name')
        if not definition: flags.append('xml_only')
        if definition and isinstance(definition['fields'].get('storeItemId'), dict): flags.append('unresolved_storeItemId_expression')
        row = dict(zip(COLUMNS, [name, category, scalar(fields.get('inherit')) or Path(origin['file']).stem,
                   scalar(fields.get('race')), scalar(fields.get('rank')), scalar(fields.get('ship_tier', fields.get('tier'))),
                   origin['file'], origin['line'], scalar(definitions.get(name, {}).get('fields', {}).get('storeItemId')),
                   ';'.join(ids), atlas.get(name, ''), key if en else '', en, ru, source if en else 'none', sorted(flags)]))
        row.update(storeIds=ids, references=[])
        ancestry, seen_bases = [], set()
        parent = definitions.get(name, {}).get('fields', {}).get('inherit')
        while isinstance(parent, str) and parent in definitions and parent not in seen_bases:
            seen_bases.add(parent)
            base = definitions[parent]
            ancestry.append(f'{base["file"]}:{base["line"]} base class {parent}')
            parent = base['fields'].get('inherit')
        row.update(classify(row, gen, scope_context, {**fields, '_base_evidence': ancestry}))
        row.update(id_cause(definition, fields, origin))
        rows.append(row)
        full.append({**row, 'keysTried': tried, 'descriptions': {lang: {suffix: tables[lang].get(name + suffix, '') for suffix in ('_desc', '_desc_lore')} for lang in tables}})
    rows.sort(key=lambda r: (r['kind'], r['defName']))
    duplicate_names = Counter(r['defName'] for r in rows)
    for row in rows:
        if duplicate_names[row['defName']] > 1: row['flags'].append('ambiguous_defName_across_kinds')
    by_name = {r['defName']: r for r in rows}
    references = set(r for r in refs if r[0] in by_name)
    # Reader assignments carry lexical line provenance for every explicit value.
    def values(value):
        if isinstance(value, str): yield value
        elif isinstance(value, list):
            for x in value: yield from values(x)
        elif isinstance(value, dict):
            for x in value.values(): yield from values(x)
    for file, a in assignments:
        for value in values(a['value']):
            if value in by_name: references.add((value, 'file', f'{file}:{a["line"]}', a['target']))
    for row in rows:
        references.add((row['defName'], 'file', f'{row["defFile"]}:{row["defLine"]}', 'definition'))
    dbrefs, unresolved, dbfields, counts = resolve(args.db, set(by_name), atlas)
    references.update(dbrefs)
    references = sorted(references)
    for name, source, location, field in references:
        by_name[name]['references'].append(dict(source=source, location=location, field=field))
    for row in rows:
        row['references'] = by_name[row['defName']]['references']
    csv_write(results / 'items.csv', COLUMNS + 'account_scope account_slot account_rule account_evidence account_uncertainty storeItemIdCause storeItemIdExpression storeItemIdEvidence'.split(), rows)
    dump(results / 'items.json', rows)
    dump(results / 'id_collisions.json', collisions(rows))
    full_by_name = {(r['kind'], r['defName']): r for r in full}
    csv_write(results / 'name_gaps.csv', ['defName', 'kind', 'missing', 'candidate_key', 'note'],
              [dict(defName=r['defName'], kind=r['kind'], missing='both' if not r['name_en'] and not r['name_ru'] else ('en' if not r['name_en'] else 'ru'),
                    candidate_key=next((k for k in fullrow['keysTried'] if k != r['nameKey'] and (k in tables['en'] or k in tables['ru'])), ''),
                    note='No nonempty bilingual value at selected key; no translation attempted')
               for r in rows if not r['name_en'] or not r['name_ru']
               for fullrow in [full_by_name[r['kind'], r['defName']]]])
    csv_write(results / 'references.csv', ['defName', 'source', 'location', 'field'], [dict(zip(['defName', 'source', 'location', 'field'], r)) for r in references])
    seen = {(r[2], r[3]) for r in dbrefs}
    text = '# Database item fields\n\n*(file)* Public schema accounts table: <DOCS_DIR>/06-database/schema.md:78-230; sample paths scanned recursively. Empty and zero references are sentinels. No document identifiers are emitted.\n\n| Collection | Path | ID type | Seen in sample |\n|---|---|---|---|\n'
    for (collection, field), info in sorted(dbfields.items()):
        text += f'| {collection} | `{field}` | {info["type"]} | {"yes" if info["seen"] else "no"} |\n'
    text += '\n⚠ Unverified: `atlas.modules.<word>` encoding is not established by the public schema; values are retained as opaque packed references, never guessed into atlas IDs. iid and vid resolve only within the same account; never against store IDs. Empty autogenItems provides no evidence for its member schema (those two rows are inferred candidates). Store-id fields were not identified in this sample.\n'
    (results / 'db_fields.md').write_text(text, encoding='utf-8')
    row_index = {(r['kind'], r['defName']): r for r in rows}
    dump(out / 'items_full.json', [{**r, **row_index[r['kind'], r['defName']]} for r in sorted(full, key=lambda r: (r['kind'], r['defName']))])
    dump(out / 'reader_coverage.json', coverage)
    dump(out / 'xml_diagnostics.json', xml_diagnostics)
    dump(out / 'string_diagnostics.json', stats)
    reconciliation, missing_catalogue = reconcile(rows, definitions, coverage, scope_context)
    (results / 'reader_reconciliation.md').write_text(reconciliation, encoding='utf-8')
    summary, checks = summarize(rows, stats, counts, atlas, unresolved, args, coverage)
    checks['Every typed inventory catalogue name represented'] = not missing_catalogue
    summary += f'\n- {"PASS" if not missing_catalogue else "FAIL"}: Every typed inventory catalogue name represented.\n'
    summary += f'\n## Generator reconciliation\n\n*(file)* See reader_reconciliation.md for per-helper counts, evidence and remaining uncertainty. Typed catalogue missing: {len(missing_catalogue)}.\n'
    (results / 'summary.md').write_text(summary, encoding='utf-8')
    return checks


def summarize(rows, stats, counts, atlas, unresolved, args, coverage):
    by_name = {r['defName']: r for r in rows}
    kinds = Counter(r['kind'] for r in rows)
    checks = {
      'EN physical lines = 41630': stats['en']['lines'] == 41630,
      'RU physical lines = 41669': stats['ru']['lines'] == 41669,
      'Nebula GS direct key': by_name.get('Ship_Race1_S_T4_Glass', {}).get('name_en') == 'Nebula GS',
      'Adaptive force field storeItemId = 9101': by_name.get('Module_AdaptiveForceField_T4_Prem', {}).get('storeItemId') == 9101,
      'At least 301 ships with storeItemId': sum(r['kind'] == 'ship' and r['storeItemId'] != '' for r in rows) >= 301,
      'ship.lua has 301 explicit storeItemIds': sum(r['defFile'] == 'data/gamedata/def/ex/ship.lua' and r['storeItemId'] != '' for r in rows) == 301,
      'Titles = 343': kinds['title'] == 343, 'Account auras = 397': kinds['account_aura'] == 397,
      'Sample 4 accounts / 7 vessels / 61 items / 26 auras': all(counts[k] == v for k, v in [('accounts', 4), ('vessels', 7), ('items', 61), ('auras', 26)]),
      'All account defName values resolve': not any(p.endswith('defName') and c == 'cosmosim_node/accounts' for c, p, v in unresolved),
      'Atlas mappings = 1205': len(atlas) == 1205,
      'Every row has file:line': all(r['defFile'] and r['defLine'] for r in rows),
    }
    checks['Twelve reviewed ships have account scope'] = all(by_name.get(n, {}).get('account_scope') == 'account' for n in REQUIRED_SHIPS)
    call_samples = ('Bundle_Ariadna', 'Avatar_231', 'Bundle_Avatar_150', 'Bundle_Battle_Pass_1_15',
                    'Bundle_Battle_Pass_3_19', 'Bundle_CorpEconomy_2_08', 'Bundle_March8_2019',
                    'Bundle_SalyutEvent_Imper', 'Bundle_XenoEvent_UnknownHorizons2', 'Taunt_Custom')
    checks['Ten reviewed counter calls remain blank with causes'] = all(
        by_name.get(n, {}).get('storeItemId') == '' and
        by_name[n]['storeItemIdCause'] == 'unevaluated_expression' and
        'GetNextStoreItemId' in by_name[n]['storeItemIdExpression'] for n in call_samples)
    checks['Every row has scope evidence and uncertainty'] = all(
        r['account_scope'] in ('account', 'npc_or_internal', 'unknown') and
        r['account_evidence'] and r['account_rule'] and r['account_uncertainty'] for r in rows)
    text = '# Item registry summary\n\n*(file)* Static build; generated XML supplements literal Lua. Counts are definition rows, not purchasability claims.\n\n| Kind | Rows | EN named | RU named |\n|---|---:|---:|---:|\n'
    for kind, count in sorted(kinds.items()): text += f'| {kind} | {count} | {sum(bool(r["name_en"]) for r in rows if r["kind"] == kind)} | {sum(bool(r["name_ru"]) for r in rows if r["kind"] == kind)} |\n'
    text += f'\nTotal: {len(rows)}; gaps: {sum(not r["name_en"] or not r["name_ru"] for r in rows)}.\n\n## String tables\n\n'
    for lang, info in stats.items():
        text += f'- {lang}: {info["lines"]} physical lines; {info["pairs"]} pairs; {info["keys"]} unique keys; {len(info["duplicates"])} duplicate occurrences (last wins); {len(info["invalid"])} non-pair lines. Diagnostics: out/string_diagnostics.json.\n'
    text += '\n## Acceptance checks\n\n'
    for name, passed in checks.items(): text += f'- {"PASS" if passed else "FAIL"}: {name}.\n'
    for name in ('Ship_Race1_S_T4_Glass', 'Module_AdaptiveForceField_T4_Prem'):
        row = by_name.get(name, {})
        text += f'- `{name}`: `{row.get("nameKey")}`, {row.get("name_en")}; storeItemId={row.get("storeItemId")}; {row.get("defFile")}:{row.get("defLine")}.\n'
    text += f'\nSample counts: {dict(sorted(counts.items()))}. Source: <DB_SAMPLE>/cosmosim_node/accounts.json:1-4.\nAtlas match: {len(set(atlas) & set(by_name))}/{len(atlas)}; source <DB_SAMPLE>/atlas_ids/ids.json:1.\n'
    text += '\n*(file)* data/gamedata/def/ex/ship.lua:55 begins the 301 explicit ship IDs. Additional ship rows include NPC/preset definitions carrying their own storeItemId; this registry deliberately retains them. cloud/data/titles.xml:3-345 contains 343 titles; cloud/data/account_auras.xml:2 declares 397 auras.\n'
    text += '\nDuplicate definition names across kinds: ' + ', '.join(f'`{name}` ({count})' for name, count in sorted(Counter(r['defName'] for r in rows).items()) if count > 1) + '. References to such names remain ambiguous across these rows.\n'
    text += '\n*(file)* store.xml has 349 actual Avatar elements; the broad `<Avatar` search also counts the `<Avatars>` container (350 matches). Dynamic avatar storeItemId calls remain blank and flagged; store IDs are never copied into that namespace.\n'
    text += '\n## Account scope\n\n*(inferred)* Exact consumer filter: account_scope == account. This is a static account catalogue, not grant authorization. Unknown rows are excluded; sample absence proves nothing. Every row includes the rule, file:line evidence, slot and uncertainty.\n\n'
    text += str(dict(sorted(Counter(r['account_scope'] for r in rows).items()))) + '\n'
    text += '\n| Kind | Account | NPC/internal | Unknown |\n|---|---:|---:|---:|\n'
    for kind in sorted(kinds):
        tally = Counter(r['account_scope'] for r in rows if r['kind'] == kind)
        text += f'| {kind} | {tally["account"]} | {tally["npc_or_internal"]} | {tally["unknown"]} |\n'
    ships = [r for r in rows if r['kind'] == 'ship']
    text += f'\nShips: {len(ships)} broad; {sum(r["defFile"] == "data/gamedata/def/ex/ship.lua" for r in ships)} player-source; {sum(bool(r["storeIds"]) for r in ships)} with store IDs. Scope: {dict(Counter(r["account_scope"] for r in ships))}. Typed vessel, tree and preset evidence is retained per row. Typed Vessel plus EN name and ship base class outside NPC/gameplay/preset families supports account scope. Rank variants use the minimum typed family rank as base; actual availability and the meaning of fake=true remain unverified.\n'
    text += '\n| Ship source | Scope | Rows | With store IDs |\n|---|---|---:|---:|\n'
    for file, scope in sorted({(r['defFile'], r['account_scope']) for r in ships}):
        members = [r for r in ships if r['defFile'] == file and r['account_scope'] == scope]
        text += f'| {file} | {scope} | {len(members)} | {sum(bool(r["storeIds"]) for r in members)} |\n'
    text += '\n## Twelve reviewed ships\n\n*(inferred)* Per-definition static evidence; engine grantability remains unverified.\n\n'
    for name in REQUIRED_SHIPS:
        r = by_name.get(name)
        if r:
            text += f'- `{name}`: {r["account_scope"]}; {r["account_rule"]}; base {r["subkind"]}; EN key {r["nameKey"]}; ' + '; '.join(r['account_evidence']) + f'; {r["account_uncertainty"]}\n'
        else:
            text += f'- `{name}`: missing; unknown.\n'
    text += '\n## Named typed Vessels excluded from account scope\n\n*(inferred)* Exhaustive audit of typed store Vessels with EN names outside account scope. Each exclusion below retains its rule and evidence; fake=true never excludes a row.\n\n'
    excluded = [r for r in ships if r['name_en'] and r['account_scope'] != 'account'
                and any('typed Vessel' in e for e in r['account_evidence'])]
    text += f'Excluded rows: {len(excluded)}.\n\n'
    for r in excluded:
        text += f'- `{r["defName"]}`: {r["account_scope"]}; {r["account_rule"]}; base {r["subkind"]}; EN key {r["nameKey"]}; ' + '; '.join(r['account_evidence']) + f'; {r["account_uncertainty"]}\n'
    text += '\n## ID collisions\n\n*(file)* storeItemId is not globally unique. results/id_collisions.json lists every member, scope evidence, Lua location and independent store IDs. Values 0, 1 and 1000 are shared/default values; engine sentinel semantics are unverified. sc_item_registry.consumer.lookup_id requires a namespace and returns missing/unique/ambiguous over account_rows; optional kind/slot constraints never force a unique answer. Use the full (kind, defName) key when available.\n\n'
    text += str(dict(sorted(Counter(g['category'] for g in collisions(rows)).items()))) + '\n'
    for field in ('storeItemId', 'storeId', 'atlasId'):
        groups = defaultdict(list)
        for r in rows:
            for value in r['storeIds'] if field == 'storeId' else [r[field]]:
                if value != '': groups[str(value)].append(r['defName'])
        duplicates = {v: ns for v, ns in groups.items() if len(ns) > 1}
        text += f'\n{field}: {len(duplicates)} collisions.\n'
        for value, names in sorted(duplicates.items()): text += f'- {value}: ' + ', '.join(f'`{n}`' for n in names) + '\n'
    text += '\n## Blank storeItemId causes\n\n*(file)* Own values only; inherited IDs are not copied. XML-only and absent values are distinct from unevaluated calls. Raw expression and evidence are recorded on every row. REVIEW.md retains ten sampled call regressions.\n\n'
    text += str(dict(sorted(Counter(r['storeItemIdCause'] for r in rows if r['storeItemId'] == '').items()))) + '\n'
    text += '\n## Unresolved DB references\n\n'
    text += 'None.\n' if not unresolved else ''
    for (collection, path, value), count in sorted(unresolved.items()): text += f'- {collection} `{path}`: `{value}` ({count}).\n'
    text += '\n## Lua coverage\n\n'
    text += f'{len(coverage)} files parsed with READER; {sum(bool(x["warnings"]) for x in coverage)} files have static-reader warnings. File-by-file skipped reasons and warnings: out/reader_coverage.json.\n'
    text += '\n## Wiki coverage\n\n'
    if args.wiki:
        try:
            titles = {json.loads(line)['title'].casefold() for line in (args.wiki / 'corpus/metadata.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()}
            for kind in ('ship', 'module'):
                selected = [r for r in rows if r['kind'] == kind]
                misses = [r for r in selected if not r['name_en'] or r['name_en'].casefold() not in titles]
                text += f'\n{kind}: {len(selected)-len(misses)}/{len(selected)} title matches (case-insensitive). Misses:\n'
                text += '\n'.join(f'- `{r["defName"]}`: {r["name_en"] or "(no EN name)"}' for r in misses) + '\n'
        except (OSError, KeyError) as error:
            text += 'Skipped: wiki metadata unreadable or missing title fields.\n'
    else: text += 'Skipped: --wiki not supplied.\n'
    return text, checks
