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
// the row never requests the event-only module_failures.json (normally absent → 404 noise in production QA)
const src = require('fs').readFileSync(__dirname + '/../docs/assets/auto-research-row.js', 'utf8');
assert(!/get\(['"]research\/module_failures/.test(src) && !/fetch\(['"][^'"]*module_failures/.test(src), 'no module_failures request');
// escaping and pre-gate flag in the detail
const html = T.itemHtml({ symbol: '<b>X', stance: 'bearish', research_date: 'r', market_as_of: 'm', decision_reason: '<script>', pre_sec_gate: true,
  supporting: [{ note: 'a<b', source: 's', as_of: 'd', pre_sec_gate: true }], opposing: [], invalidation: ['x<y'], inputs: ['price_archive'] });
assert(!html.includes('<script>') && html.includes('&lt;script&gt;') && html.includes('&lt;b&gt;X'));
assert(html.includes('门禁前生成·待复核') && html.includes('SEC 财务质量门禁'));
assert(html.includes('偏空') && html.includes('失效条件') && html.includes('反方证据'));
// B1/B2 experience basis: shown as Shadow/informational, n<30 flagged descriptive, unavailable explicit, escaped
const eb = { status: 'used', evidence_id: 'X-h', session: '2026-10-14', precedents: { n: 2, supports: 1, conflicts: 1, median_return_60: 0.01 },
  error_attribution: { symbol_cases_n: 1, tags: { '<i>t': 1 } },
  historical_reliability: [{ bucket: '> +10%', symbol_n_20: 3, pooled_n_20: 135, pooled_positive_rate_20: 0.54, min_n: 30, strength: 'descriptive' }] };
const h2 = T.itemHtml({ symbol: 'X', stance: 'neutral', invalidation: [], experience_basis: eb });
assert(h2.includes('历史经验与可靠性依据') && h2.includes('不参与判断') && h2.includes('仅描述性') && h2.includes('n=3') && h2.includes('used_in_decision=false'));
assert(!h2.includes('<i>t') && h2.includes('&lt;i&gt;t'));
const h3 = T.itemHtml({ symbol: 'Y', stance: 'neutral', invalidation: [], experience_basis: { status: 'unavailable', why: 'before B1-02' } });
assert(h3.includes('unavailable') && h3.includes('before B1-02'));
assert(!T.itemHtml({ symbol: 'Z', stance: 'neutral', invalidation: [] }).includes('历史经验'), 'no section without a basis');
console.log('auto_research_row.test.js OK');
