import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from xml.parsers import expat

PAIR = re.compile(r'^\s*"((?:\\.|[^"\\])*)"\s+"((?:\\.|[^"\\])*)"\s*$')


def unescape(text):
    return re.sub(r'\\([\\"nrt])', lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), text)


class Strings:
    def __init__(self, root):
        self.tables, self.locations = {}, {}
        self.prefixes, self.suffixes = defaultdict(set), defaultdict(set)
        self.diagnostics = {}
        for lang, folder in [('en', 'english'), ('ru', 'russian')]:
            table, locations, invalid, duplicates = {}, {}, [], []
            for line, text in enumerate((root / folder / 'string.txt').read_text(encoding='utf-8-sig').splitlines(), 1):
                match = PAIR.fullmatch(text)
                if not match:
                    if text.strip() and not text.lstrip().startswith('//'):
                        invalid.append(line)
                    continue
                key, value = map(unescape, match.groups())
                if key in table:
                    duplicates.append(line)
                table[key] = value
                locations[key] = f'<STRINGS_DIR>/{folder}/string.txt:{line}'
                for m in re.finditer('_', key):
                    self.prefixes[key[:m.end()]].add(key[m.end():])
                    self.suffixes[key[m.start():]].add(key[:m.start()])
            self.tables[lang], self.locations[lang] = table, locations
            self.diagnostics[lang] = dict(invalid=invalid, duplicates=duplicates, keys=len(table))

    def has(self, key):
        return any(t.get(key) for t in self.tables.values())

    def evidence(self, key):
        return [f'{self.locations[l][key]} key={key}' for l in ('en', 'ru') if self.tables[l].get(key)]


def scalar(value):
    return value.get('$ref', '') if isinstance(value, dict) else value


class Definitions:
    def __init__(self, root):
        reader = Path(os.environ.get('READER', Path(__file__).resolve().parents[2] / '001-sc-gamedata-reader'))
        sys.path.insert(0, str(reader))
        from sc_gamedata_reader import parse_file
        self.own, self.origins, self.custom, self.custom_origins = {}, {}, {}, {}
        for folder in ('def/objects', 'def/ex', 'shared'):
            for path in sorted((root / 'data/gamedata' / folder).glob('*.lua')):
                file = path.relative_to(root).as_posix()
                for a in parse_file(path)['assignments']:
                    if a['scope'] is not None or a['conditional']:
                        continue
                    match = re.fullmatch(r'(Def|VesselCustomElements)\.([\w]+)(?:\.([\w]+))?', a['target'])
                    if not match:
                        continue
                    space, name, field = match.groups()
                    values = self.own if space == 'Def' else self.custom
                    origins = self.origins if space == 'Def' else self.custom_origins
                    fields = values.setdefault(name, {})
                    source = f'{file}:{a["line"]}'
                    if field:
                        fields[field] = a['value']
                        origins[name, field] = source
                    elif isinstance(a['value'], dict) and not any(k.startswith('$') for k in a['value']):
                        for k, v in a['value'].items():
                            fields[k] = v
                            origins[name, k] = source
        self._cache = {}
        self.xml_custom, self.type_map, self.type_evidence = {}, {}, {}
        xml = root / 'cloud/data/vessel_custom_elements.xml'
        if xml.exists():
            parser = expat.ParserCreate()

            def start(tag, attrs):
                if tag == 'Element' and attrs.get('name') and attrs.get('type'):
                    self.xml_custom[attrs['name']] = (attrs['type'], f'cloud/data/vessel_custom_elements.xml:{parser.CurrentLineNumber}')

            parser.StartElementHandler = start
            parser.Parse(xml.read_bytes(), True)
            types, evidence = defaultdict(set), {}
            for name, (code, loc) in sorted(self.xml_custom.items()):
                typ = scalar(self.custom.get(name, {}).get('type', ''))
                if typ:
                    types[code].add(typ)
                    evidence.setdefault(code, [f'{loc} XML type={code} name={name}',
                                               f'{self.custom_origins[name, "type"]} type={typ} name={name}'])
            # Reject any ambiguous mapping; infer enum numbers only from concordant files.
            for code, values in types.items():
                if len(values) == 1:
                    self.type_map[code] = next(iter(values))
                    self.type_evidence[code] = evidence[code]

    def fields(self, name, seen=None):
        if name in self._cache:
            return self._cache[name]
        seen = set() if seen is None else seen
        if name in seen:
            return {}, {}
        seen.add(name)
        own = self.own.get(name, {})
        parent = scalar(own.get('inherit', ''))
        fields, origins = self.fields(parent, seen) if isinstance(parent, str) and parent else ({}, {})
        fields, origins = dict(fields), dict(origins)
        fields.update(own)
        origins.update({k: self.origins[name, k] for k in own})
        if parent:
            origins['inheritance:' + name] = self.origins[name, 'inherit']
        self._cache[name] = fields, origins
        return fields, origins
