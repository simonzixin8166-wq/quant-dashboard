const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'private, max-age=60',
};

type Bar = { t?: string; o?: number; h?: number; l?: number; c?: number };
type CacheEntry = { at: number; body: string };
type Scope = 'quote' | 'daily' | 'all';
const cache = new Map<string, CacheEntry>();
const DATA_BASE = 'https://data.alpaca.markets';

const finite = (value: unknown) => Number.isFinite(Number(value)) ? Number(value) : null;
const json = (value: unknown, status = 200, extra: Record<string,string> = {}) =>
  new Response(JSON.stringify(value), { status, headers: { ...corsHeaders, ...extra } });

async function fetchAlpaca(url: string, headers: Record<string,string>) {
  const response = await fetch(url, { headers, signal: AbortSignal.timeout(12000) });
  const text = await response.text();
  let body: any = {};
  try { body = text ? JSON.parse(text) : {}; } catch { body = { message: text }; }
  if (!response.ok) throw new Error(body?.message || `Alpaca HTTP ${response.status}`);
  return body;
}

function rsi(closes: number[], period = 14) {
  if (closes.length < period + 1) return null;
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i++) {
    const delta = closes[i] - closes[i - 1];
    gain += Math.max(delta, 0); loss += Math.max(-delta, 0);
  }
  gain /= period; loss /= period;
  for (let i = period + 1; i < closes.length; i++) {
    const delta = closes[i] - closes[i - 1];
    gain = (gain * (period - 1) + Math.max(delta, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-delta, 0)) / period;
  }
  return loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
}

function nyDate(value: string | number | Date) {
  return new Intl.DateTimeFormat('en-CA', { timeZone:'America/New_York', year:'numeric', month:'2-digit', day:'2-digit' }).format(new Date(value));
}

function nySessionCompleted() {
  const parts = new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(part=>[part.type,part.value]));
  const minute = Number(values.hour) * 60 + Number(values.minute);
  return !['Sat','Sun'].includes(values.weekday) && minute >= 965;
}

async function quoteRows(symbols: string[], headers: Record<string,string>) {
  const endpoint = new URL(`${DATA_BASE}/v2/stocks/snapshots`);
  endpoint.searchParams.set('symbols', symbols.join(','));
  endpoint.searchParams.set('feed','iex');
  const snapshots = await fetchAlpaca(endpoint.toString(), headers);
  const rows: Record<string,unknown> = {};
  for (const symbol of symbols) {
    const snap = snapshots?.[symbol] || {};
    const price = finite(snap?.latestTrade?.p) ?? finite(snap?.minuteBar?.c) ?? finite(snap?.dailyBar?.c) ?? finite(snap?.prevDailyBar?.c);
    const previous = finite(snap?.prevDailyBar?.c);
    rows[symbol] = {
      symbol, price, previousClose:previous,
      changePct:price!==null&&previous!==null&&previous>0 ? price/previous-1 : null,
      open:finite(snap?.dailyBar?.o), high:finite(snap?.dailyBar?.h), low:finite(snap?.dailyBar?.l),
      updated:snap?.latestTrade?.t || snap?.minuteBar?.t || snap?.dailyBar?.t || null,
      quoteSource:'Alpaca IEX参考行情',
    };
  }
  return rows;
}

async function dailyRows(symbols: string[], headers: Record<string,string>) {
  const end = new Date();
  const currentNy = nyDate(end);
  const endpoint = new URL(`${DATA_BASE}/v2/stocks/bars`);
  endpoint.searchParams.set('symbols', symbols.join(','));
  endpoint.searchParams.set('timeframe','1Day');
  endpoint.searchParams.set('start', new Date(end.getTime() - 550 * 86400000).toISOString());
  endpoint.searchParams.set('adjustment','all');
  endpoint.searchParams.set('feed','iex');
  endpoint.searchParams.set('limit','10000');
  endpoint.searchParams.set('sort','asc');
  const payload = await fetchAlpaca(endpoint.toString(), headers);
  const rows: Record<string,unknown> = {};
  for (const symbol of symbols) {
    const allBars: Bar[] = (payload?.bars?.[symbol] || []).filter((bar:Bar)=>finite(bar.c)!==null);
    const includeCurrentDay = nySessionCompleted();
    const completed = allBars.filter((bar:Bar)=>!bar.t || nyDate(bar.t) < currentNy || (includeCurrentDay && nyDate(bar.t) === currentNy));
    const history = completed.length ? completed : allBars;
    const closes = history.map(bar=>Number(bar.c));
    const latest = history.at(-1) || {};
    const completedClose = finite(latest.c);
    const year = String(latest.t ? nyDate(latest.t) : currentNy).slice(0,4);
    const yearBars = history.filter(bar=>String(bar.t || '').startsWith(year));
    const highs = (yearBars.length ? yearBars : history.slice(-252)).map(bar=>Number(bar.h ?? bar.c)).filter(Number.isFinite);
    const ytdHigh = highs.length ? Math.max(...highs) : null;
    const sma200 = closes.length >= 200 ? closes.slice(-200).reduce((a,b)=>a+b,0)/200 : null;
    rows[symbol] = {
      symbol, dailyClose:completedClose, ytdHigh,
      ytdDrawdown:completedClose!==null&&ytdHigh!==null&&ytdHigh>0 ? completedClose/ytdHigh-1 : null,
      rsi:rsi(closes),
      dist200:completedClose!==null&&sma200 ? completedClose/sma200-1 : null,
      dailyAsOf:latest.t ? nyDate(latest.t) : null,
      historyDays:closes.length,
      dailySource:'Alpaca复权完整收盘日线',
    };
  }
  return rows;
}

Deno.serve(async (request) => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (request.method !== 'GET') return json({ error:'Method not allowed' }, 405);

  const key = Deno.env.get('ALPACA_API_KEY') || Deno.env.get('APCA_API_KEY_ID') || Deno.env.get('ALPACA_KEY_ID');
  const secret = Deno.env.get('ALPACA_API_SECRET') || Deno.env.get('APCA_API_SECRET_KEY') || Deno.env.get('ALPACA_SECRET_KEY') || Deno.env.get('ALPACA_SECRET');
  if (!key || !secret) return json({ error:'Supabase尚未配置Alpaca密钥' }, 503);

  const url = new URL(request.url);
  const symbols = [...new Set((url.searchParams.get('symbols') || '').toUpperCase().split(',').map(x=>x.trim()).filter(x=>/^[A-Z0-9.-]{1,12}$/.test(x)))].slice(0,25).sort();
  if (!symbols.length) return json({ error:'缺少有效symbols参数' }, 400);
  const requestedScope = url.searchParams.get('scope') || 'all';
  const scope: Scope = requestedScope === 'quote' || requestedScope === 'daily' ? requestedScope : 'all';
  const cacheKey = `${scope}:${symbols.join(',')}`;
  const hit = cache.get(cacheKey);
  const ttl = scope === 'quote' ? 60000 : 900000;
  if (hit && Date.now() - hit.at < ttl) return new Response(hit.body, { headers:{...corsHeaders,'X-Cache':'HIT'} });

  const headers = { 'APCA-API-KEY-ID':key, 'APCA-API-SECRET-KEY':secret, Accept:'application/json' };
  try {
    const [quotes, daily] = await Promise.all([
      scope === 'daily' ? Promise.resolve({}) : quoteRows(symbols, headers),
      scope === 'quote' ? Promise.resolve({}) : dailyRows(symbols, headers),
    ]);
    const rows: Record<string,unknown> = {};
    for (const symbol of symbols) rows[symbol] = { ...(quotes as any)[symbol], ...(daily as any)[symbol], symbol };
    const body = JSON.stringify({ s:'ok', scope, rows, receivedAt:new Date().toISOString(), delayed:true, disclaimer:'参考行情；下单前以券商报价为准' });
    cache.set(cacheKey,{at:Date.now(),body});
    return new Response(body,{headers:{...corsHeaders,'X-Cache':'MISS'}});
  } catch (error) {
    return json({ error:`股票行情请求失败：${error instanceof Error ? error.message : String(error)}`, retryable:true }, 502);
  }
});
