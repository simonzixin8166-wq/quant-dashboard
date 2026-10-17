// Frontend NYSE calendar: specific sessions, early close, and fallback/delegation in the two consumers.
const assert = require('assert');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const cal = require(path.join(ROOT, 'docs/assets/trading-calendar.js'));

const at = s => new Date(s);
assert.strictEqual(cal.isUsRegularSession(at('2026-11-26T10:00:00-05:00')), false, 'Thanksgiving closed');
assert.strictEqual(cal.isUsRegularSession(at('2026-11-27T10:00:00-05:00')), true, 'early-close day open in the morning');
assert.strictEqual(cal.isUsRegularSession(at('2026-11-27T13:30:00-05:00')), false, 'early close 13:00 ET');
assert.strictEqual(cal.isUsRegularSession(at('2026-12-24T12:59:00-05:00')), true);
assert.strictEqual(cal.isUsRegularSession(at('2026-12-24T13:00:00-05:00')), false);
assert.strictEqual(cal.isUsRegularSession(at('2026-12-25T10:00:00-05:00')), false, 'Christmas closed');
assert.strictEqual(cal.isUsRegularSession(at('2026-10-19T10:00:00-04:00')), true, 'normal Monday open');
assert.strictEqual(cal.isUsRegularSession(at('2026-10-19T16:00:00-04:00')), false, '16:00 closed');
assert.strictEqual(cal.isUsRegularSession(at('2026-10-17T10:00:00-04:00')), false, 'Saturday closed');
assert.strictEqual(cal.isNyseHoliday('2027-06-18'), true, 'Juneteenth 2027 observed Friday');
assert.strictEqual(cal.isNyseHoliday('2027-12-24'), true, 'Christmas 2027 observed Friday');

// No generic globals leak; only the namespace is exported.
assert.ok(globalThis.MAVTradingCalendar && typeof globalThis.MAVTradingCalendar.isUsRegularSession === 'function');
for (const k of ['holidays', 'isUsRegularSession', 'isNyseHoliday']) assert.strictEqual(typeof globalThis[k], 'undefined', `global ${k} leaked`);

// options-v2.js delegates to the calendar when present, and falls back to the weekday rule when absent.
const optPath = path.join(ROOT, 'docs/assets/options-v2.js');
delete require.cache[require.resolve(optPath)];
require(optPath);
const opt = globalThis.OptionV2;
assert.strictEqual(opt.isUsRegularSession(at('2026-11-26T10:00:00-05:00')), false, 'options delegates to calendar');
const saved = globalThis.MAVTradingCalendar;
delete globalThis.MAVTradingCalendar;
assert.strictEqual(opt.isUsRegularSession(at('2026-11-26T10:00:00-05:00')), true, 'fallback = previous weekday rule');
assert.strictEqual(opt.isUsRegularSession(at('2026-10-17T10:00:00-04:00')), false, 'fallback still closes weekends');
globalThis.MAVTradingCalendar = saved;

console.log('PASS frontend trading calendar (holidays, early close, delegation, fallback)');
