(function (global) {
  'use strict';

  const VISITOR_KEY = 'mavAnonymousVisitor';
  const VISIT_DAY_KEY = 'mavVisitRecordedDay';

  function client() { return global.mavSupabase || null; }
  function dayKey() { return new Date().toISOString().slice(0, 10); }
  function deviceClass() {
    const width = Math.max(document.documentElement.clientWidth || 0, global.innerWidth || 0);
    return width < 700 ? 'mobile' : (width < 1100 ? 'tablet' : 'desktop');
  }
  function visitorToken() {
    let value = localStorage.getItem(VISITOR_KEY);
    if (!value) {
      value = global.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      localStorage.setItem(VISITOR_KEY, value);
    }
    return value;
  }
  async function sha256(value) {
    const bytes = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  }
  function referrerHost() {
    try { return document.referrer ? new URL(document.referrer).hostname.slice(0, 160) : ''; }
    catch (_error) { return ''; }
  }
  async function recordVisit() {
    const sb = client();
    if (!sb || localStorage.getItem(VISIT_DAY_KEY) === dayKey()) return;
    try {
      const visitorHash = await sha256(`${location.origin}|${visitorToken()}`);
      const { error } = await sb.rpc('record_site_visit_v36', {
        p_visitor_hash: visitorHash,
        p_path: location.pathname.slice(0, 220),
        p_referrer_host: referrerHost(),
        p_device: deviceClass()
      });
      if (!error) localStorage.setItem(VISIT_DAY_KEY, dayKey());
    } catch (_error) { /* 统计不可用不影响看板。 */ }
  }
  async function getSummary(days) {
    const { data, error } = await client().rpc('get_site_visit_summary_v36', { p_days: days });
    if (error) throw error;
    return Array.isArray(data) ? data[0] : data;
  }
  function number(value) { return Number(value || 0).toLocaleString('zh-CN'); }
  async function renderSummary() {
    const root = document.getElementById('siteAnalyticsRoot');
    if (!root || !client()) return;
    try {
      const [week, month] = await Promise.all([getSummary(7), getSummary(30)]);
      const last = month?.last_visit ? new Date(month.last_visit).toLocaleString('zh-CN') : '暂无记录';
      root.innerHTML = `<div class="site-analytics-grid">
        <div class="site-analytics-card"><span>近7日访问</span><strong>${number(week?.total_views)}</strong></div>
        <div class="site-analytics-card"><span>近30日访问</span><strong>${number(month?.total_views)}</strong></div>
        <div class="site-analytics-card"><span>近30日匿名浏览器</span><strong>${number(month?.unique_visitors)}</strong></div>
      </div><div class="site-analytics-note">最近访问：${last}。同一浏览器每天只计一次；无法据此确认访问者真实身份。</div>`;
    } catch (error) {
      root.innerHTML = `<div class="site-analytics-empty">访问统计尚未启用。请先执行 V3.6.0 的 Supabase SQL：${String(error.message || error)}</div>`;
    }
  }
  function onAuth(_session, authorized) { if (authorized) renderSummary(); }

  global.SiteAnalytics = { onAuth, recordVisit, renderSummary };
  global.addEventListener('load', recordVisit);
})(window);
