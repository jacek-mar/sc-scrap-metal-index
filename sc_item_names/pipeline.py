import re
import csv
import json
import random
import hashlib
from collections import Counter
from pathlib import Path
from .engine import Engine, RULES, STATUSES, location
from .sources import Strings, Definitions

COLUMNS = 'defName kind name_en name_ru name_status rule_id source_key_en source_key_ru label_en label_ru label_parts evidence'.split()
REVIEW_RULES = {**RULES, 'exact': 'Use defName first, then defName_name. The rule_id column stays empty as specified.'}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def csv_write(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, columns, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items() if k in columns})


def read_registry(path):
    if path.is_dir():
        path = path / 'items.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise ValueError('Registry must be a JSON array')
    selected, seen = [], set()
    for row in rows:
        if row.get('account_scope') != 'account':
            continue
        for key in ('defName', 'kind', 'defFile', 'defLine', 'nameSource', 'name_en', 'name_ru'):
            if key not in row:
                raise ValueError('Missing registry field: ' + key)
        identity = row['kind'], row['defName']
        if identity in seen:
            raise ValueError('Duplicate registry identity')
        seen.add(identity)
        selected.append(row)
    if not selected:
        raise ValueError('No account rows')
    return sorted(selected, key=lambda r: (r['kind'], r['defName']))


def samples(output):
    rng = random.Random(16)
    return {rule: rng.sample(rule_rows(output, rule), min(5, len(rule_rows(output, rule)))) for rule in REVIEW_RULES}


def rule_rows(output, rule):
    return [r for r in output if (r['name_status'] == 'exact' if rule == 'exact' else r['rule_id'] == rule)]


def review_digest(row):
    fields = {k: row[k] for k in ('defName', 'kind', 'name_en', 'name_ru', 'name_status', 'rule_id', 'source_key_en', 'source_key_ru', 'evidence')}
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def review_errors(output, reviews):
    errors = []
    for rule, group in samples(output).items():
        records = reviews.get(rule, [])
        if {(r['kind'], r['defName']) for r in records} != {(r['kind'], r['defName']) for r in group}:
            errors.append('Missing/stale random source review: ' + rule)
            continue
        for r in group:
            record = next(v for v in records if v['kind'] == r['kind'] and v['defName'] == r['defName'])
            if record.get('verdict') != 'PASS' or record.get('digest') != review_digest(r) or not record.get('note'):
                errors.append('Source review failed/changed: ' + r['defName'])
    return errors


def contract(rows, output, strings):
    errors = []
    if [(r['kind'], r['defName']) for r in rows] != [(r['kind'], r['defName']) for r in output]:
        errors.append('Account identities/order do not reconcile')
    for r in output:
        prefix = r['kind'] + ':' + r['defName'] + ': '
        if r['name_status'] not in STATUSES:
            errors.append(prefix + 'invalid status')
        permitted = {'': ('exact', 'none'), 'own_field': ('own_field',), 'shared_field': ('derived',),
                     'custom_prefix': ('prefixed',), 'blueprint_product': ('derived',),
                     'subtype': ('category',), 'rt_et_sibling': ('derived',)}
        if r['name_status'] not in permitted.get(r['rule_id'], ()):
            errors.append(prefix + 'status does not match rule')
        if r['name_status'] == 'none' and (r['name_en'] or r['name_ru']):
            errors.append(prefix + 'none row contains a name')
        if r['name_status'] == 'derived' and (not r['rule_id'] or not r['evidence']):
            errors.append(prefix + 'derived evidence missing')
        if r['name_status'] != 'exact' and r['name_status'] != 'none' and r['rule_id'] not in RULES:
            errors.append(prefix + 'unknown rule')
        for lang in ('en', 'ru'):
            keys, text = r['source_key_' + lang], r['name_' + lang]
            if text:
                if not keys or any(not strings.tables[lang].get(k) for k in keys):
                    errors.append(prefix + 'missing source text ' + lang)
                    continue
                expected = strings.tables[lang][keys[0]]
                if r['rule_id'] == 'blueprint_product':
                    expected = strings.tables[lang]['blueprintNamePattern'].replace('$craft_result_name$', expected)
                if text != expected:
                    errors.append(prefix + 'untraced name text ' + lang)
                if r['name_status'] == 'exact' and keys[0] not in (r['defName'], r['defName'] + '_name'):
                    errors.append(prefix + 'exact key is not own key')
            elif keys:
                errors.append(prefix + 'keys without text ' + lang)
            # Revision 2: a mark-type tie-breaker counts only where it was shown for this language.
            expected_label = ' '.join([text or '[' + r['defName'] + ']'] + [p[lang] for p in r['label_parts'] if p[lang]
                                       and (p['part'] != 'variant_tiebreak' or p.get('shown_' + lang))])
            if r['label_' + lang] != expected_label:
                errors.append(prefix + 'label parts do not reconcile ' + lang)
            for part in r['label_parts']:
                key = part['source_key']
                required = ''
                if part['part'] == 'tier' and re.fullmatch(r'T[1-5]', part['code']):
                    required = 'tier_' + part['code'][1:]
                elif part['part'] == 'rank' and re.fullmatch(r'Rank\d+', part['code']):
                    required = 'shipTooltip_rank'
                if required and (key != required or not part.get('evidence') or
                                 part.get('source_evidence') != strings.evidence(required)):
                    errors.append(prefix + 'tier/rank localization evidence missing ' + lang)

                if key and strings.tables[lang].get(key):
                    expected_part = strings.tables[lang][key]
                    if part['part'] == 'rank':
                        expected_part = (expected_part.replace('$rank$', part['code'][4:])
                                         if '$rank$' in expected_part else '[' + part['code'] + ']')
                    elif part['part'] not in ('mark', 'tier'):
                        expected_part += ' ' + part['code']
                else:
                    expected_part = '[' + part['code'] + ']'
                if (part['part'] != 'identity' or part[lang]) and part[lang] != expected_part:
                    errors.append(prefix + 'untraced label text ' + lang)
    for lang in ('en', 'ru'):
        if len(set(r['label_' + lang] for r in output)) != len(output):
            errors.append('Labels are not unique: ' + lang)
    return errors


def localized_parts_errors(rows, output, strings, definitions):
    errors = []
    for raw, named in zip(rows, output):
        fields, origins = definitions.fields(raw['defName'])
        tokens = raw['defName'].split('_')
        expected = []
        tier = next((t for t in tokens if re.fullmatch(r'T\d+', t)), '')
        numeric_field = 'ship_tier' if raw['kind'] == 'ship' else 'tier'
        value = fields.get(numeric_field)
        if tier and isinstance(value, int) and value > 0 and int(tier[1:]) != value:
            variants = [p for p in named['label_parts'] if p['part'] == 'variant' and p['code'] == tier]
            if len(variants) != 1 or 'identifier differs from numeric tier' not in variants[0]['evidence']:
                errors.append(raw['defName'] + ': conflicting identifier tier not preserved')
            tier = 'T' + str(value)
        field = 'ship_tier' if fields.get('ship_tier') else 'tier'
        if not tier and fields.get(field):
            tier = 'T' + str(fields[field])
        if tier:
            expected.append(('tier', tier, 'tier_' + tier[1:] if re.fullmatch(r'T[1-5]', tier) else ''))
        expected += [('rank', t, 'shipTooltip_rank') for t in tokens if re.fullmatch(r'Rank\d+', t)]
        for kind, code, key in expected:
            parts = [p for p in named['label_parts'] if p['part'] == kind and p['code'] == code]
            if len(parts) != 1:
                errors.append(raw['defName'] + ': missing/duplicate ' + code)
                continue
            part = parts[0]
            if part['source_key'] != key or part.get('source_evidence') != (strings.evidence(key) if key else []):
                errors.append(raw['defName'] + ': tier/rank source mismatch')
            numeric_field = 'rank' if kind == 'rank' else ('ship_tier' if raw['kind'] == 'ship' else 'tier')
            value = fields.get(numeric_field)
            if isinstance(value, (int, float)):
                number = int(code[4:] if kind == 'rank' else code[1:])
                if value != number or f'{origins[numeric_field]} {numeric_field}={value}' not in part['evidence']:
                    errors.append(raw['defName'] + ': tier/rank numeric evidence mismatch')
            for lang in ('en', 'ru'):
                text = strings.tables[lang].get(key, '')
                if kind == 'rank':
                    text = text.replace('$rank$', code[4:]) if '$rank$' in text else ''
                if part[lang] != (text or '[' + code + ']'):
                    errors.append(raw['defName'] + ': unlocalized tier/rank ' + lang)
    return errors


def acceptance(rows, output):
    by_name = {r['defName']: r for r in output}
    checks = []

    def check(title, passed, detail):
        checks.append(dict(check=title, passed=bool(passed), evidence=detail))

    for name, key, en, ru in [('Jericho_dream', 'sticker_Jericho_dream', 'Jericho nightmare', 'Кошмар Иерихона'),
                              ('BP15_Rift', 'shipChild_BP15_Rift', 'Semi-decay', 'Полураспад')]:
        r = by_name.get(name, {})
        check(name, r.get('name_status') == 'prefixed' and r.get('name_en') == en and r.get('name_ru') == ru,
              '; '.join(r.get('evidence', [])) + ' key=' + key)
    a = by_name.get('ModulePassive_AccelerationCoil_T1_Mk1', {})
    b = by_name.get('ModulePassive_AccelerationCoil_T1_Mk3', {})
    check('Acceleration coil category and distinct tier/mark', a.get('name_status') == 'category' and
          a.get('name_en') == 'Acceleration Coils' and a.get('name_ru') == 'Разгонные катушки' and
          any(p['part'] == 'tier' and p['source_key'] == 'tier_1' for p in a.get('label_parts', [])) and any(p['part'] == 'mark' and p['code'] == 'Mk1' for p in a.get('label_parts', [])) and a.get('label_en') != b.get('label_en'),
          '; '.join(a.get('evidence', [])))
    for suffix in ('RT', 'ET'):
        r = by_name.get('ModulePassive_AccelerationCoil_T1_' + suffix, {})
        check('Acceleration coil ' + suffix, bool(r) and r.get('name_status') != 'none', '; '.join(r.get('evidence', [])))
    r = by_name.get('BP_AlienCompositeAlloy', {})
    check('Explicit blueprint product', r.get('name_status') == 'derived' and r.get('rule_id') == 'blueprint_product' and
          'AlienCompositeAlloy' in r.get('source_key_en', []), '; '.join(r.get('evidence', [])) + ' actual EN=' + r.get('name_en', ''))
    check('Current account count', len(output) == len(rows), f'results/names.csv:2 onward: {len(output)} rows; input items.json account_scope=account: {len(rows)} (spec historical count 14619)')
    return checks


def write_rules(path, output, reviews):
    lines = ['# Naming rules', '', '*(inferred)* Fixed priority: exact own keys, own/shared field, typed custom prefix,',
             'explicit blueprint product, subtype, RT/ET sibling, none. First applicable rule wins.',
             'A key present in only one language does not borrow from a lower-priority rule.', '',
             '*(file)* Step-6 narrowing: the initial shared_field sample included WeaponMod_PlasmaUp1_Basic_T3_Prem.',
             'weapon_mod.lua:9210 assigns uiName=WeaponMod_PlasmaUp1_Prem as a symbolic expression, not a literal.',
             'Both field rules now reject symbolic expressions; candidate key ownership is counted across all fields.',
             'This is a conservative static limit, not a claim about the runtime value. Samples were redrawn after narrowing.', '',
             '*(file)* Exact keys have empty rule_id. No name is translated. Blueprint composition',
             'uses blueprintNamePattern verbatim with its single product placeholder replaced.', '',
             '## Labels', '',
             '*(file)* Tier parts T1-T5 use tier_1-tier_5 verbatim (I-V): EN string.txt:23427-23431;',
             'RU:23454-23458. Numeric rank tokens use shipTooltip_rank with only $rank$ substituted:',
             'EN:14060 (Rank $rank$), RU:14075 (Ранг $rank$). Missing wording keeps [Tn]/[Rankn] per language.',
             'label_parts preserves raw code, source key, physical string lines and definition origin.',
             '*(inferred)* Numeric tokens must agree with available tier/ship_tier or rank fields;',
             'Numeric definition tiers take priority over conflicting Tn identifiers; those tokens',
             'remain bracketed variant parts with both origins. Conflicting rank tokens fail.',
             'No tier-to-rank conversion.',
             'dump_ship_wiki.lua.txt:94,101 reads ship_tier and rank separately. Literal Mk tokens use',
             'mark_ keys whose EN text, ignoring periods, equals that token (e.g. mark_1 = Mk.1).',
             'No numeric enum conversion: mark_4 is Premium, so it cannot localize Mk4.',
             'Rank ranges use itemTooltip_rankRange where available. No tier-to-rank conversion.',
             'dump_shipmod_wiki.lua.txt:169,178,186,194,202 reads tier and mark suffixes,',
             'without a localized tier/mark key in that dump. The independent mark_ keys above supply wording.',
             'Rare/Epic remain raw codes; no quality reinterpretation.',
             'Collisions receive [kind:defName]; labels are unique in each language.',
             'Every label_parts entry carries its code, localization key (if any), and origin.', '']
    for rule, description in REVIEW_RULES.items():
        group = rule_rows(output, rule)
        lines += ['## ' + rule, '', '*(inferred)* ' + description, '',
                  f'*(file)* Rows: {len(group)}; kinds: ' + ', '.join(sorted(set(r['kind'] for r in group))) + '.', '',
                  'Known exceptions: missing language keys stay blank; conditional/dynamic definitions are not evaluated.', '']
        for r in group[:3]:
            lines.append('- `' + r['defName'] + '` → ' + json.dumps(r['name_en'], ensure_ascii=False) +
                         '; keys: ' + ', '.join(r['source_key_en']) + '; ' + '; '.join(r['evidence']))
        lines += ['', '### Random source review (seed 16)', '']
        reviewed = reviews.get(rule, [])
        for r in samples(output)[rule]:
            record = next((v for v in reviewed if v['defName'] == r['defName'] and v['kind'] == r['kind']), None)
            verdict = record['verdict'] + ': ' + record['note'] if record else 'PENDING source review'
            lines.append('- `' + r['defName'] + '` — ' + verdict + '; ' + '; '.join(r['evidence']))
        if not group:
            lines.append('No applications; synthetic test only.')
        lines.append('')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def wiki_counts(root, rows, output):
    if root is None:
        return dict(status='skipped: --wiki not supplied')
    try:
        titles = {json.loads(s).get('title', '').casefold().strip() for s in (root / 'corpus/metadata.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()}
    except (OSError, ValueError):
        return dict(status='skipped: WIKI_DIR metadata not readable')
    result = dict(status='title equality only; casefold and trim; denominator all account rows', total=len(rows))
    for label, records, field in [('before_name', rows, 'name_en'), ('after_name', output, 'name_en'), ('after_label', output, 'label_en')]:
        result[label] = sum(bool(r[field]) and r[field].casefold().strip() in titles for r in records)
    for kind in sorted(set(r['kind'] for r in rows)):
        before = [r for r in rows if r['kind'] == kind]
        after = [r for r in output if r['kind'] == kind]
        result[kind] = dict(total=len(before), before=sum(r['name_en'].casefold().strip() in titles for r in before if r['name_en']),
                            after=sum(r['name_en'].casefold().strip() in titles for r in after if r['name_en']),
                            label=sum(r['label_en'].casefold().strip() in titles for r in after))
    return result


def run(args):
    rows, strings, definitions = read_registry(args.registry), Strings(args.strings), Definitions(args.gamedir)
    engine = Engine(rows, strings, definitions)
    output = engine.build()
    results, out = Path('results'), Path('out')
    results.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    errors = contract(rows, output, strings)
    checks = acceptance(rows, output)
    label_errors = localized_parts_errors(rows, output, strings, definitions)
    errors += label_errors
    checks.append(dict(check='Localized tier/rank parts and numeric evidence', passed=not label_errors,
                       evidence=f'{sum(p["part"] == "tier" for r in output for p in r["label_parts"])} tier parts; '
                                f'{sum(p["part"] == "rank" for r in output for p in r["label_parts"])} rank parts; '
                                f'{len(label_errors)} failures; tier_1-tier_5 and shipTooltip_rank with string/definition evidence'))
    dump(results / 'names.json', output)
    csv_write(results / 'names.csv', COLUMNS, output)
    residual = []
    for row, named in zip(rows, output):
        missing = [l for l in ('en', 'ru') if not named['name_' + l]]
        if not missing:
            continue
        fields, origins = definitions.fields(row['defName'])
        why = 'no supported typed prefix, own/field key, named craft_result, or subtype'
        if named['name_status'] != 'none':
            why = 'selected rule/key has no text in missing language; lower-priority keys not mixed'
        if row['defName'].endswith(('_RT', '_ET')):
            why += '; RT/ET requires cant_be_equipped=true and same-kind Mk1 sibling with named subtype'
        flags = [f for f in row.get('flags', []) if f in ('test', 'hidden', 'cant_be_bought')]
        if flags:
            why += '; registry flags=' + ','.join(flags) + ' (not proof of retirement)'
        residual.append(dict(defName=row['defName'], kind=row['kind'], missing=','.join(missing), **{'defFile:defLine': location(row)}, why=why))
    csv_write(results / 'residual.csv', ['defName', 'kind', 'missing', 'defFile:defLine', 'why'], residual)
    review_path = results / 'rule_review.json'
    reviews = json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    errors += review_errors(output, reviews)
    write_rules(results / 'rules.md', output, reviews)
    dump(out / 'review_samples.json', {k: v for k, v in samples(output).items()})
    dump(out / 'string_diagnostics.json', strings.diagnostics)
    wiki = wiki_counts(args.wiki, rows, output)
    lines = ['# Current name coverage', '', f'*(file)* Account rows: **{len(rows)}**. Residual rows missing EN or RU: **{len(residual)}**.',
             f'*(file)* EN names: {sum(bool(r["name_en"]) for r in rows)} before → {sum(bool(r["name_en"]) for r in output)} after; '
             f'RU names: {sum(bool(r["name_ru"]) for r in rows)} before → {sum(bool(r["name_ru"]) for r in output)} after.',
             f'*(file)* Random source reviews: {sum(len(g) for g in samples(output).values())}; '
             f'review failures: {len(review_errors(output, reviews))}. See rules.md and rule_review.json.', '',
             '| Status | Rows |', '|---|---:|']
    counts = Counter(r['name_status'] for r in output)
    lines += [f'| {s} | {counts[s]} |' for s in STATUSES]
    lines += ['', '| Kind | Rows | Before EN | After EN | Before RU | After RU | Residual |', '|---|---:|---:|---:|---:|---:|---:|']
    for kind in sorted(set(r['kind'] for r in rows)):
        before = [r for r in rows if r['kind'] == kind]
        after = [r for r in output if r['kind'] == kind]
        values = [len(before), sum(bool(r['name_en']) for r in before), sum(bool(r['name_en']) for r in after),
                  sum(bool(r['name_ru']) for r in before), sum(bool(r['name_ru']) for r in after), sum(r['kind'] == kind for r in residual)]
        lines.append('| ' + kind + ' | ' + ' | '.join(map(str, values)) + ' |')
    lines += ['', '| Kind | ' + ' | '.join(STATUSES) + ' |', '|---|' + '---:|' * len(STATUSES)]
    for kind in sorted(set(r['kind'] for r in rows)):
        c = Counter(r['name_status'] for r in output if r['kind'] == kind)
        lines.append('| ' + kind + ' | ' + ' | '.join(str(c[s]) for s in STATUSES) + ' |')
    lines += ['', '## Acceptance checks', '', '*(file)* Historical 013 count 14,619 is superseded by the current input; no rows forced to fit.', '']
    lines += [f'- {"PASS" if c["passed"] else "FAIL"} {c["check"]}: {c["evidence"]}' for c in checks]
    lines += ['', f'*(file)* Structural/text-provenance gate: {len(errors)} failures.', '', '## Wiki coverage', '',
              '*(file)* ' + wiki['status'] + '.', '']
    if 'total' in wiki:
        lines += ['| Account metric | Matching rows | Share of all accounts |', '|---|---:|---:|']
        for title, key in [('013 name_en baseline', 'before_name'), ('Current name_en', 'after_name'), ('Current label_en', 'after_label')]:
            lines.append(f'| {title} | {wiki[key]} / {wiki["total"]} | {wiki[key] / wiki["total"]:.2%} |')
        lines += ['', '| Kind | Account rows | 013 name | Current name | Current label |', '|---|---:|---:|---:|---:|']
        for kind in sorted(set(r['kind'] for r in rows)):
            w = wiki[kind]
            lines.append(f'| {kind} | {w["total"]} | {w["before"]} | {w["after"]} | {w["label"]} |')
        lines += ['']
    lines += ['*(inferred)* Wiki equality measures title overlap, not correctness. Wiki supplies no name text.',
              'Distinguishing labels include tier/mark/rank/code parts; complete-label equality therefore falls sharply.',
              '013 reported broad ship/module figures (1,423/1,610 and 6,454/7,954); these include non-account rows.',
              'The before counts above recompute its account-only baseline for a comparable denominator.', '']
    (results / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')
    dump(out / 'checks.json', dict(checks=checks, errors=errors, wiki=wiki))
    failures = errors + [c['check'] for c in checks if not c['passed']]
    print(json.dumps(dict(rows=len(output), statuses=dict(counts), residual=len(residual), failures=failures), ensure_ascii=True))
    return 1 if args.command == 'validate' and failures else 0
