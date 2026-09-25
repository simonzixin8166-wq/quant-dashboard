const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Cache-Control': 'public, max-age=60',
  'Content-Type': 'application/json',
};

let cache = { at: 0, body: '', ttlMs: 60_000 };
let lastGood = { at: 0, body: '', ttlMs: 60_000 };
const exactSymbols = { spx: '^GSPC', ixic: '^IXIC', vix: '^VIX' };

async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = 10000) {
  return await fetch(url, { ...init, signal: AbortSignal.timeout(timeoutMs) });
}

function nyDate(epochSeconds: number) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(epochSeconds * 1000));
}

function newYorkPhase(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  if (['Sat', 'Sun'].includes(values.weekday)) return 'weekend';
  const minute = Number(values.hour) * 60 + Number(values.minute);
  return minute >= 570 && minute < 960 ? 'regular-window' : 'off-hours';
}

function responseTtl(marketState?: string | null, now = new Date()) {
  const phase = newYorkPhase(now);
  if (phase === 'weekend') return 6 * 60 * 60 * 1000;
  if (phase === 'regular-window' && marketState !== 'REGULAR') return 2 * 60 * 60 * 1000;
  return phase === 'regular-window' ? 60_000 : 30 * 60 * 1000;
}

function responseHeaders(ttlMs: number, extra: Record<string, string> = {}) {
  return { ...corsHeaders, 'Cache-Control': `public, max-age=${Math.max(1, Math.floor(ttlMs / 1000))}`, ...extra };
}

async function yahooPreviousRegularClose(symbol: string, quoteEpoch: number) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=10d&interval=1d&includePrePost=false`;
  const response = await fetchWithTimeout(url, { headers: { 'User-Agent': 'Mozilla/5.0', Accept: 'application/json' } });
  if (!response.ok) throw new Error(`Yahoo daily ${response.status}`);
  const payload = await response.json();
  const result = payload?.chart?.result?.[0];
  const timestamps = result?.timestamp || [];
  const closes = result?.indicators?.quote?.[0]?.close || [];
  const quoteDate = nyDate(quoteEpoch);
  const completed = timestamps.map((ts: number, index: number) => ({
    date: nyDate(Number(ts)), close: Number(closes[index]),
  })).filter((row) => row.date < quoteDate && Number.isFinite(row.close) && row.close > 0);
  const previous = completed.at(-1)?.close;
  if (!Number.isFinite(previous) || previous <= 0) throw new Error('Yahoo缺少上一交易日正式收盘价');
  return Number(previous);
}

async function yahooMinuteQuote(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=1m&includePrePost=true`;
  const response = await fetchWithTimeout(url, { headers: { 'User-Agent': 'Mozilla/5.0', Accept: 'application/json' } });
  if (!response.ok) throw new Error(`Yahoo ${response.status}`);
  const payload = await response.json();
  const result = payload?.chart?.result?.[0];
  const meta = result?.meta || {};
  const closes = result?.indicators?.quote?.[0]?.close || [];
  const price = Number(meta.regularMarketPrice ?? [...closes].reverse().find(Number.isFinite));
  const updated = Number(meta.regularMarketTime || Math.floor(Date.now() / 1000));
  // chartPreviousClose在range=5d时可能是整个区间开始前的收盘价，不能作为昨收。
  // 单独从日线中取“报价交易日之前”的最后一个正式收盘价。
  const previous = await yahooPreviousRegularClose(symbol, updated);
  if (!Number.isFinite(price) || price <= 0) throw new Error('Yahoo返回空价格');
  return {
    symbol,
    price,
    changepct: Number.isFinite(previous) && previous > 0 ? price / previous - 1 : null,
    previousRegularClose: previous,
    changeBasis: 'previous_regular_close',
    updated,
    source: 'Yahoo分钟行情',
    marketState: String(meta.marketState || ''),
    proxy: false,
  };
}

async function marketDataProxies() {
  const token = Deno.env.get('MARKETDATA_API_TOKEN');
  if (!token) return {};
  const response = await fetchWithTimeout('https://api.marketdata.app/v1/stocks/prices/?symbols=SPY,QQQ,VIXY', {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  });
  if (!response.ok) return {};
  const raw = await response.json();
  if (raw?.s !== 'ok') return {};
  const output = {};
  (raw.symbol || []).forEach((symbol, index) => {
    output[symbol] = {
      symbol,
      price: Number(raw.mid?.[index]),
      changepct: Number(raw.changepct?.[index]),
      updated: Number(raw.updated?.[index]),
      source: 'MarketData SmartMid实时代理',
      proxy: true,
    };
  });
  return output;
}

Deno.serve(async (request) => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (request.method !== 'GET') return new Response(JSON.stringify({ error: 'Method not allowed' }), { status: 405, headers: corsHeaders });
  if (cache.body && Date.now() - cache.at < cache.ttlMs) return new Response(cache.body, { headers: responseHeaders(cache.ttlMs, { 'X-Cache': 'HIT' }) });

  const entries = await Promise.all(Object.entries(exactSymbols).map(async ([key, symbol]) => {
    try { return [key, await yahooMinuteQuote(symbol)]; }
    catch (error) { return [key, { error: error instanceof Error ? error.message : String(error), symbol }]; }
  }));
  const exact = Object.fromEntries(entries);
  // Yahoo真实指数完整时不再请求备用行情，避免无意义消耗MarketData额度。
  const needsProxy = Object.values(exact).some((item: any) => Boolean(item?.error));
  const proxies = needsProxy ? await marketDataProxies().catch(() => ({})) : {};
  const ok = Object.values(exact).some((item) => !item.error) || Object.keys(proxies).length > 0;
  if (ok) {
    const marketState = String((exact.spx as any)?.marketState || (exact.ixic as any)?.marketState || '');
    const ttlMs = responseTtl(marketState);
    const body = JSON.stringify({ s: 'ok', exact, proxies, marketState, fetchedAt: Math.floor(Date.now() / 1000), stale: false });
    cache = { at: Date.now(), body, ttlMs };
    lastGood = cache;
    return new Response(body, { status: 200, headers: responseHeaders(ttlMs, { 'X-Cache': 'MISS' }) });
  }
  if (lastGood.body) {
    const fallback = { ...JSON.parse(lastGood.body), stale: true, fallbackReason: '上游行情暂不可用', lastSuccessAt: Math.floor(lastGood.at / 1000) };
    const body = JSON.stringify(fallback);
    const ttlMs = responseTtl(null);
    cache = { at: Date.now(), body, ttlMs };
    return new Response(body, { status: 200, headers: responseHeaders(ttlMs, { 'X-Cache': 'STALE' }) });
  }
  const body = JSON.stringify({ s: 'error', code: 'UPSTREAM_UNAVAILABLE', exact, proxies, retryable: true, failedAt: Math.floor(Date.now() / 1000) });
  cache = { at: Date.now(), body, ttlMs: 60_000 };
  return new Response(body, { status: 502, headers: { ...corsHeaders, 'X-Cache': 'MISS', 'Retry-After': '60' } });
});
