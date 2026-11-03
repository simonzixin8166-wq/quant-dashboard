// US close is 16:00 America/New_York: 20:00Z in EDT, 21:00Z in EST (DST ends 2026-11-01). The research row's
// "pending" window and option DTE use the DST-aware close instead of a fixed 20:00Z (11/2 onwards was off by 1 h).
const fs = require('fs'), vm = require('vm'), assert = require('assert');
// auto-research-row: same pending/stale verdict around the close in both seasons
require('../docs/assets/auto-research-row.js');
const api = globalThis.MAVAutoResearchRow._test;
const d = { latest_session: '2026-10-29' };
// EDT session 10/30: close 20:00Z -> 20:30Z is inside the window
assert.strictEqual(api.computeState(d, '2026-10-30', new Date('2026-10-30T20:30:00Z')).key, 'pending');
// EST session 11/02: close 21:00Z
const est = api.computeState({ latest_session: '2026-10-30' }, '2026-11-02', new Date('2026-11-02T21:30:00Z'));
assert.strictEqual(est.key, 'pending');
// 18 h after the EST close (21:00Z + 18 h = 15:00Z next day) -> stale; 17.5 h -> still pending
assert.strictEqual(api.computeState({ latest_session: '2026-10-30' }, '2026-11-02', new Date('2026-11-03T14:30:00Z')).key, 'pending');
assert.strictEqual(api.computeState({ latest_session: '2026-10-30' }, '2026-11-02', new Date('2026-11-03T15:30:00Z')).key, 'stale');
// source no longer hard-codes 20:00Z for the close
for (const f of ['auto-research-row.js', 'autonomous-agent.js', 'opportunity-radar.js']) {
  const src = fs.readFileSync(__dirname + '/../docs/assets/' + f, 'utf8');
  assert(!/T20:00:00Z'\)|T20:00:00Z`\)/.test(src.replace(/usCloseMs[\s\S]*?\};?\n/, '')), f + ' still uses a fixed 20:00Z close');
  assert(src.includes('America/New_York'), f + ' uses the New York close');
}
console.log('PASS US close DST-aware (EDT 20:00Z / EST 21:00Z) in research row window and option DTE');
