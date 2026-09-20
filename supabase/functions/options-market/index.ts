const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Cache-Control': 'private, max-age=30'
};

type CacheEntry = { at: number; body: string; status: number };
type AlpacaSnapshot = {
  latestQuote?: { ap?: number; bp?: number; t?: string };
  latestTrade?: { p?: number; t?: string };
  impliedVolatility?: number;
  greeks?: { delta?: number; gamma?: number; theta?: number; vega?: number };
  dailyBar?: { v?: number };
};

const memoryCache = new Map<string, CacheEntry>();
const FEED = 'indicative';
const PROVIDER = 'Alpaca';
const DATA_BASE = 'https://data.alpaca.markets';
const clean = (value: string | null, pattern: RegExp) => value && pattern.test(value) ? value : null;
const jsonHeaders = { ...corsHeaders, 'Content-Type': 'application/json; charset=utf-8' };
const jsonResponse = (value: unknown, status = 200, extra: Record<string, string> = {}) =>
  new Response(JSON.stringify(value), { status, headers: { ...jsonHeaders, ...extra } });
const finiteOrNull = (value: unknown) => value === null || value === undefined || value === ''
  ? null : Number.isFinite(Number(value)) ? Number(value) : null;

function isoDateInNewYork() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function addYears(date: string, years: number) {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() + years);
  return d.toISOString().slice(0, 10);
}

function occParts(optionSymbol: string) {
  const match = optionSymbol.match(/^([A-Z0-9.\-]{1,12})(\d{6})([CP])(\d{8})$/);
  if (!match) return null;
  return {
    root: match[1],
    expiration: `20${match[2].slice(0, 2)}-${match[2].slice(2, 4)}-${match[2].slice(4, 6)}`,
    side: match[3] === 'C' ? 'call' : 'put',
    strike: Number(match[4]) / 1000
  };
}

function epochSeconds(value?: string) {
  const ms = value ? Date.parse(value) : NaN;
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : null;
}

async function fetchAlpaca(url: string, headers: Record<string, string>) {
  const response = await fetch(url, { headers });
  const text = await response.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : {}; } catch { body = { message: text }; }
  if (!response.ok) {
    const error = new Error(body?.message || body?.error || `Alpaca HTTP ${response.status}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return body;
}

async function stockPrice(symbol: string, headers: Record<string, string>) {
  try {
    const url = `${DATA_BASE}/v2/stocks/${encodeURIComponent(symbol)}/snapshot?feed=iex`;
    const raw = await fetchAlpaca(url, headers);
    const values = [raw?.latestTrade?.p, raw?.minuteBar?.c, raw?.dailyBar?.c, raw?.prevDailyBar?.c]
      .map(finiteOrNull);
    return values.find((value) => value !== null) ?? null;
  } catch {
    return null;
  }
}

function normalizeSnapshots(snapshots: Record<string, AlpacaSnapshot>, underlyingPrice: number | null) {
  const rows = Object.entries(snapshots || {}).map(([optionSymbol, snapshot]) => {
    const parts = occParts(optionSymbol);
    if (!parts) return null;
    const bid = finiteOrNull(snapshot.latestQuote?.bp);
    const ask = finiteOrNull(snapshot.latestQuote?.ap);
    const last = finiteOrNull(snapshot.latestTrade?.p);
    const validBid = bid !== null && bid >= 0 ? bid : null;
    const validAsk = ask !== null && ask >= 0 ? ask : null;
    const mid = validBid !== null && validAsk !== null && (validBid > 0 || validAsk > 0)
      ? (validBid + validAsk) / 2 : null;
    const quoteTime = snapshot.latestQuote?.t || snapshot.latestTrade?.t;
    return {
      optionSymbol,
      strike: parts.strike,
      expiration: parts.expiration,
      side: parts.side,
      bid: validBid,
      ask: validAsk,
      mid,
      last,
      iv: finiteOrNull(snapshot.impliedVolatility),
      delta: finiteOrNull(snapshot.greeks?.delta),
      gamma: finiteOrNull(snapshot.greeks?.gamma),
      theta: finiteOrNull(snapshot.greeks?.theta),
      vega: finiteOrNull(snapshot.greeks?.vega),
      volume: finiteOrNull(snapshot.dailyBar?.v),
      openInterest: null,
      underlyingPrice: finiteOrNull(underlyingPrice),
      updated: epochSeconds(quoteTime)
    };
  }).filter(Boolean) as Record<string, unknown>[];

  const keys = ['optionSymbol', 'strike', 'expiration', 'side', 'bid', 'ask', 'mid', 'last', 'iv',
    'delta', 'gamma', 'theta', 'vega', 'volume', 'openInterest', 'underlyingPrice', 'updated'];
  const columnar: Record<string, unknown> = {
    s: 'ok', provider: PROVIDER, feed: FEED, delayed: true,
    disclaimer: 'Indicative参考行情；成交延迟且报价经过调整，下单前请以券商Bid/Ask为准',
    receivedAt: new Date().toISOString()
  };
  keys.forEach((key) => { columnar[key] = rows.map((row) => row[key] ?? null); });
  return columnar;
}

async function listExpirations(symbol: string, headers: Record<string, string>) {
  const today = isoDateInNewYork();
  const candidates = [Deno.env.get('ALPACA_TRADING_BASE_URL'), 'https://paper-api.alpaca.markets', 'https://api.alpaca.markets']
    .filter((value, index, all): value is string => Boolean(value) && all.indexOf(value) === index);
  let lastError: unknown = null;
  for (const base of candidates) {
    try {
      const url = new URL('/v2/options/contracts', base);
      url.searchParams.set('underlying_symbols', symbol);
      url.searchParams.set('status', 'active');
      url.searchParams.set('expiration_date_gte', today);
      url.searchParams.set('expiration_date_lte', addYears(today, 3));
      url.searchParams.set('limit', '10000');
      const raw = await fetchAlpaca(url.toString(), headers);
      const expirations = [...new Set((raw.option_contracts || []).map((item: any) => item.expiration_date).filter(Boolean))].sort();
      return { s: 'ok', provider: PROVIDER, feed: FEED, delayed: true, expirations, receivedAt: new Date().toISOString() };
    } catch (error) {
      lastError = error;
      const status = (error as Error & { status?: number }).status;
      if (status !== 401 && status !== 403) break;
    }
  }
  throw lastError || new Error('Alpaca没有返回到期日');
}

async function optionChain(symbol: string, expiration: string, side: string, headers: Record<string, string>) {
  let pageToken = '';
  const snapshots: Record<string, AlpacaSnapshot> = {};
  for (let page = 0; page < 5; page++) {
    const url = new URL(`${DATA_BASE}/v1beta1/options/snapshots/${encodeURIComponent(symbol)}`);
    url.searchParams.set('feed', FEED);
    url.searchParams.set('expiration_date', expiration);
    url.searchParams.set('type', side);
    url.searchParams.set('limit', '1000');
    if (pageToken) url.searchParams.set('page_token', pageToken);
    const raw = await fetchAlpaca(url.toString(), headers);
    Object.assign(snapshots, raw.snapshots || {});
    pageToken = raw.next_page_token || '';
    if (!pageToken) break;
  }
  const spot = await stockPrice(symbol, headers);
  return normalizeSnapshots(snapshots, spot);
}

async function optionQuote(optionSymbol: string, headers: Record<string, string>) {
  const parts = occParts(optionSymbol);
  if (!parts) throw Object.assign(new Error('期权代码格式无效'), { status: 400 });
  const url = new URL(`${DATA_BASE}/v1beta1/options/snapshots`);
  url.searchParams.set('symbols', optionSymbol);
  url.searchParams.set('feed', FEED);
  const [raw, spot] = await Promise.all([
    fetchAlpaca(url.toString(), headers),
    stockPrice(parts.root, headers)
  ]);
  return normalizeSnapshots(raw.snapshots || {}, spot);
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (req.method !== 'GET') return jsonResponse({ error: 'Method not allowed' }, 405);

  const key = Deno.env.get('ALPACA_API_KEY');
  const secret = Deno.env.get('ALPACA_API_SECRET');
  if (!key || !secret) return jsonResponse({ error: 'Supabase尚未配置 ALPACA_API_KEY / ALPACA_API_SECRET' }, 503);

  const requestUrl = new URL(req.url);
  const action = requestUrl.searchParams.get('action') || '';
  const symbol = clean(requestUrl.searchParams.get('symbol')?.toUpperCase() || null, /^[A-Z0-9.\-]{1,12}$/);
  const expiration = clean(requestUrl.searchParams.get('expiration'), /^\d{4}-\d{2}-\d{2}$/);
  const side = clean(requestUrl.searchParams.get('side'), /^(call|put)$/);
  const optionSymbol = clean(requestUrl.searchParams.get('optionSymbol')?.toUpperCase() || null, /^[A-Z0-9.\-]{1,12}\d{6}[CP]\d{8}$/);
  if (!((action === 'expirations' && symbol) || (action === 'chain' && symbol && expiration && side) || (action === 'quote' && optionSymbol))) {
    return jsonResponse({ error: '无效或缺失的查询参数' }, 400);
  }

  const cacheKey = requestUrl.search;
  const hit = memoryCache.get(cacheKey);
  const ttl = action === 'quote' ? 60_000 : action === 'chain' ? 600_000 : 3_600_000;
  if (hit && Date.now() - hit.at < ttl) {
    return new Response(hit.body, { status: hit.status, headers: { ...jsonHeaders, 'X-Cache': 'HIT' } });
  }

  const alpacaHeaders = {
    'APCA-API-KEY-ID': key,
    'APCA-API-SECRET-KEY': secret,
    'Accept': 'application/json'
  };
  try {
    let result: unknown;
    if (action === 'expirations') result = await listExpirations(symbol!, alpacaHeaders);
    else if (action === 'chain') result = await optionChain(symbol!, expiration!, side!, alpacaHeaders);
    else result = await optionQuote(optionSymbol!, alpacaHeaders);
    const body = JSON.stringify(result);
    memoryCache.set(cacheKey, { at: Date.now(), body, status: 200 });
    return new Response(body, { status: 200, headers: { ...jsonHeaders, 'X-Cache': 'MISS' } });
  } catch (error) {
    const status = (error as Error & { status?: number }).status || 502;
    const publicStatus = [400, 401, 403, 404, 429].includes(status) ? status : 502;
    const message = error instanceof Error ? error.message : String(error);
    return jsonResponse({ error: `Alpaca行情请求失败：${message}`, provider: PROVIDER }, publicStatus);
  }
});
