/* MyAlpha 今日研究 — one homepage row (#133 6109957428 P0-3).
 * Reads research/auto_research_digest.json (built from the append-only shadow journal) and shows
 * 最新交易日 | 新增 | 失效 | 弃权 | 更新时间 | 查看详情, with a state badge:
 *   正常 ok       research covers the market session the page shows
 *   待运行 pending one session behind, within the normal post-close run window
 *   陈旧 stale     behind beyond that window
 *   失败 failed    digest unreadable, or the research step failed after its last success
 * The detail view lists, per active hypothesis: stance, record date, supporting / opposing evidence with source and
 * as-of, invalidation conditions, next review, inputs and annotations. Shadow research hints only — never orders. */
(function (root) {
  var STATE = { ok: '正常', pending: '待运行', stale: '陈旧', failed: '失败' };
  var STANCE = { bullish: '偏多', bearish: '偏空', neutral: '中性', cannot_judge: '弃权' };
  var RUN_WINDOW_HOURS = 18; // close (≈20:00 UTC) → the 12:35 UTC fallback run next day, plus margin

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function computeState(d, pageMarketAsOf, now) {
    now = now || new Date();
    if (!d || typeof d !== 'object') return { key: 'failed', why: '研究摘要读取失败' };
    if (d.run_failure && d.run_failure.failed_after_last_success) return { key: 'failed', why: '最近一次自动研究运行失败（' + (d.run_failure.failed_at || '') + '）' };
    if (!d.latest_session) return { key: 'pending', why: '尚无研究记录' };
    if (!pageMarketAsOf || d.latest_session >= pageMarketAsOf) return { key: 'ok', why: '研究已覆盖页面所示交易日 ' + d.latest_session };
    var close = Date.parse(pageMarketAsOf + 'T20:00:00Z');
    var hours = (now.getTime() - close) / 3600000;
    if (hours >= 0 && hours < RUN_WINDOW_HOURS) return { key: 'pending', why: pageMarketAsOf + ' 收盘后的研究尚未运行（正常窗口内）' };
    return { key: 'stale', why: '研究停留在 ' + d.latest_session + '，页面行情已到 ' + pageMarketAsOf };
  }

  function fmtTime(iso) {
    if (!iso) return '-';
    var t = new Date(iso);
    if (isNaN(t)) return esc(iso);
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(t.getMonth() + 1) + '/' + p(t.getDate()) + ' ' + p(t.getHours()) + ':' + p(t.getMinutes());
  }

  function evList(list, empty) {
    if (!list || !list.length) return '<li class="arr-muted">' + esc(empty) + '</li>';
    return list.map(function (e) {
      return '<li>' + esc(e.note || e.name) + ' <small>' + esc(e.source || '') + (e.as_of ? ' · 截至 ' + esc(e.as_of) : '') + '</small>' +
        (e.pre_sec_gate ? ' <em class="arr-flag">门禁前生成·待复核</em>' : '') + '</li>';
    }).join('');
  }

  function itemHtml(it) {
    var notes = (it.annotations || []).map(function (a) { return '<li>' + esc(a.note) + '</li>'; }).join('');
    return '<details class="arr-item"><summary><b>' + esc(it.symbol) + '</b> <span class="arr-stance st-' + esc(it.stance) + '">' +
      esc(STANCE[it.stance] || it.stance) + '</span><small>记录 ' + esc(it.research_date) + ' · 数据截至 ' + esc(it.market_as_of) +
      (it.new_this_session ? ' · 本交易日新增' : '') + '</small></summary>' +
      '<div class="arr-body">' +
      (it.pre_sec_gate ? '<p class="arr-flag-line">此假设生成于 SEC 财务质量门禁（#195/#196）之前，其中的基本面证据不作为当前证据。</p>' : '') +
      '<p class="arr-reason">' + esc(it.decision_reason) + '</p>' +
      '<div class="arr-cols"><div><h4>支持证据</h4><ul>' + evList(it.supporting, '无') + '</ul></div>' +
      '<div><h4>反方证据</h4><ul>' + evList(it.opposing, it.opposing_note || '无反方证据') + '</ul></div></div>' +
      '<h4>失效条件</h4><ul>' + (it.invalidation || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' +
      '<p class="arr-meta">下次复核 ' + esc(it.next_review || '-') + ' · 输入来源：' + esc((it.inputs || []).join(', ')) +
      (it.unknowns && it.unknowns.length ? ' · 未知项：' + esc(it.unknowns.join('；')) : '') + '</p>' +
      (notes ? '<h4>追加注释</h4><ul class="arr-notes">' + notes + '</ul>' : '') +
      '<p class="arr-meta">' + esc(it.research_hint || '') + '</p></div></details>';
  }

  function render(el, d, st) {
    var c = (d && d.counts) || {};
    var n = function (v) { return v == null ? '-' : esc(v); };
    var html = '<div class="arr-line"><b class="arr-title">MyAlpha 今日研究</b>' +
      '<span class="arr-badge arr-' + st.key + '" title="' + esc(st.why) + '">' + STATE[st.key] + '</span>' +
      '<span>最新交易日 <b>' + n(d && d.latest_session) + '</b></span>' +
      '<span>新增 <b>' + n(c.new) + '</b></span><span>失效 <b>' + n(c.invalidated) + '</b></span>' +
      '<span>弃权 <b>' + n(c.abstained) + '</b></span>' +
      '<span>更新 ' + fmtTime(d && d.last_run && d.last_run.at) + '</span>' +
      (d ? '<button type="button" class="arr-toggle" aria-expanded="false">查看详情</button>' : '') + '</div>';
    if (d) {
      html += '<div class="arr-detail" hidden>' +
        '<p class="arr-muted">' + esc(st.why) + '。Shadow 研究提示，不是下单指令；由你自行决定。Learning UNPROVEN · 跨日复核 ' +
        n(c.revisited_cross_day) + '（仍有效 ' + n(c.still_valid) + ' / 立场变化 ' + n(c.superseded_cross_day) + ' / 到期复核 ' + n(c.review_due) + '）· 活动假设 ' + n(c.active) + '</p>' +
        ((d.invalidated || []).length ? '<h4>本交易日失效</h4><ul>' + d.invalidated.map(function (x) { return '<li><b>' + esc(x.symbol) + '</b> ' + esc(x.trigger || '') + '</li>'; }).join('') + '</ul>' : '') +
        ((d.abstained || []).length ? '<h4>弃权</h4><ul>' + d.abstained.map(function (x) { return '<li><b>' + esc(x.symbol) + '</b> ' + esc(x.reason || '') + '</li>'; }).join('') + '</ul>' : '') +
        '<h4>活动假设</h4>' + (d.items || []).map(itemHtml).join('') + '</div>';
    }
    el.innerHTML = html;
    el.setAttribute('data-state', st.key);
    var btn = el.querySelector('.arr-toggle'), det = el.querySelector('.arr-detail');
    if (btn && det) btn.addEventListener('click', function () {
      var open = det.hasAttribute('hidden');
      if (open) det.removeAttribute('hidden'); else det.setAttribute('hidden', '');
      btn.setAttribute('aria-expanded', String(open)); btn.textContent = open ? '收起详情' : '查看详情';
    });
  }

  // #133 6138793593 H-01: the compact 宏观事件与分批观察 row is loaded from here (static asset; no change to the
  // Daily-generated index.html template), with the same asset version as this script.
  function loadMacroEventRow() {
    try {
      if (document.getElementById('macroEventRowScript')) return;
      var me = document.querySelector('script[src*="auto-research-row.js"]');
      var v = me && /[?&]v=([^&]+)/.exec(me.getAttribute('src')) ? /[?&]v=([^&]+)/.exec(me.getAttribute('src'))[1] : '';
      var css = document.createElement('link'); css.rel = 'stylesheet'; css.href = 'assets/macro-event-row.css?v=' + v;
      document.head.appendChild(css);
      var s = document.createElement('script'); s.id = 'macroEventRowScript'; s.src = 'assets/macro-event-row.js?v=' + v;
      document.body.appendChild(s);
    } catch (e) { /* the research row never fails because of the macro row */ }
  }

  function init() {
    loadMacroEventRow();
    var el = document.getElementById('autoResearchRow');
    if (!el || typeof fetch !== 'function') return;
    var marketAsOf = el.getAttribute('data-market-as-of') || '';
    var get = function (u) { return fetch(u + '?v=' + Date.now(), { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }); };
    // failure state comes from the digest itself (Daily rebuilds it right after writing a failure marker);
    // module_failures.json is event-only and normally absent, so it is never requested here (no 404 noise)
    get('research/auto_research_digest.json')
      .then(function (d) { render(el, d, computeState(d, marketAsOf)); })
      .catch(function () { render(el, null, computeState(null, marketAsOf)); });
  }

  root.MAVAutoResearchRow = { _test: { computeState: computeState, esc: esc, itemHtml: itemHtml } };
  if (typeof document !== 'undefined' && document.addEventListener) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
