// #133 6109957428 P0-3: homepage research row state + escaping.
const assert = require('assert');
require('../docs/assets/auto-research-row.js');
const T = globalThis.MAVAutoResearchRow._test;
const d = { latest_session: '2026-10-12', last_run: { at: '2026-10-13T00:40:00Z' }, counts: {} };
assert.strictEqual(T.computeState(null, '2026-10-12').key, 'failed');
assert.strictEqual(T.computeState(d, '2026-10-12').key, 'ok');
assert.strictEqual(T.computeState(d, '').key, 'ok', 'no page date → trust digest');
// page shows 10-13, research still at 10-12: within the post-close window → pending, later → stale
assert.strictEqual(T.computeState(d, '2026-10-13', new Date('2026-10-14T02:00:00Z')).key, 'pending');
assert.strictEqual(T.computeState(d, '2026-10-13', new Date('2026-10-14T16:00:00Z')).key, 'stale');
assert.strictEqual(T.computeState({ latest_session: null }, '2026-10-13').key, 'pending');
assert.strictEqual(T.computeState({ ...d, run_failure: { failed_after_last_success: true } }, '2026-10-12').key, 'failed');
// failure marker merge: newer than last run → failed, older → untouched
assert.strictEqual(T.computeState(T.mergeFailure({ ...d }, { modules: { auto_research: { failed_at: '2026-10-13T05:00:00Z' } } }), '2026-10-12').key, 'failed');
assert.strictEqual(T.computeState(T.mergeFailure({ ...d }, { modules: { auto_research: { failed_at: '2026-10-12T05:00:00Z' } } }), '2026-10-12').key, 'ok');
assert.strictEqual(T.computeState(T.mergeFailure({ ...d }, null), '2026-10-12').key, 'ok');
// escaping and pre-gate flag in the detail
const html = T.itemHtml({ symbol: '<b>X', stance: 'bearish', research_date: 'r', market_as_of: 'm', decision_reason: '<script>', pre_sec_gate: true,
  supporting: [{ note: 'a<b', source: 's', as_of: 'd', pre_sec_gate: true }], opposing: [], invalidation: ['x<y'], inputs: ['price_archive'] });
assert(!html.includes('<script>') && html.includes('&lt;script&gt;') && html.includes('&lt;b&gt;X'));
assert(html.includes('门禁前生成·待复核') && html.includes('SEC 财务质量门禁'));
assert(html.includes('偏空') && html.includes('失效条件') && html.includes('反方证据'));
console.log('auto_research_row.test.js OK');
