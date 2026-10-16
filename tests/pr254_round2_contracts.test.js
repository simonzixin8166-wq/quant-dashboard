const assert = require('assert');

// 1. Test Thesis count formatting logic (0 / null / undefined / positive)
function formatThesisDetail(s) {
  const autoCount = s.autoEvidenceCount ?? 0;
  return s.loaded
    ? `${s.count} 只已载入 · ${s.researchCount > 0 ? `私有 Thesis ${s.researchCount}/${s.count}` : `官方/事件证据草稿 ${autoCount}/${s.count}`}`
    : '等待登录后载入';
}

// Thesis Count Test Cases
{
  // Case A: 0 autoEvidenceCount (must not fall back to s.count)
  const res0 = formatThesisDetail({ loaded: true, count: 26, researchCount: 0, autoEvidenceCount: 0 });
  assert.strictEqual(res0, '26 只已载入 · 官方/事件证据草稿 0/26');

  // Case B: null autoEvidenceCount
  const resNull = formatThesisDetail({ loaded: true, count: 26, researchCount: 0, autoEvidenceCount: null });
  assert.strictEqual(resNull, '26 只已载入 · 官方/事件证据草稿 0/26');

  // Case C: undefined (missing) autoEvidenceCount
  const resMissing = formatThesisDetail({ loaded: true, count: 26, researchCount: 0 });
  assert.strictEqual(resMissing, '26 只已载入 · 官方/事件证据草稿 0/26');

  // Case D: positive autoEvidenceCount
  const resPos = formatThesisDetail({ loaded: true, count: 26, researchCount: 0, autoEvidenceCount: 15 });
  assert.strictEqual(resPos, '26 只已载入 · 官方/事件证据草稿 15/26');

  // Case E: Positive private researchCount
  const resPrivate = formatThesisDetail({ loaded: true, count: 26, researchCount: 4, autoEvidenceCount: 15 });
  assert.strictEqual(resPrivate, '26 只已载入 · 私有 Thesis 4/26');
}

console.log('PASS: Thesis count formatting contract (0 / null / undefined / positive)');

// 2. Test Option Status Tone Logic (0 / partial / all usable, post-refresh recalculation)
function computeOptionAutoStatus(usableCount, totalPositions, sessionOpen) {
  if (sessionOpen) {
    if (usableCount === totalPositions && totalPositions > 0) return { tone: 'good', label: `实时报价 ${usableCount}/${totalPositions}` };
    if (usableCount > 0) return { tone: 'warn', label: `部分实时 ${usableCount}/${totalPositions}` };
    return { tone: 'bad', label: `无有效报价 ${usableCount}/${totalPositions}` };
  } else {
    if (usableCount === totalPositions && totalPositions > 0) return { tone: 'good', label: `休市参考报价 ${usableCount}/${totalPositions}` };
    if (usableCount > 0) return { tone: 'warn', label: `休市部分参考 ${usableCount}/${totalPositions}` };
    return { tone: 'bad', label: `休市无有效报价 ${usableCount}/${totalPositions}` };
  }
}

{
  // 0 usable quotes: tone MUST be bad
  const s0_open = computeOptionAutoStatus(0, 3, true);
  assert.strictEqual(s0_open.tone, 'bad');

  const s0_closed = computeOptionAutoStatus(0, 3, false);
  assert.strictEqual(s0_closed.tone, 'bad');

  // Partial usable quotes (1/3 or 2/3): tone MUST be warn
  const sPart_open = computeOptionAutoStatus(1, 3, true);
  assert.strictEqual(sPart_open.tone, 'warn');

  const sPart_closed = computeOptionAutoStatus(2, 3, false);
  assert.strictEqual(sPart_closed.tone, 'warn');

  // All usable quotes (3/3): tone IS good
  const sAll_open = computeOptionAutoStatus(3, 3, true);
  assert.strictEqual(sAll_open.tone, 'good');

  const sAll_closed = computeOptionAutoStatus(3, 3, false);
  assert.strictEqual(sAll_closed.tone, 'good');
}

console.log('PASS: Option auto-status tone contract (0 / partial / all usable quotes)');
