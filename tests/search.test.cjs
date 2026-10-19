const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const SMI = require('../site/search.js');
const root = path.resolve(__dirname, '../dist');
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'));
function data(file, key) {
  const context = {window: {}};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'site/data', file), 'utf8'), context);
  return JSON.parse(JSON.stringify(context.window[key]));
}
const account = data('items.js', 'SMI_INDEX');
const all = data('items_all.js', 'SMI_ALL');
const shared = data('shared.js', 'SMI_SHARED');
const fixture = [
  ['ship', 'Code_A', 'Alpha', 'Альфа', 'Alpha I', 'Альфа I', 'exact', 224, '', 0, 'account'],
  ['module', 'Code_B', 'Beta', 'Бета', 'Beta II', 'Бета II', 'category', 2240, 44, '', 'unknown'],
];

test('case insensitive names, labels, defName and Cyrillic', () => {
  for (const q of ['aLpHa', 'ALPHA I', 'code_a', 'АЛЬФА']) assert.deepEqual(SMI.search(fixture, {q}), [fixture[0]]);
});
test('ID matches are exact, include zero, and exclude blanks', () => {
  assert.deepEqual(SMI.search(fixture, {q: '224'}), [fixture[0]]);
  assert.deepEqual(SMI.search(fixture, {q: '0'}), [fixture[0]]);
  assert.deepEqual(SMI.search(fixture, {q: '44'}), [fixture[1]]);
  assert.equal(SMI.search(fixture, {q: '22'}).length, 0);
});
test('kind and status filters combine with text', () => {
  assert.deepEqual(SMI.search(fixture, {kind: 'module', status: 'category', q: 'бета'}), [fixture[1]]);
  assert.equal(SMI.search(fixture, {kind: 'ship', status: 'category'}).length, 0);
  assert.equal(SMI.search(fixture, {q: '   '}).length, 2);
});
test('hash roundtrip preserves Cyrillic, special characters, filters and selection', () => {
  const state = {q: 'Кошмар & #224 + %', kind: 'ship', status: 'prefixed', all: true, lang: 'ru', item: 'Code_A', itemKind: 'ship'};
  assert.deepEqual(SMI.decode(SMI.encode(state)), state);
  assert.equal(SMI.decode('#status=invalid&lang=invalid&all=0').status, '');
  assert.equal(SMI.decode('#q=%').q, '%');
});
test('warnings explain shared IDs, category, derivation, missing name, scope and placeholders', () => {
  const item = {kind: 'ship', defName: 'A', storeItemId: 0, storeItemId_shared: true, name_status: 'category', account_scope: 'unknown', desc_has_placeholders: true};
  const lines = SMI.warnings(item, {'0': [['ship', 'A'], ['module', 'B']]});
  assert.equal(lines.length, 4);
  assert.match(lines.join(' '), /module \/ B/);
  assert.doesNotMatch(lines.join(' '), /ship \/ A/);
  assert.match(SMI.warnings({...item, name_status: 'derived'}, {}).join(' '), /our derivation/);
  assert.match(SMI.warnings({...item, name_status: 'none'}, {}).join(' '), /No name was resolved/);
});
test('real indexes retain 14973 account and 19364 full rows within 4 MB', () => {
  assert.equal(account.length, 14973); assert.equal(all.length, 19364);
  assert.ok(fs.statSync(path.join(root, 'site/data/items.js')).size <= 4000000);
  assert.ok(account.every(r => r.length === 11 && r[10] === 'account'));
});
test('real Nebula GS search and reconstructed detail', () => {
  const row = SMI.search(account, {q: 'Nebula GS'}).find(r => r[1] === 'Ship_Race1_S_T4_Glass');
  assert.ok(row);
  const details = data('details-ship.js', 'SMI_DETAILS_ship');
  const item = SMI.object(row, details[row[1]]);
  assert.equal(item.defined_in, 'star conflict\\data\\gamedata\\def\\ex\\ship.lua:26711');
  assert.deepEqual(item, read('data/items.json').find(r => r.defName === row[1]));
});
test('real 224 search and warning each name the other ship', () => {
  const rows = SMI.search(account, {q: '224'});
  const details = data('details-ship.js', 'SMI_DETAILS_ship');
  for (const [name, other] of [['Ship_Race3_L_T5_Mole', 'Ship_Race2_L_T5_Protozan'], ['Ship_Race2_L_T5_Protozan', 'Ship_Race3_L_T5_Mole']]) {
    const row = rows.find(r => r[1] === name); assert.ok(row);
    assert.match(SMI.warnings(SMI.object(row, details[name]), shared).join(' '), new RegExp(other));
  }
});
test('real Russian prefixed name', () => {
  const row = SMI.search(account, {q: 'КОШМАР ИЕРИХОНА'}).find(r => r[1] === 'Jericho_dream');
  assert.ok(row); assert.equal(row[6], 'prefixed');
});
test('real Acceleration Coils labels distinguish every result in both languages', () => {
  const rows = SMI.search(account, {q: 'Acceleration Coils'});
  assert.ok(rows.length > 1);
  for (const i of [4, 5]) assert.equal(new Set(rows.map(r => r[i])).size, rows.length);
});
test('shared catalogue covers the full registry exactly', () => {
  const full = read('data/items_all.json'), expected = {};
  for (const row of full) if (row.storeItemId_shared) (expected[String(row.storeItemId)] ||= []).push([row.kind, row.defName]);
  assert.deepEqual(shared, expected);
});
test('HTML and controller enforce local scripts, text insertion, lazy full data and 200 row batches', () => {
  const html = fs.readFileSync(path.join(root, 'site/index.html'), 'utf8');
  const app = fs.readFileSync(path.join(root, 'site/app.js'), 'utf8');
  assert.match(html, /Content-Security-Policy/); assert.match(html, /connect-src 'none'/);
  assert.doesNotMatch(html, /src="(?:https?:|\/\/)|src="data\/items_all/);
  assert.match(app, /if \(state.all\).*await load\('items_all'\)/);
  assert.match(app, /slice\(0, limit\)/); assert.match(app, /limit \+= 200/);
  for (const file of ['app.js', 'search.js']) assert.doesNotMatch(fs.readFileSync(path.join(root, 'site', file), 'utf8'), /innerHTML|fetch\s*\(|XMLHttpRequest|WebSocket|https?:/);
});
test('every CSS color meets 4.5:1 against the only background', () => {
  const css = fs.readFileSync(path.join(root, 'site/style.css'), 'utf8');
  const colors = [...new Set(css.match(/#[0-9a-f]{6}/gi))];
  function lum(hex) {
    const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    return rgb.reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
  }
  for (const color of colors.filter(c => c !== '#101820')) assert.ok((lum(color) + .05) / (lum('#101820') + .05) >= 4.5, color);
  assert.ok(colors.length === 7);
});

// Revision 1 (v0.2) helpers.
const labelRows = [
  ['ship', 'Ship_M', 'Mole', 'Mole', 'Mole V [Mole]', 'Mole V [Mole]', 'exact', 224, 4409, '', 'account'],
  ['ship', 'Ship_N', 'Nebula GS', 'Nebula GS', 'Nebula GS IV [Glass]', 'Nebula GS IV [Glass]', 'exact', 228, 728, '', 'account'],
  ['module', 'C_RT', 'Coil', 'Катушка', 'Coil I [RT]', 'Катушка I [RT]', 'category', 1, 2, '', 'account'],
  ['module', 'C_ET', 'Coil', 'Катушка', 'Coil I [ET]', 'Катушка I [ET]', 'category', 1, 3, '', 'account'],
  ['module', 'V', 'Volt', 'Вольт', 'Volt V', 'Вольт V', 'category', 8567, 5936, 224, 'account'],
];
test('labels drop a bracket only when it repeats the name or is not needed', () => {
  assert.deepEqual(SMI.displayLabels(labelRows, 'en'), ['Mole V', 'Nebula GS IV', 'Coil I [RT]', 'Coil I [ET]', 'Volt V']);
  assert.deepEqual(SMI.displayLabels(labelRows, 'ru').slice(2, 4), ['Катушка I [RT]', 'Катушка I [ET]']);
});
test('matched id type is reported', () => {
  assert.deepEqual(SMI.matchedIds(labelRows[4], '224'), ['atlasId']);
  assert.deepEqual(SMI.matchedIds(labelRows[0], '224'), ['storeItemId']);
  assert.deepEqual(SMI.matchedIds(labelRows[0], 'Mole'), []);
});
test('count text uses singular for one result', () => {
  assert.equal(SMI.countText(1, 1, false), '1 result · showing 1 · account items');
  assert.equal(SMI.countText(2, 2, true), '2 results · showing 2 · all definitions');
});
test('locations are grouped in editor order', () => {
  const groups = SMI.groupLocations([['used_by', 'a:1', 'required ship of', 'W'], ['edit_here', 'b:2', 'definition', ''], ['generated', 'c:3', 'server copy', '']]);
  assert.deepEqual(groups.map(g => g.key), ['edit_here', 'generated', 'used_by']);
});
test('real data: Mole locations and ship database field', () => {
  const loc = data('locations-ship.js', 'SMI_LOC_ship');
  const groups = SMI.groupLocations(loc['Ship_Race3_L_T5_Mole']);
  const edit = groups.find(g => g.key === 'edit_here').rows.map(r => r[1]);
  assert.ok(edit.includes(String.raw`star conflict\data\gamedata\def\ex\ship.lua:15649`));
  const used = groups.find(g => g.key === 'used_by').rows;
  assert.ok(used.some(r => r[2] === 'required ship of' && r[3] === 'Weapon_MoleGun_T5_Mk1'));
  const db = data('db.js', 'SMI_DB');
  assert.equal(SMI.dbFor('ship', db)[0].field_path, 'vessels[].defName');
});
test('bulk default ids get a one-line summary, small groups keep the list', () => {
  const many = {'1': Array.from({length: 30}, (_, i) => ['craft_part', 'P' + i])};
  const bulk = SMI.warnings({kind: 'craft_part', defName: 'P0', storeItemId: 1, storeItemId_shared: true, name_status: 'exact', account_scope: 'account'}, many);
  assert.ok(bulk.some(l => l.includes('shared default used by 30 definitions')));
  assert.ok(!bulk.some(l => l.includes('P5')));
  const few = {'224': [['ship', 'A'], ['ship', 'B'], ['ship', 'C']]};
  const small = SMI.warnings({kind: 'ship', defName: 'A', storeItemId: 224, storeItemId_shared: true, name_status: 'exact', account_scope: 'account'}, few);
  assert.ok(small.some(l => l.includes('ship / B') && l.includes('ship / C')));
});

// Revision 2 localization checks, including the inventory of former UI literals.
const I18N = require('../site/i18n.js');
test('EN/RU keys, values, placeholders, fallback and substitution', () => {
  assert.deepEqual(Object.keys(I18N.en).sort(), Object.keys(I18N.ru).sort());
  for (const key of Object.keys(I18N.en)) {
    assert.ok(I18N.en[key].trim() && I18N.ru[key].trim(), key);
    const params = text => [...new Set(text.match(/\{\w+\}/g) || [])].sort();
    assert.deepEqual(params(I18N.en[key]), params(I18N.ru[key]), key);
  }
  assert.equal(I18N.t('xx', 'showAll', {n: 12}), 'Show all 12');
  I18N.en.onlyEnglish = 'English fallback';
  assert.equal(I18N.t('ru', 'onlyEnglish'), 'English fallback');
  delete I18N.en.onlyEnglish;
  assert.equal(I18N.t('ru', 'unknown'), 'unknown');
});
test('former English UI literals occur only in the string table', () => {
  const former = ['Loading local details…', 'Loading all definitions…', 'Cannot load local data.',
    'Copied.', 'Select the text below', 'Text to copy', 'English name', 'Russian name',
    'No file locations recorded.', 'Where it appears in the game files',
    'Where it can appear in the database', 'Not determined for this kind.',
    'Seen in a sample database:', 'Mail: ', 'Show all ', 'matched: ',
    'This id is shared:', 'This name is our derivation', 'No name was resolved',
    'Account scope is unknown.', 'Raw $...$ placeholders', 'Edit here (source definition)',
    'Generated server copy - do not edit', 'Where an item can be stored is not permission'];
  for (const file of ['app.js', 'search.js']) {
    const source = fs.readFileSync(path.join(__dirname, '../site', file), 'utf8');
    for (const literal of former) assert.ok(!source.includes(literal), file + ': ' + literal);
  }
  const html = fs.readFileSync(path.join(__dirname, '../site/index.html'), 'utf8');
  for (const [, key] of html.matchAll(/data-i18n(?:-placeholder|-aria-label)?="([^"]+)"/g)) assert.ok(I18N.en[key], key);
});
test('Russian counts, warnings, location groups and code options', () => {
  assert.match(SMI.countText(1, 1, false, 'ru'), /Результатов: 1/);
  assert.match(SMI.countText(22, 22, true, 'ru'), /все определения/);
  assert.match(SMI.warnings({name_status: 'derived', account_scope: 'unknown'}, {}, 'ru').join(' '), /составлено нами/);
  assert.match(SMI.groupLocations([['edit_here', 'a:1', 'definition', '']], 'ru')[0].title, /Изменять здесь/);
  assert.match(I18N.t('ru', 'code_prefixed'), /\(prefixed\)$/);
  assert.equal(I18N.t('en', 'code_ship'), 'ship');
});
test('every actual dropdown code, location role and database row has Russian prose', () => {
  for (const code of new Set([...all.map(r => r[0]), ...SMI.statuses])) {
    assert.ok(I18N.ru['code_' + code], code);
    assert.ok(I18N.ru['code_' + code].endsWith('(' + code + ')'), code);
  }
  for (const kind of new Set(all.map(r => r[0]))) {
    const loc = data('locations-' + kind + '.js', 'SMI_LOC_' + kind);
    for (const rows of Object.values(loc)) for (const row of rows) {
      if (!row[2].startsWith('own field ')) assert.ok(I18N.ru['role_' + row[2]], row[2]);
    }
  }
  for (const row of data('db.js', 'SMI_DB')) {
    assert.ok(row.value_written_ru);
    if (row.mail) assert.ok(row.mail_ru);
  }
});
test('controller switches EN/RU without losing query, filters or open item', async () => {
  class Element {
    constructor(tag = 'div') { this.tag = tag; this.children = []; this.listeners = {}; this.value = ''; this.dataset = {}; this.isConnected = true; }
    set textContent(value) { this.text = String(value); this.children = []; }
    get textContent() { return (this.text || '') + this.children.map(c => typeof c === 'string' ? c : c.textContent).join(''); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.text = ''; this.children = children; }
    get firstChild() { return this.children[0]; }
    get options() { return this.children; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    setAttribute(name, value) { this[name] = value; }
    querySelectorAll() { return []; }
    focus() {}
    close() { this.open = false; }
    showModal() { this.open = true; }
  }
  const ids = Object.fromEntries(['query', 'kind', 'status', 'lang', 'scope', 'count', 'results', 'more', 'detail', 'detail-title', 'detail-body', 'copy-status', 'close'].map(id => [id, new Element()]));
  ids.status.append(new Element('option'));
  const label = new Element('span'); label.dataset.i18n = 'language';
  const links = Object.fromEntries(['guide', 'dictionary', 'notice'].map(k => [k, new Element('a')]));
  const row = fixture[0];
  const state = {q: 'Alpha', kind: 'ship', status: 'exact', lang: 'en', all: false, item: 'Code_A', itemKind: 'ship'};
  let hash;
  const context = {SMI, SMI_I18N: I18N, URLSearchParams, console, setTimeout, clearTimeout,
    location: {hash: SMI.encode(state)}, history: {replaceState: (_, __, value) => { hash = value; }},
    navigator: {}, document: {activeElement: ids.query, documentElement: {},
      getElementById: id => ids[id], createElement: tag => new Element(tag),
      querySelectorAll: selector => selector === '[data-i18n]' ? [label] : [],
      querySelector: selector => links[selector.match(/"(\w+)"/)[1]],
      head: {append: script => queueMicrotask(() => script.onload())}}};
  context.window = {SMI_INDEX: [row], SMI_DETAILS_ship: {Code_A: {defined_in: 'star conflict\\a:1'}}, SMI_DB: [], addEventListener() {}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../site/app.js'), 'utf8'), context);
  const settle = () => new Promise(resolve => setImmediate(resolve));
  await settle(); await settle();
  assert.ok(ids.detail.open); assert.match(ids['detail-body'].textContent, /Identity/);
  ids.lang.value = 'ru'; ids.lang.listeners.change();
  await settle(); await settle();
  assert.equal(context.document.documentElement.lang, 'ru');
  assert.equal(label.textContent, 'Язык');
  assert.match(ids.count.textContent, /Результатов: 1/);
  assert.match(ids['detail-body'].textContent, /Идентификация/);
  assert.ok(ids.detail.open);
  assert.deepEqual(SMI.decode(hash), {...state, lang: 'ru'});
  assert.equal(links.guide.href, '../docs/ru/using-the-search.md');
  ids.lang.value = 'en'; ids.lang.listeners.change();
  await settle(); await settle();
  assert.match(ids['detail-body'].textContent, /Identity/);
  assert.deepEqual(SMI.decode(hash), state);
});
