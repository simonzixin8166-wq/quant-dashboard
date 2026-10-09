// 博主麻你 · VGT homepage row: recent, non-commentary, plan labelled 非成交, links to original, author signal only.
const assert = require('assert');
const api = require('../docs/assets/invest-actions.js');
const rec = (o = {}) => ({ author: '麻你', published_at: '2026-10-07 21:00:00', captured_at: '2026-10-08T01:20:00Z', url: 'https://bbs.wenxuecity.com/tzlc/1.html',
  headline: { symbol: 'VGT', action_type: 'SELL_PLANNED', kind: 'planned', text: 'VGT：计划减仓（非成交） 4% @ 117.57' }, ...o });
let r = api.latestAuthorSignal({ records: [rec()] }, '2026-10-09');
assert.equal(r.day, '2026-10-07'); assert.equal(r.age, 2);
assert.equal(api.latestAuthorSignal({ records: [rec({ published_at: '2026-09-01 10:00:00' })] }, '2026-10-09'), null);   // stale → no row
assert.equal(api.latestAuthorSignal({ records: [rec({ headline: { kind: 'view', text: 'VGT：仅观点' } })] }, '2026-10-09'), null); // commentary → no row
assert.equal(api.latestAuthorSignal(null, '2026-10-09'), null);
api._state.authorSignals = { records: [rec({ published_at: new Date().toISOString().slice(0, 10) + ' 09:00:00' })] };
const html = api.authorRow();
assert(/计划减仓（非成交）/.test(html) && /计划·非成交/.test(html) && /作者信号/.test(html) && /href="https:\/\/bbs\.wenxuecity\.com\/tzlc\/1\.html"/.test(html), html);
assert(!/BUY|SELL<|ACTION/.test(html.replace(/SELL_PLANNED/g, '')), 'no MyAlpha action wording');
api._state.authorSignals = null;
assert.equal(api.authorRow(), '');
console.log('PASS author signal row');
