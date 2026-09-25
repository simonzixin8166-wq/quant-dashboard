(function () {
  'use strict';
  const endpoint = 'https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/market-snapshot';
  const names = { spx: '标普500', ixic: '纳斯达克综合', vix: 'VIX' };
  const proxyNames = { spx: 'SPY', ixic: 'QQQ', vix: 'VIXY' };
  const fmt = (n, key) => key === 'vix' ? Number(n).toFixed(2) : Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
  const pct = n => `${Number(n) >= 0 ? '+' : ''}${(Number(n) * 100).toFixed(2)}%`;
  let refreshTimer = null;
  let providerMarketState = null;

  function isUsRegularSession(now = new Date()) {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    const minute = Number(values.hour) * 60 + Number(values.minute);
    return !['Sat', 'Sun'].includes(values.weekday) && minute >= 570 && minute < 960;
  }

  function usSessionPhase(now = new Date()) {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    if (['Sat', 'Sun'].includes(values.weekday)) return 'weekend';
    const minute = Number(values.hour) * 60 + Number(values.minute);
    return minute >= 570 && minute < 960 ? 'regular-window' : 'off-hours';
  }
  function nextDelay(now = new Date()) {
    const phase = usSessionPhase(now);
    if (phase === 'weekend') return null;
    if (phase === 'regular-window' && providerMarketState && providerMarketState !== 'REGULAR') return 2 * 60 * 60 * 1000;
    return phase === 'regular-window' ? 5 * 60 * 1000 : 30 * 60 * 1000;
  }
  function cadenceLabel(now = new Date()) {
    const delay = nextDelay(now);
    if (delay === null) return '周末仅打开时检查一次';
    if (delay >= 2 * 60 * 60 * 1000) return '交易日休市2小时检查';
    return delay <= 5 * 60 * 1000 ? '盘中5分钟刷新' : '盘前盘后30分钟检查';
  }
  function schedule() {
    clearTimeout(refreshTimer);
    const delay = nextDelay();
    if (delay === null) return;
    refreshTimer = window.setTimeout(async () => { if (document.visibilityState === 'visible') await refresh(); schedule(); }, delay);
  }

  function updateVixGauge(value) {
    const v = Number(value);
    if (!Number.isFinite(v)) return;
    const zones = v < 15
      ? ['平静区', '#1f9d63']
      : v < 20 ? ['温和波动', '#91b63c']
      : v < 25 ? ['警戒区', '#e2a62b']
      : v < 30 ? ['高风险', '#db7131']
      : ['极端恐慌', '#bd3f35'];
    const angle = -90 + Math.min(Math.max(v, 0), 40) / 40 * 180;
    document.querySelectorAll('[data-vix-gauge]').forEach(el => el.style.setProperty('--vix-angle', `${angle}deg`));
    document.querySelectorAll('[data-vix-zone]').forEach(el => { el.textContent = zones[0]; el.style.color = zones[1]; });
    document.querySelectorAll('[data-vix-dot]').forEach(el => { el.style.background = zones[1]; });
  }

  function setStatus(id, text, good) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    const item = el.closest('.status-item');
    if (item) item.dataset.tone = good ? 'good' : 'warn';
  }

  function updateExact(key, quote) {
    if (!quote || quote.error || !Number.isFinite(Number(quote.price))) return false;
    document.querySelectorAll(`[data-us-live-price="${key}"]`).forEach(el => { el.textContent = fmt(quote.price, key); });
    if (key === 'vix') updateVixGauge(quote.price);
    // 只有接口明确确认“上一交易日正式收盘”为基准时才覆盖静态收盘涨跌幅。
    // 旧版Edge Function的chartPreviousClose可能指向5日区间起点，必须拒绝。
    if (quote.changeBasis === 'previous_regular_close' && Number.isFinite(Number(quote.changepct))) {
      document.querySelectorAll(`[data-us-live-chg="${key}"]`).forEach(el => {
        el.textContent = pct(quote.changepct);
        el.classList.remove('positive', 'negative');
        el.classList.add(Number(quote.changepct) >= 0 ? 'positive' : 'negative');
      });
    }
    const stamp = quote.updated ? new Date(Number(quote.updated) * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
    const basis = quote.changeBasis === 'previous_regular_close' ? '较昨收' : '涨跌幅沿用收盘日线';
    document.querySelectorAll(`[data-us-live-note="${key}"]`).forEach(el => { el.textContent = `${quote.source} · ${basis} · ${stamp}`; });
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
      if (document.visibilityState === 'hidden') return;
      const response = await fetch(`${endpoint}?t=${Date.now()}`, { cache: 'no-store', signal: AbortSignal.timeout(12000) });
      const body = await response.json();
      if (!response.ok || body.s !== 'ok') throw new Error(body.error || `HTTP ${response.status}`);
      providerMarketState = body.marketState || body.exact?.spx?.marketState || body.exact?.ixic?.marketState || null;
      const spxOk = updateExact('spx', body.exact?.spx);
      const ixicOk = updateExact('ixic', body.exact?.ixic);
      const vixOk = updateExact('vix', body.exact?.vix);
      if (!spxOk) showProxy('spx', body.proxies?.SPY);
      if (!ixicOk) showProxy('ixic', body.proxies?.QQQ);
      if (!vixOk) showProxy('vix', body.proxies?.VIXY);
      const cadence = cadenceLabel();
      const stalePrefix = body.stale ? '缓存行情 · ' : '';
      setStatus('usLiveIndexStatus', spxOk && ixicOk ? `${stalePrefix}指数分钟行情（${cadence}）` : '指数日线；盘中代理见上方', spxOk && ixicOk && !body.stale);
      setStatus('usLiveVixStatus', vixOk ? `${stalePrefix}VIX分钟行情（${cadence}）` : 'VIX日线；VIXY代理见上方', vixOk && !body.stale);
      const asOf = document.getElementById('usLiveAsOf');
      const providerTimes = [body.exact?.spx?.updated, body.exact?.ixic?.updated, body.exact?.vix?.updated].map(Number).filter(Number.isFinite);
      const providerStamp = providerTimes.length ? new Date(Math.max(...providerTimes) * 1000).toLocaleString() : '时间未知';
      const marketLabel = providerMarketState === 'REGULAR' ? '常规交易时段' : (usSessionPhase() === 'weekend' ? '周末休市' : '当前休市');
      if (asOf) asOf.textContent = `美股行情时点: ${providerStamp}${body.stale ? '（缓存）' : ''} | ${marketLabel} | 宽度: 上一完整收盘日`;
    } catch (_error) {
      setStatus('usLiveIndexStatus', '实时接口未部署/暂不可用，保留收盘日线', false);
      setStatus('usLiveVixStatus', '实时接口未部署/暂不可用，保留收盘日线', false);
    }
  }

  window.addEventListener('load', async () => {
    const initialVix = document.querySelector('[data-us-live-price="vix"]')?.textContent;
    updateVixGauge(initialVix);
    await refresh();
    schedule();
  });
  document.addEventListener('visibilitychange', async () => { if (document.visibilityState === 'visible') { await refresh(); schedule(); } else clearTimeout(refreshTimer); });
})();
