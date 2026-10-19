"""Deterministic public data writers (CC0-1.0)."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .core import COLUMNS, STATUSES, database, db_reference, game_location, load
from .descriptions import normalize, select, strings
from .locations import DB_COLUMNS, LOCATION_COLUMNS, db_by_kind, locations, race_names

MEANINGS = {
    'defName': 'Internal definition code. Primary identity together with kind; use it for lookup.',
    'kind': 'Registry item family, such as ship or module.',
    'name_en': 'English identifying name; empty when unresolved.',
    'name_ru': 'Russian identifying name; empty when unresolved.',
    'label_en': 'English name with distinguishing tier, rank and variant parts; raw code when unnamed.',
    'label_ru': 'Russian distinguishing display label; raw code when unnamed.',
    'name_status': 'Trust vocabulary: exact (direct key), own_field (own definition field), prefixed (known key prefix), category (shared subtype), derived (our derivation), none (unresolved). Category and derived are not exact item titles.',
    'short_desc_en': 'English description, whitespace normalized, at most 200 Unicode characters, or empty. Own short description, own description, then category description. Long candidates are skipped. No lore.',
    'short_desc_ru': 'Russian description selected independently with the same limit and fallback order.',
    'desc_status': 'Same vocabulary as name_status. If language sources differ, the more general status wins: category, derived, prefixed, own_field, exact. none means both descriptions are empty. Per-language provenance is retained by the local build.',
    'desc_has_placeholders': 'Boolean: either description contains a raw $value$ placeholder. Values are never substituted.',
    'race': 'Raw static race code, for example ai.Race.EMPIRE; empty if unavailable.',
    'rank': 'Static numeric rank or empty; never inferred from tier.',
    'tier': 'Static numeric tier or empty; never converted to rank.',
    'storeItemId': 'Own definition ID or empty. NOT unique: lookup by kind and defName. Expressions and inherited IDs stay blank.',
    'storeId': 'Store XML identifier or empty; a separate namespace from storeItemId.',
    'atlasId': 'Atlas identifier or empty; a separate namespace from store and account instance IDs.',
    'storeItemId_shared': 'Boolean: another row in the full registry shares this nonempty storeItemId; includes shared defaults and zero.',
    'account_scope': 'account, npc_or_internal, or unknown. Main items files contain account only. unknown means scope is unestablished. Account classification does not prove grantability.',
    'defined_in': 'Standard relative install location and physical line: star conflict\\data\\gamedata\\def\\ex\\ship.lua:26711. Resolve under your Steam installation.',
    'db_fields': 'Database field paths where this item was seen in a sample database, e.g. cosmosim_<WinUser>.accounts.vessels[].defName. Only a confirmation: where an item of a kind CAN be stored is in data/db_by_kind.csv. Numeric sample attachment indices become <>.',
    'flags': 'Registry diagnostic code list, such as no_name or xml_only; retained independently of improved names.',
    'race_en': 'English race or group name from the game string tables (race_<CODE>), e.g. Empire; empty if the item has no race code.',
    'race_ru': 'Russian race or group name from the game string tables, e.g. Империя.',
}


MEANINGS_RU = {
    'defName': 'Внутренний код определения. Вместе с kind задаёт основную идентичность; используйте для поиска.',
    'kind': 'Тип предмета в реестре, например ship или module.',
    'name_en': 'Английское идентифицирующее название; пусто, если не найдено.',
    'name_ru': 'Русское идентифицирующее название; пусто, если не найдено.',
    'label_en': 'Английское название с различающими технологическим уровнем, рангом и вариантом; исходный код для безымянных предметов.',
    'label_ru': 'Русское отображаемое название для различения вариантов; исходный код для безымянных предметов.',
    'name_status': 'Степень достоверности: exact (прямой ключ), own_field (собственное поле определения), prefixed (известный префикс ключа), category (общий подтип), derived (составлено нами), none (не найдено). category и derived не являются точными названиями предметов.',
    'short_desc_en': 'Английское описание с нормализованными пробелами, не более 200 символов Unicode, либо пустое. Сначала собственное краткое описание, затем собственное описание, затем описание категории. Длинные варианты пропускаются. Художественный текст исключён.',
    'short_desc_ru': 'Русское описание выбирается независимо с тем же пределом и порядком запасных вариантов.',
    'desc_status': 'Те же статусы, что у name_status. Если источники языков различаются, выбирается более общий статус: category, derived, prefixed, own_field, exact. none означает, что оба описания пусты. Происхождение по языкам сохраняется в локальной сборке.',
    'desc_has_placeholders': 'Логическое значение: хотя бы одно описание содержит необработанную подстановку $value$. Значения не подставляются.',
    'race': 'Исходный статический код расы, например ai.Race.EMPIRE; пусто, если недоступен.',
    'rank': 'Статический числовой ранг или пустое значение; не выводится из технологического уровня.',
    'tier': 'Статический числовой технологический уровень или пустое значение; не преобразуется в ранг.',
    'storeItemId': 'Собственный ID определения или пустое значение. НЕ уникален: ищите по kind и defName. Выражения и унаследованные ID оставляются пустыми.',
    'storeId': 'Идентификатор XML магазина или пустое значение; отдельная система нумерации от storeItemId.',
    'atlasId': 'Идентификатор атласа или пустое значение; отдельная система от ID магазина и экземпляров учётной записи.',
    'storeItemId_shared': 'Логическое значение: другая строка полного реестра использует тот же непустой storeItemId; включает общие значения по умолчанию и ноль.',
    'account_scope': 'account, npc_or_internal или unknown. Основные файлы items содержат только account. unknown — область не установлена. Классификация как предмета учётной записи не доказывает возможность выдачи.',
    'defined_in': r'Стандартный относительный путь установки и физическая строка: star conflict\data\gamedata\def\ex\ship.lua:26711. Ищите внутри своей установки Steam.',
    'db_fields': 'Пути полей базы данных, где предмет наблюдался в образце, например cosmosim_<WinUser>.accounts.vessels[].defName. Это лишь подтверждение; возможные места хранения предметов по типам перечислены в data/db_by_kind.csv. Числовые индексы вложений образца заменены на <>.',
    'flags': 'Список диагностических кодов реестра, например no_name или xml_only; сохраняется независимо от уточнённых названий.',
    'race_en': 'Английское название расы или группы из игровых таблиц текстов (race_<CODE>), например Empire; пусто при отсутствии кода расы.',
    'race_ru': 'Русское название расы или группы из игровых таблиц текстов, например Империя.',
}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


def csv_write(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(row[k], ensure_ascii=False) if isinstance(row[k], (list, dict, bool)) else row[k] for k in columns})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def legacy_name(row):
    source = row['nameSource']
    status = ('none' if source == 'none' else 'category' if source == 'field:item_subtype' else 'exact' if source.startswith('defName') else 'own_field')
    return dict(name_en=row['name_en'], name_ru=row['name_ru'], label_en=row['name_en'] or '['+row['defName']+']', label_ru=row['name_ru'] or '['+row['defName']+']', name_status=status)


def rows(registry, names, tables):
    counts = Counter(str(r['storeItemId']) for r in registry.values() if r['storeItemId'] != '')
    result, evidence = [], []
    lore = {normalize(text) for table in tables.values() for key, (text, _) in table.items() if key.endswith('_desc_lore') and normalize(text)}
    for identity, row in sorted(registry.items()):
        name = names.get(identity)
        text, status, placeholders, ev = select(row, name, tables, lore)
        output = {k: row[k] for k in ['defName', 'kind', 'race', 'rank', 'tier', 'storeItemId', 'storeId', 'atlasId', 'account_scope', 'flags']}
        output.update({k: (name or legacy_name(row))[k] for k in ['name_en', 'name_ru', 'label_en', 'label_ru', 'name_status']})
        output.update(short_desc_en=text['en'], short_desc_ru=text['ru'], desc_status=status, desc_has_placeholders=placeholders,
                      storeItemId_shared=row['storeItemId'] != '' and counts[str(row['storeItemId'])] > 1,
                      defined_in=game_location(row['defFile'], row['defLine']),
                      db_fields=sorted({db_reference(r) for r in row['references'] if r['source'] == 'db'}))
        output['race_en'], output['race_ru'] = race_names(row['race'], tables)
        result.append({k: output[k] for k in COLUMNS})
        evidence.append(dict(kind=row['kind'], defName=row['defName'], languages=ev))
    return result, evidence


def db_rows(r013, registry):
    examples = {}
    for row in registry.values():
        for ref in row['references']:
            if ref['source'] == 'db':
                examples.setdefault(db_reference(ref), set()).add(row['kind'])
    result = []
    for line in (Path(r013)/'results/db_fields.md').read_text(encoding='utf-8').splitlines():
        cells = [c.strip().strip('`') for c in line.strip('|').split('|')]
        if len(cells) != 4 or '/' not in cells[0]:
            continue
        db, collection = cells[0].split('/')
        ref = database(db)+'.'+collection+'.'+cells[1]
        result.append(dict(database=database(db), collection=collection, field_path=cells[1], id_type=cells[2], example_kind=';'.join(sorted(examples.get(ref, set()))), seen_in_sample=cells[3]=='yes'))
    if not result:
        raise ValueError('no database field definitions')
    return sorted(result, key=lambda r: (r['database'], r['collection'], r['field_path']))


def schema():
    props = {k: {'type': 'string', 'description': MEANINGS[k]} for k in COLUMNS}
    for key in ['storeItemId', 'storeId', 'atlasId', 'rank', 'tier']:
        props[key]['type'] = ['string', 'integer']
    for key in ['db_fields', 'flags']:
        props[key].update(type='array', items={'type': 'string'}, uniqueItems=True)
    for key in ['storeItemId_shared', 'desc_has_placeholders']:
        props[key]['type'] = 'boolean'
    for key in ['name_status', 'desc_status']:
        props[key]['enum'] = STATUSES
    props['account_scope']['enum'] = ['account', 'npc_or_internal', 'unknown']
    for key in ['short_desc_en', 'short_desc_ru']:
        props[key]['maxLength'] = 200
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': 'Unofficial SC Scrap Metal Index item array', 'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': COLUMNS, 'properties': props}}


def documents(dist):
    (dist/'docs').mkdir(parents=True, exist_ok=True)
    docs = '# Data dictionary\n\nUnofficial community data, v0.1. JSON arrays and CSV rows have the same columns, sorted by kind and defName. UTF-8 without BOM. JSON keeps arrays and booleans; CSV list cells are JSON and booleans are true/false. Blank scalar values mean unavailable, never zero.\n\n'
    docs += '\n'.join('## '+k+'\n\n'+MEANINGS[k]+'\n' for k in COLUMNS)
    docs += '\n## Database field catalogue\n\nFields: database (standard database name), collection, field_path (nested path), id_type (reference namespace), example_kind (semicolon-separated observed item families, empty if unresolved), seen_in_sample (true/false). A sample database confirms these structures; where an item of each kind can be stored is listed in data/db_by_kind.csv. iid and vid are account-local instance references, never store IDs. Opaque atlas packed words remain unresolved. Unseen autogenItems fields are candidates, not established member schemas.\n\n## Standard locations\n\nGame references are relative to your star conflict installation. Client strings are inside star conflict\\data\\strings.pak: strings/english/string.txt and strings/russian/string.txt. Local server data is under %LOCALAPPDATA%\\Targem\\StarConflict\\. A local server database is cosmosim_<WinUser>; hosts may configure another name.\n\n## Coverage\n\nAccount names and distinguishing labels preserve the reviewed name statuses. The optional all-items files include NPC/internal and unknown rows; their non-account names retain original registry provenance, with direct keys mapped to exact, subtype fields to category, and other own fields to own_field. Those labels fall back to a raw code and do not have the account label enrichment. No sample absence establishes impossibility. No lore or assets are included.\n'
    (dist/'docs/data-dictionary.md').write_text(docs, encoding='utf-8', newline='\n')
    (dist/'NOTICE.md').write_text('# Notice\n\nItem names and descriptions are © Gaijin Entertainment / Targem Games, quoted as short identifying references. Unofficial community project, not affiliated with or endorsed by Gaijin or Targem.\n\nOur code, documentation and compilation: CC0-1.0 (https://creativecommons.org/publicdomain/zero/1.0/). Game text is not ours. Authors: jacek-mar / Hystrix. No game logos or assets are included.\n\nBuild: Hub 1.99.0.167293, stock files. Community configuration packs change files and are not reflected here. Database locations are given per kind (data/db_by_kind.csv): where an item can be stored, not permission to grant it. Battle and statistics history is not covered yet.\n', encoding='utf-8', newline='\n')
    (dist/'README.md').write_text('# SC Scrap Metal Index — v0.1\n\nUnofficial Star Conflict item data for community hosts and modders. Stock files, Hub 1.99.0.167293.\n\nOpen data/items.csv in a spreadsheet, or use data/items.json for account item lookup. Use kind and defName together as identity. storeItemId is not unique. Category and derived names need their status labels. Empty text is unresolved; unknown scope remains unknown. Placeholders in descriptions are raw game text.\n\nThe optional data/items_all files include NPC/internal and unknown entries. data/db_fields.csv lists database reference structures; data/schema.json defines the item contract; data/manifest.json records counts and SHA-256 hashes. Read [the data dictionary](docs/data-dictionary.md) and [notices](NOTICE.md) before use. A browser search site and standalone generator are future phases.\n\nResearch: [Unofficial Star Conflict Server - Under the Hood](https://github.com/jacek-mar/sc-server-under-the-hood). Authors: jacek-mar / Hystrix. Nothing in this export authorizes granting an item or establishes runtime availability.\n', encoding='utf-8', newline='\n')
    public_docs = Path(__file__).resolve().parent.parent / 'public_docs'
    for source, target in [('README.md', dist/'README.md'), ('using-the-search.md', dist/'docs/using-the-search.md'),
                           ('rebuild-and-host.md', dist/'docs/rebuild-and-host.md')]:
        target.write_text((public_docs/source).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    full = json.loads((dist/'data/items_all.json').read_text(encoding='utf-8'))
    account_kinds = sorted({r['kind'] for r in full if r['account_scope'] == 'account'})
    all_kinds = sorted({r['kind'] for r in full})
    flags = sorted({flag for r in full for flag in r['flags']})
    docs = docs.replace('v0.1', 'v0.2')
    docs += '\n## Actual values in this export\n\nAccount kinds: ' + ', '.join('`'+k+'`' for k in account_kinds) + '.\n\n'
    docs += 'All-definition kinds: ' + ', '.join('`'+k+'`' for k in all_kinds) + '.\n\n'
    docs += 'Flags: ' + ', '.join('`'+k+'`' for k in flags) + '.\n\n'
    docs += 'Name and description statuses: ' + ', '.join('`'+k+'`' for k in STATUSES) + '.\n\n'
    docs += (public_docs/'dictionary-extra.md').read_text(encoding='utf-8')
    (dist/'docs/data-dictionary.md').write_text(docs, encoding='utf-8', newline='\n')

    russian_documents(dist, public_docs, account_kinds, all_kinds, flags)


def russian_documents(dist, public_docs, account_kinds, all_kinds, flags):
    for source, target in [('README.md', dist/'ru/README.md'),
                           ('using-the-search.md', dist/'docs/ru/using-the-search.md')]:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((public_docs/'ru'/source).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    docs = '# Словарь данных\n\nНеофициальные данные сообщества, v0.2.2. Массивы JSON и строки CSV имеют одинаковые столбцы и отсортированы по kind и defName. UTF-8 без BOM. JSON сохраняет массивы и логические значения; ячейки списков CSV содержат JSON, логические значения — true/false. Пустые скалярные значения означают отсутствие данных, а не ноль.\n\n'
    docs += '\n'.join('## '+k+'\n\n'+MEANINGS_RU[k]+'\n' for k in COLUMNS)
    docs += '\n## Каталог полей базы данных\n\nПоля: database (стандартное имя базы данных), collection, field_path (вложенный путь), id_type (пространство идентификаторов ссылки), example_kind (наблюдавшиеся типы предметов через точку с запятой; пусто, если не определены), seen_in_sample (true/false). Образец базы данных подтверждает эти структуры; места возможного хранения по типам перечислены в data/db_by_kind.csv. iid и vid — ссылки на экземпляры внутри учётной записи, а не ID магазина. Непрозрачные упакованные слова атласа не расшифрованы. Ненаблюдавшиеся поля autogenItems — возможные варианты, а не установленная схема элементов.\n'
    docs += '\n## Стандартные пути\n\nИгровые ссылки заданы относительно вашей установки star conflict. Тексты клиента находятся внутри star conflict\\data\\strings.pak: strings/english/string.txt и strings/russian/string.txt. Данные локального сервера — в %LOCALAPPDATA%\\Targem\\StarConflict\\. База локального сервера — cosmosim_<WinUser>; оператор может настроить другое имя.\n'
    docs += '\n## Охват\n\nНазвания предметов учётной записи и различающие варианты названия сохраняют проверенные статусы. Необязательные файлы всех предметов включают внутренние / NPC и неустановленные записи; названия вне учётных записей сохраняют происхождение из исходного реестра: прямые ключи — exact, поля подтипов — category, другие собственные поля — own_field. Эти отображаемые названия при отсутствии текста используют код и не имеют уточнений вариантов учётных записей. Отсутствие в образце не доказывает невозможность. Художественный текст и ресурсы игры не включены.\n'
    docs += '\n## Фактические значения в этой выгрузке\n\n'
    for label, values in [('Типы учётных записей', account_kinds), ('Типы всех определений', all_kinds), ('Признаки', flags), ('Статусы названий и описаний', STATUSES)]:
        docs += label+': '+', '.join('`'+v+'`' for v in values)+'.\n\n'
    docs += (public_docs/'ru/dictionary-extra.md').read_text(encoding='utf-8')
    (dist/'docs/ru/data-dictionary.md').write_text(docs, encoding='utf-8', newline='\n')
    notice = (dist/'NOTICE.md').read_text(encoding='utf-8')
    # Keep the English D3 paragraph verbatim before the convenience translation.
    notice += '\n## Русский перевод\n\nНазвания и описания предметов © Gaijin Entertainment / Targem Games; приведены в виде кратких цитат для идентификации. Неофициальный проект сообщества, не связанный с Gaijin или Targem и не одобренный ими.\n\nПеревод приведён для удобства; при расхождениях действует английский текст.\n\nНаш код, документация и составление данных: CC0-1.0. Игровой текст нам не принадлежит. Авторы: jacek-mar / Hystrix. Логотипы и ресурсы игры не включены.\n\nСборка: Hub 1.99.0.167293, штатные файлы. Изменения из пакетов конфигурации сообщества здесь не отражены. Пути базы данных приведены по типам (data/db_by_kind.csv): возможное место хранения не является разрешением на выдачу. История боёв и статистики пока не охвачена.\n'
    (dist/'ru/NOTICE.md').write_text(notice, encoding='utf-8', newline='\n')


def build(args):
    if not Path(args.gamedir).is_dir():
        raise ValueError('game input directory does not exist')
    registry, names = load(args.r013, args.r016)
    tables = strings(args.strings)
    all_rows, evidence = rows(registry, names, tables)
    accounts = [r for r in all_rows if r['account_scope'] == 'account']
    dist = Path('dist'); data = dist/'data'
    counts = {}
    for stem, group in [('items', accounts), ('items_all', all_rows)]:
        dump(data/(stem+'.json'), group)
        csv_write(data/(stem+'.csv'), group, COLUMNS)
        for suffix in ['.csv', '.json']:
            counts[stem+suffix] = {'rows': len(group), 'by_kind': dict(sorted(Counter(r['kind'] for r in group).items()))}
    fields = db_rows(args.r013, registry)
    csv_write(data/'db_fields.csv', fields, ['database', 'collection', 'field_path', 'id_type', 'example_kind', 'seen_in_sample'])
    counts['db_fields.csv'] = {'rows': len(fields)}
    places = locations(registry)
    dump(data/'locations.json', places); csv_write(data/'locations.csv', places, LOCATION_COLUMNS)
    counts['locations.json'] = counts['locations.csv'] = {'rows': len(places), 'by_group': dict(sorted(Counter(r['group'] for r in places).items()))}
    kinds = db_by_kind()
    dump(data/'db_by_kind.json', kinds); csv_write(data/'db_by_kind.csv', kinds, DB_COLUMNS)
    counts['db_by_kind.json'] = counts['db_by_kind.csv'] = {'rows': len(kinds)}
    dump(data/'schema.json', schema())
    documents(dist)
    from .site import generate
    generate(dist)
    manifest = dict(build_id='Hub 1.99.0.167293', generated_at=datetime.now(timezone.utc).isoformat(), files=counts,
                    sha256={p.name: digest(p) for p in sorted(data.iterdir()) if p.name != 'manifest.json'})
    dump(data/'manifest.json', manifest)
    dump(Path('out/description_evidence.json'), evidence)
    return accounts, all_rows, tables
