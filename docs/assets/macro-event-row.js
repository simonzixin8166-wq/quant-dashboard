/* MyAlpha 宏观事件与分批观察 — one compact homepage row (#133 6138793593, H-01/H-02). Shadow, read-only.
 * Reads research/macro_event_watch.json. Event phase (计划中 / 事件前 / 已发布 / T+n) is computed from the clock
 * against precomputed DST-aware windows, so a pre-event reminder never waits for a post-close run.
 * Judgment shows one of 偏风险 / 中性待确认 / 条件改善 / 数据不足 — MyAlpha's Shadow reading, not the author's
 * forecast and never a BUY/SELL instruction. Stale or unreadable data → a visible 待更新/数据不足 state,
 * never the previous optimistic judgment. */
(function (root) {
  var JUDGE = { risk_elevated: ['偏风险', 'mer-risk'], neutral_awaiting_confirmation: ['中性待确认', 'mer-neutral'],
                conditions_improving: ['条件改善', 'mer-good'], data_insufficient: ['数据不足', 'mer-warn'] };

  var ST = { met: '满足', unmet: '未满足', unknown: '未知', not_met: '未满足', candidate: '候选（Shadow）', conflict_frozen: '冲突冻结',
             price_condition_met_needs_manual_budget_and_guardrail_check: '价格条件满足·需人工核对' };
  function stz(k) { return ST[k] || k; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function ms(iso) { var t = Date.parse(iso); return isNaN(t) ? null : t; }
  function hm(ev) { return (ev.release && ev.release.beijing_label) || ''; }

  // phase of one event at time `now` (ms)
  function phase(ev, now) {
    var w = ev.windows || {}, tp = w.t_plus || {};
    var rel = ms(w.release);
    if (now >= ms(w.archive_after)) return { key: 'archived', label: '已归档', order: 9 };
    if (now < ms(w.t_minus_1_start)) return { key: 'planned', label: '计划中', order: 3 };
    if (now < ms(w.event_day_start)) return { key: 't_minus_1', label: '明天 ' + hm(ev) + '｜事件前观察', order: 0 };
    if (now < rel) return { key: 'pre_event', label: '今天 ' + hm(ev) + ' 发布｜事件前', order: 0 };
    if (!ev.official_outcome) return { key: 'released_pending', label: '已发布｜待核实官方结果', order: 0 };
    var last = 'T', keys = ['T+1', 'T+3', 'T+5', 'T+10'];
    for (var i = 0; i < keys.length; i++) if (now >= ms(tp[keys[i]])) last = keys[i];
    return { key: 'post', label: '已公布｜' + last, order: 1 };
  }

  // current event = the earliest not archived whose phase is active; otherwise the next planned
  function pick(events, now) {
    var live = (events || []).map(function (e) { return { ev: e, ph: phase(e, now) }; }).filter(function (x) { return x.ph.key !== 'archived'; });
    live.sort(function (a, b) { return a.ph.order - b.ph.order || ms(a.ev.release.utc) - ms(b.ev.release.utc); });
    var cur = live[0] || null;
    var nxt = live.filter(function (x) { return cur && x !== cur && ms(x.ev.release.utc) > ms(cur.ev.release.utc); })
      .sort(function (a, b) { return ms(a.ev.release.utc) - ms(b.ev.release.utc); })[0] || null;
    return { current: cur, next: nxt };
  }

  function quality(d, pageMarketAsOf, now) {
    if (!d) return { key: 'failed', label: '读取失败', judge: 'data_insufficient' };
    var age = (now - ms(d.generated_at)) / 3600000;
    var f = d.freshness || {};
    if (!(age >= 0) || age > (d.stale_after_hours || 36)) return { key: 'stale', label: '待更新（最后检查 ' + esc(d.generated_at) + '）', judge: 'data_insufficient' };
    if (pageMarketAsOf && f.market_as_of && f.market_as_of < pageMarketAsOf) return { key: 'stale', label: '待更新（分析截至 ' + esc(f.market_as_of) + '，行情已到 ' + esc(pageMarketAsOf) + '）', judge: 'data_insufficient' };
    if (f.data_stale) return { key: 'stale', label: '数据不足（输入过期）', judge: 'data_insufficient' };
    return { key: 'fresh', label: '数据截至 ' + esc(f.market_as_of), judge: (d.judgment || {}).key || 'data_insufficient' };
  }

  function lineHtml(d, sel, q) {
    var j = JUDGE[q.judge] || JUDGE.data_insufficient;
    var cur = sel.current, nxt = sel.next;
    var main = (d.lines || [])[0];
    return '<div class="mer-line"><b class="mer-title">宏观事件与分批观察</b>' +
      (cur ? '<span class="mer-event"><b>' + esc(cur.ev.name_zh) + '</b> ' + esc(cur.ph.label) + '</span>' : '<span class="mer-event">暂无待观察事件</span>') +
      '<span class="mer-judge ' + j[1] + '">' + j[0] + '</span>' +
      (q.judge === 'data_insufficient' ? '<span class="mer-text">' + esc(q.label) + '｜不据此判断</span>' :
        (main ? '<span class="mer-text">' + esc(main.text) + '</span>' : '')) +
      '<span class="mer-meta">' + esc(q.label) + '</span>' +
      (nxt ? '<span class="mer-meta mer-next">下一事件 ' + esc(nxt.ev.name_zh) + ' ' + esc(hm(nxt.ev)) + '</span>' : '') +
      '<button type="button" class="mer-toggle" aria-expanded="false">查看分析</button></div>';
  }

  function detailHtml(d, sel, now) {
    var src = d.source || {};
    var rows = (d.events || []).map(function (e) {
      var p = phase(e, now);
      var cp = e.checkpoints || {};
      return '<tr><td>' + esc(e.name_zh) + '</td><td>' + esc(e.release.et_label) + '</td><td>' + esc(e.release.beijing_label) + '</td><td>' +
        esc(p.label) + '</td><td>' + ['T-1', 'T', 'T+1', 'T+3', 'T+5', 'T+10'].map(function (k) {
          var due = ms(((e.windows || {}).t_plus || {})[k] || '');
          return esc(k) + ' ' + esc((cp[k] || '').slice(5)) + (k === 'T-1' || !due || now < due || !e.official_outcome ? '' : ' ✓');
        }).join(' · ') + '</td><td><small>' + esc(e.time_status) + '</small></td></tr>';
    }).join('');
    return '<div class="mer-detail" hidden>' +
      '<p class="mer-muted">MyAlpha 判断依据：按作者的分批规则做 Shadow 核验，并叠加 MyAlpha 自己的数据护栏；不是作者的预测。作者观点「' + esc(src.author_forecast) +
      '」。Shadow 研究提示，不是买卖指令；由你自行决定。Learning UNPROVEN。</p>' +
      '<h4>三批条件（作者规则 · MyAlpha 核验）</h4><ul>' + (d.lines || []).map(function (l) {
        return '<li><b>第' + esc(l.tranche) + '批</b> <span class="mer-st">' + esc(stz(l.state)) + '</span> ' + esc(l.text) + '</li>';
      }).join('') + '</ul>' +
      '<h4>风险暂停条件</h4><ul>' + ((d.risk_off || {}).conditions || []).map(function (c) {
        return '<li>' + esc(String(c.rule || '').replace(/^author:\s*/, '作者：')) + ' — <span class="mer-st">' + esc(stz(c.status)) + '</span></li>';
      }).join('') + '</ul>' +
      '<h4>事件时间表（美东 / 北京）</h4><div class="mer-table"><table><thead><tr><th>事件</th><th>美东</th><th>北京</th><th>阶段</th><th>检查点</th><th>时间来源</th></tr></thead><tbody>' +
      rows + '</tbody></table></div>' +
      '<p class="mer-meta">数据：行情 ' + esc((d.freshness || {}).market_as_of) + ' · 10Y ' + esc((d.freshness || {}).y10_as_of) + ' · 宽度 ' +
      esc((d.freshness || {}).breadth_as_of) + ' · 生成 ' + esc(d.generated_at) + ' · 规则 ' + esc(d.rules_version) + '</p>' +
      '<p class="mer-meta">来源：<a href="' + esc(src.url) + '" target="_blank" rel="noopener noreferrer">' + esc(src.author) + '《' + esc(src.title) +
      '》</a>（' + esc(src.reading_basis_zh || 'MyAlpha 未读到全文，依据 owner 提纲与 360 字摘录，partial') + '） · <a href="' + esc(src.analysis_url) + '" target="_blank" rel="noopener noreferrer">完整中文分析</a></p></div>';
  }

  function render(el, d, pageMarketAsOf, now) {
    now = now || Date.now();
    var q = quality(d, pageMarketAsOf, now);
    if (!d) {
      el.innerHTML = '<div class="mer-line"><b class="mer-title">宏观事件与分批观察</b><span class="mer-judge mer-warn">数据不足</span><span class="mer-text">事件分析读取失败｜不据此判断</span></div>';
      el.setAttribute('data-state', 'failed');
      return q;
    }
    var sel = pick(d.events, now);
    el.innerHTML = lineHtml(d, sel, q) + detailHtml(d, sel, now);
    el.setAttribute('data-state', q.key);
    el.setAttribute('data-judgment', q.judge);
    var btn = el.querySelector('.mer-toggle'), det = el.querySelector('.mer-detail');
    if (btn && det) btn.addEventListener('click', function () {
      var open = det.hasAttribute('hidden');
      if (open) det.removeAttribute('hidden'); else det.setAttribute('hidden', '');
      btn.setAttribute('aria-expanded', String(open)); btn.textContent = open ? '收起分析' : '查看分析';
    });
    return q;
  }

  function init() {
    if (typeof document === 'undefined' || typeof fetch !== 'function') return;
    var anchor = document.getElementById('autoResearchRow');
    if (!anchor || document.getElementById('macroEventRow')) return;
    var el = document.createElement('section');
    el.id = 'macroEventRow'; el.className = 'macro-event-row'; el.setAttribute('aria-label', '宏观事件与分批观察');
    anchor.parentNode.insertBefore(el, anchor.nextSibling);
    var page = anchor.getAttribute('data-market-as-of') || '';
    fetch('research/macro_event_watch.json?v=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) { render(el, d, page); })
      .catch(function () { render(el, null, page); });
  }

  root.MAVMacroEventRow = { _test: { phase: phase, pick: pick, quality: quality, render: render, esc: esc } };
  if (typeof document !== 'undefined' && document.addEventListener) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
