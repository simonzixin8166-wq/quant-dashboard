(function () {
  'use strict';
  const endpoint = 'https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/market-snapshot';
  const names = { spx: '标普500', ixic: '纳斯达克综合', vix: 'VIX' };
  const proxyNames = { spx: 'SPY', ixic: 'QQQ', vix: 'VIXY' };
  const fmt = (n, key) => key === 'vix' ? Number(n).toFixed(2) : Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
  const pct = n => `${Number(n) >= 0 ? '+' : ''}${(Number(n) * 100).toFixed(2)}%`;

  function setStatus(id, text, good) {
    const el = document.getElementById(id);
    if (el) el.textContent = `${good ? '🟢' : '🟡'} ${text}`;
  }

  function updateExact(key, quote) {
    if (!quote || quote.error || !Number.isFinite(Number(quote.price))) return false;
    document.querySelectorAll(`[data-us-live-price="${key}"]`).forEach(el => { el.textContent = fmt(quote.price, key); });
    if (Number.isFinite(Number(quote.changepct))) {
      document.querySelectorAll(`[data-us-live-chg="${key}"]`).forEach(el => {
        el.textContent = pct(quote.changepct);
        el.classList.remove('positive', 'negative');
        el.classList.add(Number(quote.changepct) >= 0 ? 'positive' : 'negative');
      });
    }
    const stamp = quote.updated ? new Date(Number(quote.updated) * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
    document.querySelectorAll(`[data-us-live-note="${key}"]`).forEach(el => { el.textContent = `${quote.source} · ${stamp}`; });
    return true;
  }

  function showProxy(key, quote) {
    if (!quote || !Number.isFinite(Number(quote.price))) return;
    const change = Number.isFinite(Number(quote.changepct)) ? ` (${pct(quote.changepct)})` : '';
    const text = `${names[key]}暂不可用；${proxyNames[key]}实时代理 ${fmt(quote.price, key)}${change}`;
    document.querySelectorAll(`[data-us-live-note="${key}"]`).forEach(el => { el.textContent = text; });
  }

  async function refresh() {
    try {
      const response = await fetch(`${endpoint}?t=${Date.now()}`, { cache: 'no-store' });
      const body = await response.json();
      if (!response.ok || body.s !== 'ok') throw new Error(body.error || `HTTP ${response.status}`);
      const spxOk = updateExact('spx', body.exact?.spx);
      const ixicOk = updateExact('ixic', body.exact?.ixic);
      const vixOk = updateExact('vix', body.exact?.vix);
      if (!spxOk) showProxy('spx', body.proxies?.SPY);
      if (!ixicOk) showProxy('ixic', body.proxies?.QQQ);
      if (!vixOk) showProxy('vix', body.proxies?.VIXY);
      setStatus('usLiveIndexStatus', spxOk && ixicOk ? '指数分钟行情（30秒刷新）' : '指数日线；盘中代理见上方', spxOk && ixicOk);
      setStatus('usLiveVixStatus', vixOk ? 'VIX分钟行情（30秒刷新）' : 'VIX日线；VIXY代理见上方', vixOk);
      const asOf = document.getElementById('usLiveAsOf');
      if (asOf) asOf.textContent = `美股盘中接口: ${new Date().toLocaleTimeString()} | 宽度指标: 上一完整收盘日`;
    } catch (_error) {
      setStatus('usLiveIndexStatus', '实时接口未部署/暂不可用，保留收盘日线', false);
      setStatus('usLiveVixStatus', '实时接口未部署/暂不可用，保留收盘日线', false);
    }
  }

  window.addEventListener('load', () => { refresh(); window.setInterval(refresh, 30000); });
})();
