// P0-2 contract-level next step: six primary actions, named missing data, events only when exposed.
const assert = require('assert');
let events = [];
globalThis.OptionV2 = { getEvents: () => events };
require('../docs/assets/autonomous-agent.js');
const A = globalThis.MAVAutonomousAgent;
const day = d => new Date(Date.now() + d * 86400000).toISOString().slice(0, 10);
const pos = (o = {}) => ({ id: 'x', symbol: 'IREN', side: 'short', opt_type: 'put', strike: 40, expiry: day(40), cost: 2.0, qty: 1, multiplier: 100, assignment_mode: 'avoid', ...o });
const q = (o = {}) => ({ bid: 1.35, ask: 1.45, mid: 1.40, underlyingPrice: 44, delta: -0.22, iv: 0.8, ...o });

// No quote / stale quote -> CANNOT_JUDGE with the exact missing fields, never a generic "review".
let s = A.optionDecisionSummary(pos(), null, null);
assert.strictEqual(s.primary, 'CANNOT_JUDGE'); assert(s.missing.some(x => x.includes('期权报价')));
s = A.optionDecisionSummary(pos(), q(), { usable: false, status: 'stale', label: '报价已过期' });
assert.strictEqual(s.primary, 'CANNOT_JUDGE'); assert(s.missing[0].includes('报价已过期'));
s = A.optionDecisionSummary(pos({ cost: 0 }), q(), null);
assert.strictEqual(s.primary, 'CANNOT_JUDGE'); assert(s.missing.some(x => x.includes('原始权利金')));
// Missing Delta alone is named but does not block a judgement.
s = A.optionDecisionSummary(pos(), q({ delta: null }), null);
assert.notStrictEqual(s.primary, 'CANNOT_JUDGE'); assert(s.missing.includes('Delta'));

// Short put: 85% captured, low delta, tight spread, 30 DTE -> consider closing.
s = A.optionDecisionSummary(pos({ expiry: day(30) }), q({ bid: 0.28, ask: 0.30, mid: 0.29, delta: -0.06, underlyingPrice: 50 }), null);
assert.strictEqual(s.primary, 'CLOSE', JSON.stringify(s)); assert(s.reasons.some(r => r.includes('权利金收益')));
// Short put 5 DTE near strike, avoid assignment -> urgent manual review (roll/close today).
s = A.optionDecisionSummary(pos({ expiry: day(5) }), q({ underlyingPrice: 40.5, delta: -0.45, bid: 1.0, ask: 1.1, mid: 1.05 }), null);
assert.strictEqual(s.primary, 'URGENT', JSON.stringify(s));
// Same but willing to take assignment -> still urgent: decide today whether to accept the shares.
s = A.optionDecisionSummary(pos({ expiry: day(5), assignment_mode: 'accept' }), q({ underlyingPrice: 40.5, delta: -0.45 }), null);
assert.strictEqual(s.primary, 'URGENT'); assert(/接货/.test(s.advice.decision));
// Losing + high delta + avoid -> consider rolling.
s = A.optionDecisionSummary(pos(), q({ bid: 3.9, ask: 4.1, mid: 4.0, underlyingPrice: 37, delta: -0.6 }), null);
assert.strictEqual(s.primary, 'ROLL', JSON.stringify(s));
// Normal: 30% captured, far OTM, FOMC in 3 days -> keep holding; event is context, not an escalation.
events = [{ type: 'FOMC', datetime: new Date(Date.now() + 3 * 86400000).toISOString() }];
s = A.optionDecisionSummary(pos(), q(), null);
assert.strictEqual(s.primary, 'HOLD', JSON.stringify(s));
assert(s.advice.reasons.some(r => r.includes('事件影响有限')));
// Same event but the contract sits near the strike -> watch (not a blanket L2 for every position).
s = A.optionDecisionSummary(pos(), q({ underlyingPrice: 41.2, delta: -0.30 }), null);
assert.strictEqual(s.primary, 'WAIT', JSON.stringify(s));
assert(s.advice.reasons.some(r => r.includes('FOMC') && (r.includes('价内')||r.includes('价外'))));
events = [];
// Short call near/in the money -> ex-dividend early-assignment data explicitly listed as missing.
s = A.optionDecisionSummary(pos({ opt_type: 'call', strike: 45, assignment_mode: 'accept' }), q({ underlyingPrice: 46, delta: 0.55 }), null);
assert(s.missing.some(x => x.includes('除息日')));
// Long call within 21 DTE -> consider rolling (or closing); never a specific strike/date suggestion.
s = A.optionDecisionSummary(pos({ side: 'long', opt_type: 'call', expiry: day(15), cost: 5 }), q({ bid: 6, ask: 6.2, mid: 6.1, delta: 0.6 }), null);
assert.strictEqual(s.primary, 'ROLL'); assert(!/\$\d+.*展到|展到.*\d{4}-\d{2}/.test(JSON.stringify(s)));
// Preference surfaced for short premium when relevant.
s = A.optionDecisionSummary(pos(), q(), null);
assert(s.reasons.length <= 3 && s.next_check);
// Different contracts produce different texts (no template reused across positions).
const a1 = A.optionDecisionSummary(pos(), q(), null), a2 = A.optionDecisionSummary(pos({ symbol: 'SOFI', strike: 20, expiry: day(12) }), q({ underlyingPrice: 20.4, delta: -0.4, bid: 0.9, ask: 1.0, mid: 0.95 }), null);
assert.notStrictEqual(JSON.stringify(a1.reasons), JSON.stringify(a2.reasons));
// Real case reported 2026-10-09: IREN 40P, cost 2.64, 42 DTE, mid 6.57, Delta -0.584, spot 35.73, CPI in 5 days.
events = [{ type: 'CPI', datetime: new Date(Date.now() + 5 * 86400000).toISOString() }];
const iren = pos({ strike: 40, cost: 2.64, open_fee: 1.04, expiry: day(42), assignment_mode: 'accept' });
const irenQ = q({ bid: 6.40, ask: 6.73, mid: 6.57, delta: -0.584, iv: 0.852, underlyingPrice: 35.73 });
s = A.optionDecisionSummary(iren, irenQ, null);                                 // 'accept' is only the DB default
assert.strictEqual(s.primary, 'WAIT', JSON.stringify(s));
assert.strictEqual(s.primary_zh, '需人工确认接货意愿');
assert(/37\.3[0-9]/.test(s.action) && /愿意 → 继续持有/.test(s.action) && /不愿意 → 考虑展期/.test(s.action), s.action);
assert(s.missing.some(m => /接货意愿确认/.test(m)) && s.missing.some(m => /购买力/.test(m)));
assert(s.reasons.some(r => /已价内 10\.7%/.test(r)), s.reasons);               // unambiguous moneyness
s = A.optionDecisionSummary({ ...iren, assignment_confirmed: true }, irenQ, null);
assert.strictEqual(s.primary, 'HOLD'); assert(/准备接货/.test(s.primary_zh));
s = A.optionDecisionSummary({ ...iren, assignment_mode: 'avoid' }, irenQ, null);
assert.strictEqual(s.primary, 'ROLL'); assert(/展期/.test(s.primary_zh) && /Roll down/.test(s.action));
// card markup must not reuse the red button class
const fs = require('fs');
const ov = fs.readFileSync(__dirname + '/../docs/assets/options-v2.js', 'utf8');
assert(!/option-card-decision option-primary/.test(ov) && /option-card-decision option-next/.test(ov));
events = [];
console.log('PASS P0-2 option contract-level decision');
