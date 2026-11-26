/* 策略模拟（纸面）— one compact homepage row (Owner 2026-11-25).
 * Reads research/sim_tqqq_ma200.json and shows four 5,000 USD paper books from the same start (Owner 2026-11-26):
 * the 200-day rule with a 2% band, YIFAN's 530 rule, the two combined, and holding QQQ; the detail (positions,
 * fill log, max drawdown, the next open's target, the rules) is collapsed. Paper numbers only: never an order, never a MyAlpha alert or threshold.
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

  var ORDER = ['band2', 'ema530', 'hybrid'];
  function order(d) { return (d && d.order && d.order.length) ? d.order : ORDER; }

  function lineHtml(d) {
    if (!d || !d.accounts) return '<div class="sim-line"><span class="sim-title">策略模拟（纸面）</span><span class="sim-muted">暂无数据</span></div>';
    var keys = order(d), q = d.benchmark || {};
    var first = d.accounts[keys[0]] || {};
    if (first.status !== 'running') {
      return '<div class="sim-line"><span class="sim-title">策略模拟（纸面，每个 5,000 美元）</span><span class="sim-muted">今晚收盘后开始记录（收盘出信号，第二天开盘成交）</span></div>';
    }
    var items = keys.map(function (k) {
      var a = d.accounts[k] || {};
      return '<span>' + esc(a.label_zh || k) + ' <b>' + usd(a.value) + '</b> <em class="' + tone(a['return']) + '">' + pct(a['return']) + '</em></span>';
    }).join('');
    return '<div class="sim-line"><span class="sim-title">策略模拟（纸面，每个 5,000 美元）</span>' + items +
      '<span>' + esc(q.label_zh || '一直持有 QQQ') + ' <b>' + usd(q.value) + '</b> <em class="' + tone(q['return']) + '">' + pct(q['return']) + '</em></span>' +
      '<span class="sim-muted">截至 ' + esc(first.as_of) + '</span>' +
      '<button type="button" class="sim-toggle" aria-expanded="false">详情</button></div>';
  }

  function money(v) { return v == null ? '-' : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  var SIDE = { BUY: '买入', SELL: '卖出' };

  function bookHtml(a) {
    var pos = (a.positions || []).map(function (p) {
      return '<tr><td>' + esc(p.symbol) + '</td><td>' + esc(p.shares) + '</td><td>' + money(p.avg_cost) + '</td><td>' + money(p.price) +
        '</td><td>' + money(p.market_value) + '</td><td class="' + tone(p.unrealized_pnl) + '">' + money(p.unrealized_pnl) + ' (' + pct(p.unrealized_pct) + ')</td></tr>';
    }).join('') || '<tr><td colspan="6" class="sim-muted">无持仓</td></tr>';
    var fills = (a.fills || []).slice().reverse().map(function (f) {
      return '<tr><td>' + esc(f.date) + '</td><td>' + esc(SIDE[f.side] || f.side) + '</td><td>' + esc(f.symbol) + '</td><td>' + esc(f.shares) +
        '</td><td>' + money(f.price) + '</td><td>' + money(f.amount) + '</td><td>' + money(f.commission) + '</td><td>' +
        (f.realized_pnl == null ? '-' : '<span class="' + tone(f.realized_pnl) + '">' + money(f.realized_pnl) + '</span>') + '</td></tr>';
    }).join('') || '<tr><td colspan="8" class="sim-muted">暂无成交</td></tr>';
    return '<h4>' + esc(a.label_zh) + '　市值 ' + money(a.value) + '　现金 ' + money(a.cash_usd) + '　已实现盈亏 ' + money(a.realized_pnl) +
      '　最深回撤 ' + pct(a.max_drawdown) + '　下个开盘目标：' + esc(target(a.next_open_target)) + '</h4>' +
      '<div class="sim-table"><table><thead><tr><th>标的</th><th>股数</th><th>平均成本</th><th>收盘价</th><th>市值</th><th>未实现盈亏</th></tr></thead><tbody>' + pos + '</tbody></table></div>' +
      '<div class="sim-table"><table><thead><tr><th>成交日期</th><th>方向</th><th>标的</th><th>股数</th><th>成交价（开盘）</th><th>成交金额</th><th>佣金</th><th>已实现盈亏</th></tr></thead><tbody>' + fills + '</tbody></table></div>';
  }

  function benchHtml(q) {
    return '<h4>' + esc(q.label_zh || '一直持有 QQQ') + '　市值 ' + money(q.value) + '　收益 ' + pct(q['return']) + '　最深回撤 ' + pct(q.max_drawdown) +
      '</h4><p class="sim-muted">' + esc(q.started || '-') + ' 开盘一次性买入 QQQ ' + esc(q.qqq_shares == null ? '-' : q.qqq_shares) + ' 股，成交价 ' +
      money(q.buy_price) + '，剩余现金 ' + money(q.cash_usd) + '，之后不再买卖。</p>';
  }

  function detailHtml(d) {
    if (!d || !d.accounts) return '';
    var keys = order(d);
    return keys.map(function (k) { return bookHtml(d.accounts[k] || {}); }).join('') + benchHtml(d.benchmark || {}) +
      '<p class="sim-muted">规则：' + esc(d.rules_zh) + '</p><p class="sim-muted">' + esc(d.note_zh) +
      ' 开始于 ' + esc((d.accounts[keys[0]] || {}).started || '-') + '。</p>';
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

  root.MAVSimCard = { _test: { lineHtml: lineHtml, detailHtml: detailHtml, target: target, esc: esc, benchHtml: benchHtml } };
  if (typeof document !== 'undefined' && document.addEventListener) {
    // the macro row inserts itself asynchronously; wait a moment so this row lands under it
    var go = function () { setTimeout(init, 300); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
  }
})(typeof window !== 'undefined' ? window : globalThis);
