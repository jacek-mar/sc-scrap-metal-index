/* CC0-1.0. Pure search and state helpers, also used by Node tests. */
(function (root) {
  'use strict';
  const {t} = typeof module !== 'undefined' ? require('./i18n.js') : root.SMI_I18N;
  const columns = 'kind defName name_en name_ru label_en label_ru name_status storeItemId storeId atlasId account_scope'.split(' ');
  const statuses = ['exact', 'own_field', 'prefixed', 'category', 'derived', 'none'];
  function search(rows, state) {
    const q = (state.q || '').trim().toLowerCase();
    return rows.filter(r => (!state.kind || r[0] === state.kind) &&
      (!state.status || r[6] === state.status) &&
      (!q || r.slice(1, 6).some(v => String(v).toLowerCase().includes(q)) ||
        r.slice(7, 10).some(v => v !== '' && String(v) === q)));
  }
  function decode(hash) {
    const p = new URLSearchParams(hash.replace(/^#/, ''));
    return {q: p.get('q') || '', kind: p.get('kind') || '',
      status: statuses.includes(p.get('status')) ? p.get('status') : '',
      all: p.get('all') === '1', lang: p.get('lang') === 'ru' ? 'ru' : 'en',
      item: p.get('item') || '', itemKind: p.get('itemKind') || ''};
  }
  function encode(state) {
    const p = new URLSearchParams();
    for (const k of ['q', 'kind', 'status', 'lang', 'item', 'itemKind']) if (state[k]) p.set(k, state[k]);
    if (state.all) p.set('all', '1');
    return '#' + p.toString();
  }
  function object(row, detail) { return Object.assign(Object.fromEntries(columns.map((k, i) => [k, row[i]])), detail); }
  function warnings(item, shared, lang = 'en') {
    const lines = [];
    const explanations = {category: t(lang, 'text83'),
      derived: t(lang, 'text84'), none: t(lang, 'text85')};
    if (explanations[item.name_status]) lines.push(explanations[item.name_status]);
    if (item.account_scope === 'unknown') lines.push(t(lang, 'text86'));
    if (item.storeItemId_shared) {
      const others = (shared[String(item.storeItemId)] || []).filter(r => r[0] !== item.kind || r[1] !== item.defName);
      // 0, 1 and 1000 are bulk default values shared by thousands of definitions (research Q58):
      // listing them helps nobody, so large groups get a one-line summary instead.
      if (others.length > 12)
        lines.push(t(lang, 'sharedDefault', {id: item.storeItemId, n: others.length + 1}));
      else lines.push(t(lang, 'shared', {items: others.map(r => r[0] + ' / ' + r[1]).join(', ')}));
    }
    if (item.desc_has_placeholders) lines.push(t(lang, 'text87'));
    return lines;
  }
  // Display helpers.
  const idNames = ['storeItemId', 'storeId', 'atlasId'];
  function matchedIds(row, q) {
    q = (q || '').trim();
    return q ? idNames.filter((_, i) => row[7 + i] !== '' && String(row[7 + i]) === q) : [];
  }
  // Drop a trailing [code] when the label is unique without it in the shown rows,
  // or when the code only repeats words of the name.
  function displayLabels(rows, lang) {
    const col = lang === 'ru' ? 5 : 4;
    const strip = label => String(label || '').replace(/\s*\[[^\]]*\]\s*$/, '');
    const counts = new Map();
    for (const r of rows) { const s = strip(r[col]); counts.set(s, (counts.get(s) || 0) + 1); }
    return rows.map(r => {
      const label = String(r[col] || '');
      const bare = strip(label), code = (label.match(/\[([^\]]*)\]\s*$/) || [])[1];
      if (!code || !bare) return label || r[1];
      const repeats = String(r[2] || '').toLowerCase().includes(code.toLowerCase());
      return counts.get(bare) === 1 || repeats ? bare : label;
    });
  }
  function countText(n, shown, all, lang = 'en') {
    return t(lang, n === 1 ? 'countOne' : 'countMany', {n, shown, scope: t(lang, all ? 'all' : 'account')});
  }
  const groupKeys = {"edit_here": "text88", "generated": "text89", "server_rules": "text90", "inert": "text91", "used_by": "text92"};
  const groupTitles = Object.fromEntries(Object.entries(groupKeys).map(([k, v]) => [k, t('en', v)]));
  function groupLocations(rows, lang = 'en') {
    const groups = Object.keys(groupTitles).map(key => ({key, title: t(lang, groupKeys[key]), rows: []}));
    for (const r of rows || []) { const g = groups.find(x => x.key === r[0]); if (g) g.rows.push(r); }
    return groups.filter(g => g.rows.length);
  }
  function dbFor(kind, table) { return (table || []).filter(r => r.kind === kind); }
  const api = {columns, statuses, search, decode, encode, object, warnings,
    matchedIds, displayLabels, countText, groupLocations, groupTitles, dbFor};
  if (typeof module !== 'undefined') module.exports = api;
  else root.SMI = api;
})(typeof window !== 'undefined' ? window : globalThis);
