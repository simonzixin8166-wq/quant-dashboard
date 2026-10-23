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
const vc = v => [{ key: 'volatility', status: 'ok', name: '波动率', score: 8, value: { vix: v } }];
assert.ok(T.vsVix({ score: 31, components: vc(18.4) }).includes('尚未恐慌') && T.vsVix({ score: 31, components: vc(18.4) }).includes('不是信号'));
assert.ok(T.vsVix({ score: 20, components: vc(32) }).includes('同时走弱'));
assert.strictEqual(T.vsVix({ score: 31, components: [] }), '');
assert.strictEqual(MT._test.changeText({}), '首日记录，暂无比较');
console.log('PASS market temperature UI');

// MT-04 加仓分档: existing production ladder is the trigger; size hint + VIX>=25 confirmation only (#133 6283755497)
const core = (lvl, dd, extra = {}) => ({ drawdown: dd, tiers: { t1: 0.12, t2: 0.18, t3: 0.25 }, level: lvl, ath_is_true: true, ath_validation: 'PASS', ...extra });
const mk = (q, v, l, vix) => ({ spy_date: '2026-10-19', core: { QQQM: q, VGT: v, QLD: l }, market_indicators: { vix: { close: vix, date: '2026-10-19' } } });
let a = T.addonTiers(mk(core(0, -0.058), core(0, -0.079), core(0, -0.116), 18.4));
assert.strictEqual(a.hit, false); assert.strictEqual(a.confirm, 'pending');
assert.ok(a.rows[0].text.includes('未到一级') && a.rows[0].text.includes('一级 −12.0%') && a.rows[0].text.includes('还差 6.2%'), a.rows[0].text);
a = T.addonTiers(mk(core(1, -0.13), core(2, -0.19), core(3, -0.30), 27));
assert.strictEqual(a.hit, true); assert.strictEqual(a.confirm, 'confirmed');
assert.ok(a.rows[0].text.includes('本月可加 1 倍月定投') && a.rows[1].text.includes('2 倍') && !a.rows[2].text.includes('倍月定投') && a.rows[2].text.includes('只补回目标权重'));
assert.strictEqual(T.addonTiers(mk(core(1, -0.13), core(0, -0.05), core(0, -0.1), 25)).confirm, 'confirmed', 'VIX exactly 25 confirms');
assert.strictEqual(T.addonTiers(mk(core(1, -0.13), core(0, -0.05), core(0, -0.1), null)).confirm, 'unavailable', 'missing VIX is unavailable, never pending/confirmed');
// the ladder level is used only when the ATH is verified; never invent a tier from missing data
const unver = T.addonTiers(mk(core(2, -0.2, { ath_validation: 'CHECK' }), core(1, -0.16, { ath_is_true: false }), { error: 'x' }, 30));
assert.deepStrictEqual(unver.rows.map(r => r.status), ['unverified', 'unverified', 'unavailable']); assert.strictEqual(unver.hit, false);
assert.ok(T.addonTiers(null).rows.every(r => r.status === 'unavailable'));
const ah = T.addonHtml(mk(core(1, -0.13), core(0, -0.05), core(0, -0.1), 22));
assert.ok(ah.includes('已到加仓档，恐慌待确认') && ah.includes('VIX 22.0 &lt; 25') && ah.includes('人工决定'), ah);
assert.ok(T.addonHtml(mk(core(0, -0.05), core(0, -0.05), core(0, -0.1), 18.4)).includes('到档后需 VIX ≥ 25'), 'no tier hit: confirmation explained, not shown as pending');
console.log('PASS MT-04 add-on tiers');
// TP-01 front-end: result only (headline, action, 4 statuses with value/date); escaped; placeholder before first run
const tpd = { market_date: '2026-10-21', tag: '外部观点 · 未验证 · 观察用，不是买卖信号',
  summary: { met: 0, near: 1, triggered: false, headline: '0 / 4 满足、1 项接近 · 尚未出现转折条件', action: '继续按原计划定投，不因本清单加减仓；满足 3 项时会提醒你重新评估。' },
  items: [{ key: 'earnings', name: '科技巨头财报', status: 'waiting', value: '本季尚未公布 · 0/6 家' },
          { key: 'yield_10y', name: '10 年期美债', status: 'not_met', value: '5.15%（需 < 5.0%）', as_of: '2026-10-20' },
          { key: 'sentiment', name: '情绪出清', status: 'near', value: '<b>x</b>', as_of: '2026-10-21' },
          { key: 'easing', name: '通胀与油价缓解', status: 'unavailable', value: '通胀与油价数据不足' }] };
const th = T.tpHtml(tpd);
['变盘信号清单', '0 / 4 满足、1 项接近', '继续按原计划定投', '等待中', '未满足', '接近', '不可用', '10/20', '不是买卖信号', '&lt;b&gt;x&lt;/b&gt;'].forEach(t => assert.ok(th.includes(t), t));
assert.ok(!th.includes('tp-on'), 'not triggered → no highlight');
assert.ok(T.tpHtml({ ...tpd, summary: { ...tpd.summary, triggered: true } }).includes('tp-on'));
assert.ok(T.tpHtml(null).includes('结果将在下一次每日更新后生成') && T.tpHtml({}).includes('结果将在下一次每日更新后生成'));
// cannot_judge (GPT 6333569916 C): missing data never reads as "not met"
assert.ok(th.includes('1 项数据不可用，可判断 2/4') && !th.includes('tp-unknown'), 'partial data: denominator shown, verdict kept (max reachable 2 < 3)');
const two = { ...tpd, items: tpd.items.map(x => x.key === 'yield_10y' ? { ...x, status: 'unavailable' } : x) };
const tu = T.tpHtml(two);
assert.ok(tu.includes('暂无法判断') && tu.includes('2 项数据不可用') && tu.includes('可判断 1/4') && tu.includes('tp-unknown') && !tu.includes('尚未出现转折条件'), tu);
const allOk = { ...tpd, items: tpd.items.map(x => ({ ...x, status: 'not_met' })) };
assert.strictEqual(T.tpVerdict(allOk).headline, tpd.summary.headline);
assert.ok(!T.tpVerdict({ ...two, summary: { ...two.summary, triggered: true } }).cannot, 'triggered stays triggered');
console.log('PASS TP-01 front-end');

