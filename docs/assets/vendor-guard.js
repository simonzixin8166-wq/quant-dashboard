/* MyAlpha vendor guard (#133 6109957428 P0-2).
 * Runs after vendor-fallback.js. When Chart.js or supabase-js is still missing, install inert stand-ins so the
 * page never throws 'Chart is not defined' / 'supabaseClient is not defined':
 *  - Chart stub draws "图表暂不可用" on the canvas; update/destroy/resize are no-ops.
 *  - supabase stub: no session, every query resolves to {data:null, error:{message}} — nothing is written,
 *    login shows as unavailable. Private data is never touched by the stub.
 * A small, dismissible notice tells the visitor which part is degraded. Status: window.MAV_VENDOR. */
(function () {
  var V = window.MAV_VENDOR || {};
  var MSG = { chart: '图表组件暂不可用', supabase: '登录 / 私有数据服务暂不可用' };
  var degraded = [];

  function chartStub() {
    function StubChart(item, config) {
      this.config = config || {}; this.data = (config && config.data) || { labels: [], datasets: [] };
      this.options = (config && config.options) || {}; this.__mavStub = true;
      var c = item && item.canvas ? item.canvas : item;
      if (c && typeof c === 'string') c = document.getElementById(c);
      if (c && c.getContext) {
        try {
          var ctx = c.getContext('2d'); var w = c.width || c.clientWidth || 300, h = c.height || c.clientHeight || 150;
          ctx.clearRect(0, 0, w, h); ctx.fillStyle = '#696d76'; ctx.font = '13px sans-serif'; ctx.textAlign = 'center';
          ctx.fillText('图表暂不可用（图表库未加载）', w / 2, h / 2);
        } catch (e) { /* canvas unavailable: stay silent */ }
      }
      this.canvas = c || null;
    }
    ['update', 'destroy', 'resize', 'render', 'stop', 'reset', 'clear'].forEach(function (m) {
      StubChart.prototype[m] = function () { return this; };
    });
    StubChart.prototype.toBase64Image = function () { return ''; };
    StubChart.register = function () {}; StubChart.unregister = function () {};
    StubChart.defaults = { plugins: {}, scales: {}, font: {} }; StubChart.instances = {}; StubChart.__mavStub = true;
    StubChart.getChart = function () { return undefined; };
    return StubChart;
  }

  function supabaseStub() {
    var err = { message: MSG.supabase + '（supabase-js 未加载）', code: 'MAV_VENDOR_UNAVAILABLE' };
    var result = { data: null, error: err, count: null, status: 0 };
    function query() {
      var q = new Proxy(function () {}, {
        get: function (_t, prop) {
          if (prop === 'then') return function (ok, bad) { return Promise.resolve(result).then(ok, bad); };
          if (prop === 'catch') return function (f) { return Promise.resolve(result).catch(f); };
          if (prop === 'finally') return function (f) { return Promise.resolve(result).finally(f); };
          return function () { return q; };
        },
        apply: function () { return q; }
      });
      return q;
    }
    var noSession = function () { return Promise.resolve({ data: { session: null, user: null }, error: null }); };
    var denied = function () { return Promise.resolve({ data: { session: null, user: null }, error: err }); };
    var client = {
      __mavStub: true,
      from: query, rpc: query, schema: function () { return client; },
      channel: function () { return { on: function () { return this; }, subscribe: function () { return this; }, unsubscribe: function () {} }; },
      removeChannel: function () { return Promise.resolve('ok'); },
      storage: { from: query },
      functions: { invoke: function () { return Promise.resolve(result); } },
      auth: {
        getSession: noSession, getUser: noSession, refreshSession: noSession,
        signInWithOtp: denied, signInWithPassword: denied, signInWithOAuth: denied, signUp: denied,
        signOut: function () { return Promise.resolve({ error: null }); },
        onAuthStateChange: function () { return { data: { subscription: { unsubscribe: function () {} } } }; }
      }
    };
    return { createClient: function () { return client; }, __mavStub: true };
  }

  if (!window.Chart) { window.Chart = chartStub(); degraded.push('chart'); }
  if (!window.supabase || typeof window.supabase.createClient !== 'function') { window.supabase = supabaseStub(); degraded.push('supabase'); }
  Object.keys(V).forEach(function (k) { V[k].loaded = degraded.indexOf(k) < 0; V[k].stubbed = degraded.indexOf(k) >= 0; });
  V.degraded = degraded;

  if (!degraded.length) return;
  try { console.warn('[MyAlpha vendor] degraded:', degraded.join(','), V); } catch (e) {}
  function notice() {
    if (document.getElementById('mavVendorNotice')) return;
    var d = document.createElement('div');
    d.id = 'mavVendorNotice'; d.setAttribute('role', 'status');
    var bottom = (window.innerWidth || 1024) <= 760 ? 'calc(env(safe-area-inset-bottom, 0px) + 92px)' : '12px'; // clear the mobile bottom nav
    d.style.cssText = 'position:fixed;left:12px;right:12px;bottom:' + bottom + ';z-index:9999;max-width:560px;margin:0 auto;' +
      'background:#fff8e6;color:#5c4400;border:1px solid #e8c66a;border-radius:10px;padding:10px 36px 10px 12px;' +
      'font:13px/1.5 sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.12)';
    d.textContent = degraded.map(function (k) { return MSG[k]; }).join('；') +
      '。其余内容（研究、黄金/定投提醒）正常显示，刷新页面可重试。';
    var x = document.createElement('button');
    x.type = 'button'; x.setAttribute('aria-label', '关闭'); x.textContent = '×';
    x.style.cssText = 'position:absolute;right:8px;top:6px;border:0;background:none;font-size:18px;cursor:pointer;color:inherit';
    x.onclick = function () { d.remove(); };
    d.appendChild(x); document.body.appendChild(d);
  }
  if (document.body) notice(); else document.addEventListener('DOMContentLoaded', notice);
})();
