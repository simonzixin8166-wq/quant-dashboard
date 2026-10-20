/* MyAlpha 市场温度 (#133 2026-10-17): compact gauge in the cockpit header, details on click.
   MyAlpha's own descriptive measure built from existing data — not the CNN index, not a forecast. */
(function (global) {
  'use strict';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const TONE = { '极度恐惧': 'mt-xfear', '恐惧': 'mt-fear', '中性': 'mt-neutral', '贪婪': 'mt-greed', '极度贪婪': 'mt-xgreed' };

  // zone bands match scripts/market_temperature.py BANDS: <25 / <45 / <56 / <76 / ≥76
  const ZONES = [[0, 25, '极度恐惧'], [25, 45, '恐惧'], [45, 56, '中性'], [56, 76, '贪婪'], [76, 100, '极度贪婪']];
  const CX = 160, CY = 150, R = 104;
  const pt = (v, r) => { const a = Math.PI * (1 - Math.max(0, Math.min(100, v)) / 100); return [CX + r * Math.cos(a), CY - r * Math.sin(a)]; };
  const f1 = n => n.toFixed(1);

  function gauge(score) {
    const [x0, y0] = pt(0, R), [x1, y1] = pt(100, R);
    let ticks = '';
    for (let v = 0; v <= 100; v += 5) {
      const major = v % 25 === 0, [a, b] = pt(v, R + 14), [c, d] = pt(v, R + (major ? 24 : 19));
      ticks += `<line x1="${f1(a)}" y1="${f1(b)}" x2="${f1(c)}" y2="${f1(d)}" class="${major ? 'mt-tick-major' : 'mt-tick'}"/>`;
      if (major) { const [tx, ty] = pt(v, R + 36); ticks += `<text x="${f1(tx)}" y="${f1(ty + 4)}" class="mt-num" text-anchor="middle">${v}</text>`; }
    }
    const zones = ZONES.map(([lo, hi, name]) => { const [tx, ty] = pt((lo + hi) / 2, R + 58); return `<text x="${f1(tx)}" y="${f1(ty + 4)}" class="mt-zone" text-anchor="middle">${name}</text>`; }).join('');
    const [nx, ny] = pt(score, R - 26);
    return `<svg viewBox="0 0 320 170" class="mt-gauge" role="img" aria-label="市场温度 ${esc(Math.round(score))}">
      <defs><linearGradient id="mtGrad" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#a8503d"/><stop offset=".5" stop-color="#c49a45"/><stop offset="1" stop-color="#5d7a4c"/></linearGradient></defs>
      <path d="M${f1(x0)} ${f1(y0)} A${R} ${R} 0 0 1 ${f1(x1)} ${f1(y1)}" class="mt-arc"/>${ticks}${zones}
      <line x1="${CX}" y1="${CY}" x2="${f1(nx)}" y2="${f1(ny)}" class="mt-needle"/><circle cx="${f1(nx)}" cy="${f1(ny)}" r="6" class="mt-needle-dot"/></svg>`;
  }

  function changeText(d) {
    if (!d.change_vs) return '首日记录，暂无比较';
    const v = d.change_vs.delta;
    return `${v > 0 ? '升温' : v < 0 ? '降温' : '持平'} ${v > 0 ? '+' : ''}${v}（对比 ${esc(d.change_vs.as_of)}）`;
  }

  function trendWord(d) {
    const v = d.change_vs ? d.change_vs.delta : null, fearSide = d.score < 45, greedSide = d.score >= 56;
    if (v === null || Math.abs(v) < 2) return '基本持平';  // integer readings: a 1-point move is noise
    if (fearSide) return v > 0 ? '正在缓和' : '正在加剧';
    if (greedSide) return v > 0 ? '正在升温' : '正在降温';
    return v > 0 ? '偏向乐观' : '偏向谨慎';
  }

  function fromTo(d) {
    if (!d.change_vs) return `今日 ${esc(Math.round(d.score))}（首日记录）`;
    const prev = d.score - d.change_vs.delta, v = d.change_vs.delta;
    return `${esc(String(d.change_vs.as_of).slice(5).replace('-', '/'))} ${esc(Math.round(prev))} → 今日 ${esc(Math.round(d.score))}（${v > 0 ? '+' : ''}${esc(v)}）`;
  }

  function drivers(d) {
    const ok = (d.components || []).filter(c => c.status === 'ok' && typeof c.score === 'number');
    if (ok.length < 2 || (d.score >= 45 && d.score < 56)) return '各项读数大体均衡。';
    const sorted = ok.slice().sort((a, b) => a.score - b.score), two = d.score < 45 ? sorted.slice(0, 2) : sorted.slice(-2).reverse();
    return `${two.map(c => esc(c.name)).join('与')}${d.score < 45 ? '仍在拖累市场情绪' : '正在推升市场情绪'}。`;
  }

  // one descriptive sentence contrasting the broad reading with VIX (taken from this artifact's own volatility input)
  function vsVix(d) {
    const vol = (d.components || []).find(c => c.key === 'volatility' && c.status === 'ok');
    const vix = vol && vol.value && typeof vol.value.vix === 'number' ? vol.value.vix : null;
    if (vix === null) return '';
    let t;
    if (d.score < 45 && vix < 20) t = '情绪偏弱，但期权市场尚未恐慌，更像回调或板块轮动';
    else if (d.score < 45) t = '情绪与波动率同时走弱，避险较为普遍';
    else if (d.score >= 56 && vix < 15) t = '情绪偏乐观且波动很低，留意过度乐观';
    else if (d.score >= 56 && vix >= 20) t = '情绪偏乐观但波动率偏高，分歧较大';
    else t = '两者读数大致一致';
    return `<span class="mt-vs">对照 VIX ${esc(vix.toFixed(2))}：${t}（描述，不是信号）</span>`;
  }

  function html(d) {
    if (!d || d.status !== 'ok' || d.score === null || d.score === undefined) {
      return `<div class="mt-card mt-na"><span class="mt-k">市场温度</span><b>不可用</b><small>可用数据不足 ${esc(d?.components_available ?? 0)}/6</small></div>`;
    }
    const rows = (d.components || []).map(c => c.status === 'ok'
      ? `<li><span>${esc(c.name)}</span><b>${esc(c.score)}</b><small>${esc(c.as_of || '')} · ${c.method === 'percentile_252' ? '与过去一年比' : '固定标尺（历史不足一年）'}</small></li>`
      : `<li class="mt-off"><span>${esc(c.name)}</span><b>不可用</b><small>${esc(c.reason || '')}</small></li>`).join('');
    return `<details class="mt-card ${TONE[d.label] || ''}"><summary><span class="mt-k">市场温度</span>${gauge(d.score)}
      <b class="mt-score">${esc(Math.round(d.score))}</b><span class="mt-label">${esc(d.label)}，${trendWord(d)}</span>
      <span class="mt-fromto">${fromTo(d)}</span><span class="mt-why">${drivers(d)}</span>${vsVix(d)}<span class="mt-more">查看 6 项分解 ▾</span></summary>
      <div class="mt-body"><ul>${rows}</ul><p>0–100，越高代表市场越偏向冒险；每项看今天在过去一年里有多反常。${esc(changeText(d))}。由 ${esc(d.components_available)}/6 项现有数据合成${d.fixed_scale_components ? `（其中 ${esc(d.fixed_scale_components)} 项历史不足一年，暂用固定标尺，结果只作粗略参考）` : ''}，数据截至 ${esc(d.as_of)}；落后超过 2 个交易日的数据不计入。这是 MyAlpha 自己的描述性指标，不是 CNN 指数，也不预测涨跌。</p><a href="${esc(d.cnn_link)}" target="_blank" rel="noopener noreferrer">CNN 恐惧与贪婪指数（官方）↗</a></div></details>`;
  }

  const CSS = `.mt-root{min-width:0}
/* 市场简报 row: VIX and 市场温度 side by side so the two readings can be compared at a glance */
.research-shell{grid-template-columns:minmax(0,1fr) minmax(0,600px)!important}
.brief-gauges{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;align-items:stretch}
.brief-gauges .brief-vix{max-width:none!important}.brief-gauges .brief-vix .metric-card,.brief-gauges .mt-card{height:100%;box-sizing:border-box}
.brief-gauges .mt-card{width:100%;border-radius:18px;padding:16px 18px}
@media (max-width:1180px){.research-shell{grid-template-columns:1fr!important}}
@media (max-width:620px){.brief-gauges{grid-template-columns:1fr}}
.mt-card{border:1px solid var(--line,#e3e8ef);border-radius:14px;background:var(--card,#fff);padding:10px 14px 12px;width:100%;font-size:12px;box-sizing:border-box}
.mt-card summary{list-style:none;cursor:pointer;display:flex;flex-direction:column;align-items:center;text-align:center;gap:2px}
.mt-card summary::-webkit-details-marker{display:none}
.mt-k{align-self:flex-start;color:var(--muted,#6b7280);font-size:15px;font-weight:700}
.mt-vs{margin-top:6px;padding-top:6px;border-top:1px dashed var(--line,#e3e8ef);color:var(--muted,#6b7280);font-size:11.5px;line-height:1.5}
.mt-gauge{width:100%;height:auto;margin:-2px 0 -26px;overflow:visible}
.mt-arc{fill:none;stroke:url(#mtGrad);stroke-width:20}
.mt-tick{stroke:#b9b2a4;stroke-width:1}.mt-tick-major{stroke:#8f897c;stroke-width:2}
.mt-num{font-size:10px;fill:#8f897c;font-variant-numeric:tabular-nums}.mt-zone{font-size:10.5px;fill:#a39b8b;font-weight:600}
.mt-needle{stroke:var(--text,#1d1d1b);stroke-width:3;stroke-linecap:round}.mt-needle-dot{fill:var(--text,#1d1d1b);stroke:var(--card,#fff);stroke-width:2}
.mt-score{font-size:34px;line-height:1;font-weight:800;color:var(--text,#18212f);font-variant-numeric:tabular-nums}
.mt-label{font-weight:700;font-size:14px}.mt-fromto{color:var(--muted,#6b7280);font-variant-numeric:tabular-nums}
.mt-why{color:var(--muted,#6b7280)}.mt-more{color:var(--muted,#6b7280);font-size:11px;margin-top:2px}
.mt-xfear .mt-label{color:#b42318}.mt-fear .mt-label{color:#c2410c}.mt-neutral .mt-label{color:#6b7280}.mt-greed .mt-label{color:#15803d}.mt-xgreed .mt-label{color:#166534}
.mt-body{color:var(--text,#18212f);margin-top:8px;text-align:left}.mt-body ul{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.mt-body li{display:grid;grid-template-columns:1fr auto;gap:0 8px}.mt-body li small{grid-column:1/-1;color:var(--muted,#6b7280)}.mt-body li.mt-off b{color:var(--muted,#6b7280)}
.mt-body p{margin:8px 0 4px;line-height:1.5;color:var(--muted,#6b7280)}.mt-na b{display:block;font-size:14px}
html[data-theme="dark"] .mt-card{background:#17191d;border-color:#303339}
html[data-theme="dark"] .mt-score,html[data-theme="dark"] .mt-body{color:#f1f3f5}
html[data-theme="dark"] .mt-needle{stroke:#f1f3f5}html[data-theme="dark"] .mt-needle-dot{fill:#f1f3f5;stroke:#17191d}`;

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

  global.MAVMarketTemperature = { html, load, _test: { gauge, changeText, trendWord, fromTo, drivers, vsVix } };
  if (typeof module !== 'undefined' && module.exports) module.exports = global.MAVMarketTemperature;
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
  }
})(typeof window !== 'undefined' ? window : globalThis);
