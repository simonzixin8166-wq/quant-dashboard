/* MyAlpha 市场温度 (#133 2026-10-17): compact gauge in the cockpit header, details on click.
   MyAlpha's own descriptive measure built from existing data — not the CNN index, not a forecast. */
(function (global) {
  'use strict';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const TONE = { '极度恐惧': 'mt-xfear', '恐惧': 'mt-fear', '中性': 'mt-neutral', '贪婪': 'mt-greed', '极度贪婪': 'mt-xgreed' };

  function arc(score) {
    // half-circle gauge, 0 at the left, 100 at the right
    const a = Math.PI * (1 - Math.max(0, Math.min(100, score)) / 100);
    const x = 50 + 40 * Math.cos(a), y = 50 - 40 * Math.sin(a);
    return `<svg viewBox="0 0 100 56" class="mt-gauge" aria-hidden="true"><path d="M10 50 A40 40 0 0 1 90 50" class="mt-track"/><path d="M10 50 A40 40 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}" class="mt-fill"/></svg>`;
  }

  function changeText(d) {
    if (!d.change_vs) return '首日记录，暂无比较';
    const v = d.change_vs.delta;
    return `${v > 0 ? '升温' : v < 0 ? '降温' : '持平'} ${v > 0 ? '+' : ''}${v}（对比 ${esc(d.change_vs.as_of)}）`;
  }

  function html(d) {
    if (!d || d.status !== 'ok' || d.score === null || d.score === undefined) {
      return `<div class="mt-card mt-na"><span class="mt-k">市场温度</span><b>不可用</b><small>可用数据不足 ${esc(d?.components_available ?? 0)}/6</small></div>`;
    }
    const rows = (d.components || []).map(c => c.status === 'ok'
      ? `<li><span>${esc(c.name)}</span><b>${esc(c.score)}</b><small>${esc(c.as_of || '')}</small></li>`
      : `<li class="mt-off"><span>${esc(c.name)}</span><b>不可用</b><small>${esc(c.reason || '')}</small></li>`).join('');
    return `<details class="mt-card ${TONE[d.label] || ''}"><summary><span class="mt-k">市场温度</span>${arc(d.score)}<b class="mt-score">${esc(Math.round(d.score))}</b><span class="mt-label">${esc(d.label)}</span><small>${esc(changeText(d))}</small></summary>
      <div class="mt-body"><ul>${rows}</ul><p>0–100，越高代表市场越偏向冒险。由 ${esc(d.components_available)}/6 项现有数据合成，数据截至 ${esc(d.as_of)}。这是 MyAlpha 自己的描述性指标，不是 CNN 指数，也不预测涨跌。</p><a href="${esc(d.cnn_link)}" target="_blank" rel="noopener noreferrer">CNN 恐惧与贪婪指数（官方）↗</a></div></details>`;
  }

  const CSS = `.mt-card{border:1px solid var(--line,#e3e8ef);border-radius:12px;background:var(--card,#fff);padding:8px 12px;min-width:150px;font-size:12px}
.mt-card summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:auto auto;align-items:center;gap:0 8px}
.mt-card summary::-webkit-details-marker{display:none}
.mt-k{grid-column:1/-1;color:var(--muted,#6b7280);font-size:11px;letter-spacing:.04em}
.mt-gauge{width:58px;height:33px}.mt-track{fill:none;stroke:var(--line,#e3e8ef);stroke-width:9}.mt-fill{fill:none;stroke:currentColor;stroke-width:9;stroke-linecap:round}
.mt-score{font-size:22px;line-height:1;font-variant-numeric:tabular-nums}.mt-label{grid-column:1/-1;font-weight:700}
.mt-card small{grid-column:1/-1;color:var(--muted,#6b7280)}
.mt-xfear{color:#b42318}.mt-fear{color:#c2410c}.mt-neutral{color:#6b7280}.mt-greed{color:#15803d}.mt-xgreed{color:#166534}
.mt-body{color:var(--text,#18212f);margin-top:8px;min-width:240px}.mt-body ul{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.mt-body li{display:grid;grid-template-columns:1fr auto;gap:0 8px}.mt-body li small{grid-column:1/-1}.mt-body li.mt-off b{color:var(--muted,#6b7280)}
.mt-body p{margin:8px 0 4px;line-height:1.5;color:var(--muted,#6b7280)}.mt-na b{display:block;font-size:14px}`;

  function inject() {
    if (typeof document === 'undefined' || document.getElementById('mt-style')) return;
    const s = document.createElement('style'); s.id = 'mt-style'; s.textContent = CSS; document.head.appendChild(s);
  }

  async function load() {
    const root = typeof document !== 'undefined' && document.getElementById('marketTemperatureRoot');
    if (!root) return;
    inject();
    try {
      const r = await fetch('research/market_temperature.json?v=' + Date.now(), { cache: 'no-store' });
      root.innerHTML = html(r.ok ? await r.json() : null);
    } catch (e) {
      root.innerHTML = html(null);
    }
  }

  global.MAVMarketTemperature = { html, load, _test: { arc, changeText } };
  if (typeof module !== 'undefined' && module.exports) module.exports = global.MAVMarketTemperature;
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
  }
})(typeof window !== 'undefined' ? window : globalThis);
