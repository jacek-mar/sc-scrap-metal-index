/* CC0-1.0. Offline DOM controller; all content is inserted as text. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const ui = {query: $('query'), kind: $('kind'), status: $('status'), lang: $('lang'), scope: $('scope')};
  let state = SMI.decode(location.hash), limit = 200, matches = [], version = 0, openVersion = 0, returnFocus;
  const T = (key, params) => SMI_I18N.t(state.lang, key, params);
  const loads = new Map();
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function load(file) {
    if (!loads.has(file)) loads.set(file, new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'data/' + file + '.js';
      script.onload = resolve;
      script.onerror = () => { loads.delete(file); script.remove(); reject(new Error(T('text40'))); };
      document.head.append(script);
    }));
    return loads.get(file);
  }
  function save() { history.replaceState(null, '', SMI.encode(state)); }
  function kinds(rows) {
    ui.kind.replaceChildren(node('option', T('text10')));
    ui.kind.firstChild.value = '';
    for (const kind of [...new Set(rows.map(r => r[0]))].sort()) {
      const opt = node('option', T('code_' + kind)); opt.value = kind; ui.kind.append(opt);
    }
    if (![...ui.kind.options].some(o => o.value === state.kind)) state.kind = '';
    ui.kind.value = state.kind;
  }
  async function refresh(restoreItem = false) {
    const current = ++version;
    try {
      if (state.all) { $('count').textContent = T('text41'); await load('items_all'); }
      if (current !== version) return;
      const rows = state.all ? window.SMI_ALL : window.SMI_INDEX;
      if (!Array.isArray(rows)) { $('count').textContent = T('noData'); return; }
      kinds(rows);
      matches = SMI.search(rows, state); limit = 200; render();
      if (restoreItem && state.item) {
        const row = rows.find(r => r[0] === state.itemKind && r[1] === state.item);
        if (row) await open(row); else { state.item = ''; state.itemKind = ''; save(); }
      }
    } catch (error) { $('count').textContent = error.message; }
  }
  function render() {
    $('results').replaceChildren();
    const shown = matches.slice(0, limit), labels = SMI.displayLabels(shown, state.lang);
    shown.forEach((row, index) => {
      const tr = node('tr'), td = node('td');
      tr.addEventListener('click', e => { if (!e.target.closest('button')) open(row); });
      const button = node('button', labels[index], 'item');
      button.type = 'button'; button.addEventListener('click', () => open(row));
      button.addEventListener('keydown', e => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault(); const buttons = [...$('results').querySelectorAll('button')];
          buttons[Math.max(0, Math.min(buttons.length - 1, buttons.indexOf(button) + (e.key === 'ArrowDown' ? 1 : -1)))].focus();
        }
      });
      td.append(button); tr.append(td);
      for (const value of [row[1], row[0], row[6]]) tr.append(node('td', value));
      const ids = node('td', row.slice(7, 10).map(v => v === '' ? '—' : v).join(' / '));
      const matched = SMI.matchedIds(row, state.q);
      if (matched.length) ids.append(node('br'), node('span', T('text42') + matched.join(', '), 'matched'));
      tr.append(ids);
      $('results').append(tr);
    });
    $('count').textContent = SMI.countText(matches.length, Math.min(limit, matches.length), state.all, state.lang);
    $('more').hidden = limit >= matches.length;
  }
  function close() {
    ++openVersion;
    if ($('detail').open) $('detail').close();
    state.item = ''; state.itemKind = ''; save();
    if (returnFocus && returnFocus.isConnected) returnFocus.focus();
  }
  async function copy(text) {
    try {
      if (!navigator.clipboard) throw new Error(T('text43'));
      await navigator.clipboard.writeText(text);
      $('copy-status').textContent = T('text44');
    } catch (_) {
      $('copy-status').replaceChildren(node('span', T('text45')));
      const field = node('textarea', text); field.readOnly = true;
      field.setAttribute('aria-label', T('text46')); $('copy-status').append(field); field.focus(); field.select();
    }
  }
  async function open(row) {
    const current = ++openVersion;
    returnFocus = document.activeElement;
    state.item = row[1]; state.itemKind = row[0]; save();
    $('detail-title').textContent = SMI.displayLabels([row], state.lang)[0];
    $('detail-body').replaceChildren(node('p', T('text47')));
    $('copy-status').textContent = '';
    if (!$('detail').open) $('detail').showModal();
    try {
      await Promise.all([load('details-' + row[0]), load('locations-' + row[0]).catch(() => null), load('db')]);
      const item = SMI.object(row, window['SMI_DETAILS_' + row[0]][row[1]]);
      if (item.storeItemId_shared) await load('shared');
      if (current !== openVersion) return;
      const body = $('detail-body'); body.replaceChildren();
      for (const message of SMI.warnings(item, window.SMI_SHARED || {}, state.lang)) body.append(node('p', message, 'warning'));
      const text = v => Array.isArray(v) ? (v.join('\n') || '—') : v === '' || v === undefined ? '—' : String(v);
      function section(title, fields) {
        const h = node('h3', title), dl = node('dl');
        for (const [label, key, help] of fields) {
          const dt = node('dt', label); dt.append(' ', node('code', key, 'raw'));
          if (help) dt.title = help;
          const dd = node('dd', text(item[key]));
          if (key === 'defName' || key === 'defined_in') {
            const button = node('button', T('text48')); button.type = 'button';
            button.setAttribute('aria-label', T('text49') + key);
            button.addEventListener('click', () => copy(String(item[key]))); dd.append(' ', button);
          }
          dl.append(dt, dd);
        }
        body.append(h, dl);
      }
      section(T('text50'), [[T('text51'), 'name_en'], [T('text52'), 'name_ru'],
        [T('text11'), 'name_status', T('text53')],
        [T('text54'), 'race_en'], [T('text55'), 'race_ru']]);
      section(T('text56'), [[T('text57'), 'defName', T('text58')], [T('text9'), 'kind'],
        [T('text59'), 'storeItemId', T('text60')], [T('text61'), 'storeId'], [T('text62'), 'atlasId']]);
      if (item.desc_status === 'none') {
        body.append(node('h3', T('text63')), node('p', T(item.kind === 'ship' ? 'descNoneShip' : 'descNone')));
      } else section(T('text63'), [[T('text64'), 'short_desc_en'], [T('text65'), 'short_desc_ru'], [T('text66'), 'desc_status']]);
      // Where the item appears in the files, grouped by what it means for an editor.
      body.append(node('h3', T('text67')));
      const groups = SMI.groupLocations((window['SMI_LOC_' + row[0]] || {})[row[1]], state.lang);
      if (!groups.length) body.append(node('p', T('text68')));
      for (const g of groups) {
        const details = node('details'); details.open = g.key === 'edit_here';
        details.append(node('summary', g.title + ' · ' + g.rows.length));
        const list = node('ul');
        const add = rows => { for (const [, location, role, referrer] of rows) {
          const li = node('li'); li.append(node('code', location), ' — ' + (role.startsWith('own field ') ? T('ownField', {field: role.slice(10)}) : T('role_' + role)) + (referrer ? ' ' + referrer : ''));
          list.append(li); } };
        add(g.rows.slice(0, 50));
        details.append(list);
        if (g.rows.length > 50) {
          const more = node('button', T('showAll', {n: g.rows.length})); more.type = 'button';
          more.addEventListener('click', () => { list.replaceChildren(); add(g.rows); more.remove(); });
          details.append(more);
        }
        body.append(details);
      }
      // Where an item of this kind can be stored in the game database.
      body.append(node('h3', T('text69')));
      const fields = SMI.dbFor(item.kind, window.SMI_DB);
      if (!fields.length) body.append(node('p', T('text70')));
      else {
        const ul = node('ul');
        for (const f of fields) {
          const li = node('li');
          if (f.field_path) li.append(node('code', f.database + '.' + f.collection + '.' + f.field_path), ' — ');
          li.append(state.lang === 'ru' && f.value_written_ru || f.value_written);
          if (f.mail) li.append(node('br'), T('text71') + (state.lang === 'ru' && f.mail_ru || f.mail));
          ul.append(li);
        }
        body.append(ul);
      }
      if (item.db_fields && item.db_fields.length) body.append(node('p', T('text72') + item.db_fields.join(', ')));
      section(T('text73'), [[T('text74'), 'rank'], [T('text75'), 'tier'], [T('text76'), 'account_scope', T('text77')],
        [T('text78'), 'flags'], [T('text79'), 'defined_in'], [T('text80'), 'storeItemId_shared']]
        .concat(item.desc_has_placeholders ? [[T('descPlaceholders'), 'desc_has_placeholders']] : []));
      body.append(node('p', T('text82')));
    } catch (error) { if (current === openVersion) $('detail-body').textContent = error.message; }
  }
  for (const status of SMI.statuses) { const opt = node('option', T('code_' + status)); opt.value = status; ui.status.append(opt); }
  function translate() {
    document.documentElement.lang = state.lang;
    for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = T(el.dataset.i18n);
    for (const attr of ['placeholder', 'aria-label']) {
      for (const el of document.querySelectorAll('[data-i18n-' + attr + ']')) el.setAttribute(attr, T(el.getAttribute('data-i18n-' + attr)));
    }
    document.title = T('text1');
    for (const opt of ui.status.options) if (opt.value) opt.textContent = T('code_' + opt.value);
    const ru = state.lang === 'ru';
    document.querySelector('[data-doc="guide"]').href = ru ? '../docs/ru/using-the-search.md' : '../docs/using-the-search.md';
    document.querySelector('[data-doc="dictionary"]').href = ru ? '../docs/ru/data-dictionary.md' : '../docs/data-dictionary.md';
    document.querySelector('[data-doc="notice"]').href = ru ? '../ru/NOTICE.md' : '../NOTICE.md';
  }
  function syncControls() {
    ui.query.value = state.q; ui.status.value = state.status; ui.lang.value = state.lang; ui.scope.value = state.all ? 'all' : 'account';
  }
  let timer;
  function change(languageOnly = false) {
    state = {...state, q: ui.query.value, kind: ui.kind.value, status: ui.status.value, lang: ui.lang.value,
      all: ui.scope.value === 'all', item: languageOnly ? state.item : '', itemKind: languageOnly ? state.itemKind : ''};
    ++openVersion; if ($('detail').open) $('detail').close(); save(); translate(); refresh(languageOnly);
  }
  ui.query.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => change(), 160); });
  for (const name of ['kind', 'status', 'lang', 'scope']) ui[name].addEventListener('change', () => { clearTimeout(timer); change(name === 'lang'); });
  $('more').addEventListener('click', () => { const previous = Math.min(limit, matches.length); limit += 200; render(); $('results').querySelectorAll('button')[previous]?.focus(); });
  $('close').addEventListener('click', close);
  $('detail').addEventListener('cancel', e => { e.preventDefault(); close(); });
  window.addEventListener('hashchange', () => {
    clearTimeout(timer); ++openVersion; if ($('detail').open) $('detail').close();
    state = SMI.decode(location.hash); syncControls(); translate(); refresh(true);
  });
  syncControls(); translate(); refresh(true);
})();
