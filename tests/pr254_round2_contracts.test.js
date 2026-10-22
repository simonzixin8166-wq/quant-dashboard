const assert = require('assert');

// Require the actual assets
require('../docs/assets/options-v2.js');
require('../docs/assets/product-intelligence.js');

const optTest = (globalThis.OptionV2 && globalThis.OptionV2._test) || (globalThis.MAVOptions && globalThis.MAVOptions._test);
const piTest = globalThis.MAVProductIntelligence && globalThis.MAVProductIntelligence._test;

assert(optTest && typeof optTest.autoStatusTone === 'function', 'autoStatusTone must be exported under _test in options-v2.js');
assert(piTest && typeof piTest.thesisDetail === 'function', 'thesisDetail must be exported under _test in product-intelligence.js');

// Test autoStatusTone exported function directly
assert.strictEqual(optTest.autoStatusTone(0, 3, true), 'bad', '0 usable quotes must return bad');
assert.strictEqual(optTest.autoStatusTone(0, 3, false), 'bad', '0 usable quotes on closed market must return bad');

assert.strictEqual(optTest.autoStatusTone(1, 3, true), 'warn', 'Partial usable quotes (1/3) must return warn');
assert.strictEqual(optTest.autoStatusTone(2, 3, false), 'warn', 'Partial usable quotes (2/3) on closed market must return warn');

assert.strictEqual(optTest.autoStatusTone(3, 3, true), 'good', 'All usable quotes (3/3) must return good');
assert.strictEqual(optTest.autoStatusTone(3, 3, false), 'good', 'All usable quotes (3/3) on closed market must return good');

// Test thesisDetail exported function directly
assert.strictEqual(
  piTest.thesisDetail({ loaded: true, count: 26, researchCount: 0, autoEvidenceCount: 0 }),
  '26 只已载入 · 官方/事件证据草稿 0/26',
  '0 autoEvidenceCount must render 0/26 without fallback'
);

assert.strictEqual(
  piTest.thesisDetail({ loaded: true, count: 26, researchCount: 0, autoEvidenceCount: null }),
  '26 只已载入 · 官方/事件证据草稿 0/26',
  'null autoEvidenceCount must render 0/26'
);

assert.strictEqual(
  piTest.thesisDetail({ loaded: true, count: 26, researchCount: 0 }),
  '26 只已载入 · 官方/事件证据草稿 0/26',
  'missing autoEvidenceCount must render 0/26'
);

assert.strictEqual(
  piTest.thesisDetail({ loaded: true, count: 26, researchCount: 0, autoEvidenceCount: 15 }),
  '26 只已载入 · 官方/事件证据草稿 15/26',
  'positive autoEvidenceCount must render 15/26'
);

assert.strictEqual(
  piTest.thesisDetail({ loaded: true, count: 26, researchCount: 4, autoEvidenceCount: 15 }),
  '26 只已载入 · 私有 Thesis 4/26',
  'positive private researchCount must take precedence over auto draft'
);

console.log('pr254_round2_contracts.test.js OK');
