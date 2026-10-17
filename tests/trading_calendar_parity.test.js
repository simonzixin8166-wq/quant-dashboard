const assert = require('assert');
const { holidays, isUsRegularSession } = require('../docs/assets/trading-calendar.js');

function runTests() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error("Missing holidays JSON argument");
    process.exit(1);
  }

  const pyHolidays = JSON.parse(args[0]);

  // Check 2026-2028 parity
  let jsHolidays = [];
  for (let year = 2026; year <= 2028; year++) {
    jsHolidays = jsHolidays.concat(holidays(year));
  }

  // Sort both arrays just to be sure
  pyHolidays.sort();
  jsHolidays.sort();

  assert.deepStrictEqual(jsHolidays, pyHolidays, "JS holidays do not match Python holidays");

  // Specific assertions as requested:
  // 2026-11-26 休市 (Thanksgiving)
  const d1 = new Date("2026-11-26T10:00:00-05:00");
  assert.strictEqual(isUsRegularSession(d1), false, "2026-11-26 should be closed");

  // 2026-11-27 13:30 ET 为非交易时段 (Black Friday, early close at 13:00)
  const d2 = new Date("2026-11-27T13:30:00-05:00");
  assert.strictEqual(isUsRegularSession(d2), false, "2026-11-27 13:30 ET should be closed");

  // 2026-11-27 10:00 ET should be open
  const d2_open = new Date("2026-11-27T10:00:00-05:00");
  assert.strictEqual(isUsRegularSession(d2_open), true, "2026-11-27 10:00 ET should be open");

  // 2026-10-19 10:00 ET 为交易时段
  const d3 = new Date("2026-10-19T10:00:00-04:00");
  assert.strictEqual(isUsRegularSession(d3), true, "2026-10-19 10:00 ET should be open");

  console.log("All JS calendar tests passed");
}

runTests();
