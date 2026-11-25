/* 策略模拟（纸面）— one compact homepage row (Owner 2026-11-25).
 * Reads research/sim_tqqq_ma200.json and shows the two 5,000 USD paper accounts of the forum QQQ/TQQQ 200-day
 * strategy (original rule, +/-2% band) against holding QQQ; the detail (holdings, max drawdown, trades, the next
 * open's target, the rules) is collapsed. Paper numbers only: never an order, never a MyAlpha alert or threshold.
 * Loaded from auto-research-row.js (no change to the Daily-generated index.html); inserted under the macro row. */
(function (root) {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function usd(v) { return v == null ? '-' : '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }); }
  function pct(v) { return v == null ? '-' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%'; }
  function tone(v) { return v == null ? '' : (v >= 0 ? 'sim-up' : 'sim-down'); }
  function target(t) {
    if (!t) return '-';
    if (t.tqqq > 0) return 'TQQQ ' + Math.round(t.tqqq * 100) + '%';
    if (t.qqq > 0) return 'QQQ ' + Math.round(t.qqq * 100) + '%，其余现金';
    return '全部现金';
  }
  function holding(h) {
    if (!h) return '-';
    return 'QQQ ' + usd(h.qqq_usd) + ' · TQQQ ' + usd(h.tqqq_usd) + ' · 现金 ' + usd(h.cash_usd);
  }

  function lineHtml(d) {
    if (!d || !d.accounts) return '<div class="sim-line"><span class="sim-title">策略模拟（纸面）</span><span class="sim-muted">暂无数据</span></div>';
    var o = d.accounts.original || {}, b = d.accounts.band2 || {}, q = d.benchmark || {};
    if (o.status !== 'running') {
      return '<div class="sim-line"><span class="sim-title">策略模拟（纸面 5,000 美元）</span><span class="sim-muted">今晚收盘后开始记录（首个信号：80% QQQ，第二天开盘买入）</span></div>';
    }
    return '<div class="sim-line"><span class="sim-title">策略模拟（纸面 5,000 美元）</span>' +
      '<span>原规则 <b>' + usd(o.value) + '</b> <em class="' + tone(o['return']) + '">' + pct(o['return']) + '</em></span>' +
      '<span>加 2% 缓冲 <b>' + usd(b.value) + '</b> <em class="' + tone(b['return']) + '">' + pct(b['return']) + '</em></span>' +
      '<span>持有 QQQ <b>' + usd(q.value) + '</b> <em class="' + tone(q['return']) + '">' + pct(q['return']) + '</em></span>' +
      '<span class="sim-muted">截至 ' + esc(o.as_of) + '</span>' +
      '<button type="button" class="sim-toggle" aria-expanded="false">详情</button></div>';
  }

  function detailHtml(d) {
    if (!d || !d.accounts) return '';
    var rows = ['original', 'band2'].map(function (k) {
      var a = d.accounts[k] || {};
      return '<tr><td>' + esc(a.label_zh) + '</td><td>' + holding(a.holding_at_close) + '</td><td>' + pct(a.max_drawdown) +
        '</td><td>' + esc(a.trades == null ? '-' : a.trades) + '</td><td>' + esc(target(a.next_open_target)) + '</td></tr>';
    }).join('');
    return '<div class="sim-table"><table><thead><tr><th>账户</th><th>收盘持仓</th><th>最深回撤</th><th>交易次数</th><th>下个开盘目标</th></tr></thead><tbody>' +
      rows + '</tbody></table></div><p class="sim-muted">规则：' + esc(d.rules_zh) + '</p><p class="sim-muted">' + esc(d.note_zh) +
      ' 开始于 ' + esc((d.accounts.original || {}).started || '-') + '。</p>';
  }

  function render(el, d) {
    el.innerHTML = lineHtml(d) + '<div class="sim-detail" hidden>' + detailHtml(d) + '</div>';
    var btn = el.querySelector('.sim-toggle'), det = el.querySelector('.sim-detail');
    if (btn && det) btn.addEventListener('click', function () {
      var open = det.hasAttribute('hidden');
      if (open) det.removeAttribute('hidden'); else det.setAttribute('hidden', '');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false'); btn.textContent = open ? '收起' : '详情';
    });
  }

  function init() {
    if (typeof document === 'undefined' || typeof fetch !== 'function') return;
    if (document.getElementById('simStrategyRow')) return;
    var anchor = document.getElementById('macroEventRow') || document.getElementById('autoResearchRow');
    if (!anchor) return;
    var el = document.createElement('section');
    el.id = 'simStrategyRow'; el.className = 'sim-row'; el.setAttribute('aria-label', '策略模拟（纸面）');
    anchor.parentNode.insertBefore(el, anchor.nextSibling);
    fetch('research/sim_tqqq_ma200.json?v=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) { render(el, d); })
      .catch(function () { render(el, null); });
  }

  root.MAVSimCard = { _test: { lineHtml: lineHtml, detailHtml: detailHtml, target: target, esc: esc } };
  if (typeof document !== 'undefined' && document.addEventListener) {
    // the macro row inserts itself asynchronously; wait a moment so this row lands under it
    var go = function () { setTimeout(init, 300); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
  }
})(typeof window !== 'undefined' ? window : globalThis);
