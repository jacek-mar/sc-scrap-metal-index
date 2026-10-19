from collections import Counter
import re
from .joins import documents

# Public schema: accounts table, rows 78-230. Dynamic keys are represented by <>.
SCHEMA = {
 'auras[].defName': 'defName', 'items[].defName': 'defName', 'items[].iid': 'iid',
 'vessels[].defName': 'defName', 'vessels[].vid': 'vid', 'vessels[].equipped[]': 'iid',
 'vessels[].munition[].def': 'defName', 'vessels[].customElements[].defName': 'defName',
 'bSlots[]': 'vid', 'quests.active[].vid': 'vid', 'shipQuests.quests[].vids[]': 'vid',
 'craftResources.<>': 'defName', 'atlas.modules.<>': 'atlas id (opaque packed representation)',
 'autogenItems[].iid': 'iid', 'autogenItems[].defName': 'defName',
}


def leaves(value, path=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, f'{path}.{key}' if path else key)
    elif isinstance(value, list):
        for child in value: yield from leaves(child, path + '[]')
    else: yield path, value


def resolve(db, names, atlas):
    refs, unresolved, fields, observed = set(), Counter(), {}, set()
    counts = Counter()
    account_indexes = {}
    account_file = db / 'cosmosim_node/accounts.json'
    if account_file.exists():
        for doc in documents(account_file):
            account_indexes[doc.get('uid')] = (
                {x.get('iid'): x.get('defName') for x in doc.get('items', [])},
                {x.get('vid'): x.get('defName') for x in doc.get('vessels', [])})
    for file in sorted(db.glob('*/*.json')):
        collection = file.parent.name + '/' + file.stem
        for doc in documents(file):
            account = collection == 'cosmosim_node/accounts'
            iids = {x.get('iid'): x.get('defName') for x in doc.get('items', [])} if account else {}
            vids = {x.get('vid'): x.get('defName') for x in doc.get('vessels', [])} if account else {}
            if account:
                counts['accounts'] += 1
                for key in ('vessels', 'items', 'auras'): counts[key] += len(doc.get(key, []))
                for key in doc.get('craftResources', {}):
                    fields[collection, 'craftResources.<>'] = 'defName'
                    observed.add((collection, 'craftResources.<>'))
                    if key in names: refs.add((key, 'db', collection, 'craftResources.<defName>'))
                    else: unresolved[collection, 'craftResources.<>', key] += 1
                for word, bits in doc.get('atlas', {}).get('modules', {}).items():
                    fields[collection, 'atlas.modules.<>'] = 'atlas id (opaque packed representation)'
                    observed.add((collection, 'atlas.modules.<>'))
                    if bits: unresolved[collection, 'atlas.modules.<>', '<opaque packed word; encoding unverified>'] += 1
            for path, value in leaves(doc):
                typ = SCHEMA.get(path) if account else None
                if path.endswith(('.defName', '.def', '.pwDefName', '.activeModules[]', '.passiveModules[]', '.munition[]')): typ = 'defName'
                if path.endswith('.vid'): typ = 'vid'
                if '.specialModules.' in path and isinstance(value, str): typ = 'defName'
                if not typ or 'packed' in typ: continue
                fields[collection, path] = typ
                observed.add((collection, path))
                if value in ('', 0, None): continue
                local_iids, local_vids = iids, vids
                if not account:
                    player = re.match(r'gameStats\.(player_\d+)\.', path)
                    uid = doc.get('gameStats', {}).get(player[1], {}).get('uid') if player else doc.get('receiver')
                    local_iids, local_vids = account_indexes.get(uid, ({}, {}))
                name = value if typ == 'defName' else (local_iids if typ == 'iid' else local_vids).get(value)
                if name in names: refs.add((name, 'db', collection, path))
                else:
                    # Never emit account-local numeric identifiers.
                    unresolved[collection, path, str(value) if typ == 'defName' else '<unresolved instance>'] += 1
    for path, typ in SCHEMA.items(): fields.setdefault(('cosmosim_node/accounts', path), typ)
    for collection, path, typ in [
        ('delivered_node/delivered', 'attachments.<>.content.defName', 'defName'),
        ('delivered_node/delivered', 'attachments.<>.content.vid', 'vid'),
        ('games_node/games', 'gameStats.player_<>.vesselsRewards[].vid', 'vid'),
        ('games_node/games', 'gameStats.player_<>.vesselsStats[].vid', 'vid'),
        ('logs_node/logs', 'eventDesc.defName', 'defName'),
        ('logs_node/logs', 'eventDesc.vid', 'vid'),
        ('logs_node/logs', 'eventDesc.craftResources.<>', 'defName')]:
        fields.setdefault((collection, path), typ)
    normalized, seen = {}, set()
    for (collection, path), typ in fields.items():
        normalized_path = re.sub(r'(?<=player_)\d+', '<>', path)
        normalized_path = re.sub(r'(?<=attachments\.)\d+', '<>', normalized_path)
        normalized[collection, normalized_path] = typ
        if (collection, path) in observed: seen.add((collection, normalized_path))
    return refs, unresolved, {k: dict(type=v, seen=k in seen) for k, v in normalized.items()}, counts
