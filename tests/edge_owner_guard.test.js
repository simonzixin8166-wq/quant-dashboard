// SEC-01 (#133): options-market / stock-market are owner-only (sign-up stays open). Runs the exact guard block from
// both functions (its few type annotations stripped; CI runs Node 20) with a mocked Deno.env, and checks it runs before any Alpaca work.
const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert'), { execFileSync } = require('child_process');
const b64 = o => Buffer.from(JSON.stringify(o)).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const jwt = claims => `${b64({ alg: 'HS256' })}.${b64(claims)}.sig`;
for (const fn of ['options-market', 'stock-market']) {
  const src = fs.readFileSync(`supabase/functions/${fn}/index.ts`, 'utf8');
  const m = src.match(/\/\/ owner-guard:start[\s\S]*?\/\/ owner-guard:end/);
  assert(m, `${fn}: owner guard block missing`);
  // the 403 check sits inside the handler, after the method check and before Alpaca credentials / cache / fetch
  const handler = src.slice(src.indexOf('serve(async'));
  const gate = handler.indexOf('if (!callerAllowed(');
  const later = ['ALPACA', 'emoryCache.get', 'cache.get', 'Promise.all', 'await '].map(t => handler.indexOf(t)).filter(i => i >= 0);
  assert(gate > 0 && later.length >= 2 && later.every(i => gate < i), `${fn}: guard must run before any upstream work`);
  assert(/OWNER_ONLY'?\s*}\s*,\s*403\)/.test(handler.slice(gate, gate + 200)), `${fn}: non-owner gets 403`);
  const cases = {
    owner: jwt({ role: 'authenticated', email: 'XXJ8166@gmail.com' }),
    stranger: jwt({ role: 'authenticated', email: 'someone@example.com' }),
    service: jwt({ role: 'service_role' }),
    anon: jwt({ role: 'anon' }),
    rawService: 'raw-service-key',
    garbage: 'not-a-jwt',
    none: '',
  };
  const js = m[0].replace(/\)\s*:\s*(?:Record<string, unknown> \| null|boolean)\s*\{/g, ') {').replace(/\((\w+)\s*:\s*(?:string|Request)\)/g, '($1)');
  assert(!/:\s*(string|Request|boolean)\b/.test(js.replace(/\/\/.*$/gm, '')), `${fn}: unexpected type annotation left in guard`);
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'guard-')), 'g.js');
  fs.writeFileSync(file, `const Deno = { env: { get: (k) => k === 'SUPABASE_SERVICE_ROLE_KEY' ? 'raw-service-key' : undefined } };
${js}
const cases = ${JSON.stringify(cases)};
const out = {};
for (const [k, t] of Object.entries(cases)) out[k] = callerAllowed(new Request('https://x/', { headers: t ? { authorization: 'Bearer ' + t } : {} }));
console.log(JSON.stringify(out));`);
  const out = JSON.parse(execFileSync(process.execPath, [file], { encoding: 'utf8' }).trim());
  assert.deepStrictEqual(out, { owner: true, stranger: false, service: true, anon: false, rawService: true, garbage: false, none: false }, `${fn}: ${JSON.stringify(out)}`);
}
console.log('PASS edge owner guard: owner/service allowed; other accounts, anon and malformed tokens get 403 before any Alpaca call');
