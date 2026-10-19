"""Reproducible real-install inventory and known-fact checks. CC0-1.0."""
import argparse
from collections import Counter
import json
from pathlib import Path
from .contract import FORMAT_VERSION, table_get
from .reporting import write_csv, group_warnings, write_warning_audit

QUEST_FILE = 'data/gamedata/shared/quests.lua'
GAMEPLAY_FILE = 'data/gamedata/gameplaysettings.lua'
PLATFORM_FILE = 'cloud/data/default_platform_config.lua'


def known_checks(documents):
    """Check parsed values and ranges, not source substrings."""
    checks = []

    def record(name, passed, evidence, value):
        checks.append(dict(check=name, passed=bool(passed), evidence=evidence, parsed_value=value))

    def assignment(file, target, scope=None):
        return next((a for a in documents.get(file, {}).get('assignments', [])
                     if a['target'] == target and a['scope'] == scope), None)

    quest = assignment(QUEST_FILE, 'Quests[QuestId.CAMPAIGN_QUEST_23]')
    stages = table_get(quest['value'], 'stages') if quest else None
    restrictions = table_get(table_get(stages, 1), 'restrictions', [])
    restrictions = restrictions if isinstance(restrictions, list) else []
    objective = {'$ref': 'ai.GameplayObjectives.PLANT_BOMB'}
    quest_ok = any(table_get(r, 'param') == {'$ref': 'ai.GameEventParam.GAMEPLAY_OBJECTIVE'}
                   and isinstance(table_get(r, 'num_value'), list)
                   and objective in table_get(r, 'num_value') for r in restrictions)
    record('campaign_quest_23_plant_bomb', quest_ok,
           f"{QUEST_FILE}:{quest['line'] if quest else '?'} (restriction :1804)",
           'ai.GameplayObjectives.PLANT_BOMB' if quest_ok else 'missing objective restriction')

    gameplay = assignment(GAMEPLAY_FILE, 'GameplayDef[ai.Gameplay.BOMB_THE_BASE]')
    value = table_get(gameplay['value'], 'bomb_plant_time') if gameplay else None
    record('bomb_plant_time', type(value) in (int, float) and value == 6,
           f"{GAMEPLAY_FILE}:{gameplay['line'] if gameplay else '?'} (field :1138)", value)

    for target, scope, line in [('cvars.store_allowAllItemsForBying', 'ConfigureShard', 83),
                                ('cvars.sv_autogenModulesEnabled', 'ConfigureZoneInstance', 1445)]:
        a = assignment(PLATFORM_FILE, target, scope)
        value = a['value'] if a else None
        ok = a and a['line'] == line and type(value) in (int, float) and value == 0 and not a['conditional']
        record(target, ok, f'{PLATFORM_FILE}:{line}',
               f'{value!r}; scope={a["scope"] if a else "missing"}; line={a["line"] if a else "missing"}')

    platform = documents.get(PLATFORM_FILE, {})
    for name, line in [('ConfigureDediServer',1179), ('ConfigureDediServerFlags',1388),
                       ('ConfigureZoneInstance',1403)]:
        f = next((f for f in platform.get('functions', []) if f['name'] == name and f['line'] == line), None)
        record(name + '_range', f and f['end_line'] is not None and f['end_line'] > line,
               f'{PLATFORM_FILE}:{line}',
               f'{f["line"]}-{f["end_line"]}' if f else 'missing function')

    templates = [a for a in platform.get('assignments', []) if a['scope'] == 'ConfigureMatchmaker'
                 and a['target'] == 'local:coopQueueTemplate']
    queue_ok = False
    for a in templates:
        maps = table_get(a['value'], 'levelsDesc')
        if a['line'] == 429 and isinstance(maps, dict) and len(maps) == 5:
            queue_ok = all(v == [4,9,11] and all(type(n) is int for n in v) for v in maps.values())
    record('coop_template_gameplays', queue_ok, f'{PLATFORM_FILE}:429 (levelsDesc :435-440)',
           '5 map lists, each [4,9,11]' if queue_ok else 'missing or changed template')
    # Older synthetic documents without this additive capability retain the
    # original eight checks. New exports additionally validate call records.
    if platform.get('call_format_version') == 1:
        calls=platform['calls']
        insert=next((c for c in calls if c['callee']=='table.insert' and c['line']==448),None)
        child=next((c for c in calls if insert and c['parent_id']==insert['id']
                    and c['callee']=='InstantiateQueueTemplate'),None)
        ok=(insert and insert['scope']=='ConfigureMatchmaker' and insert['context']=='statement'
            and insert['arguments'] and insert['arguments'][0]=={'$ref':'queuesConfigLo'}
            and child and child['arguments'] and child['arguments'][0]=={'$ref':'coopQueueTemplate'})
        record('structured_coop_insert',ok,f'{PLATFORM_FILE}:448',
               'table.insert(queuesConfigLo, InstantiateQueueTemplate(coopQueueTemplate,...))' if ok else 'missing or changed call')
        for line,queue in [(878,'queuesConfig'),(881,'queuesConfigLo')]:
            call=next((c for c in calls if c['callee']=='MatchMaker_ReconfigureQueues' and c['line']==line),None)
            ok=call and call['arguments'] and call['arguments'][0]=={'$ref':queue} and call['scope']=='ConfigureMatchmaker'
            record('structured_register_'+queue,ok,f'{PLATFORM_FILE}:{line}',
                   queue if ok else 'missing or changed call')
    return checks


def write_spot_checks(path, checks):
    lines = ['# Parsed known-fact checks', '',
             '*(file)* Generated from format-version-2 parsed assignments and function ranges.',
             'Values remain static observations; no game Lua was executed.', '',
             '| Check | Status | Relative source evidence | Parsed value |',
             '|---|---|---|---|']
    for check in checks:
        value = str(check['parsed_value']).replace('|', '\\|').replace('\n', ' ')
        lines.append(f"| {check['check']} | {'PASS' if check['passed'] else 'FAIL'} | `{check['evidence']}` | `{value}` |")
    lines += ['', 'Field/restriction line hints are pinned to the reviewed install in README.md.',
              'Assignment/function declaration lines come from the parser. A failed check',
              'requires inspection of input-version drift or parser behaviour, not updating',
              'expected values automatically.', '']
    path.write_text('\n'.join(lines), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Export and validate a read-only game install.')
    parser.add_argument('--gamedir', required=True, type=Path)
    parser.add_argument('--out', type=Path, default=Path('out/install'))
    parser.add_argument('--results', type=Path, default=Path('results'))
    args = parser.parse_args(argv)
    from .__main__ import export_main, inside
    root = args.gamedir.resolve()
    if inside(args.results.resolve(), root):
        parser.error('Results must be outside the game install')
    export_status = export_main(['--gamedir', str(root), '--out', str(args.out)])
    inventory, warnings, documents = [], [], {}
    files = sorted((root / 'data/gamedata').rglob('*.lua')) + [root / PLATFORM_FILE]
    total_assignments = 0
    for source in files:
        label = source.relative_to(root).as_posix()
        output = args.out / Path(label).with_suffix('.json')
        with output.open(encoding='utf-8') as stream:
            document = json.load(stream)
        scopes = Counter(a['scope'] or '<top-level>' for a in document['assignments'])
        inventory.append(dict(file=label, assignments=len(document['assignments']),
                              calls=len(document['calls']),
                              warnings=len(document['warnings']),
                              scopes=json.dumps(dict(sorted(scopes.items())), sort_keys=True)))
        total_assignments += len(document['assignments'])
        warnings.extend(document['warnings'])
        if label in (QUEST_FILE, GAMEPLAY_FILE, PLATFORM_FILE):
            documents[label] = document
    platform = documents.get(PLATFORM_FILE, {})
    functions = []
    for f in platform.get('functions', []):
        if not f['name'].startswith('Configure'):
            continue
        count = sum(a['scope'] == f['name'] and f['line'] <= a['line'] <= (f['end_line'] or 0)
                    for a in platform['assignments'])
        functions.append(dict(file=PLATFORM_FILE, function=f['name'], start_line=f['line'],
                              end_line=f['end_line'], assignments=count))
    call_rows=[]
    for call in platform.get('calls',[]):
        refs=[v['$ref'] for v in call['arguments'] if isinstance(v,dict) and '$ref' in v]
        call_rows.append(dict(file=PLATFORM_FILE,id=call['id'],parent_id=call['parent_id'],
                              scope=call['scope'],callee=call['callee'] or '<dynamic>',
                              arguments=len(call['arguments']),argument_refs='; '.join(refs),
                              line=call['line'],end_line=call['end_line'],
                              conditional=call['conditional'],context=call['context']))
    checks = known_checks(documents)
    try:
        write_csv(args.results / 'inventory.csv', ['file','assignments','calls','warnings','scopes'],
                  sorted(inventory, key=lambda row: row['file']))
        codes = [dict(code=r['cause'], count=r['count'], examples=r['examples'])
                 for r in group_warnings(warnings, lambda w: w['code'])]
        write_csv(args.results / 'warnings_by_code.csv', ['code','count','examples'], codes)
        write_csv(args.results / 'platform_functions.csv',
                  ['file','function','start_line','end_line','assignments'], functions)
        write_csv(args.results / 'platform_calls.csv',
                  ['file','id','parent_id','scope','callee','arguments','argument_refs',
                   'line','end_line','conditional','context'],call_rows)
        write_warning_audit(args.results, warnings)
        write_spot_checks(args.results / 'spot_checks.md', checks)
    except OSError:
        parser.exit(2, 'Cannot write validation results\n')
    failed = sum(not c['passed'] for c in checks)
    print(json.dumps(dict(format_version=FORMAT_VERSION, files=len(inventory),
                          assignments=total_assignments, warnings=len(warnings),
                          checks=len(checks), failed_checks=failed), sort_keys=True))
    return 1 if failed or export_status else 0
