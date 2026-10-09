// #133 item B: private stock ledger helpers (synthetic data only).
const assert = require('assert');
require('../docs/assets/stock-positions.js');
const T = globalThis.StockPositions._test;
const accounts = [{ id: 1, name: 'IBKR-A' }, { id: 2, name: 'IBKR-B' }];
const rows = [
  { id: 1, broker_account_id: 1, symbol: 'ZZA', shares: 10, status: 'open' },
  { id: 2, broker_account_id: 2, symbol: 'ZZA', shares: 5, status: 'open' },
  { id: 3, broker_account_id: 2, symbol: 'ZZB', shares: 1, status: 'open' },
];
const g = T.groupByAccount(rows, accounts);
assert.strictEqual(g.length, 2, 'accounts must stay separate');
assert.deepStrictEqual(g.map(x => x.rows.length), [1, 2]);
assert(g.every(x => x.rows.every(r => String(r.broker_account_id) === x.account_id)), 'no cross-account merge');
assert.strictEqual(T.groupByAccount([], accounts).length, 0, 'empty ledger renders no groups');
// validation
assert(T.validate({ broker_account_id: '1', symbol: 'qqqm', shares: '3' }).ok);
assert.strictEqual(T.validate({ broker_account_id: '1', symbol: 'qqqm', shares: '3' }).payload.symbol, 'QQQM');
assert(!T.validate({ broker_account_id: '1', symbol: 'BAD SYM', shares: '3' }).ok);
assert(!T.validate({ broker_account_id: '1', symbol: 'ZZA', shares: '0' }).ok);
assert(!T.validate({ broker_account_id: '1', symbol: 'ZZA', shares: '1', cost_basis: '-1' }).ok);
assert(!T.validate({ broker_account_id: '', symbol: 'ZZA', shares: '1' }).ok, 'account required');
assert.strictEqual(T.validate({ broker_account_id: '1', symbol: 'ZZA', shares: '1', cost_basis: '' }).payload.cost_basis, null);
// freshness
const now = Date.parse('2026-10-09T00:00:00Z');
assert(!T.isStale({ data_as_of: '2026-10-05T00:00:00Z' }, now));
assert(T.isStale({ data_as_of: '2026-09-30T00:00:00Z' }, now));
assert(T.isStale({ data_as_of: null }, now), 'missing as_of is stale');
console.log('stock_positions.test.js PASS');
