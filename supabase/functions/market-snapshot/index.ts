const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Cache-Control': 'public, max-age=20',
  'Content-Type': 'application/json',
};

let cache = { at: 0, body: '' };
let lastGood = { at: 0, body: '' };
const exactSymbols = { spx: '^GSPC', ixic: '^IXIC', vix: '^VIX' };

async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = 10000) {
  return await fetch(url, { ...init, signal: AbortSignal.timeout(timeoutMs) });
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
  const previous = Number(meta.chartPreviousClose ?? meta.previousClose);
  if (!Number.isFinite(price) || price <= 0) throw new Error('Yahoo返回空价格');
  return {
    symbol,
    price,
    changepct: Number.isFinite(previous) && previous > 0 ? price / previous - 1 : null,
    updated: Number(meta.regularMarketTime || Math.floor(Date.now() / 1000)),
    source: 'Yahoo分钟行情',
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
  if (cache.body && Date.now() - cache.at < 20000) return new Response(cache.body, { headers: { ...corsHeaders, 'X-Cache': 'HIT' } });

  const entries = await Promise.all(Object.entries(exactSymbols).map(async ([key, symbol]) => {
    try { return [key, await yahooMinuteQuote(symbol)]; }
    catch (error) { return [key, { error: error instanceof Error ? error.message : String(error), symbol }]; }
  }));
  const exact = Object.fromEntries(entries);
  const proxies = await marketDataProxies().catch(() => ({}));
  const ok = Object.values(exact).some((item) => !item.error) || Object.keys(proxies).length > 0;
  if (ok) {
    const body = JSON.stringify({ s: 'ok', exact, proxies, fetchedAt: Math.floor(Date.now() / 1000), stale: false });
    cache = { at: Date.now(), body };
    lastGood = cache;
    return new Response(body, { status: 200, headers: { ...corsHeaders, 'X-Cache': 'MISS' } });
  }
  if (lastGood.body) {
    const fallback = { ...JSON.parse(lastGood.body), stale: true, fallbackReason: '上游行情暂不可用', lastSuccessAt: Math.floor(lastGood.at / 1000) };
    const body = JSON.stringify(fallback);
    cache = { at: Date.now(), body };
    return new Response(body, { status: 200, headers: { ...corsHeaders, 'X-Cache': 'STALE' } });
  }
  const body = JSON.stringify({ s: 'error', code: 'UPSTREAM_UNAVAILABLE', exact, proxies, retryable: true, failedAt: Math.floor(Date.now() / 1000) });
  cache = { at: Date.now(), body };
  return new Response(body, { status: 502, headers: { ...corsHeaders, 'X-Cache': 'MISS', 'Retry-After': '60' } });
});
