"""CC0-1.0. Maintainer tool: reduce a sanitised database sample to the bundled snapshot.

Keeps only what the item registry reads (sc_item_registry.scope.context,
.database.resolve, .joins atlas): typed item references (defName, iid, vid),
the keys that join them (uid, receiver, gameStats.player_<n>.uid), list
lengths, craftResources keys and the atlas id map. Document order and line
numbers are preserved because registry evidence cites them. Names, ids of
documents, balances and every other field are dropped.

Usage: python -m sc_smi_gen.make_snapshot <DB_SAMPLE> <target folder>
"""
import json
import re
import sys
from pathlib import Path

from sc_item_registry.database import SCHEMA

TYPED_SUFFIXES = ('.defName', '.def', '.pwDefName', '.activeModules[]', '.passiveModules[]', '.munition[]', '.vid')
JOIN_KEYS = re.compile(r'^(uid|receiver|gameStats\.player_\d+\.uid|items\[\]\.iid|vessels\[\]\.vid)$')
KEEP_SUBTREE = re.compile(r'^(craftResources|atlas\.modules|modules)$')


def typed(path, value, account):
    if account and path in SCHEMA:
        return True
    if path.endswith(TYPED_SUFFIXES):
        return True
    return '.specialModules.' in path and isinstance(value, str)


def reduce(value, path, account):
    """Return (kept, value); lists of objects keep every element so lengths stay."""
    if isinstance(value, dict) and value and all(k.startswith('$') for k in value):
        pass  # extended JSON scalar ({"$numberLong": ...}): a leaf
    elif isinstance(value, dict):
        if KEEP_SUBTREE.match(path):
            return True, value
        out = {}
        for key, child in value.items():
            if key == '_id' and not path:
                continue
            keep, reduced = reduce(child, f'{path}.{key}' if path else key, account)
            if keep:
                out[key] = reduced
        return bool(out), out
    if isinstance(value, list):
        child_path = path + '[]'
        if any(isinstance(x, (dict, list)) for x in value):
            items = [reduce(x, child_path, account)[1] for x in value]
            return True, items
        keep = typed(child_path, value[0] if value else None, account) or path in ('auras', 'autogenItems', 'items', 'vessels')
        return keep, value if keep else []
    return bool(typed(path, value, account) or JOIN_KEYS.match(path)), value


def main(source, target):
    source, target = Path(source), Path(target)
    for file in sorted(source.glob('*/*.json')):
        collection = file.parent.name + '/' + file.stem
        lines = []
        for line in file.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():
                continue
            doc = json.loads(line)
            if collection == 'atlas_ids/ids':
                reduced = {'modules': doc.get('modules', {})}
            else:
                reduced = reduce(doc, '', collection == 'cosmosim_node/accounts')[1]
            lines.append(json.dumps(reduced, ensure_ascii=False, separators=(',', ':'), sort_keys=True))
        out = target / file.parent.name / file.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(''.join(x + '\n' for x in lines), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
