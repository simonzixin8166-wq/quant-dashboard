// V6.11 投资行动速览: client view never creates BUY on its own; stale data downgrades; DCA labels.
const assert = require('assert');
const api = require('../docs/assets/invest-actions.js');
const stages = [
  { stage: 1, min: 4000, max: 4050, budget_pct: 10 }, { stage: 2, min: 3950, max: 4000, budget_pct: 25 },
  { stage: 3, min: 3850, max: 3950, budget_pct: 25 }, { stage: 4, min: 3650, max: 3850, budget_pct: 20 }];
const wed = Date.parse('2026-10-07T15:00:00Z');
const status = (gold) => ({ generated_at: new Date(wed - 10 * 60e3).toISOString(), freshness: {},
  gold: { stages, core_watch_zone: { min: 3950, max: 4050 }, quote: { price: 4100, basis: 'spot', freshness: 'LIVE', as_of: new Date(wed - 12 * 60e3).toISOString() }, reasons: [], blockers: [], ...gold } });
const live = (price, minsAgo = 2, basis = 'spot') => ({ price, updated: Math.floor((wed - minsAgo * 60e3) / 1000), basis, realtime: basis === 'spot', source: 't' });

// 4100 → 4050 → 4020 → 3950 driven by fresher live quotes: WAIT → WATCH(1) → WATCH(1) → WATCH(2).
assert.equal(api.goldView(status({ state: 'WAIT' }), live(4100), wed).state, 'WAIT');
let v = api.goldView(status({ state: 'WAIT' }), live(4050), wed);
assert.equal(v.state, 'WATCH'); assert.equal(v.stage.stage, 1);
assert.equal(api.goldView(status({ state: 'WAIT' }), live(4020), wed).state, 'WATCH');
assert.equal(api.goldView(status({ state: 'WAIT' }), live(3950), wed).stage.stage, 2);
// BUY only when the server confirmed BUY for the same stage on a fresh spot quote.
assert.equal(api.goldView(status({ state: 'BUY', stage: 1 }), live(4020), wed).state, 'BUY');
assert.equal(api.goldView(status({ state: 'BUY', stage: 1 }), live(3990), wed).state, 'WATCH');
assert.equal(api.goldView(status({ state: 'BUY', stage: 1 }), live(4020, 2, 'futures_proxy'), wed).state, 'WATCH');
const old = status({ state: 'BUY', stage: 1 }); old.generated_at = new Date(wed - 3 * 36e5).toISOString();
assert.equal(api.goldView(old, live(4020), wed).state, 'WATCH');
// PAUSE / DEEP_REVIEW have precedence over any price move.
assert.equal(api.goldView(status({ state: 'PAUSE', reasons: ['x'] }), live(4020), wed).state, 'PAUSE');
// Stale data: no BUY, explicit DATA_STALE.
const st = status({ state: 'BUY', stage: 1 }); st.gold.quote.as_of = new Date(wed - 5 * 36e5).toISOString();
assert.equal(api.goldView(st, null, wed).state, 'DATA_STALE');
assert.equal(api.goldView(status({ state: 'WAIT' }), live(4300), wed).review_kind, 'BREAKOUT_REVIEW');
// Weekend: last Friday quote is CLOSED, not live and not stale.
const sat = Date.parse('2026-10-10T15:00:00Z');
assert.equal(api.quoteFreshness(Date.parse('2026-10-09T20:55:00Z'), sat, true, {}), 'CLOSED');
assert.equal(api.goldMarketOpen(new Date('2026-10-11T23:00:00Z')), true);
// CNY/gram and DCA split.
assert.equal(Math.round(api.cnyPerGram(4050, 6.703)), 873);
// USD amounts, canonical order even when jsonb returns QLD/VGT/QQQM.
assert.deepStrictEqual(api.dcaSplit(5000, { QLD: .2, VGT: .4, QQQM: .4 }).map(x => [x.symbol, x.amount_usd]), [['QQQM', 2000], ['QLD', 1000], ['VGT', 2000]]);
assert.deepStrictEqual(Object.keys(api.orderedWeights({ QLD: .2, VGT: .4, QQQM: .4 })), ['QQQM', 'QLD', 'VGT']);
const win = { month: '2026-10', due_date: '2026-10-07', window_end: '2026-10-12' };
assert.equal(api.dcaLabel({ status: 'pending' }, win, '2026-10-06').key, 'upcoming');
assert.equal(api.dcaLabel({ status: 'pending' }, win, '2026-10-08').text, '待执行');
assert.equal(api.dcaLabel({ status: 'pending' }, win, '2026-10-20').key, 'overdue');
assert.equal(api.dcaLabel({ status: 'partial' }, win, '2026-10-08').text, '部分完成');
assert.equal(api.dcaLabel({ status: 'completed' }, win, '2026-10-08').text, '本月已完成');
assert.equal(api.dcaLabel({ status: 'skipped' }, win, '2026-10-08').text, '本月已跳过');
assert.equal(api.windowText(win), '10月7–12日');
assert.equal(api.windowText({ due_date: '2026-11-09', window_end: '2026-11-10' }), '11月9–10日');
console.log('PASS V6.11 invest-actions client view');
