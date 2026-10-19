"""Namespace-explicit lookup with no last-row-wins behaviour."""
from collections import defaultdict
from .scope import account_rows


def lookup_id(rows, namespace, value, *, kind=None, slot=None):
    if namespace not in ('storeItemId', 'storeId', 'atlasId'):
        raise ValueError('Specify storeItemId, storeId or atlasId')
    if value is None or str(value) == '':
        return dict(status='missing', matches=[])
    matches = []
    for row in account_rows(rows):
        if kind and row['kind'] != kind:
            continue
        if slot and row['account_slot'] != slot:
            continue
        values = row['storeIds'] if namespace == 'storeId' else [row[namespace]]
        if str(value) in map(str, values):
            matches.append(row)
    return dict(status='missing' if not matches else 'unique' if len(matches) == 1 else 'ambiguous', matches=matches)


def collisions(rows):
    groups = defaultdict(list)
    for row in rows:
        if row['storeItemId'] != '':
            groups[str(row['storeItemId'])].append(row)
    result = []
    for value, members in sorted(groups.items(), key=lambda p: int(p[0])):
        if len(members) < 2:
            continue
        scopes = {r['account_scope'] for r in members}
        if value in ('1', '1000'):
            category = 'bulk_shared_default'
        elif value == '0' and scopes == {'npc_or_internal'}:
            category = 'zero_npc_internal'
        elif value == '0' and not account_rows(members):
            category = 'zero_npc_internal_with_unknown'
        elif len(account_rows(members)) > 1:
            category = 'account_catalogue_overlap'
        else:
            category = 'uncertain'
        result.append(dict(storeItemId=value, category=category,
                           accountMatches=len(account_rows(members)), members=[{
                               k: r[k] for k in ('defName', 'kind', 'account_scope', 'account_slot',
                                                'account_rule', 'account_evidence', 'account_uncertainty',
                                                'defFile', 'defLine', 'storeIds')
                           } for r in members]))
    return result
