// #133 6109957428 P0-2: CDN libraries missing → inert stubs, no ReferenceError, nothing written.
const assert = require('assert');
const vm = require('vm');
const fs = require('fs');
const src = f => fs.readFileSync(__dirname + '/../docs/assets/' + f, 'utf8');

function sandbox(preload) {
  const written = []; const appended = [];
  const body = { appendChild: n => appended.push(n) };
  const doc = { body, getElementById: () => null, write: s => written.push(s),
    createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, remove() {} }), addEventListener() {} };
  const win = Object.assign({ document: doc, console: { warn() {} }, Promise, Proxy }, preload || {});
  win.window = win; vm.createContext(win);
  return { win, written, appended };
}

// 1) both libraries missing
{
  const { win, written, appended } = sandbox();
  vm.runInContext(src('vendor-fallback.js'), win);
  assert.strictEqual(written.length, 2, 'one unpkg retry per missing library');
  assert(written.every(w => w.includes('https://unpkg.com/') && w.includes('integrity="sha384-') && w.includes('crossorigin="anonymous"')));
  assert(written[0].includes('chart.js@4.5.1/') && written[1].includes('supabase-js@2.117.3/'), 'same exact versions on fallback');
  vm.runInContext(src('vendor-guard.js'), win);
  assert.deepStrictEqual(Array.from(win.MAV_VENDOR.degraded), ['chart', 'supabase']);
  assert.strictEqual(appended.length, 1, 'one visible notice');
  // Chart stub behaves like a Chart for the calls the site makes
  const canvas = { width: 300, height: 150, getContext: () => ({ clearRect() {}, fillText() {} }) };
  const c = new win.Chart(canvas, { type: 'line', data: { labels: [1], datasets: [] } });
  assert(c.__mavStub); c.update(); c.destroy();
  // supabase stub: chained query resolves to an error, no session, no write
  const client = win.supabase.createClient('https://x', 'k');
  vm.runInContext('void 0', win);
  (async () => {
    const r = await client.from('stock_targets').select('*').eq('symbol', 'ZZA').order('x');
    assert.strictEqual(r.data, null); assert.strictEqual(r.error.code, 'MAV_VENDOR_UNAVAILABLE');
    const u = await client.from('options_positions').update({ a: 1 }).eq('id', 1);
    assert(u.error, 'writes fail closed');
    const s = await client.auth.getSession(); assert.strictEqual(s.data.session, null);
    const o = await client.auth.signInWithOtp({ email: 'a@b.c' }); assert(o.error, 'login reports unavailable');
    const sub = client.auth.onAuthStateChange(() => {}); sub.data.subscription.unsubscribe();
    const rpc = await client.rpc('fn', {}); assert(rpc.error);
    console.log('vendor_guard.test.js OK');
  })().catch(e => { console.error(e); process.exit(1); });
}

// 2) both libraries present → no retry, no stub, no notice
{
  const real = { Chart: function RealChart() {}, supabase: { createClient: () => ({ real: true }) } };
  const { win, written, appended } = sandbox(real);
  vm.runInContext(src('vendor-fallback.js'), win);
  vm.runInContext(src('vendor-guard.js'), win);
  assert.strictEqual(written.length, 0); assert.strictEqual(appended.length, 0);
  assert.strictEqual(win.Chart, real.Chart); assert(win.supabase.createClient().real);
  assert.deepStrictEqual(Array.from(win.MAV_VENDOR.degraded), []);
}
