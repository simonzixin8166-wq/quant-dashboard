const assert = require('assert');
const MT = require('../docs/assets/market-temperature.js');
assert.ok(/不可用/.test(MT.html(null)));
const d = { status: 'ok', score: 39.5, label: '恐惧', as_of: '2026-10-16', components_available: 5, cnn_link: 'https://www.cnn.com/markets/fear-and-greed',
  change_vs: { as_of: '2026-10-09', delta: -6.2 }, components: [{ status: 'ok', name: '价格动量', score: 57.6, as_of: '2026-10-16' }, { status: 'unavailable', name: '信用风险', reason: 'HY OAS missing' }] };
const h = MT.html(d);
assert.ok(h.includes('市场温度') && h.includes('40') && h.includes('恐惧') && h.includes('降温 -6.2') && h.includes('不是 CNN 指数') && h.includes('HY OAS missing') && h.includes('固定标尺'));
assert.ok(MT.html({ ...d, components: [{ status: 'ok', name: '<img>', score: 1 }] }).includes('&lt;img&gt;'));
assert.strictEqual(MT._test.changeText({}), '首日记录，暂无比较');
console.log('PASS market temperature UI');
