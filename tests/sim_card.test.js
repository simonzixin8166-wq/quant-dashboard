// Owner 2026-11-25: 策略模拟（纸面）homepage row — before the first run, running values, detail table, escaping,
// no order wording. Fixtures are labelled as fixtures.
const assert = require('assert');
require('../docs/assets/sim-card.js');
const T = globalThis.MAVSimCard._test;
assert(T.lineHtml(null).includes('暂无数据'));
const waiting = { accounts: { original: { status: 'first signal recorded; the account opens at the next session\'s open' } } };
assert(T.lineHtml(waiting).includes('今晚收盘后开始记录'));
const FIXTURE = {
  rules_zh: 'FIXTURE rules', note_zh: '纸面模拟，不是买卖建议',
  benchmark: { value: 4900, return: -0.02 },
  accounts: {
    original: { label_zh: '原规则', status: 'running', as_of: '2026-11-25', started: '2026-11-25', value: 4950.4, return: -0.0099,
      max_drawdown: -0.01, trades: 1, holding_at_close: { qqq_usd: 3950, tqqq_usd: 0, cash_usd: 1000 }, next_open_target: { qqq: 0.8, tqqq: 0 } },
    band2: { label_zh: '加 2% 缓冲<script>', status: 'running', as_of: '2026-11-25', value: 5010, return: 0.002, max_drawdown: 0,
      trades: 1, holding_at_close: { qqq_usd: 0, tqqq_usd: 5010, cash_usd: 0 }, next_open_target: { qqq: 0, tqqq: 1 } } } };
const line = T.lineHtml(FIXTURE);
assert(line.includes('$4,950') && line.includes('-1.0%') && line.includes('+0.2%') && line.includes('$4,900') && line.includes('截至 2026-11-25'));
const det = T.detailHtml(FIXTURE);
assert(det.includes('QQQ 80%，其余现金') && det.includes('TQQQ 100%') && det.includes('&lt;script&gt;') && !det.includes('<script>'));
assert.strictEqual(T.target({ qqq: 0, tqqq: 0 }), '全部现金');
assert(!/买入建议|立即买入|下单/.test(line + det.replace('不是买卖建议', '')));
console.log('PASS sim card: waiting / running line, collapsed detail, escaped labels, no order wording');
