import re
from collections import Counter, defaultdict
from .sources import scalar

STATUSES = ('exact', 'own_field', 'prefixed', 'category', 'derived', 'none')
RULES = {
    'own_field': 'A literal definition field points to a string key used by only this account identity (ship_name, name, localized_name, uiName, default_icon). Shared references are handled separately. Symbolic field expressions are excluded.',
    'shared_field': 'A shared definition field points to game text. The text is reused as a derived name, never claimed to belong to this item alone.',
    'custom_prefix': 'Typed custom elements: STICKER uses sticker_; CHILD shipChild_; MATERIAL shipColor_; MPRESET shipPreset_. XML enum numbers are inferred only from unambiguous XML/Lua overlaps, with both origins retained. Unknown/contradictory types are excluded.',
    'blueprint_product': 'An is_blueprint=true definition with literal craft_result uses blueprintNamePattern, substituting the named product. No guessed BP_ relationship.',
    'subtype': 'Use only the shared itemSubType_ key explicitly identified by the inherited item_subtype field; status stays category.',
    'rt_et_sibling': 'For module/weapon/munition RT or ET definitions with explicit cant_be_equipped=true, reuse the same stem and tier Mk1 sibling subtype. This names the family, not a playable variant; status derived.',
}
FIELDS = ('ship_name', 'name', 'localized_name', 'uiName', 'default_icon')


def location(row):
    return f'{row["defFile"]}:{row["defLine"]}'


MARK_EXPECTED = {'Prem': 4, 'Rel': 5, 'Rare': 6, 'Epic': 7}
MARK_CODES = set(MARK_EXPECTED)


def keys_for_field(value):
    return (value + '_name', value)


class Engine:
    def __init__(self, rows, strings, definitions):
        self.rows, self.s, self.d = rows, strings, definitions
        self.mark_keys = {}
        for key, text in sorted(strings.tables['en'].items()):
            if re.fullmatch(r'mark_\d+', key) and re.fullmatch(r'Mk\.\d+', text):
                self.mark_keys.setdefault(text.replace('.', ''), key)
        self.by_name = defaultdict(list)
        self.owners = defaultdict(set)
        for r in rows:
            self.by_name[r['defName']].append(r)
            fields, _ = definitions.fields(r['defName'])
            for field in FIELDS:
                value = fields.get(field, '')
                if isinstance(value, str) and value:
                    for key in keys_for_field(value):
                        self.owners[key].add((r['kind'], r['defName']))

    def result(self, row, status, rule, key, extra=(), pattern=''):
        keys = [key] + ([pattern] if pattern else [])
        result = dict(defName=row['defName'], kind=row['kind'], name_status=status, rule_id=rule,
                      evidence=list(dict.fromkeys([location(row)] + list(extra) + sum((self.s.evidence(k) for k in keys), []))))
        for lang in ('en', 'ru'):
            text = self.s.tables[lang].get(key, '')
            if pattern:
                template = self.s.tables[lang].get(pattern, '')
                text = template.replace('$craft_result_name$', text) if text and '$craft_result_name$' in template else ''
            result['name_' + lang] = text
            result['source_key_' + lang] = keys if text else []
        return result

    def exact(self, row, fields, origins):
        for key in (row['defName'], row['defName'] + '_name'):
            if self.s.has(key):
                return self.result(row, 'exact', '', key)

    def field_name(self, row, fields, origins, unique_only):
        for field in FIELDS:
            value = fields.get(field, '')
            if not isinstance(value, str) or not value:
                continue
            for key in keys_for_field(value):
                unique = len(self.owners[key]) == 1
                if unique != unique_only:
                    continue
                if self.s.has(key):
                    rule = 'own_field' if unique else 'shared_field'
                    evidence = [f'{origins[field]} {field}={value}'] + self.ancestry(origins)
                    return self.result(row, 'own_field' if unique else 'derived', rule, key, evidence)

    def own_field(self, row, fields, origins):
        return self.field_name(row, fields, origins, True)

    def shared_field(self, row, fields, origins):
        return self.field_name(row, fields, origins, False)

    @staticmethod
    def ancestry(origins):
        return [f'{v} {k}' for k, v in origins.items() if k.startswith('inheritance:')]

    def custom_prefix(self, row, fields, origins):
        if row['kind'] != 'custom_element':
            return
        name = row['defName']
        custom = self.d.custom.get(name, {})
        typ = scalar(custom.get('type', ''))
        extra = [f'{self.d.custom_origins[name, "type"]} type={typ}'] if typ else []
        xml = self.d.xml_custom.get(name)
        if xml:
            code, loc = xml
            mapped = self.d.type_map.get(code)
            if typ and mapped and typ != mapped:
                return
            if not typ and mapped:
                typ = mapped
                extra = [f'{loc} XML type={code}'] + self.d.type_evidence[code]
        prefix = {'ai.VesselCustomElementType.STICKER': 'sticker_', 'ai.VesselCustomElementType.CHILD': 'shipChild_',
                  'ai.VesselCustomElementType.MATERIAL': 'shipColor_', 'ai.VesselCustomElementType.MPRESET': 'shipPreset_'}.get(typ)
        if prefix and self.s.has(prefix + name):
            return self.result(row, 'prefixed', 'custom_prefix', prefix + name, extra)

    def blueprint_product(self, row, fields, origins):
        product = fields.get('craft_result')
        if fields.get('is_blueprint') is not True or not isinstance(product, str) or not self.s.has('blueprintNamePattern'):
            return
        targets = self.by_name.get(product, [])
        if len(targets) != 1 or product == row['defName']:
            return
        target = targets[0]
        tf, to = self.d.fields(product)
        # Product lookup deliberately excludes blueprint recursion and stem guesses.
        found = self.exact(target, tf, to) or self.own_field(target, tf, to) or self.shared_field(target, tf, to) or self.subtype(target, tf, to)
        if found:
            key = next((found['source_key_' + l][0] for l in ('en', 'ru') if found['source_key_' + l]), '')
            return self.result(row, 'derived', 'blueprint_product', key,
                               [f'{origins["craft_result"]} craft_result={product}',
                                f'{origins["is_blueprint"]} is_blueprint=true'] + found['evidence'], 'blueprintNamePattern')

    def subtype(self, row, fields, origins):
        value = scalar(fields.get('item_subtype', ''))
        if isinstance(value, str) and value.startswith('ItemSubtype.'):
            key = 'itemSubType_' + value.split('.')[-1]
            if self.s.has(key):
                return self.result(row, 'category', 'subtype', key,
                                   [f'{origins["item_subtype"]} item_subtype={value}'] + self.ancestry(origins))

    def rt_et_sibling(self, row, fields, origins):
        if row['kind'] not in ('module', 'weapon', 'munition') or fields.get('cant_be_equipped') is not True:
            return
        stem = re.fullmatch(r'(.+_T\d+)_(RT|ET)', row['defName'])
        if not stem:
            return
        siblings = [r for r in self.by_name.get(stem[1] + '_Mk1', []) if r['kind'] == row['kind']]
        if len(siblings) != 1:
            return
        sibling = siblings[0]
        sf, so = self.d.fields(sibling['defName'])
        found = self.subtype(sibling, sf, so)
        if found:
            key = next(found['source_key_' + l][0] for l in ('en', 'ru') if found['source_key_' + l])
            return self.result(row, 'derived', 'rt_et_sibling', key,
                               [f'{origins["cant_be_equipped"]} cant_be_equipped=true',
                                f'{location(sibling)} same stem/tier Mk1 sibling={sibling["defName"]}'] + found['evidence'])

    def name(self, row):
        fields, origins = self.d.fields(row['defName'])
        for rule in (self.exact, self.own_field, self.shared_field, self.custom_prefix, self.blueprint_product, self.subtype, self.rt_et_sibling):
            found = rule(row, fields, origins)
            if found:
                return found
        return self.result(row, 'none', '', '')

    def labels(self, row, result):
        fields, origins = self.d.fields(row['defName'])
        parts = []

        def add(kind, code, source, key=''):
            p = dict(part=kind, code=str(code), evidence=source, source_key=key)
            p['source_evidence'] = self.s.evidence(key) if key else []
            for lang in ('en', 'ru'):
                text = self.s.tables[lang].get(key, '') if key else ''
                if kind == 'rank':
                    text = text.replace('$rank$', str(code)[4:]) if '$rank$' in text else ''
                elif text and kind not in ('mark', 'tier'):
                    text += ' ' + str(code)
                p[lang] = text or '[' + str(code) + ']'
            parts.append(p)

        def tier_key(code):
            return 'tier_' + code[1:] if re.fullmatch(r'T[1-5]', code) else ''

        def numeric_source(kind, number, source):
            candidates = ('rank',) if kind == 'rank' else (('ship_tier',) if row['kind'] == 'ship' else ('tier',))
            for field in candidates:
                value = fields.get(field)
                if isinstance(value, (int, float)):
                    if value != number:
                        raise ValueError(f'{row["defName"]}: {kind} token {number} conflicts with {field}={value}')
                    source += f'; {origins[field]} {field}={value}'
            return source

        tokens = row['defName'].split('_')
        tier = next((t for t in tokens if re.fullmatch(r'T\d+', t)), '')
        field = 'ship_tier' if row['kind'] == 'ship' else 'tier'
        value = fields.get(field)
        if isinstance(value, int) and value > 0 and tier and int(tier[1:]) != value:
            source = f'{location(row)} defName tier token; {origins[field]} {field}={value}'
            add('tier', 'T' + str(value), source, tier_key('T' + str(value)))
            add('variant', tier, source + '; identifier differs from numeric tier')
            tier = ''
            tier_resolved = True
        else:
            tier_resolved = False
        if tier:
            add('tier', tier, numeric_source('tier', int(tier[1:]), location(row) + ' defName tier token'), tier_key(tier))
        elif not tier_resolved and (fields.get('tier') or fields.get('ship_tier')):
            f = 'ship_tier' if fields.get('ship_tier') else 'tier'
            code = 'T' + str(fields[f])
            add('tier', code, origins[f] + ' ' + f + '=' + str(fields[f]), tier_key(code))
        # Revision 2: the definition's numeric `mark` field is an enum named by mark_<n>
        # (mark_4 = Premium, mark_5 = Mk.5, mark_6 = Mk.2, mark_7 = Mk.4). Use it when present.
        mark = fields.get('mark')
        mark_key = 'mark_' + str(mark) if isinstance(mark, int) and not isinstance(mark, bool) else ''
        if mark_key and not self.s.tables['en'].get(mark_key):
            mark_key = ''
        mark_token = next((t for t in tokens if re.fullmatch(r'Mk\d+', t)), '')
        # A Mk<n> token in the name wins: some families (missiles) set mark=1 on every variant.
        if mark_token:
            mark_key = ''
        # A quality suffix is trusted only when the field agrees with it (Prem 4, Rel 5, Rare 6,
        # Epic 7); e.g. missile _Prem rows carry mark=1, so they get no mark word.
        suffix = tokens[-1] if tokens else ''
        if mark_key and suffix in MARK_EXPECTED and MARK_EXPECTED[suffix] != mark:
            mark_key = ''
        if mark_key:
            add('mark', mark_token or 'mark' + str(mark), origins['mark'] + ' mark=' + str(mark), mark_key)
        for token in tokens:
            if re.fullmatch(r'Mk\d+|Rank\d+', token):
                if token.startswith('Mk') and mark_key:
                    continue  # already labelled from the mark field
                kind = 'mark' if token.startswith('Mk') else 'rank'
                key = self.mark_keys.get(token, '') if kind == 'mark' else 'shipTooltip_rank'
                source = location(row) + ' defName token'
                if kind == 'rank':
                    source = numeric_source('rank', int(token[4:]), source)
                add(kind, token, source, key)
        lo, hi = fields.get('rank_min'), fields.get('rank_max')
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            add('rank_range', f'{lo}-{hi}', f'{origins["rank_min"]} rank_min; {origins["rank_max"]} rank_max', 'itemTooltip_rankRange')
        # Preserve ALL remaining code suffixes after tier/rank, rather than a guessed list.
        anchor = next((i for i, t in enumerate(tokens) if re.fullmatch(r'T\d+|Rank\d+', t)), None)
        if anchor is not None:
            rest = [t for t in tokens[anchor + 1:] if not re.fullmatch(r'Mk\d+|Rank\d+', t)]
            # Revision 2: a mark-type code already expressed by the mark field becomes a hidden
            # tie-breaker, shown only when two labels would otherwise be identical (build()).
            explained = bool(mark_key) and len(rest) == 1 and rest[0] in MARK_CODES
            if rest:
                add('variant_tiebreak' if explained else 'variant', '_'.join(rest), location(row) + ' defName suffix')
        result['label_parts'] = parts
        for lang in ('en', 'ru'):
            result['label_' + lang] = ' '.join([result['name_' + lang] or '[' + row['defName'] + ']'] +
                                               [p[lang] for p in parts if p['part'] != 'variant_tiebreak'])
        return result

    def build(self):
        output = [self.labels(r, self.name(r)) for r in self.rows]
        # Revision 2: where labels collide, show the hidden mark-type code (e.g. [Rare] next to Mk.2).
        for lang in ('en', 'ru'):
            counts = Counter(r['label_' + lang] for r in output)
            for r in output:
                tie = next((p for p in r['label_parts'] if p['part'] == 'variant_tiebreak'), None)
                if tie and counts[r['label_' + lang]] > 1:
                    r['label_' + lang] += ' ' + tie[lang]
                    tie['shown_' + lang] = True
        # A code identity fallback guarantees distinguishability even for unmodelled variants.
        for lang in ('en', 'ru'):
            counts = Counter(r['label_' + lang] for r in output)
            for r in output:
                if counts[r['label_' + lang]] > 1:
                    code = r['kind'] + ':' + r['defName']
                    r['label_' + lang] += ' [' + code + ']'
                    p = next((p for p in r['label_parts'] if p['part'] == 'identity'), None)
                    if p is None:
                        p = dict(part='identity', code=code, source_key='', evidence='registry kind/defName', en='', ru='')
                        r['label_parts'].append(p)
                    p[lang] = '[' + code + ']'
        return output
