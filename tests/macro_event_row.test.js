// #133 6138793593 H-01: compact macro-event row — phases from the clock (DST-aware windows), four judgment states,
// stale data never shows an optimistic judgment, escaping, no BUY/SELL wording. Fixtures are labelled as fixtures.
const assert = require('assert');
require('../docs/assets/macro-event-row.js');
const T = globalThis.MAVMacroEventRow._test;
const real = require('../docs/research/macro_event_watch.json');      // the committed artifact (real inputs, not a fixture)
const cpi = real.events.find(e => e.key === 'cpi_2026_09');
const at = s => Date.parse(s);
// phases around CPI (10/14 08:30 EDT = 12:30Z = 20:30 北京)
assert.strictEqual(T.phase(cpi, at('2026-10-12T12:00:00Z')).key, 'planned');
assert.strictEqual(T.phase(cpi, at('2026-10-13T12:00:00Z')).key, 't_minus_1');
assert(T.phase(cpi, at('2026-10-13T12:00:00Z')).label.includes('10/14 20:30 北京'));
assert.strictEqual(T.phase(cpi, at('2026-10-14T05:00:00Z')).key, 'pre_event');
assert.strictEqual(T.phase(cpi, at('2026-10-14T12:31:00Z')).key, 'released_pending', 'no official outcome yet → never a fake T result');
const withOutcome = { ...cpi, official_outcome: { recorded_at: '2026-10-14T13:00:00Z', summary: 'FIXTURE' } };
assert.strictEqual(T.phase(withOutcome, at('2026-10-15T21:00:00Z')).label, '已公布｜T+1');
assert.strictEqual(T.phase(withOutcome, at('2026-10-19T21:00:00Z')).label, '已公布｜T+3');
assert.strictEqual(T.phase(withOutcome, at('2026-10-30T00:00:00Z')).key, 'archived');
// DST: the November refunding release is 08:30 EST = 13:30Z
const ref = real.events.find(e => e.key === 'treasury_refunding_2026_11_04');
assert.strictEqual(ref.release.utc, '2026-11-04T13:30:00Z');
assert.strictEqual(T.phase(ref, at('2026-11-04T13:00:00Z')).key, 'pre_event');
// current/next event priority: today CPI is current, FOMC next
const sel = T.pick(real.events, at('2026-10-13T12:00:00Z'));
assert.strictEqual(sel.current.ev.key, 'cpi_2026_09'); assert.strictEqual(sel.next.ev.key, 'fomc_2026_10');
// quality / four judgment states (FIXTURES derived from the real artifact)
const now = at(real.generated_at) + 3600e3;
const fx = k => ({ ...real, judgment: { ...real.judgment, key: k }, freshness: { ...real.freshness, data_stale: false } });
for (const k of ['risk_elevated', 'neutral_awaiting_confirmation', 'conditions_improving']) assert.strictEqual(T.quality(fx(k), real.freshness.market_as_of, now).judge, k);
assert.strictEqual(T.quality({ ...fx('conditions_improving'), freshness: { ...real.freshness, data_stale: true } }, '', now).judge, 'data_insufficient');
// stale: old artifact or page market ahead of the analysis → 数据不足, never the previous optimistic judgment
assert.strictEqual(T.quality(fx('conditions_improving'), '', at(real.generated_at) + 40 * 3600e3).judge, 'data_insufficient');
assert.strictEqual(T.quality(fx('conditions_improving'), '2099-01-01', now).judge, 'data_insufficient');
assert.strictEqual(T.quality(null, '', now).key, 'failed');
// render into a minimal fake element
function fakeEl() { const a = {}; return { innerHTML: '', setAttribute: (k, v) => (a[k] = v), getAttribute: k => a[k], querySelector: () => null, attrs: a }; }
const el = fakeEl();
T.render(el, fx('risk_elevated'), real.freshness.market_as_of, now);
assert(el.innerHTML.includes('宏观事件与分批观察') && el.innerHTML.includes('偏风险') && el.innerHTML.includes('查看分析'));
assert(el.innerHTML.includes('美东') && el.innerHTML.includes('北京') && el.innerHTML.includes('完整中文分析'));
assert(!/马上买|马上卖|立即买入|立即卖出|BUY|SELL/.test(el.innerHTML), 'no trade instructions');
const el2 = fakeEl(); T.render(el2, null, '', now);
assert(el2.innerHTML.includes('数据不足') && el2.attrs['data-state'] === 'failed');
// escaping
const el3 = fakeEl(); T.render(el3, { ...fx('neutral_awaiting_confirmation'), lines: [{ tranche: 1, state: 'x', text: '<img src=x onerror=1>' }] }, '', now);
assert(!el3.innerHTML.includes('<img') && el3.innerHTML.includes('&lt;img'));
// the artifact itself is inert
assert(real.production_use === false && real.used_in_decision === false && real.automatic_orders === false);
console.log('macro_event_row.test.js OK');
