/* MyAlpha 事件日历 (UX-02) — one compact homepage row under 宏观事件与分批观察. Display only, read-only.
 * Reads data/event_calendar.json (Daily, scripts/event_calendar.py): FOMC/CPI official, NFP/PPI/GDP/PCE official
 * release dates from FRED (08:30 ET = agency practice), watchlist earnings from Yahoo = UNOFFICIAL (labelled per row).
 * Default: up to 3 events in the next 7 days; expand for the 30-day list with source status.
 * Never a trade instruction; nothing here feeds a decision. Stale or unreadable data is shown as such. */
(function (root) {
  var DEFAULT_DAYS = 7, FULL_DAYS = 30, DEFAULT_N = 3, STALE_HOURS = 48;
  var LABEL = { official: ['官方', 'ec-off'], official_date_standard_time: ['官方日期·惯例时间', 'ec-off'],
                unofficial_date: ['非官方', 'ec-unoff'], unofficial_estimated_range: ['非官方·估计区间', 'ec-unoff'] };
  var SRC_ZH = { NFP: '非农', PPI: 'PPI', GDP: 'GDP', PCE: 'PCE', CPI: 'CPI(FRED)', EARNINGS: '财报', FOMC: 'FOMC', FOMC_CPI: 'FOMC/CPI' };
  var WD = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function ms(iso) { var t = Date.parse(iso); return isNaN(t) ? null : t; }
  // calendar parts of instant `t` in time zone `tz`
  function parts(t, tz) {
    var o = {};
    new Intl.DateTimeFormat('en-US', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit',
      minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(t)).forEach(function (p) { o[p.type] = p.value; });
    return o;
  }
  function etDate(t) { var p = parts(t, 'America/New_York'); return p.year + '-' + p.month + '-' + p.day; }
  function addDays(isoDate, n) {
    var d = new Date(isoDate + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10);
  }
  function md(isoDate) {
    var d = new Date(isoDate + 'T12:00:00Z');
    return (d.getUTCMonth() + 1) + '/' + d.getUTCDate() + ' ' + WD[d.getUTCDay()];
  }
  function when(e) {
    var t = ms(e.datetime);
    if (t == null) {
      return md(e.date) + (e.date_end ? ' – ' + md(e.date_end) : '') + '（美东日期，盘前/盘后未知）';
    }
    var et = parts(t, 'America/New_York'), bj = parts(t, 'Asia/Shanghai');
    return md(e.date) + ' ' + et.hour + ':' + et.minute + ' ET · 北京 ' + Number(bj.month) + '/' + Number(bj.day) + ' ' + bj.hour + ':' + bj.minute;
  }

  // events still ahead at `now`: timed rows until 3h after release, date-only rows through their (last) ET date
  function upcoming(events, now, days) {
    var today = etDate(now), last = addDays(today, days);
    return (events || []).filter(function (e) {
      if (!e || !e.date || e.date > last) return false;
      var t = ms(e.datetime);
      return t != null ? t + 3 * 3600e3 > now : (e.date_end || e.date) >= today;
    });
  }

  function quality(d, now) {
    if (!d || !Array.isArray(d.events)) return { key: 'failed', label: '读取失败' };
    var age = (now - ms(d.generated_at)) / 3600e3;
    if (!(age >= 0) || age > STALE_HOURS) return { key: 'stale', label: '待更新（最后生成 ' + esc(String(d.generated_at || '未知').slice(0, 16)) + '）' };
    return { key: 'fresh', label: '更新于 ' + esc(String(d.generated_at).slice(0, 16).replace('T', ' ')) + 'Z' };
  }

  function chip(e) {
    var l = LABEL[e.time_status] || [esc(e.time_status || '未知'), 'ec-unoff'];
    return '<span class="ec-chip ' + l[1] + '" title="' + esc(e.time_note || e.source || '') + '">' + l[0] + '</span>' +
      (e.cached ? '<span class="ec-chip ec-cached" title="本次来源失败，沿用上次结果">缓存</span>' : '');
  }
  function itemHtml(e) {
    return '<span class="ec-item"><b>' + esc(e.title_zh || e.type) + '</b> ' + esc(when(e).replace(/（.*）$/, '')) + ' ' + chip(e) + '</span>';
  }

  function statusHtml(d) {
    var st = d.source_status || {}, bad = [];
    Object.keys(st).forEach(function (k) {
      var v = st[k];
      if (v && typeof v === 'object') {
        // FOMC/CPI from the Fed/BLS pages (update_market_events.py)
        Object.keys(v).forEach(function (kk) {
          if (v[kk] !== 'fresh') bad.push(kk + ' 官方日历' + (v[kk] === 'cached' ? '为缓存' : '：' + v[kk]));
        });
      } else if (!/^fresh/.test(String(v))) {
        bad.push((SRC_ZH[k] || k) + ' 暂不可用');
      }
    });
    var cov = d.earnings_coverage || {};
    return '<p class="ec-meta">来源状态：' + (bad.length ? esc(bad.join('；')) : '全部正常') + '</p>' +
      '<p class="ec-meta">财报日期覆盖 ' + esc(cov.with_date) + '/' + esc(cov.watchlist) +
      ((cov.unknown || []).length ? '；未取得日期：' + esc(cov.unknown.join('、')) : '') + '</p>';
  }

  function detailHtml(d, now) {
    var rows = upcoming(d.events, now, FULL_DAYS).map(function (e) {
      var src = e.source_url ? '<a href="' + esc(e.source_url) + '" target="_blank" rel="noopener noreferrer">' + esc(e.source) + '</a>' : esc(e.source);
      return '<tr><td>' + esc(when(e)) + '</td><td>' + esc(e.title_zh || e.type) + '</td><td>' + chip(e) + '</td><td>' + src + '</td></tr>';
    }).join('');
    return '<div class="ec-detail" hidden>' +
      '<div class="ec-table"><table><thead><tr><th>时间（美东 / 北京）</th><th>事件</th><th>口径</th><th>来源</th></tr></thead><tbody>' +
      (rows || '<tr><td colspan="4">未来 30 天暂无已知事件</td></tr>') + '</tbody></table></div>' +
      '<p class="ec-meta">' + esc(d.note) + ' 仅供查看，不参与任何判断，也不是买卖指令。</p>' + statusHtml(d) + '</div>';
  }

  function render(el, d, now) {
    now = now || Date.now();
    var q = quality(d, now);
    el.setAttribute('data-state', q.key);
    if (q.key === 'failed') {
      el.innerHTML = '<div class="ec-line"><b class="ec-title">事件日历</b><span class="ec-meta">读取失败｜请以官方日历为准</span></div>';
      return q;
    }
    var soon = upcoming(d.events, now, DEFAULT_DAYS), top = soon.slice(0, DEFAULT_N);
    var nextLater = soon.length ? null : upcoming(d.events, now, FULL_DAYS)[0];
    el.innerHTML = '<div class="ec-line"><b class="ec-title">事件日历</b>' +
      (top.length ? top.map(itemHtml).join('') + (soon.length > top.length ? '<span class="ec-meta">7 天内另有 ' + (soon.length - top.length) + ' 项</span>' : '')
        : '<span class="ec-text">7 天内无已知重要事件' + (nextLater ? '；下一项 ' + esc(nextLater.title_zh || nextLater.type) + ' ' + esc(md(nextLater.date)) : '') + '</span>') +
      '<span class="ec-meta">' + q.label + '</span>' +
      '<button type="button" class="ec-toggle" aria-expanded="false">30 天日历</button></div>' + detailHtml(d, now);
    var btn = el.querySelector('.ec-toggle'), det = el.querySelector('.ec-detail');
    if (btn && det) btn.addEventListener('click', function () {
      var open = det.hasAttribute('hidden');
      if (open) det.removeAttribute('hidden'); else det.setAttribute('hidden', '');
      btn.setAttribute('aria-expanded', String(open)); btn.textContent = open ? '收起' : '30 天日历';
    });
    return q;
  }

  function init() {
    if (typeof document === 'undefined' || typeof fetch !== 'function') return;
    if (document.getElementById('eventCalendarRow')) return;
    var anchor = document.getElementById('macroEventRow') || document.getElementById('autoResearchRow');
    if (!anchor) return;
    var el = document.createElement('section');
    el.id = 'eventCalendarRow'; el.className = 'event-calendar-row'; el.setAttribute('aria-label', '事件日历');
    anchor.parentNode.insertBefore(el, anchor.nextSibling);
    fetch('data/event_calendar.json?v=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) { render(el, d); })
      .catch(function () { render(el, null); });
  }

  root.MAVEventCalendar = { _test: { upcoming: upcoming, quality: quality, render: render, when: when, etDate: etDate, esc: esc } };
  if (typeof document !== 'undefined' && document.addEventListener) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
