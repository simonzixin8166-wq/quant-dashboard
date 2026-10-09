// #133 6083622772 P0-A: reproducible scenario matrix (synthetic data; no private positions).
// Prints a table of primary decision + key reason for each scenario and asserts the safety invariants.
const assert = require('assert');
let events = [];
globalThis.OptionV2 = { getEvents: () => events };
require('../docs/assets/autonomous-agent.js');
const A = globalThis.MAVAutonomousAgent;
const day = d => new Date(Date.now() + d * 86400000).toISOString().slice(0, 10);
const put = (o = {}) => ({ id: 'p', symbol: 'ZZP', side: 'short', opt_type: 'put', strike: 40, expiry: day(42), cost: 2.64, open_fee: 1.04, qty: 1, multiplier: 100, broker_account_id: 1, ...o });
const itm = (o = {}) => ({ bid: 6.40, ask: 6.73, mid: 6.57, delta: -0.584, iv: 0.85, underlyingPrice: 35.73, ...o });
const confirmed = (v) => ({ assignment_preference: v, assignment_confirmed_at: '2026-10-09T15:00:00Z' });
const rows = [];
const run = (name, p, q, fresh = null) => { const s = A.optionDecisionSummary(p, q, fresh); rows.push([name, s.primary, s.primary_zh, (s.missing || []).slice(0, 2).join(' / ')]); return s; };

let s = run('ITM put · 默认未确认 (DB accept)', put({ assignment_mode: 'accept' }), itm());
assert.strictEqual(s.primary, 'WAIT'); assert(!/准备接货/.test(s.primary_zh));
s = run('ITM put · 未设置任何偏好', put(), itm());
assert.strictEqual(s.primary, 'WAIT');
s = run('ITM put · 明确愿意接货', put(confirmed('accept')), itm());
assert.strictEqual(s.primary, 'HOLD'); assert(s.missing.some(m => /购买力/.test(m)));
s = run('ITM put · 明确愿意接货 · 5 DTE', put({ ...confirmed('accept'), expiry: day(5) }), itm());
assert.strictEqual(s.primary, 'URGENT');
s = run('ITM put · 明确避免接货', put(confirmed('avoid')), itm());
assert.strictEqual(s.primary, 'ROLL');
s = run('ITM put · preference 未带确认时间', put({ assignment_preference: 'accept' }), itm());
assert.strictEqual(s.primary, 'WAIT');                                      // no timestamp → not confirmed
s = run('报价过期', put(confirmed('accept')), itm(), { usable: false, status: 'stale', label: '报价已过期' });
assert.strictEqual(s.primary, 'CANNOT_JUDGE');
s = run('无报价', put(), null);
assert.strictEqual(s.primary, 'CANNOT_JUDGE');
s = run('Delta 缺失 (OTM)', put(), itm({ delta: null, underlyingPrice: 46, bid: 0.9, ask: 1.0, mid: 0.95 }));
assert.notStrictEqual(s.primary, 'CANNOT_JUDGE'); assert(s.missing.includes('Delta'));
s = run('OTM put · 85% 已赚 · 30 DTE', put({ expiry: day(30) }), itm({ bid: 0.28, ask: 0.30, mid: 0.29, delta: -0.06, underlyingPrice: 50 }));
assert.strictEqual(s.primary, 'CLOSE');
// two accounts, same contract, different confirmed preferences → independent decisions
const a1 = A.optionDecisionSummary(put({ broker_account_id: 1, ...confirmed('accept') }), itm(), null);
const a2 = A.optionDecisionSummary(put({ broker_account_id: 2, ...confirmed('avoid') }), itm(), null);
rows.push(['两账户同合约 · 账户1 愿意 / 账户2 避免', `${a1.primary} / ${a2.primary}`, '', '']);
assert.strictEqual(a1.primary, 'HOLD'); assert.strictEqual(a2.primary, 'ROLL');
// covered call is managed by its own rules; put assignment preference does not change it
s = run('Covered Call · 近平值 5 DTE', { id: 'c', symbol: 'ZZC', side: 'short', opt_type: 'call', strike: 50, expiry: day(5), cost: 1.2, qty: 1, multiplier: 100, collateral_mode: 'covered', ...confirmed('accept') }, { bid: 1.5, ask: 1.6, mid: 1.55, delta: 0.55, iv: 0.5, underlyingPrice: 50.5 });
assert.notStrictEqual(s.primary_zh, '继续持有 · 准备接货');
// unconfirmed preference must never produce "准备接货"
for (const r of rows) if (/未确认|未设置|未带确认/.test(r[0])) assert(!/准备接货/.test(r[2]), r);
if (process.env.SHOW_SCENARIOS) console.table(rows);
console.log(`PASS option scenarios (${rows.length})`);
