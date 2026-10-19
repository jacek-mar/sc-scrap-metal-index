import json
import re
import xml.etree.ElementTree as ET
from xml.parsers import expat
from collections import defaultdict


def extended(value):
    if isinstance(value, dict):
        if len(value) == 1 and ('$numberLong' in value or '$numberInt' in value):
            return int(next(iter(value.values())))
        return {k: extended(v) for k, v in value.items()}
    if isinstance(value, list): return [extended(v) for v in value]
    return value


def documents(path):
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip(): yield extended(json.loads(line))


def xml_records(path, diagnostics=None):
    # iterparse validates XML; lexical lines preserve exact source provenance.
    raw = path.read_bytes()
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: text = raw.decode('cp1251')
    # Client XML includes fragment files with multiple top-level elements.
    try: ET.fromstring('<RegistryRoot>' + re.sub(r'<\?xml[^?]*\?>', '', text) + '</RegistryRoot>')
    except ET.ParseError as error:
        if path.name != 'defmod_rules_new.xml': raise
        if diagnostics is not None: diagnostics.append(dict(file=path.name, issue=str(error), rule='lexical attribute references only; no item rows generated'))
    for number, line in enumerate(text.splitlines(), 1):
        for match in re.finditer(r'<([A-Za-z_][\w]*)\b([^<>]*)/?>', line):
            attrs = dict(re.findall(r'([\w]+)="([^"]*)"', match[2]))
            yield match[1], attrs, number


def autogen_context(path):
    """Typed ancestry and physical lines, without interpreting Lua or XML values."""
    parser = expat.ParserCreate()
    records, stack = [], []
    def start(tag, attrs):
        if attrs.get('defName'):
            records.append((tag, attrs, parser.CurrentLineNumber, '/'.join(stack + [tag])))
        stack.append(tag)
    def end(tag):
        stack.pop()
    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.Parse(path.read_bytes(), True)
    return records


def joins(gamedir, db, diagnostics=None):
    store, generated, references = defaultdict(list), {}, []
    kinds = {'titles.xml': ('Title', 'title'), 'account_auras.xml': ('AccountAura', 'account_aura'),
             'vessel_custom_elements.xml': (None, 'custom_element'), 'autogen.xml': (None, 'autogen')}
    for path in sorted((gamedir / 'cloud/data').glob('*.xml')):
        rel = path.relative_to(gamedir).as_posix()
        for tag, attrs, line in xml_records(path, diagnostics):
            name = attrs.get('defName')
            if (path.name == 'titles.xml' and tag == 'Title') or (path.name == 'vessel_custom_elements.xml' and tag == 'Element'): name = attrs.get('name')
            if name:
                references.append((name, 'file', f'{rel}:{line}', 'defName' if 'defName' in attrs else 'name'))
                if path.name == 'store.xml' and 'id' in attrs:
                    store[name].append(attrs['id'])
                if path.name in kinds:
                    wanted, kind = kinds[path.name]
                    if wanted is None or wanted == tag:
                        generated[kind, name] = dict(kind=kind, file=rel, line=line, attrs=attrs, tag=tag)
        if path.name == 'autogen.xml':
            for tag, attrs, line, ancestry in autogen_context(path):
                generated['autogen', attrs['defName']].update(tag=tag, context=ancestry, line=line)
    atlas = {}
    for doc in documents(db / 'atlas_ids/ids.json'):
        atlas.update(doc.get('modules', {}))
    return store, generated, atlas, references
