"""Own IDs only: inherited/default values are evidence, never substituted."""
import json


def id_cause(definition, fields, origin):
    own = definition['fields'] if definition else {}
    value = own.get('storeItemId')
    location = f'{origin["file"]}:{origin["line"]}'
    expression = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, dict) else ''
    if value is not None and not isinstance(value, dict):
        cause = 'literal_own_id'
    elif isinstance(value, dict):
        cause = 'unevaluated_expression'
    elif definition is None or origin['file'].startswith('cloud/'):
        cause = 'xml_only_no_own_id'
    elif 'storeItemId' in fields:
        cause = 'inherited_id_not_an_own_id'
        expression = json.dumps(fields['storeItemId'], ensure_ascii=False, sort_keys=True)
    else:
        cause = 'no_own_or_inherited_id'
    return dict(storeItemIdCause=cause, storeItemIdExpression=expression,
                storeItemIdEvidence=location)
