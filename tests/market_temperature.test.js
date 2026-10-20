const assert = require('assert');
const MT = require('../docs/assets/market-temperature.js');
assert.ok(/不可用/.test(MT.html(null)));
const d = { status: 'ok', score: 39.5, label: '恐惧', as_of: '2026-10-16', components_available: 5, cnn_link: 'https://www.cnn.com/markets/fear-and-greed',
  change_vs: { as_of: '2026-10-09', delta: -6.2 }, components: [{ status: 'ok', name: '价格动量', score: 57.6, as_of: '2026-10-16' }, { status: 'unavailable', name: '信用风险', reason: 'HY OAS missing' }] };
const h = MT.html(d);
assert.ok(h.includes('市场温度') && h.includes('40') && h.includes('恐惧') && h.includes('降温 -6.2') && h.includes('不是 CNN 指数') && h.includes('HY OAS missing') && h.includes('固定标尺'));
assert.ok(MT.html({ ...d, fixed_scale_components: 3 }).includes('其中 3 项历史不足一年') && !h.includes('其中 '));
assert.ok(MT.html({ ...d, components: [{ status: 'stale', name: '市场宽度', reason: '数据截至 2026-10-09，落后市场日 2026-10-16 5 个交易日，不计入' }] }).includes('落后市场日'));
assert.ok(MT.html({ ...d, components: [{ status: 'ok', name: '<img>', score: 1 }] }).includes('&lt;img&gt;'));
// gauge: five labelled zones, 0/25/50/75/100 scale, needle; text says direction and what drags it
['极度恐惧', '恐惧', '中性', '贪婪', '极度贪婪', '>0<', '>25<', '>50<', '>75<', '>100<', 'mt-needle'].forEach(t => assert.ok(h.includes(t), t));
const T = MT._test;
assert.strictEqual(T.trendWord({ score: 23, change_vs: { delta: 5.2 } }), '正在缓和');
assert.strictEqual(T.trendWord({ score: 23, change_vs: { delta: -3 } }), '正在加剧');
assert.strictEqual(T.trendWord({ score: 70, change_vs: { delta: 4 } }), '正在升温');
assert.strictEqual(T.trendWord({ score: 30, change_vs: { delta: 0.4 } }), '基本持平');
assert.strictEqual(T.trendWord({ score: 31, change_vs: { delta: -1 } }), '基本持平');
assert.strictEqual(T.fromTo({ score: 23.1, change_vs: { as_of: '2026-10-16', delta: 5.2 } }), '10/16 18 → 今日 23（+5.2）');
const comps = [{ status: 'ok', name: '价格动量', score: 14 }, { status: 'ok', name: '波动率', score: 8 }, { status: 'ok', name: '市场宽度', score: 46 }, { status: 'unavailable', name: '信用风险' }];
assert.strictEqual(T.drivers({ score: 23, components: comps }), '波动率与价格动量仍在拖累市场情绪。');
assert.strictEqual(T.drivers({ score: 80, components: comps }), '市场宽度与价格动量正在推升市场情绪。');
assert.strictEqual(MT._test.changeText({}), '首日记录，暂无比较');
console.log('PASS market temperature UI');
