// UX-02 homepage event calendar row: default ≤3 events in 7 days, 30-day list on expand, official vs UNOFFICIAL
// labels, cached / source status visible, ET + Beijing times (DST-aware), stale/failed states, escaping, no trade wording.
// FIXTURES below are labelled; the committed placeholder is only checked to render.
const assert = require('assert');
require('../docs/assets/event-calendar.js');
const T = globalThis.MAVEventCalendar._test;
const at = s => Date.parse(s);
const NOW = at('2026-10-26T08:00:00Z');
const ev = (o) => Object.assign({ category: 'macro', importance: 'high', source: 'FIXTURE' }, o);
const FX = {   // FIXTURE
  generated_at: '2026-10-26T07:30:00+00:00', policy: 'display_only', production_use: false, used_in_decision: false,
  note: 'FIXTURE note',
  source_status: { NFP: 'unavailable:OSError', PPI: 'fresh', GDP: 'fresh', PCE: 'fresh_none_in_window', EARNINGS: 'fresh',
                   FOMC_CPI: { CPI: 'cached', FOMC: 'fresh' } },
  earnings_coverage: { watchlist: 5, with_date: 3, unknown: ['IREN', 'SOFI'] },
  events: [
    ev({ key: 'cpi_2026-10-14', type: 'CPI', title_zh: '美国 CPI', date: '2026-10-14', datetime: '2026-10-14T08:30:00-04:00', time_status: 'official' }),
    ev({ key: 'fomc_2026-10-28', type: 'FOMC', title_zh: 'FOMC 利率决议', date: '2026-10-28', datetime: '2026-10-28T14:00:00-04:00', time_status: 'official',
         source_url: 'https://www.federalreserve.gov/' }),
    ev({ key: 'gdp_2026-10-29', type: 'GDP', title_zh: '美国 GDP', date: '2026-10-29', datetime: '2026-10-29T08:30:00-04:00', time_status: 'official_date_standard_time' }),
    ev({ key: 'pce_2026-10-30', type: 'PCE', title_zh: 'PCE', date: '2026-10-30', datetime: '2026-10-30T08:30:00-04:00', time_status: 'official_date_standard_time' }),
    ev({ key: 'earnings_AMD_2026-11-01', category: 'earnings', type: 'EARNINGS', symbol: 'AMD', title_zh: 'AMD 财报', date: '2026-11-01',
         date_end: '2026-11-03', datetime: null, time_status: 'unofficial_estimated_range', cached: true }),
    ev({ key: 'nfp_2026-11-06', type: 'NFP', title_zh: '美国非农就业报告', date: '2026-11-06', datetime: '2026-11-06T08:30:00-05:00',
         time_status: 'official_date_standard_time', cached: true }),
    ev({ key: 'earnings_NVDA_2026-11-18', category: 'earnings', type: 'EARNINGS', symbol: 'NVDA', title_zh: 'NVDA 财报', date: '2026-11-18',
         datetime: null, time_status: 'unofficial_date' }),
    ev({ key: 'earnings_TSLA_2026-12-20', category: 'earnings', type: 'EARNINGS', symbol: 'TSLA', title_zh: 'TSLA 财报', date: '2026-12-20',
         datetime: null, time_status: 'unofficial_date' }),
  ] };

// windows: past dropped, 7-day and 30-day windows by ET date
assert.strictEqual(T.etDate(at('2026-10-27T03:00:00Z')), '2026-10-26', 'ET date, not UTC date');
assert.deepStrictEqual(T.upcoming(FX.events, NOW, 7).map(e => e.key),
  ['fomc_2026-10-28', 'gdp_2026-10-29', 'pce_2026-10-30', 'earnings_AMD_2026-11-01']);
assert.deepStrictEqual(T.upcoming(FX.events, NOW, 30).map(e => e.key).slice(-2), ['nfp_2026-11-06', 'earnings_NVDA_2026-11-18']);
// a timed event drops 3h after release; a date-only range stays through its last day
assert(T.upcoming(FX.events, at('2026-10-28T20:00:00Z'), 7).some(e => e.type === 'FOMC'));
assert(!T.upcoming(FX.events, at('2026-10-28T21:01:00Z'), 7).some(e => e.type === 'FOMC'));
assert(T.upcoming(FX.events, at('2026-11-03T20:00:00Z'), 7).some(e => e.symbol === 'AMD'));
// ET + Beijing, DST-aware (FOMC in EDT, NFP after the switch to EST)
assert.strictEqual(T.when(FX.events[1]), '10/28 周三 14:00 ET · 北京 10/29 02:00');
assert.strictEqual(T.when(FX.events[5]), '11/6 周五 08:30 ET · 北京 11/6 21:30');
assert(T.when(FX.events[6]).includes('盘前/盘后未知'), 'earnings never get an invented time');
assert(T.when(FX.events[4]).startsWith('11/1 周日 – 11/3 周二'));

function fakeEl() { const a = {}; return { innerHTML: '', setAttribute: (k, v) => (a[k] = v), getAttribute: k => a[k], querySelector: () => null, attrs: a }; }
const el = fakeEl();
assert.strictEqual(T.render(el, FX, NOW).key, 'fresh');
const line = el.innerHTML.split('<div class="ec-detail"')[0], detail = el.innerHTML.slice(line.length);
// default line: first 3 in 7 days + count of the rest; expand button
assert(line.includes('FOMC 利率决议') && line.includes('美国 GDP') && line.includes('PCE') && !line.includes('AMD 财报'));
assert(line.includes('7 天内另有 1 项') && line.includes('30 天日历') && line.includes('官方日期·惯例时间'));
// detail: 30-day list with unofficial + cached labels, source status, coverage; past / out-of-window rows absent
assert(detail.includes('AMD 财报') && detail.includes('非官方·估计区间') && detail.includes('NVDA 财报') && detail.includes('>非官方<'));
assert(detail.includes('>缓存<') && !detail.includes('TSLA') && !detail.includes('10/14'));
assert(detail.includes('非农 暂不可用') && detail.includes('CPI 官方日历为缓存') && !detail.includes('PCE 暂不可用'));
assert(detail.includes('财报日期覆盖 3/5') && detail.includes('IREN、SOFI') && detail.includes('不参与任何判断'));
assert(detail.includes('href="https://www.federalreserve.gov/"') && detail.includes('rel="noopener noreferrer"'));
assert(!/马上买|马上卖|立即买入|立即卖出|BUY|SELL/.test(el.innerHTML), 'no trade instructions');
// nothing within 7 days -> says so and names the next item
const el2 = fakeEl(); T.render(el2, { ...FX, events: FX.events.slice(5) }, NOW);
assert(el2.innerHTML.includes('7 天内无已知重要事件；下一项 美国非农就业报告 11/6 周五'));
// stale / failed / malformed
const el3 = fakeEl(); assert.strictEqual(T.render(el3, FX, at('2026-10-29T08:00:00Z')).key, 'stale');
assert(el3.innerHTML.includes('待更新') && el3.attrs['data-state'] === 'stale');
for (const bad of [null, {}, { events: 'x' }]) {
  const e = fakeEl(); T.render(e, bad, NOW);
  assert(e.attrs['data-state'] === 'failed' && e.innerHTML.includes('读取失败'));
}
// escaping
const el4 = fakeEl();
T.render(el4, { ...FX, note: '<script>x</script>', events: [ev({ key: 'k', type: 'X', title_zh: '<img src=x onerror=1>', date: '2026-10-27', datetime: null, time_status: 'unofficial_date' })] }, NOW);
assert(!el4.innerHTML.includes('<img') && !el4.innerHTML.includes('<script>') && el4.innerHTML.includes('&lt;img'));
// the committed data file renders (whatever Daily wrote last) and is inert
const real = require('../docs/data/event_calendar.json');
assert(real.policy === 'display_only' && real.used_in_decision === false && real.production_use === false);
const el5 = fakeEl(); assert.notStrictEqual(T.render(el5, real, at(real.generated_at) + 3600e3).key, 'failed');
// loaded by the macro row (dynamic asset, so an old index.html picks it up too - rule 7)
const mer = require('fs').readFileSync(require('path').join(__dirname, '../docs/assets/macro-event-row.js'), 'utf8');
assert(mer.includes("'assets/event-calendar.js?v='") && mer.includes("'assets/event-calendar.css?v='") && mer.includes('loadEventCalendar();'));
console.log('PASS UX-02 event calendar row: 7-day top 3, 30-day list, official/unofficial labels, ET+北京, stale/failed, escaped');
